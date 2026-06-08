import pandas as pd

from src.common.sa2_coverage import COVERAGE_COLUMNS, build_coverage_report, derive_station_universe, load_broadacre_sa2_areas, select_target_sa2s


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
