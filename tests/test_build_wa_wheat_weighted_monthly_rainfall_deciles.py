"""Tests for build_wa_wheat_weighted_monthly_rainfall_deciles."""

import numpy as np
import pandas as pd
import pytest

import scripts.build_wa_wheat_weighted_monthly_rainfall_deciles as mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_history(sa2_rainfall_by_year_month):
    """Build a history DataFrame from {sa2_code: [(year, month, rainfall_mm), ...]}.

    All SA2s share the same sa2_name prefix for simplicity.
    """
    rows = []
    for sa2_code, entries in sa2_rainfall_by_year_month.items():
        for year, month, rain in entries:
            rows.append({
                "year": year,
                "month": month,
                "sa2_code": str(sa2_code),
                "sa2_name": f"SA2-{sa2_code}",
                "rainfall_mm": rain,
                "extraction_method": "test",
                "source_file": "test.nc",
                "source_variable": "monthly_rain",
                "quality_flag": "ok",
            })
    return pd.DataFrame(rows)


def _make_weights(sa2_areas, fallback_codes=None):
    """Build a weights DataFrame.

    sa2_areas: {sa2_code: area_ha} — use None for null area
    fallback_codes: set of sa2_codes that have area_is_fallback=True
    """
    if fallback_codes is None:
        fallback_codes = set()
    rows = []
    for code, area in sa2_areas.items():
        is_fallback = str(code) in {str(c) for c in fallback_codes}
        rows.append({
            "sa2_code": str(code),
            "sa2_name": f"SA2-{code}",
            "area_ha_for_weighting": area,
            "area_source_year": "2020-21" if not is_fallback else "2015-16",
            "area_is_fallback": is_fallback,
            "area_fallback_reason": (
                "Uses 2015-16 ABS fallback area (np)" if is_fallback else None
            ),
        })
    return pd.DataFrame(rows)


def _two_sa2_history(n_hist_years=12, base_year=2005, month=5,
                     rain_a=None, rain_b=None):
    """Two SA2s with n_hist_years of 20mm history, plus optional extra entries."""
    entries_a = [(base_year + i, month, 20.0) for i in range(n_hist_years)]
    entries_b = [(base_year + i, month, 20.0) for i in range(n_hist_years)]
    if rain_a is not None:
        entries_a.append(rain_a)
    if rain_b is not None:
        entries_b.append(rain_b)
    return _make_history({"A": entries_a, "B": entries_b})


def _two_sa2_weights(area_a=1000.0, area_b=1000.0):
    return _make_weights({"A": area_a, "B": area_b})


# ---------------------------------------------------------------------------
# _compute_decile
# ---------------------------------------------------------------------------

class TestComputeDecile:
    def _h(self, values):
        return pd.Series(values, dtype=float)

    def test_minimum_value_is_decile_1(self):
        assert mod._compute_decile(0.0, self._h(range(1, 101))) == 1

    def test_maximum_value_is_decile_10(self):
        assert mod._compute_decile(200.0, self._h(range(1, 101))) == 10

    def test_decile_clamped_between_1_and_10(self):
        hist = self._h([10.0, 20.0, 30.0])
        assert 1 <= mod._compute_decile(0.0, hist) <= 10
        assert 1 <= mod._compute_decile(100.0, hist) <= 10


# ---------------------------------------------------------------------------
# Core contract: weighted totals first, then deciles
# ---------------------------------------------------------------------------

