"""Tests for scripts/join_sa2_rainfall_crop_context.py"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.join_sa2_rainfall_crop_context import build_join, load_features, load_crop_context


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ctx(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "sa2_code": "501010001",
        "station_sa2_5dig16": "51001",
        "sa2_name": "Test Region A",
        "state": "Western Australia",
        "financial_year": "2020-21",
        "crop": "wheat",
        "area_ha": 1000.0,
        "production_t": 2000.0,
        "yield_t_ha": 2.0,
        "area_share": 0.5,
        "area_rse": None,
        "production_rse": None,
        "yield_rse": None,
        "boundary_status": "matched",
        "source_dataset": "ABS Agricultural Census 2020-21",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _make_feat(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "sa2_code": "51001",
        "season_year": 2025,
        "station_count": 3,
        "aggregation_method": "simple_mean",
        "rainfall_total_apr_oct_mm": 250.0,
        "rainfall_total_may_oct_mm": 220.0,
        "sowing_window_rain_mm": 80.0,
        "in_crop_rain_mm": 200.0,
        "flowering_rain_mm": 40.0,
        "grain_fill_rain_mm": 30.0,
        "harvest_rain_mm": 20.0,
        "autumn_break_date": "2025-04-10",
        "autumn_break_status": "early",
        "dry_spell_days_7d_lt_5mm": 10.0,
        "dry_spell_days_14d_lt_10mm": 8.0,
        "data_quality_score": 0.95,
        "season_coverage_ratio": 0.99,
        "feature_quality_flag": "complete",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


# ---------------------------------------------------------------------------
# Phase 4, Test 1: ABS-frame preservation
# ---------------------------------------------------------------------------

class TestAbsFramePreservation:
    def test_two_ctx_one_rainfall_both_in_output(self):
        ctx = _make_ctx([
            {"sa2_code": "501010001", "station_sa2_5dig16": "51001", "sa2_name": "Region A"},
            {"sa2_code": "501010002", "station_sa2_5dig16": "51002", "sa2_name": "Region B"},
        ])
        feat = _make_feat([{"sa2_code": "51001"}])

        result = build_join(feat, ctx)

        assert len(result) == 2, "Both SA2s must appear in output"

    def test_missing_rainfall_row_has_no_data_flag(self):
        ctx = _make_ctx([
            {"sa2_code": "501010001", "station_sa2_5dig16": "51001"},
            {"sa2_code": "501010002", "station_sa2_5dig16": "51002"},
        ])
        feat = _make_feat([{"sa2_code": "51001"}])

        result = build_join(feat, ctx)

        no_match = result[result["station_sa2_5dig16"] == "51002"]
        assert len(no_match) == 1
        assert no_match.iloc[0]["rainfall_feature_quality_flag"] == "no_data"

    def test_matched_row_has_non_no_data_flag(self):
        ctx = _make_ctx([{"sa2_code": "501010001", "station_sa2_5dig16": "51001"}])
        feat = _make_feat([{"sa2_code": "51001", "feature_quality_flag": "complete"}])

        result = build_join(feat, ctx)

        assert result.iloc[0]["rainfall_feature_quality_flag"] == "complete"


# ---------------------------------------------------------------------------
# Phase 4, Test 2: SA2 key preservation
# ---------------------------------------------------------------------------

class TestSa2KeyPreservation:
    def setup_method(self):
        ctx = _make_ctx([{"sa2_code": "501010001", "station_sa2_5dig16": "51001"}])
        feat = _make_feat([{"sa2_code": "51001"}])
        self.result = build_join(feat, ctx)

    def test_abs_sa2_code_present(self):
        assert "abs_sa2_code" in self.result.columns
        assert self.result.iloc[0]["abs_sa2_code"] == "501010001"

    def test_station_sa2_5dig16_present(self):
        assert "station_sa2_5dig16" in self.result.columns
        assert self.result.iloc[0]["station_sa2_5dig16"] == "51001"

    def test_rainfall_sa2_code_present(self):
        assert "rainfall_sa2_code" in self.result.columns
        assert self.result.iloc[0]["rainfall_sa2_code"] == "51001"

    def test_rainfall_sa2_code_null_when_no_match(self):
        ctx = _make_ctx([{"sa2_code": "501010002", "station_sa2_5dig16": "51002"}])
        feat = _make_feat([{"sa2_code": "51001"}])
        result = build_join(feat, ctx)
        assert pd.isna(result.iloc[0]["rainfall_sa2_code"])

    def test_codes_never_cast_to_int(self):
        assert self.result["abs_sa2_code"].dtype == object
        assert self.result["station_sa2_5dig16"].dtype == object


# ---------------------------------------------------------------------------
# Phase 4, Test 3: Complete match preserves rainfall flag
# ---------------------------------------------------------------------------

class TestCompleteMatch:
    @pytest.mark.parametrize("flag", ["complete", "insufficient_season"])
    def test_rainfall_flag_carried_through(self, flag):
        ctx = _make_ctx([{"station_sa2_5dig16": "51001"}])
        feat = _make_feat([{"sa2_code": "51001", "feature_quality_flag": flag}])
        result = build_join(feat, ctx)
        assert result.iloc[0]["rainfall_feature_quality_flag"] == flag


# ---------------------------------------------------------------------------
# Phase 4, Test 4: Join coverage summary columns
# ---------------------------------------------------------------------------

class TestJoinCoverage:
    def test_output_contains_coverage_fields(self):
        ctx = _make_ctx([
            {"station_sa2_5dig16": "51001"},
            {"station_sa2_5dig16": "51002"},
        ])
        feat = _make_feat([{"sa2_code": "51001", "station_count": 5}])
        result = build_join(feat, ctx)

        assert "station_count" in result.columns
        assert "season_year" in result.columns
        assert "rainfall_feature_quality_flag" in result.columns

        matched = result[result["rainfall_sa2_code"].notna()]
        assert matched.iloc[0]["station_count"] == 5

        unmatched = result[result["rainfall_sa2_code"].isna()]
        assert pd.isna(unmatched.iloc[0]["station_count"])


# ---------------------------------------------------------------------------
# Phase 4, Test 5: SA2 codes never cast to int
# ---------------------------------------------------------------------------

class TestNoCastToInt:
    def test_leading_zero_preserved_in_5dig_key(self):
        ctx = _make_ctx([{"sa2_code": "101010001", "station_sa2_5dig16": "11001"}])
        feat = _make_feat([{"sa2_code": "11001"}])
        result = build_join(feat, ctx)
        assert result.iloc[0]["station_sa2_5dig16"] == "11001"
        assert result.iloc[0]["rainfall_sa2_code"] == "11001"

    def test_load_features_preserves_sa2_code_dtype(self, tmp_path):
        csv = tmp_path / "feat.csv"
        _make_feat([{"sa2_code": "51001"}]).to_csv(csv, index=False)
        df = load_features(str(csv), season_year=None)
        assert df["sa2_code"].dtype == object

    def test_load_crop_context_preserves_sa2_code_dtype(self, tmp_path):
        csv = tmp_path / "ctx.csv"
        _make_ctx([{"sa2_code": "501010001", "station_sa2_5dig16": "51001",
                    "state": "Western Australia", "financial_year": "2020-21"}]).to_csv(csv, index=False)
        df = load_crop_context(str(csv), "Western Australia", "2020-21")
        assert df["sa2_code"].dtype == object
        assert df["station_sa2_5dig16"].dtype == object
