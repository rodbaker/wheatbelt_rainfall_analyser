import pandas as pd

from src.common.sa2_coverage import load_broadacre_sa2_areas, select_target_sa2s


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
