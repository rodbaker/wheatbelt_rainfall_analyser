from pathlib import Path

import pandas as pd
import pytest

from src.common.config_loader import load_config
from src.agents.silo_wrangler.run_ingest import load_coverage_stations
from src.common.sa2_coverage import (
    COVERAGE_COLUMNS,
    build_coverage_report,
    build_sa2_polygon_index,
    derive_station_universe,
    load_broadacre_sa2_areas,
    resolve_gap_points,
    select_target_sa2s,
)

_ROOT = Path(__file__).resolve().parents[1]


def _write_crop_csv(tmp_path):
    # Two crop rows for a big SA2, one for a small SA2, and an all-null-area SA2.
    rows = [
        # sa2_code (9-dig), station_sa2_5dig16 (5-dig), sa2_name, state, crop, area_ha
        ("103011060", "11060", "Big Region", "New South Wales", "wheat", "4000"),
        ("103011060", "11060", "Big Region", "New South Wales", "barley", "1500"),
        ("201021007", "21007", "Null Region", "Victoria", "wheat", ""),       # all-null area
        ("201021007", "21007", "Null Region", "Victoria", "canola", ""),
        ("301011099", "11099", "Tiny Region", "Queensland", "oats", "300"),
    ]
    df = pd.DataFrame(rows, columns=[
        "sa2_code", "station_sa2_5dig16", "sa2_name", "state", "crop", "area_ha"])
    p = tmp_path / "crop_context_sa2.csv"
    df.to_csv(p, index=False)
    return p


def test_load_aggregates_area_nan_skipping(tmp_path):
    path = _write_crop_csv(tmp_path)
    areas = load_broadacre_sa2_areas(path)
    by = areas.set_index("sa2_5")["total_area_ha"].to_dict()
    assert by["11060"] == 5500.0           # 4000 + 1500
    assert by["21007"] == 0.0              # all-null -> 0.0, retained (not dropped)
    assert by["11099"] == 300.0
    assert set(areas["sa2_5"]) == {"11060", "21007", "11099"}


def test_select_threshold_zero_is_row_presence(tmp_path):
    areas = load_broadacre_sa2_areas(_write_crop_csv(tmp_path))
    assert select_target_sa2s(areas, threshold_ha=0) == {"11060", "21007", "11099"}


def test_select_threshold_excludes_null_area_and_fringe(tmp_path):
    areas = load_broadacre_sa2_areas(_write_crop_csv(tmp_path))
    # default 5000: only the big SA2 survives; null-area and tiny dropped
    assert select_target_sa2s(areas, threshold_ha=5000) == {"11060"}
    # any >=1 threshold drops the 0.0-area SA2
    assert "21007" not in select_target_sa2s(areas, threshold_ha=1)


def _stations_df():
    # Mirrors WheatbeltStationsLoader._stations_df after column rename:
    # station_id (zfilled str), name, sa2_code (the 5-dig SA2), latitude, longitude.
    return pd.DataFrame([
        {"station_id": "008137", "name": "ALPHA", "sa2_code": 11060, "latitude": -31.0, "longitude": 117.0},
        {"station_id": "009999", "name": "BETA",  "sa2_code": 11060, "latitude": -31.5, "longitude": 117.5},
        {"station_id": "055325", "name": "GAMMA", "sa2_code": 99999, "latitude": -31.2, "longitude": 150.0},
    ])


def test_derive_station_universe_filters_to_target_sa2s():
    uni = derive_station_universe({"11060"}, _stations_df())
    assert set(uni["station_id"]) == {"008137", "009999"}   # GAMMA's SA2 not in target
    assert "sa2_5" in uni.columns
    assert set(uni["sa2_5"]) == {"11060"}


def test_derive_station_universe_handles_float_sa2_codes():
    # pandas may load SA2_5DIG16 as float when NaNs present -> 11060.0
    df = _stations_df()
    df["sa2_code"] = df["sa2_code"].astype(float)
    uni = derive_station_universe({"11060"}, df)
    assert set(uni["station_id"]) == {"008137", "009999"}


