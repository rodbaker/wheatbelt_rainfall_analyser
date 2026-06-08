import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.rainfall.analytics import (
    area_weighted,
    decile_rank,
    decile_score,
    percentile_rank,
    weighted_mean,
)

# The canonical decile producer. decile_rank() must reproduce its bucketing
# exactly so report scripts and the v1.0 deciles contract never disagree.
_CANON_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_sa2_rainfall_deciles.py"
_spec = importlib.util.spec_from_file_location("build_sa2_rainfall_deciles", _CANON_PATH)
_canon = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_canon)


def test_percentile_rank_uses_strict_ties_and_ignores_nan():
    assert percentile_rank([10, 20, 20, 30, np.nan], 20) == 25.0


def test_percentile_rank_empty_baseline_is_nan():
    assert math.isnan(percentile_rank([np.nan], 20))


def test_decile_rank_matches_canonical_producer():
    # Regression guard: decile_rank must equal scripts/build_sa2_rainfall_deciles
    # ._compute_decile (the v1.0 canonical decile method) across the full rank
    # range and several baseline sizes, including the n=21 contract baseline.
    for n in (10, 11, 20, 21, 25):
        hist = list(range(n))
        for k in range(n + 1):
            target = k - 0.5  # exactly k baseline values strictly below
            expected = _canon._compute_decile(target, pd.Series(hist))
            assert decile_rank(hist, target) == expected, f"n={n} k_below={k}"


def test_decile_rank_clamps_strict_ties_and_ignores_missing():
    assert decile_rank(range(10), -1) == 1            # below entire baseline
    assert decile_rank(range(10), 100) == 10          # above entire baseline
    assert decile_rank([10, 20, 20, 30, np.nan], 20) == 5  # ties don't lift, NaN dropped
    assert decile_rank([np.nan], 5) is None           # empty valid baseline
    assert decile_rank([1, 2, 3], float("nan")) is None


def test_decile_score_below_baseline_returns_one():
    assert decile_score(range(21), -1) == 1.0


def test_decile_score_above_baseline_clamps_to_ten():
    assert decile_score(range(21), 100) == 10.0


def test_decile_score_ties_do_not_lift_rank_and_ignores_nan():
    # 20 has one strictly-lower value (10): rank 2 of 4 -> 5.0; NaN dropped.
    assert decile_score([10, 20, 20, 30], 20) == 5.0
    assert decile_score([10, 20, 20, 30, np.nan], 20) == 5.0


def test_decile_score_empty_or_nan_is_none():
    assert decile_score([np.nan], 5) is None
    assert decile_score([1, 2, 3], float("nan")) is None


def test_decile_score_agrees_with_canonical_rank_formula_n21():
    n = 21
    hist = list(range(n))
    for k in range(n + 1):
        target = k - 0.5  # exactly k baseline values strictly below
        expected = round(max(1.0, min(10.0, (k + 1) / n * 10.0)), 1)
        assert decile_score(hist, target) == expected, f"k_below={k}"
        # The integer decile (decile_rank) must be ceil of the unclamped score.
        assert decile_rank(hist, target) == max(1, min(10, math.ceil((k + 1) / n * 10.0)))


def test_weighted_mean_ignores_nan_and_non_positive_weights():
    assert weighted_mean([(10, 1), (20, 3), (999, 0), (np.nan, 10)]) == 17.5


def test_area_weighted_groups_by_requested_columns():
    rainfall = pd.DataFrame(
        [
            {"year": 2026, "month": 5, "state_name": "WA", "sa2_code": 1, "rainfall_mm": 10.0},
            {"year": 2026, "month": 5, "state_name": "WA", "sa2_code": 2, "rainfall_mm": 20.0},
            {"year": 2026, "month": 5, "state_name": "VIC", "sa2_code": 3, "rainfall_mm": 30.0},
        ]
    )
    weights = pd.DataFrame(
        [
            {"state_name": "WA", "sa2_code": 1, "weight": 1.0},
            {"state_name": "WA", "sa2_code": 2, "weight": 3.0},
            {"state_name": "VIC", "sa2_code": 3, "weight": 2.0},
        ]
    )

    result = area_weighted(
        rainfall,
        weights,
        "rainfall_mm",
        ["year", "month", "state_name"],
    )

    wa = result[result["state_name"] == "WA"].iloc[0]
    vic = result[result["state_name"] == "VIC"].iloc[0]
    assert wa["rainfall_mm"] == 17.5
    assert vic["rainfall_mm"] == 30.0
