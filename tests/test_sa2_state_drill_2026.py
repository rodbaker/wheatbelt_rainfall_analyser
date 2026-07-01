import importlib.util
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sa2_state_drill_2026.py"
spec = importlib.util.spec_from_file_location("sa2_state_drill_2026", SCRIPT_PATH)
sa2_state_drill = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(sa2_state_drill)


def test_jan_may_partial_scales_historical_may_baseline_to_mtd_day():
    """When May 2026 is absent from history, the partial-May MTD is added to the
    2026 cumulative and the historical May baseline is scaled by mtd_day/31, so a
    partial 2026 May is ranked against a proportionally-scaled baseline — never
    against full historical Mays.
    """
    universe = pd.DataFrame(
        [{"sa2_code": 1, "state_name": "Western Australia", "sa2_name": "Example"}]
    )
    rows = []
    for year in range(2005, 2026):
        for month in [1, 2, 3, 4]:
            rows.append({"year": year, "month": month, "sa2_code": 1, "rainfall_mm": 10.0})
        rows.append({"year": year, "month": 5, "sa2_code": 1, "rainfall_mm": 60.0})
    # 2026 has NO May in history — only Jan-Apr; May arrives via the MTD frame.
    for month in [1, 2, 3, 4]:
        rows.append({"year": 2026, "month": month, "sa2_code": 1, "rainfall_mm": 10.0})

    history = pd.DataFrame(rows)
    mtd = pd.DataFrame(
        [{"year": 2026, "month": 5, "sa2_code": 1, "rainfall_mm": 45.0}]
    )

    result = sa2_state_drill.compute_window_ranks(
        history, universe, [1, 2, 3, 4, 5], mtd, "Jan-May_d20_cum", mtd_day=20
    )

    row = result.iloc[0]
    # 2026 = Jan-Apr (40) + partial May MTD (45) = 85, added exactly once.
    assert row["rainfall_2026_mm"] == 85.0
    # Baseline May scaled by 20/31: 40 + 60*20/31 = 78.7 (NOT the full-May 100).
    assert row["hist_median_mm"] == 78.7
    # 85 > 78.7 for every baseline year → top rank (the old full-May bug gave 0).
    assert row["percentile_rank"] == 100.0


def test_incomplete_historical_years_are_excluded_not_zero_filled():
    """A historical baseline year missing its Jan-Apr component OR its May
    component must be dropped from the baseline entirely — never admitted as a
    partial total via a 0 mm fill of the missing component.
    """
    universe = pd.DataFrame(
        [{"sa2_code": 1, "state_name": "Western Australia", "sa2_name": "Example"}]
    )
    rows = []
    for year in range(2005, 2026):  # 21 candidate baseline years
        if year == 2010:
            # Missing May entirely — only Jan-Apr present.
            for month in [1, 2, 3, 4]:
                rows.append({"year": year, "month": month, "sa2_code": 1, "rainfall_mm": 10.0})
        elif year == 2011:
            # Missing all Jan-Apr — only May present.
            rows.append({"year": year, "month": 5, "sa2_code": 1, "rainfall_mm": 60.0})
        else:
            for month in [1, 2, 3, 4]:
                rows.append({"year": year, "month": month, "sa2_code": 1, "rainfall_mm": 10.0})
            rows.append({"year": year, "month": 5, "sa2_code": 1, "rainfall_mm": 60.0})
    # 2026 target: Jan-Apr in history, May via the MTD frame.
    for month in [1, 2, 3, 4]:
        rows.append({"year": 2026, "month": month, "sa2_code": 1, "rainfall_mm": 10.0})

    history = pd.DataFrame(rows)
    mtd = pd.DataFrame(
        [{"year": 2026, "month": 5, "sa2_code": 1, "rainfall_mm": 45.0}]
    )

    result = sa2_state_drill.compute_window_ranks(
        history, universe, [1, 2, 3, 4, 5], mtd, "Jan-May_d20_cum", mtd_day=20
    )

    row = result.iloc[0]
    # 21 candidate years minus the two incomplete ones (2010, 2011) = 19.
    # Under the old fill_value=0.0 path both would have leaked in as partials.
    assert row["n_hist_years"] == 19
    # Baseline is the 19 complete years only: 40 + 60*20/31 = 78.7.
    assert row["hist_median_mm"] == 78.7
    assert row["rainfall_2026_mm"] == 85.0


def test_jan_may_full_may_in_history_is_preserved_and_mtd_not_double_counted():
    """When May 2026 is already present in history as a full month, the
    full-vs-full comparison is preserved and the MTD frame is NOT added on top.
    """
    universe = pd.DataFrame(
        [{"sa2_code": 1, "state_name": "Western Australia", "sa2_name": "Example"}]
    )
    rows = []
    for year in range(2005, 2026):
        for month in [1, 2, 3, 4]:
            rows.append({"year": year, "month": month, "sa2_code": 1, "rainfall_mm": 10.0})
        rows.append({"year": year, "month": 5, "sa2_code": 1, "rainfall_mm": 60.0})
    for month in [1, 2, 3, 4]:
        rows.append({"year": 2026, "month": month, "sa2_code": 1, "rainfall_mm": 10.0})
    rows.append({"year": 2026, "month": 5, "sa2_code": 1, "rainfall_mm": 90.0})

    history = pd.DataFrame(rows)
    mtd = pd.DataFrame(
        [{"year": 2026, "month": 5, "sa2_code": 1, "rainfall_mm": 25.0}]
    )

    result = sa2_state_drill.compute_window_ranks(
        history, universe, [1, 2, 3, 4, 5], mtd, "Jan-May_d20_cum", mtd_day=20
    )

    row = result.iloc[0]
    # 2026 = Jan-Apr (40) + full May (90) = 130; MTD (25) must NOT be added.
    assert row["rainfall_2026_mm"] == 130.0
    # Full-month baseline preserved: 40 + 60 = 100.
    assert row["hist_median_mm"] == 100.0
    assert row["percentile_rank"] == 100.0
