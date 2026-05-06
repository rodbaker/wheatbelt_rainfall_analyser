"""Tests for build_sa2_rainfall_deciles."""

import numpy as np
import pandas as pd
import pytest

import scripts.build_sa2_rainfall_deciles as mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_history(sa2_code, months_years_rain):
    """Build a minimal history DataFrame.

    months_years_rain: list of (month, year, rainfall_mm)
    """
    rows = [
        {
            "year": y,
            "month": m,
            "sa2_code": str(sa2_code),
            "sa2_name": "Test SA2",
            "rainfall_mm": r,
            "extraction_method": "test",
            "source_file": "test.nc",
            "source_variable": "monthly_rain",
            "quality_flag": "ok",
        }
        for m, y, r in months_years_rain
    ]
    return pd.DataFrame(rows)


def _history_for_sa2_month(sa2, month, n_years=15, base_year=2005, base_rain=20.0):
    """n_years of synthetic history for a single SA2+month."""
    return [(month, base_year + i, base_rain + i) for i in range(n_years)]


# ---------------------------------------------------------------------------
# _compute_decile
# ---------------------------------------------------------------------------

class TestComputeDecile:
    def _hist(self, values):
        return pd.Series(values, dtype=float)

    def test_minimum_value_is_decile_1(self):
        hist = self._hist(range(1, 101))  # 1..100
        assert mod._compute_decile(0.5, hist) == 1

    def test_maximum_value_is_decile_10(self):
        hist = self._hist(range(1, 101))
        assert mod._compute_decile(200.0, hist) == 10

    def test_median_value_is_near_decile_5_or_6(self):
        # Median of 1..100 is ~50.5; rank of 50 in 1..100 is ~50th percentile → decile 5
        hist = self._hist(range(1, 101))
        decile = mod._compute_decile(50.0, hist)
        assert decile in (5, 6)

    def test_decile_clamped_to_1_10(self):
        hist = self._hist([10.0, 20.0, 30.0])
        assert 1 <= mod._compute_decile(5.0, hist) <= 10
        assert 1 <= mod._compute_decile(50.0, hist) <= 10

    def test_exact_boundary_decile_10(self):
        # 10 values: value higher than all → decile 10
        hist = self._hist([float(i) for i in range(1, 11)])
        assert mod._compute_decile(100.0, hist) == 10

    def test_exact_boundary_decile_1(self):
        hist = self._hist([float(i) for i in range(1, 11)])
        assert mod._compute_decile(0.0, hist) == 1


# ---------------------------------------------------------------------------
# _decile_label
# ---------------------------------------------------------------------------

class TestDecileLabel:
    def test_all_labels(self):
        expected = {
            1: "very low",
            2: "below normal",
            3: "below normal",
            4: "near normal",
            5: "near normal",
            6: "near normal",
            7: "near normal",
            8: "above normal",
            9: "above normal",
            10: "very high",
        }
        for d, label in expected.items():
            assert mod._decile_label(d) == label


# ---------------------------------------------------------------------------
# compute_deciles: current-year exclusion
# ---------------------------------------------------------------------------

class TestCurrentYearExclusion:
    def test_current_year_excluded_from_own_baseline(self):
        # 11 years of history for SA2+month, plus one "current" year with extreme value
        rows = _history_for_sa2_month("501021007", month=5, n_years=11, base_rain=20.0)
        # Add a current year with extreme rainfall (should not influence its own decile)
        rows.append((5, 2025, 1000.0))
        df = _make_history("501021007", rows)

        result = mod.compute_deciles(df)
        current = result[(result["year"] == 2025) & (result["month"] == 5)]
        assert len(current) == 1
        # historical_year_count should be 11, not 12
        assert current.iloc[0]["historical_year_count"] == 11
        # The extreme value should score decile 10
        assert current.iloc[0]["rainfall_decile"] == 10

    def test_low_value_excluded_from_own_baseline(self):
        rows = _history_for_sa2_month("501021007", month=7, n_years=11, base_rain=30.0)
        rows.append((7, 2024, 0.0))  # near-zero
        df = _make_history("501021007", rows)

        result = mod.compute_deciles(df)
        current = result[(result["year"] == 2024) & (result["month"] == 7)]
        assert current.iloc[0]["rainfall_decile"] == 1


# ---------------------------------------------------------------------------
# compute_deciles: insufficient history
# ---------------------------------------------------------------------------

class TestInsufficientHistory:
    def test_below_threshold_flags_insufficient(self):
        # Only 9 years of history (< 10)
        rows = _history_for_sa2_month("501021007", month=3, n_years=9)
        rows.append((3, 2025, 25.0))
        df = _make_history("501021007", rows)

        result = mod.compute_deciles(df)
        target = result[(result["year"] == 2025) & (result["month"] == 3)]
        assert target.iloc[0]["climatology_quality_flag"].startswith("insufficient_history")
        assert pd.isna(target.iloc[0]["rainfall_decile"])
        assert pd.isna(target.iloc[0]["historical_median_mm"])

    def test_exactly_10_is_sufficient(self):
        rows = _history_for_sa2_month("501021007", month=3, n_years=10)
        rows.append((3, 2025, 25.0))
        df = _make_history("501021007", rows)

        result = mod.compute_deciles(df)
        target = result[(result["year"] == 2025) & (result["month"] == 3)]
        assert target.iloc[0]["climatology_quality_flag"] == "ok"
        assert pd.notna(target.iloc[0]["rainfall_decile"])

    def test_flag_includes_actual_count(self):
        rows = _history_for_sa2_month("501021007", month=6, n_years=5)
        rows.append((6, 2025, 10.0))
        df = _make_history("501021007", rows)

        result = mod.compute_deciles(df)
        target = result[(result["year"] == 2025) & (result["month"] == 6)]
        assert "5" in target.iloc[0]["climatology_quality_flag"]


