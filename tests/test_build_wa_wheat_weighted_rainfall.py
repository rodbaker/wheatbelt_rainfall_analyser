"""Tests for scripts/build_wa_wheat_weighted_rainfall.py"""

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_wa_wheat_weighted_rainfall import build_summary_row, weighted_mean, WEIGHTED_METRICS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(**kwargs) -> dict:
    """Return a wheat row with sensible defaults, overridden by kwargs."""
    defaults = {
        "state": "Western Australia",
        "crop": "wheat",
        "sa2_name": "TestRegion",
        "abs_sa2_code": "509021240",
        "area_ha": 100_000.0,
        "rainfall_feature_quality_flag": "complete",
        "season_year": 2025,
        "sowing_window_rain_mm": 90.0,
        "in_crop_rain_mm": 250.0,
        "rainfall_total_apr_oct_mm": 300.0,
        "rainfall_total_may_oct_mm": 260.0,
        "flowering_rain_mm": 40.0,
        "grain_fill_rain_mm": 35.0,
        "harvest_rain_mm": 25.0,
        "dry_spell_days_7d_lt_5mm": 100.0,
        "dry_spell_days_14d_lt_10mm": 80.0,
    }
    return {**defaults, **kwargs}


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# weighted_mean
# ---------------------------------------------------------------------------

class TestWeightedMean:
    def test_equal_weights(self):
        v = pd.Series([100.0, 200.0])
        w = pd.Series([1.0, 1.0])
        assert weighted_mean(v, w) == pytest.approx(150.0)

    def test_unequal_weights(self):
        v = pd.Series([100.0, 200.0])
        w = pd.Series([3.0, 1.0])
        assert weighted_mean(v, w) == pytest.approx(125.0)

    def test_single_value(self):
        v = pd.Series([77.5])
        w = pd.Series([500_000.0])
        assert weighted_mean(v, w) == pytest.approx(77.5)

    def test_returns_none_when_all_weights_zero(self):
        v = pd.Series([100.0, 200.0])
        w = pd.Series([0.0, 0.0])
        assert weighted_mean(v, w) is None

    def test_ignores_null_values(self):
        v = pd.Series([100.0, None, 200.0])
        w = pd.Series([1.0, 1.0, 1.0])
        assert weighted_mean(v, w) == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# build_summary_row — counts
# ---------------------------------------------------------------------------

class TestSummaryRowCounts:
    def test_28_qgis_universe_sa2s(self):
        rows = (
            [_row(sa2_name=f"R{i}", abs_sa2_code=f"50900{i:05d}", season_year=2025.0) for i in range(8)]
            + [_row(sa2_name=f"I{i}", rainfall_feature_quality_flag="insufficient_season",
                    season_year=2025.0) for i in range(4)]
            + [_row(sa2_name=f"N{i}", rainfall_feature_quality_flag="no_data",
                    season_year=2025.0, area_ha=None) for i in range(16)]
        )
        result = build_summary_row(_df(rows))
        assert result["n_sa2s_qgis_universe"] == 28

    def test_counts_by_flag(self):
        rows = (
            [_row(sa2_name="A", season_year=2025.0)]       # complete
            + [_row(sa2_name="B", rainfall_feature_quality_flag="insufficient_season", season_year=2025.0)]
            + [_row(sa2_name="C", rainfall_feature_quality_flag="no_data",
                    season_year=2025.0, area_ha=None)]
        )
        result = build_summary_row(_df(rows))
        assert result["n_sa2s_complete"] == 1
        assert result["n_sa2s_insufficient_season"] == 1
        assert result["n_sa2s_no_data"] == 1

    def test_complete_with_null_area_counted_separately(self):
        rows = [
            _row(sa2_name="WithArea",    area_ha=100_000.0),
            _row(sa2_name="NullArea",    area_ha=None),
        ]
        result = build_summary_row(_df(rows))
        assert result["n_sa2s_eligible"] == 1
        assert result["n_sa2s_complete_no_area"] == 1
        assert result["n_sa2s_complete"] == 2


# ---------------------------------------------------------------------------
# build_summary_row — area and coverage
# ---------------------------------------------------------------------------