def test_coverage_report_classifies_gap_status():
    areas = pd.DataFrame([
        {"sa2_5": "11060", "sa2_name": "Big",    "state": "NSW", "total_area_ha": 5500.0},
        {"sa2_5": "21007", "sa2_name": "GapDD",  "state": "VIC", "total_area_ha": 9000.0},
        {"sa2_5": "31000", "sa2_name": "GapNone","state": "QLD", "total_area_ha": 7000.0},
    ])
    universe = pd.DataFrame([
        {"station_id": "008137", "sa2_5": "11060"},
        {"station_id": "009999", "sa2_5": "11060"},
    ])
    target = {"11060", "21007", "31000"}
    dd_covered = {"21007", "11060"}    # 11060 also in dd_covered -> internal_bom must still win

    rep = build_coverage_report(target, areas, universe, dd_covered_sa2s=dd_covered)
    assert list(rep.columns) == COVERAGE_COLUMNS
    by = rep.set_index("sa2_code")
    assert by.loc["11060", "gap_status"] == "internal_bom"
    assert by.loc["11060", "n_stations"] == 2
    assert by.loc["11060", "station_ids"] == "008137;009999"
    assert by.loc["21007", "gap_status"] == "data_drill_gapfill"
    assert by.loc["31000", "gap_status"] == "unresolved_gap"
    assert by.loc["31000", "n_stations"] == 0


def _geo_crop(tmp_path):
    # crop table mapping 5-dig <-> 9-dig
    crop = pd.DataFrame([
        {"sa2_code": "201021007", "station_sa2_5dig16": "21007", "sa2_name": "GapDD",
         "state": "Victoria", "crop": "wheat", "area_ha": "9000"},
        {"sa2_code": "301031000", "station_sa2_5dig16": "31000", "sa2_name": "GapNone",
         "state": "Queensland", "crop": "oats", "area_ha": "7000"},
    ])
    crop_path = tmp_path / "crop.csv"
    crop.to_csv(crop_path, index=False)

    # GeoJSON: a unit square per SA2, keyed by 9-digit SA2_MAIN16.
    def square(cx, cy):
        return {"type": "Polygon", "coordinates": [[
            [cx, cy], [cx + 1, cy], [cx + 1, cy + 1], [cx, cy + 1], [cx, cy]]]}
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"SA2_MAIN16": 201021007},
         "geometry": square(117.0, -32.0)},
        {"type": "Feature", "properties": {"SA2_MAIN16": 301031000},
         "geometry": square(140.0, -34.0)},
    ]}
    import json
    geo_path = tmp_path / "regions.geojson"
    geo_path.write_text(json.dumps(gj))
    return crop_path, geo_path


def test_polygon_index_keyed_by_5dig(tmp_path):
    crop_path, geo_path = _geo_crop(tmp_path)
    crop = pd.read_csv(crop_path, dtype=str)
    idx = build_sa2_polygon_index(crop, geo_path)
    assert set(idx.keys()) == {"21007", "31000"}


def test_resolve_gap_points_injects_inside_polygon(tmp_path):
    crop_path, geo_path = _geo_crop(tmp_path)
    crop = pd.read_csv(crop_path, dtype=str)
    idx = build_sa2_polygon_index(crop, geo_path)

    points = resolve_gap_points({"21007", "31000"}, idx)
    assert set(points.keys()) == {"21007", "31000"}
    # representative point of the 117..118 / -32..-31 square is inside it
    lat, lon = points["21007"]
    assert 117.0 <= lon <= 118.0 and -32.0 <= lat <= -31.0
    # deterministic: same call -> same point
    assert resolve_gap_points({"21007"}, idx)["21007"] == points["21007"]


def test_resolve_gap_points_reuses_existing_grid_point(tmp_path):
    crop_path, geo_path = _geo_crop(tmp_path)
    crop = pd.read_csv(crop_path, dtype=str)
    idx = build_sa2_polygon_index(crop, geo_path)
    existing = [(-31.5, 117.5)]   # inside the 21007 square
    points = resolve_gap_points({"21007"}, idx, existing_points=existing)
    assert points["21007"] == (-31.5, 117.5)


def test_resolve_gap_points_skips_sa2_without_polygon(tmp_path):
    crop_path, geo_path = _geo_crop(tmp_path)
    crop = pd.read_csv(crop_path, dtype=str)
    idx = build_sa2_polygon_index(crop, geo_path)
    points = resolve_gap_points({"99999"}, idx)   # no polygon -> unresolved
    assert "99999" not in points