# ---------------------------------------------------------------------------
# compute_deciles: null rainfall
# ---------------------------------------------------------------------------

class TestNullRainfall:
    def test_null_rainfall_sets_null_decile_fields(self):
        rows = _history_for_sa2_month("501021007", month=8, n_years=12)
        rows.append((8, 2025, None))
        df = _make_history("501021007", rows)

        result = mod.compute_deciles(df)
        target = result[(result["year"] == 2025) & (result["month"] == 8)]
        row = target.iloc[0]
        assert row["climatology_quality_flag"] == "null_rainfall"
        assert pd.isna(row["rainfall_decile"])
        assert pd.isna(row["rainfall_decile_label"])
        assert pd.isna(row["anomaly_mm"])

    def test_null_row_excluded_from_others_baseline(self):
        # The null-rainfall row should be excluded from historical baselines via dropna()
        rows = _history_for_sa2_month("501021007", month=8, n_years=10)
        rows.append((8, 2020, None))   # null row in the middle
        rows.append((8, 2025, 25.0))
        df = _make_history("501021007", rows)

        result = mod.compute_deciles(df)
        target = result[(result["year"] == 2025) & (result["month"] == 8)]
        # dropna on historical removes the null row — count should be 10, not 11
        assert target.iloc[0]["historical_year_count"] == 10
        assert target.iloc[0]["climatology_quality_flag"] == "ok"


# ---------------------------------------------------------------------------
# compute_deciles: SA2 isolation
# ---------------------------------------------------------------------------

class TestSA2Isolation:
    def test_deciles_not_mixed_across_sa2s(self):
        # SA2 A: low rainfall regime (~10mm history), current = 50mm (very high for this SA2)
        rows_a = _history_for_sa2_month("SA2_A", month=1, n_years=12, base_rain=5.0)
        rows_a.append((1, 2025, 50.0))
        # SA2 B: high rainfall regime (~100mm history), current = 50mm (very low for this SA2)
        rows_b = _history_for_sa2_month("SA2_B", month=1, n_years=12, base_rain=100.0)
        rows_b.append((1, 2025, 50.0))

        df_a = _make_history("SA2_A", rows_a)
        df_b = _make_history("SA2_B", rows_b)
        df_b["sa2_name"] = "SA2 B"
        df = pd.concat([df_a, df_b], ignore_index=True)

        result = mod.compute_deciles(df)
        r_a = result[(result["sa2_code"] == "SA2_A") & (result["year"] == 2025) & (result["month"] == 1)]
        r_b = result[(result["sa2_code"] == "SA2_B") & (result["year"] == 2025) & (result["month"] == 1)]

        # 50mm is above-normal for SA2_A (history 5–16mm) and below-normal for SA2_B (history 100–111mm)
        assert r_a.iloc[0]["rainfall_decile"] == 10
        assert r_b.iloc[0]["rainfall_decile"] == 1


# ---------------------------------------------------------------------------
# compute_deciles: anomaly computation
# ---------------------------------------------------------------------------

class TestAnomalyComputation:
    def test_anomaly_mm_positive_when_above_median(self):
        rows = [(1, 2005 + i, 10.0) for i in range(11)]  # all 10mm
        rows.append((1, 2025, 20.0))
        df = _make_history("SA2_X", rows)

        result = mod.compute_deciles(df)
        target = result[(result["year"] == 2025) & (result["month"] == 1)]
        assert target.iloc[0]["anomaly_mm"] == pytest.approx(10.0, abs=0.1)

    def test_anomaly_pct_zero_median_yields_null(self):
        # All historical values are 0mm → median = 0 → anomaly_pct undefined
        rows = [(1, 2005 + i, 0.0) for i in range(11)]
        rows.append((1, 2025, 5.0))
        df = _make_history("SA2_X", rows)

        result = mod.compute_deciles(df)
        target = result[(result["year"] == 2025) & (result["month"] == 1)]
        assert pd.isna(target.iloc[0]["anomaly_pct"])


# ---------------------------------------------------------------------------
# SA2 code preserved as string
# ---------------------------------------------------------------------------

class TestSA2CodePreservation:
    def test_sa2_code_preserved_as_string(self):
        rows = _history_for_sa2_month("501021007", month=4, n_years=11)
        rows.append((4, 2025, 15.0))
        df = _make_history("501021007", rows)

        result = mod.compute_deciles(df)
        assert result["sa2_code"].dtype == object
        assert all(isinstance(v, str) for v in result["sa2_code"])


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class TestOutputSchema:
    def test_output_columns_complete(self):
        rows = _history_for_sa2_month("501021007", month=2, n_years=11)
        rows.append((2, 2025, 18.0))
        df = _make_history("501021007", rows)

        result = mod.compute_deciles(df)
        assert list(result.columns) == mod.OUTPUT_COLS