class TestWeightedTotalsBeforeDeciles:
    """Prove the decile is derived from weighted yearly totals, not averaged SA2 deciles."""

    def test_weighted_total_is_area_weighted_mean(self):
        # SA2-A gets 100mm, SA2-B gets 0mm; area_A=3000, area_B=1000
        # Weighted total = (100*3000 + 0*1000) / 4000 = 75mm
        entries = {
            "A": [(2020, 5, 100.0)],
            "B": [(2020, 5, 0.0)],
        }
        # Add 12 years of history so decile can be computed
        for yr in range(2005, 2017):
            entries["A"].append((yr, 5, 40.0))
            entries["B"].append((yr, 5, 40.0))

        hist = _make_history(entries)
        weights = _make_weights({"A": 3000.0, "B": 1000.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2020) & (result["month"] == 5)].iloc[0]
        assert row["rainfall_mm_wt"] == pytest.approx(75.0, abs=0.1)

    def test_decile_reflects_weighted_total_not_averaged_sa2_deciles(self):
        # 12 years of history: SA2-A=20mm, SA2-B=20mm → weighted total = 20mm
        # Target year: SA2-A=200mm (extreme high), SA2-B=0mm (extreme low)
        # Equal weights → weighted total = 100mm, still above all history (20mm)
        # → decile should be 10 (aggregate is very high, even though SA2-B individually is decile 1)
        entries = {"A": [], "B": []}
        for yr in range(2005, 2017):
            entries["A"].append((yr, 6, 20.0))
            entries["B"].append((yr, 6, 20.0))
        entries["A"].append((2025, 6, 200.0))
        entries["B"].append((2025, 6, 0.0))

        hist = _make_history(entries)
        weights = _make_weights({"A": 1000.0, "B": 1000.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2025) & (result["month"] == 6)].iloc[0]

        # Weighted total = (200+0)/2 = 100mm > all history 20mm → decile 10
        assert row["rainfall_mm_wt"] == pytest.approx(100.0, abs=0.1)
        assert row["rainfall_decile"] == 10

    def test_historical_distribution_uses_weighted_totals_per_year(self):
        # Two SA2s, different weights. The historical distribution should be the
        # weighted total per year — not the unweighted mean.
        # SA2-A weight=3000, SA2-B weight=1000
        # History years 2005-2016: A=10mm, B=30mm → weighted=(10*3000+30*1000)/4000=15mm
        entries = {"A": [], "B": []}
        for yr in range(2005, 2017):
            entries["A"].append((yr, 3, 10.0))
            entries["B"].append((yr, 3, 30.0))
        # Target: A=40mm, B=0mm → weighted=(40*3000+0*1000)/4000=30mm
        entries["A"].append((2025, 3, 40.0))
        entries["B"].append((2025, 3, 0.0))

        hist = _make_history(entries)
        weights = _make_weights({"A": 3000.0, "B": 1000.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        target = result[(result["year"] == 2025) & (result["month"] == 3)].iloc[0]

        assert target["rainfall_mm_wt"] == pytest.approx(30.0, abs=0.1)
        # All historical weighted totals = 15mm; target 30mm > all → decile 10
        assert target["rainfall_decile"] == 10
        assert target["historical_median_mm_wt"] == pytest.approx(15.0, abs=0.1)


# ---------------------------------------------------------------------------
# Current-year exclusion from own baseline
# ---------------------------------------------------------------------------

class TestCurrentYearExclusion:
    def test_current_year_not_in_own_historical_distribution(self):
        # 11 history years at 20mm; target year at 1000mm (extreme)
        # If target were included in its own baseline, the count would be 12 and
        # the median would shift. historical_year_count must be 11.
        entries = {"A": [], "B": []}
        for yr in range(2005, 2016):
            entries["A"].append((yr, 4, 20.0))
            entries["B"].append((yr, 4, 20.0))
        entries["A"].append((2025, 4, 1000.0))
        entries["B"].append((2025, 4, 1000.0))

        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        row = result[(result["year"] == 2025) & (result["month"] == 4)].iloc[0]
        assert row["historical_year_count"] == 11
        assert row["rainfall_decile"] == 10

    def test_extreme_low_current_year_scores_decile_1(self):
        entries = {"A": [], "B": []}
        for yr in range(2005, 2016):
            entries["A"].append((yr, 8, 50.0))
            entries["B"].append((yr, 8, 50.0))
        entries["A"].append((2025, 8, 0.0))
        entries["B"].append((2025, 8, 0.0))

        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        row = result[(result["year"] == 2025) & (result["month"] == 8)].iloc[0]
        assert row["rainfall_decile"] == 1


# ---------------------------------------------------------------------------
# Insufficient history
# ---------------------------------------------------------------------------

class TestInsufficientHistory:
    def test_below_min_history_count_flags_insufficient(self):
        entries = {"A": [], "B": []}
        for yr in range(2005, 2014):  # 9 history years
            entries["A"].append((yr, 7, 20.0))
            entries["B"].append((yr, 7, 20.0))
        entries["A"].append((2025, 7, 25.0))
        entries["B"].append((2025, 7, 25.0))

        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        row = result[(result["year"] == 2025) & (result["month"] == 7)].iloc[0]
        assert row["climatology_quality_flag"].startswith("insufficient_history")
        assert pd.isna(row["rainfall_decile"])
        assert "9" in row["climatology_quality_flag"]

    def test_exactly_10_is_sufficient(self):
        entries = {"A": [], "B": []}
        for yr in range(2005, 2015):  # exactly 10 history years
            entries["A"].append((yr, 7, 20.0))
            entries["B"].append((yr, 7, 20.0))
        entries["A"].append((2025, 7, 25.0))
        entries["B"].append((2025, 7, 25.0))

        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        row = result[(result["year"] == 2025) & (result["month"] == 7)].iloc[0]
        assert row["climatology_quality_flag"] == "ok"
        assert pd.notna(row["rainfall_decile"])


# ---------------------------------------------------------------------------
# Missing rainfall disclosure
# ---------------------------------------------------------------------------

class TestMissingRainfallDisclosure:
    def test_sa2_with_null_rainfall_excluded_from_weighted_calc(self):
        # SA2-A has rainfall; SA2-B has null → only SA2-A contributes
        # Both have area; weighted total = SA2-A rainfall (since B excluded)
        entries = {
            "A": [(2020, 1, 60.0)] + [(2005 + i, 1, 20.0) for i in range(12)],
            "B": [(2020, 1, None)] + [(2005 + i, 1, 20.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 1000.0, "B": 1000.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2020) & (result["month"] == 1)].iloc[0]

        # Only SA2-A contributed: weighted total = 60mm (B was null)
        assert row["rainfall_mm_wt"] == pytest.approx(60.0, abs=0.1)
        assert row["n_sa2s_weighted"] == 1
        assert row["n_sa2s_missing_rainfall"] == 1

    def test_n_sa2s_missing_rainfall_zero_when_all_present(self):
        entries = {"A": [(2020, 2, 30.0)], "B": [(2020, 2, 30.0)]}
        for yr in range(2005, 2017):
            entries["A"].append((yr, 2, 30.0))
            entries["B"].append((yr, 2, 30.0))
        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        row = result[(result["year"] == 2020) & (result["month"] == 2)].iloc[0]
        assert row["n_sa2s_missing_rainfall"] == 0

    def test_all_sa2s_null_rainfall_yields_null_weighted_total(self):
        entries = {
            "A": [(2020, 9, None)] + [(2005 + i, 9, 20.0) for i in range(12)],
            "B": [(2020, 9, None)] + [(2005 + i, 9, 20.0) for i in range(12)],
        }
        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        row = result[(result["year"] == 2020) & (result["month"] == 9)].iloc[0]
        assert row["climatology_quality_flag"] == "null_weighted_rainfall"
        assert pd.isna(row["rainfall_mm_wt"])
        assert pd.isna(row["rainfall_decile"])


# ---------------------------------------------------------------------------
# Null-area SA2 exclusion
# ---------------------------------------------------------------------------

class TestNullAreaExclusion:
    def test_sa2_with_null_area_excluded_from_all_months(self):
        # SA2-C has null area; it must not influence any weighted total
        entries = {
            "A": [(2020, 3, 10.0)] + [(2005 + i, 3, 10.0) for i in range(12)],
            "C": [(2020, 3, 999.0)] + [(2005 + i, 3, 999.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 1000.0, "C": None})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2020) & (result["month"] == 3)].iloc[0]

        # SA2-C (999mm) should be excluded; weighted total = 10mm (SA2-A only)
        assert row["rainfall_mm_wt"] == pytest.approx(10.0, abs=0.1)
        assert row["n_sa2s_weighted"] == 1

    def test_null_area_sa2_not_counted_as_missing_rainfall(self):
        # SA2-C is excluded due to null area, not null rainfall; n_sa2s_missing should be 0
        entries = {
            "A": [(2020, 3, 10.0)] + [(2005 + i, 3, 10.0) for i in range(12)],
            "C": [(2020, 3, 30.0)] + [(2005 + i, 3, 30.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 1000.0, "C": None})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2020) & (result["month"] == 3)].iloc[0]
        assert row["n_sa2s_missing_rainfall"] == 0


# ---------------------------------------------------------------------------
# Fallback area disclosure
# ---------------------------------------------------------------------------

class TestFallbackAreaDisclosure:
    def test_fallback_sa2_count_correct(self):
        entries = {
            "A": [(2020, 5, 20.0)] + [(2005 + i, 5, 20.0) for i in range(12)],
            "B": [(2020, 5, 20.0)] + [(2005 + i, 5, 20.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 1000.0, "B": 1000.0}, fallback_codes={"B"})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        # Every row should report fallback_area_sa2s = 1
        assert (result["fallback_area_sa2s"] == 1).all()

    def test_fallback_caveat_populated_when_fallback_sa2s_present(self):
        entries = {
            "A": [(2020, 5, 20.0)] + [(2005 + i, 5, 20.0) for i in range(12)],
            "B": [(2020, 5, 20.0)] + [(2005 + i, 5, 20.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 1000.0, "B": 1000.0}, fallback_codes={"B"})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        caveats = result["area_fallback_caveat"]
        assert (caveats.str.len() > 0).all()
        assert caveats.iloc[0].startswith("Monthly gridded rainfall weighting uses 2015-16 ABS fallback area for")

    def test_no_caveat_when_no_fallback_sa2s(self):
        entries = {
            "A": [(2020, 5, 20.0)] + [(2005 + i, 5, 20.0) for i in range(12)],
            "B": [(2020, 5, 20.0)] + [(2005 + i, 5, 20.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 1000.0, "B": 1000.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        assert (result["fallback_area_sa2s"] == 0).all()
        assert (result["area_fallback_caveat"] == "").all()


# ---------------------------------------------------------------------------
# Anomaly computation
# ---------------------------------------------------------------------------

class TestAnomalyComputation:
    def test_anomaly_mm_positive_when_above_median(self):
        # 12 history years at 10mm → median 10mm; target = 20mm → anomaly = 10mm
        entries = {"A": [], "B": []}
        for yr in range(2005, 2017):
            entries["A"].append((yr, 1, 10.0))
            entries["B"].append((yr, 1, 10.0))
        entries["A"].append((2025, 1, 20.0))
        entries["B"].append((2025, 1, 20.0))

        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        row = result[(result["year"] == 2025) & (result["month"] == 1)].iloc[0]
        assert row["anomaly_mm_wt"] == pytest.approx(10.0, abs=0.1)

    def test_anomaly_pct_null_when_median_is_zero(self):
        entries = {"A": [], "B": []}
        for yr in range(2005, 2017):
            entries["A"].append((yr, 2, 0.0))
            entries["B"].append((yr, 2, 0.0))
        entries["A"].append((2025, 2, 5.0))
        entries["B"].append((2025, 2, 5.0))

        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        row = result[(result["year"] == 2025) & (result["month"] == 2)].iloc[0]
        assert pd.isna(row["anomaly_pct_wt"])


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class TestOutputSchema:
    def test_output_columns_complete(self):
        entries = {"A": [], "B": []}
        for yr in range(2005, 2017):
            entries["A"].append((yr, 6, 20.0))
            entries["B"].append((yr, 6, 20.0))
        entries["A"].append((2025, 6, 25.0))
        entries["B"].append((2025, 6, 25.0))

        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        assert list(result.columns) == mod.OUTPUT_COLS

    def test_one_row_per_year_month(self):
        entries = {"A": [], "B": []}
        for yr in range(2005, 2010):
            for mo in range(1, 4):
                entries["A"].append((yr, mo, 20.0))
                entries["B"].append((yr, mo, 20.0))

        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        # 5 years × 3 months = 15 rows
        assert len(result) == 15
        assert result.groupby(["year", "month"]).size().max() == 1

    def test_partial_month_preserved(self):
        # Future/current partial month rows should not be dropped
        entries = {"A": [(2025, 11, 5.0)], "B": [(2025, 11, 5.0)]}
        for yr in range(2005, 2016):
            entries["A"].append((yr, 11, 20.0))
            entries["B"].append((yr, 11, 20.0))

        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        assert ((result["year"] == 2025) & (result["month"] == 11)).any()

    def test_weighting_area_ha_is_sum_of_eligible_weights(self):
        # area_A=3000, area_B=1000; all have rainfall → weighting_area_ha = 4000
        entries = {
            "A": [(2020, 7, 20.0)] + [(2005 + i, 7, 20.0) for i in range(12)],
            "B": [(2020, 7, 20.0)] + [(2005 + i, 7, 20.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 3000.0, "B": 1000.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2020) & (result["month"] == 7)].iloc[0]
        assert row["weighting_area_ha"] == pytest.approx(4000.0, abs=1.0)


# ---------------------------------------------------------------------------
# n_sa2s_universe and weighting_area_share
# ---------------------------------------------------------------------------

class TestCoverageFields:
    def test_n_sa2s_universe_equals_eligible_weight_count(self):
        # Eligible: A(1000ha), B(1000ha); C has null area → excluded
        entries = {
            "A": [(2020, 5, 20.0)] + [(2005 + i, 5, 20.0) for i in range(12)],
            "B": [(2020, 5, 20.0)] + [(2005 + i, 5, 20.0) for i in range(12)],
            "C": [(2020, 5, 20.0)] + [(2005 + i, 5, 20.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 1000.0, "B": 1000.0, "C": None})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        assert (result["n_sa2s_universe"] == 2).all()

    def test_weighting_area_share_is_1_when_all_sa2s_contribute(self):
        entries = {
            "A": [(2020, 5, 20.0)] + [(2005 + i, 5, 20.0) for i in range(12)],
            "B": [(2020, 5, 20.0)] + [(2005 + i, 5, 20.0) for i in range(12)],
        }
        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        row = result[(result["year"] == 2020) & (result["month"] == 5)].iloc[0]
        assert row["weighting_area_share"] == pytest.approx(1.0, abs=0.001)

    def test_weighting_area_share_reflects_missing_sa2_area(self):
        # SA2-A=8500ha, SA2-B=1500ha. Target has B null → share = 8500/10000 = 0.85
        entries = {
            "A": [(2020, 4, 20.0)] + [(2005 + i, 4, 20.0) for i in range(12)],
            "B": [(2020, 4, None)] + [(2005 + i, 4, 20.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 8500.0, "B": 1500.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2020) & (result["month"] == 4)].iloc[0]
        assert row["weighting_area_share"] == pytest.approx(0.85, abs=0.001)

    def test_weighting_area_share_constant_across_all_months_when_full_coverage(self):
        entries = {"A": [], "B": []}
        for yr in range(2005, 2017):
            for mo in [1, 6, 12]:
                entries["A"].append((yr, mo, 10.0))
                entries["B"].append((yr, mo, 10.0))
        result = mod.compute_weighted_monthly_deciles(
            _make_history(entries), _two_sa2_weights()
        )
        shares = result["weighting_area_share"].dropna()
        assert (shares - 1.0).abs().max() < 0.001


# ---------------------------------------------------------------------------
# Low coverage suppression
# ---------------------------------------------------------------------------

class TestLowCoverageSuppression:
    def test_decile_suppressed_when_coverage_below_threshold(self):
        # SA2-A=500ha, SA2-B=9500ha. Target has A only → share = 500/10000 = 0.05
        entries = {
            "A": [(2020, 6, 30.0)] + [(2005 + i, 6, 20.0) for i in range(12)],
            "B": [(2020, 6, None)] + [(2005 + i, 6, 20.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 500.0, "B": 9500.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2020) & (result["month"] == 6)].iloc[0]
        assert row["climatology_quality_flag"].startswith("low_coverage")
        assert pd.isna(row["rainfall_decile"])
        assert pd.notna(row["rainfall_mm_wt"])  # rainfall still reported

    def test_decile_suppressed_flag_includes_share_value(self):
        entries = {
            "A": [(2020, 6, 30.0)] + [(2005 + i, 6, 20.0) for i in range(12)],
            "B": [(2020, 6, None)] + [(2005 + i, 6, 20.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 500.0, "B": 9500.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2020) & (result["month"] == 6)].iloc[0]
        assert "0.05" in row["climatology_quality_flag"]

    def test_decile_not_suppressed_when_coverage_at_threshold(self):
        # SA2-A=8000ha, SA2-B=2000ha. Target has A only → share = 0.80 ≥ threshold
        entries = {
            "A": [(2020, 7, 25.0)] + [(2005 + i, 7, 20.0) for i in range(12)],
            "B": [(2020, 7, None)] + [(2005 + i, 7, 20.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 8000.0, "B": 2000.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2020) & (result["month"] == 7)].iloc[0]
        assert row["climatology_quality_flag"] == "ok"
        assert pd.notna(row["rainfall_decile"])

    def test_partial_month_suppressed_before_low_coverage_check(self):
        # Even if coverage is fine, partial month suppresses decile first
        entries = {
            "A": [(2020, 8, 20.0)] + [(2005 + i, 8, 20.0) for i in range(12)],
            "B": [(2020, 8, 20.0)] + [(2005 + i, 8, 20.0) for i in range(12)],
        }
        hist = _make_history(entries)
        hist.loc[
            (hist["year"] == 2020) & (hist["month"] == 8), "is_partial_month"
        ] = True
        result = mod.compute_weighted_monthly_deciles(hist, _two_sa2_weights())
        row = result[(result["year"] == 2020) & (result["month"] == 8)].iloc[0]
        assert row["climatology_quality_flag"] == "partial_month"


# ---------------------------------------------------------------------------
# Same SA2 mask for historical distribution
# ---------------------------------------------------------------------------

class TestSameSA2MaskForHistoricalDistribution:
    """Prove that historical weighted totals are recomputed with the target month's SA2 mask.

    Without the fix, the historical distribution is computed using whatever SA2s
    had data in each historical year (typically all of them), while the target
    month might have a different SA2 set. This can produce misleading deciles.
    """

    def test_historical_distribution_restricted_to_target_month_sa2s(self):
        # Universe: SA2-A (8500ha), SA2-B (1500ha)
        # History: A=10mm, B=50mm per year → full-mask weighted = (10*8500+50*1500)/10000=16mm
        # Target (2026, month=4): SA2-A=13mm, SA2-B=null → coverage=85% (above threshold)
        # With fix: historical uses only SA2-A → [10mm × 12 years]; 13mm > 10mm → decile 8+
        # Without fix: historical = [16mm × 12 years]; 13mm < 16mm → decile 1–3
        entries = {
            "A": [(2026, 4, 13.0)] + [(2005 + i, 4, 10.0) for i in range(12)],
            "B": [(2026, 4, None)] + [(2005 + i, 4, 50.0) for i in range(12)],
        }
        hist = _make_history(entries)
        weights = _make_weights({"A": 8500.0, "B": 1500.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2026) & (result["month"] == 4)].iloc[0]

        assert row["climatology_quality_flag"] == "ok"
        # SA2-A only: historical median should be ~10mm, not 16mm
        assert row["historical_median_mm_wt"] == pytest.approx(10.0, abs=0.5)
        # 13mm > 10mm historical → above median → decile 7 or higher
        assert row["rainfall_decile"] >= 7

    def test_historical_count_reflects_years_with_any_target_mask_sa2(self):
        # Historical years that lack ALL target-mask SA2s are excluded from the count.
        # Here SA2-A is the only target SA2; 11 history years have A; 1 does not.
        entries = {"A": [], "B": []}
        for yr in range(2005, 2016):   # 11 years have A
            entries["A"].append((yr, 9, 20.0))
        # year 2016 has no SA2-A data in month 9 (omit it)
        for yr in range(2005, 2017):   # 12 years have B
            entries["B"].append((yr, 9, 20.0))
        entries["A"].append((2026, 9, 25.0))
        entries["B"].append((2026, 9, None))   # B missing in target → mask is A only

        hist = _make_history(entries)
        weights = _make_weights({"A": 8000.0, "B": 2000.0})

        result = mod.compute_weighted_monthly_deciles(hist, weights)
        row = result[(result["year"] == 2026) & (result["month"] == 9)].iloc[0]
        # Only 11 historical years have SA2-A data for month 9
        assert row["historical_year_count"] == 11