def test_derive_station_universe_dedupes_station_id():
    # Simulate the station_regions.csv merge fan-out: same station_id appears twice.
    df = pd.DataFrame([
        {"station_id": "008137", "name": "ALPHA", "sa2_code": 11060, "latitude": -31.0, "longitude": 117.0},
        {"station_id": "008137", "name": "ALPHA", "sa2_code": 11060, "latitude": -31.0, "longitude": 117.0},
        {"station_id": "009999", "name": "BETA",  "sa2_code": 11060, "latitude": -31.5, "longitude": 117.5},
    ])
    uni = derive_station_universe({"11060"}, df)
    assert len(uni) == 2
    assert sorted(uni["station_id"]) == ["008137", "009999"]


def test_coverage_report_counts_unique_stations_only():
    areas = pd.DataFrame([
        {"sa2_5": "11060", "sa2_name": "Big", "state": "NSW", "total_area_ha": 5500.0},
    ])
    universe = pd.DataFrame([
        {"station_id": "008137", "sa2_5": "11060"},
        {"station_id": "008137", "sa2_5": "11060"},   # duplicate
        {"station_id": "009999", "sa2_5": "11060"},
    ])
    rep = build_coverage_report({"11060"}, areas, universe)
    row = rep.set_index("sa2_code").loc["11060"]
    assert row["n_stations"] == 2
    assert row["station_ids"] == "008137;009999"


def test_resolve_gap_points_existing_point_outside_falls_back(tmp_path):
    crop_path, geo_path = _geo_crop(tmp_path)
    crop = pd.read_csv(crop_path, dtype=str)
    idx = build_sa2_polygon_index(crop, geo_path)
    # existing point is far outside the 21007 square (117..118 / -32..-31)
    outside = [(-10.0, 100.0)]
    points = resolve_gap_points({"21007"}, idx, existing_points=outside)
    lat, lon = points["21007"]
    assert 117.0 <= lon <= 118.0 and -32.0 <= lat <= -31.0   # representative_point, not the outside one
    assert (lat, lon) != (-10.0, 100.0)


def test_shipped_config_defaults_to_sa2_broadacre():
    cfg = load_config(str(_ROOT / "config" / "silo_sources.yaml"))
    cov = cfg["coverage"]
    assert cov["mode"] == "sa2_broadacre"
    assert cov["sa2_broadacre"]["min_broadacre_area_ha"] == 5000
    assert cov["sa2_broadacre"]["area_column"] == "area_ha"
    assert cov["sa2_broadacre"]["enable_data_drill_gaps"] is True
    assert cfg["api"]["concurrency"] >= 1


def test_default_config_derives_many_stations():
    # Guard against silent regression to the 16-station active tier.
    cfg = load_config(str(_ROOT / "config" / "silo_sources.yaml"))
    cov = cfg["coverage"]["sa2_broadacre"]
    areas = load_broadacre_sa2_areas(_ROOT / cov["crop_context_file"], cov["area_column"])
    target = select_target_sa2s(areas, cov["min_broadacre_area_ha"])
    assert len(target) > 150  # ~159 SA2s at 5000 ha; far more than the 16 active tier


def test_active_tier_mode_uses_config_tiers():
    cfg = load_config(str(_ROOT / "config" / "silo_sources.yaml"))
    stations = load_coverage_stations(cfg, coverage_mode="active_tier", tiers="active")
    # active tier is the small hand-picked set; currently 16 stations
    assert 5 <= len(stations) <= 40
    assert all(isinstance(k, str) for k in stations)


def test_sa2_broadacre_mode_returns_large_universe():
    cfg = load_config(str(_ROOT / "config" / "silo_sources.yaml"))
    stations = load_coverage_stations(cfg, coverage_mode="sa2_broadacre", tiers="active")
    assert len(stations) > 500       # ~1,293 stations at the 5000 ha default


def test_load_coverage_stations_missing_sa2_block_raises():
    cfg = {"coverage": {"mode": "sa2_broadacre"}, "bom_dataset": {"file_path": "x"}}
    with pytest.raises(ValueError):
        load_coverage_stations(cfg, coverage_mode="sa2_broadacre")


def test_load_coverage_stations_missing_bom_dataset_raises():
    cfg = {"coverage": {"mode": "sa2_broadacre", "sa2_broadacre": {
        "crop_context_file": "data/meta/crop_context_sa2.csv"}}}
    with pytest.raises(ValueError):
        load_coverage_stations(cfg, coverage_mode="sa2_broadacre")