class TestSummaryRowArea:
    def test_total_wheat_area_sums_eligible_only(self):
        rows = [
            _row(sa2_name="A", area_ha=100_000.0),
            _row(sa2_name="B", area_ha=200_000.0),
            _row(sa2_name="C", area_ha=None),               # complete but null area
            _row(sa2_name="D", rainfall_feature_quality_flag="no_data", area_ha=50_000.0),
        ]
        result = build_summary_row(_df(rows))
        assert result["total_wheat_area_ha"] == pytest.approx(300_000.0, rel=1e-4)

    def test_qgis_mapped_area_sums_all_nonnull(self):
        rows = [
            _row(sa2_name="A", area_ha=100_000.0),
            _row(sa2_name="B", area_ha=200_000.0),
            _row(sa2_name="C", area_ha=None),
            _row(sa2_name="D", rainfall_feature_quality_flag="no_data", area_ha=50_000.0),
        ]
        result = build_summary_row(_df(rows))
        # A + B + D (C is null)
        assert result["qgis_wheat_area_mapped_ha"] == pytest.approx(350_000.0, rel=1e-4)

    def test_coverage_share(self):
        rows = [
            _row(sa2_name="A", area_ha=300_000.0),
            _row(sa2_name="B", rainfall_feature_quality_flag="no_data", area_ha=100_000.0),
        ]
        result = build_summary_row(_df(rows))
        assert result["coverage_share"] == pytest.approx(0.75, rel=1e-4)

    def test_coverage_share_none_when_no_mapped_area(self):
        rows = [_row(sa2_name="A", area_ha=None)]
        result = build_summary_row(_df(rows))
        assert result["coverage_share"] is None


# ---------------------------------------------------------------------------
# build_summary_row — weighted metrics
# ---------------------------------------------------------------------------

class TestSummaryRowWeightedMetrics:
    def test_weighted_sowing_rain(self):
        rows = [
            _row(sa2_name="A", area_ha=100_000.0, sowing_window_rain_mm=80.0),
            _row(sa2_name="B", area_ha=300_000.0, sowing_window_rain_mm=100.0),
        ]
        result = build_summary_row(_df(rows))
        expected = (80.0 * 100_000 + 100.0 * 300_000) / 400_000
        assert result["sowing_window_rain_mm_wt"] == pytest.approx(expected, rel=1e-4)

    def test_incomplete_rows_excluded_from_weighting(self):
        rows = [
            _row(sa2_name="A", area_ha=100_000.0, sowing_window_rain_mm=80.0),
            _row(sa2_name="B", area_ha=100_000.0, sowing_window_rain_mm=200.0,
                 rainfall_feature_quality_flag="insufficient_season"),
        ]
        result = build_summary_row(_df(rows))
        assert result["sowing_window_rain_mm_wt"] == pytest.approx(80.0, rel=1e-4)

    def test_null_area_complete_row_excluded_from_weighting(self):
        rows = [
            _row(sa2_name="A", area_ha=100_000.0, sowing_window_rain_mm=80.0),
            _row(sa2_name="B", area_ha=None, sowing_window_rain_mm=500.0),
        ]
        result = build_summary_row(_df(rows))
        assert result["sowing_window_rain_mm_wt"] == pytest.approx(80.0, rel=1e-4)

    def test_all_weighted_metrics_present(self):
        rows = [_row()]
        result = build_summary_row(_df(rows))
        for metric in WEIGHTED_METRICS:
            assert f"{metric}_wt" in result, f"Missing {metric}_wt in output"


# ---------------------------------------------------------------------------
# build_summary_row — SA2 name lists
# ---------------------------------------------------------------------------

class TestSummaryRowNameLists:
    def test_eligible_sa2s_sorted(self):
        rows = [
            _row(sa2_name="Merredin"),
            _row(sa2_name="Dowerin"),
        ]
        result = build_summary_row(_df(rows))
        assert result["eligible_sa2s"] == "Dowerin; Merredin"

    def test_excluded_lists_populated(self):
        rows = [
            _row(sa2_name="A"),
            _row(sa2_name="B", area_ha=None),                                  # complete, no area
            _row(sa2_name="C", rainfall_feature_quality_flag="insufficient_season"),
            _row(sa2_name="D", rainfall_feature_quality_flag="no_data", area_ha=None),
        ]
        result = build_summary_row(_df(rows))
        assert "B" in result["excluded_complete_no_area_sa2s"]
        assert "C" in result["excluded_insufficient_season_sa2s"]
        assert "D" in result["excluded_no_data_sa2s"]

    def test_season_year_in_output(self):
        rows = [_row(season_year=2025.0)]
        result = build_summary_row(_df(rows))
        assert result["season_year"] == 2025
