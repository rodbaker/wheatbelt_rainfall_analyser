"""
Tests for scripts/build_sa2_rainfall_features.py

Covers:
- season-year assignment (boundary cases)
- monthly rainfall aggregation
- dry spell metrics
- autumn break detection
- SA2 grouping / simple-mean aggregation
- station ID normalisation
- output schema
"""

import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# Add repo root to path so the script module is importable without installation
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.build_sa2_rainfall_features import (
    assign_season_year,
    compute_station_season_features,
    aggregate_to_sa2,
    build_output,
    _detect_autumn_break,
    _dry_spell_days,
    _quality_score,
    load_station_sa2_map,
    PIPELINE_VERSION,
)


def _make_obs(station_id: str, dates: list[str], rainfall: list[float],
              quality: int = 0) -> pd.DataFrame:
    df = pd.DataFrame({
        'station_id': station_id,
        'date': pd.to_datetime(dates),
        'rainfall': rainfall,
        'rainfall_quality': quality,
    })
    df['station_id'] = df['station_id'].astype(str)
    return df


def _full_season_obs(station_id: str, season_year: int,
                     daily_rain: float = 2.0, quality: int = 0) -> pd.DataFrame:
    """Generate daily observations for the full Apr–Mar season year."""
    start = pd.Timestamp(season_year, 4, 1)
    end = pd.Timestamp(season_year + 1, 3, 31)
    dates = pd.date_range(start, end, freq='D')
    return pd.DataFrame({
        'station_id': station_id,
        'date': dates,
        'rainfall': daily_rain,
        'rainfall_quality': quality,
    })


class TestSeasonYearAssignment(unittest.TestCase):

    def test_april_is_same_year(self):
        dates = pd.Series(pd.to_datetime(['2025-04-01', '2025-06-15', '2025-12-31']))
        result = assign_season_year(dates)
        self.assertTrue((result == 2025).all())

    def test_jan_mar_is_previous_year(self):
        dates = pd.Series(pd.to_datetime(['2026-01-01', '2026-02-28', '2026-03-31']))
        result = assign_season_year(dates)
        self.assertTrue((result == 2025).all())

    def test_boundary_march_31(self):
        d = pd.Series(pd.to_datetime(['2025-03-31']))
        self.assertEqual(assign_season_year(d).iloc[0], 2024)

    def test_boundary_april_1(self):
        d = pd.Series(pd.to_datetime(['2025-04-01']))
        self.assertEqual(assign_season_year(d).iloc[0], 2025)

    def test_december_same_year(self):
        d = pd.Series(pd.to_datetime(['2025-12-01']))
        self.assertEqual(assign_season_year(d).iloc[0], 2025)


class TestMonthlyRainfallAggregation(unittest.TestCase):

    def test_monthly_totals_correct(self):
        obs = _full_season_obs('010001', 2025, daily_rain=1.0)
        result = compute_station_season_features(obs, min_coverage=0.5)
        self.assertFalse(result.empty)
        row = result.iloc[0]
        # April 2025 has 30 days × 1mm = 30mm
        self.assertAlmostEqual(row['monthly_rainfall_apr_mm'], 30.0, places=1)
        # July has 31 days
        self.assertAlmostEqual(row['monthly_rainfall_jul_mm'], 31.0, places=1)

    def test_missing_rainfall_is_none_not_zero(self):
        obs = _full_season_obs('010001', 2025, daily_rain=np.nan, quality=999)
        result = compute_station_season_features(obs, min_coverage=0.01)
        if not result.empty:
            row = result.iloc[0]
            # With quality=999, values are set to NaN; monthly total should be None
            self.assertIsNone(row['monthly_rainfall_apr_mm'])

    def test_partial_coverage_below_threshold_returns_none(self):
        # Only 5 days of April present with min_coverage=0.8 → should be None
        obs = _make_obs('010001',
                        ['2025-04-01', '2025-04-02', '2025-04-03', '2025-04-04', '2025-04-05'],
                        [5.0] * 5)
        result = compute_station_season_features(obs, min_coverage=0.8)
        # Station may be skipped entirely (coverage < 0.5*0.8) or individual months may be None
        if not result.empty:
            self.assertIsNone(result.iloc[0]['monthly_rainfall_apr_mm'])

    def test_seasonal_totals_apr_oct(self):
        obs = _full_season_obs('010001', 2025, daily_rain=1.0)
        result = compute_station_season_features(obs, min_coverage=0.5)
        row = result.iloc[0]
        # Apr(30)+May(31)+Jun(30)+Jul(31)+Aug(31)+Sep(30)+Oct(31) = 214 days
        self.assertAlmostEqual(row['rainfall_total_apr_oct_mm'], 214.0, places=0)


class TestDrySpellMetrics(unittest.TestCase):

    def _season_rows(self, season_year, daily_rain):
        obs = _full_season_obs('010001', season_year, daily_rain=daily_rain)
        obs['month'] = obs['date'].dt.month
        obs['year'] = obs['date'].dt.year
        in_season = obs[(obs['year'] == season_year) &
                        (obs['month'] >= 4) & (obs['month'] <= 10)].copy()
        return in_season

    def test_no_dry_spells_with_sufficient_rain(self):
        rows = self._season_rows(2025, 10.0)
        result = _dry_spell_days(rows, window=7, threshold=5.0)
        self.assertEqual(result, 0.0)

    def test_all_dry_spells_with_no_rain(self):
        rows = self._season_rows(2025, 0.0)
        result = _dry_spell_days(rows, window=7, threshold=5.0)
        # Every window-complete day should be counted
        self.assertGreater(result, 0)

    def test_returns_none_for_empty_input(self):
        empty = pd.DataFrame(columns=['date', 'rainfall'])
        result = _dry_spell_days(empty, window=7, threshold=5.0)
        self.assertIsNone(result)


class TestAutumnBreakDetection(unittest.TestCase):

    def _grp(self, dates, rainfall, season_year=2025):
        df = _make_obs('010001', dates, rainfall)
        df['month'] = df['date'].dt.month
        df['year'] = df['date'].dt.year
        return df

    def test_single_day_trigger(self):
        grp = self._grp(['2025-05-20'], [15.0])
        break_date, _, status = _detect_autumn_break(grp, 2025)
        self.assertIsNotNone(break_date)
        self.assertEqual(status, 'on_time')

    def test_absent_when_no_qualifying_event(self):
        dates = [f'2025-04-{d:02d}' for d in range(1, 31)]
        grp = self._grp(dates, [1.0] * 30)
        _, _, status = _detect_autumn_break(grp, 2025)
        self.assertEqual(status, 'absent')

    def test_early_break_before_may_15(self):
        grp = self._grp(['2025-04-20'], [12.0])
        _, _, status = _detect_autumn_break(grp, 2025)
        self.assertEqual(status, 'early')

    def test_late_break_after_jun_15(self):
        grp = self._grp(['2025-06-20'], [12.0])
        _, _, status = _detect_autumn_break(grp, 2025)
        self.assertEqual(status, 'late')

    def test_rolling_7d_trigger(self):
        # 26mm over 7 days (≥25 mm threshold)
        dates = pd.date_range('2025-05-01', periods=7, freq='D').strftime('%Y-%m-%d').tolist()
        grp = self._grp(dates, [3.71] * 7)  # 3.71*7 ≈ 25.97
        _, break_7d, status = _detect_autumn_break(grp, 2025)
        self.assertIsNotNone(break_7d)
        self.assertNotEqual(status, 'absent')


class TestSA2Grouping(unittest.TestCase):

    def test_simple_mean_across_two_stations(self):
        obs = pd.concat([
            _full_season_obs('010001', 2025, daily_rain=2.0),
            _full_season_obs('010002', 2025, daily_rain=4.0),
        ])
        station_features = compute_station_season_features(obs, min_coverage=0.5)

        station_map = pd.DataFrame({
            'station_id': ['010001', '010002'],
            'sa2_code': ['51238', '51238'],
            'sa2_name': ['Test SA2', 'Test SA2'],
            'state_name': ['Western Australia', 'Western Australia'],
        })
        sa2_df = aggregate_to_sa2(station_features, station_map)
        self.assertFalse(sa2_df.empty)
        row = sa2_df[(sa2_df['sa2_code'] == '51238') & (sa2_df['season_year'] == 2025)]
        self.assertFalse(row.empty)
        self.assertEqual(int(row['station_count'].iloc[0]), 2)
        # Mean of Apr totals: (2*30 + 4*30)/2 = 90
        self.assertAlmostEqual(row['monthly_rainfall_apr_mm'].iloc[0], 90.0, places=0)

    def test_contributing_station_ids_sorted(self):
        obs = pd.concat([
            _full_season_obs('010002', 2025, daily_rain=1.0),
            _full_season_obs('010001', 2025, daily_rain=1.0),
        ])
        station_features = compute_station_season_features(obs, min_coverage=0.5)
        station_map = pd.DataFrame({
            'station_id': ['010001', '010002'],
            'sa2_code': ['51238', '51238'],
            'sa2_name': ['Test SA2', 'Test SA2'],
            'state_name': ['Western Australia', 'Western Australia'],
        })
        sa2_df = aggregate_to_sa2(station_features, station_map)
        row = sa2_df[sa2_df['sa2_code'] == '51238'].iloc[0]
        ids = row['contributing_station_ids'].split('|')
        self.assertEqual(ids, sorted(ids))


class TestStationIdNormalisation(unittest.TestCase):

    def test_leading_zeros_preserved_in_map(self):
        import tempfile, os
        meta_content = (
            "Station number,Lat,Lon,Station name,SA2_5DIG16,SA2_NAME16,STE_CODE16,STE_NAME16,2010_11_area\n"
            "8002,-30.6,116.77,BALLIDU,51238,Dowerin,5,Western Australia,409182\n"
        )
        regions_content = "station_id,sa2_name,sa3_name,sa4_name\n008002,Dowerin,Wheat Belt - North,WA\n"

        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False) as mf:
            mf.write(meta_content)
            meta_path = mf.name
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False) as rf:
            rf.write(regions_content)
            regions_path = rf.name

        try:
            station_map = load_station_sa2_map(meta_path, regions_path)
            row = station_map[station_map['sa2_code'] == '51238']
            self.assertFalse(row.empty)
            station_id = row['station_id'].iloc[0]
            self.assertEqual(len(station_id), 6)
            self.assertTrue(station_id.startswith('0'), f"Expected leading zero, got {station_id}")
        finally:
            os.unlink(meta_path)
            os.unlink(regions_path)


class TestOutputSchema(unittest.TestCase):

    REQUIRED_COLUMNS = [
        'season_year', 'state_name', 'sa2_code', 'sa2_name',
        'station_count', 'contributing_station_ids', 'aggregation_method',
        'rainfall_total_apr_oct_mm', 'rainfall_total_may_oct_mm',
        'monthly_rainfall_jan_mm', 'monthly_rainfall_jun_mm', 'monthly_rainfall_dec_mm',
        'sowing_window_rain_mm', 'in_crop_rain_mm', 'flowering_rain_mm',
        'grain_fill_rain_mm', 'harvest_rain_mm',
        'autumn_break_date', 'autumn_break_7d_mm', 'autumn_break_status',
        'dry_spell_days_7d_lt_5mm', 'dry_spell_days_14d_lt_10mm',
        'data_quality_score', 'source_dataset', 'pipeline_version', 'created_at',
    ]

    def _build_sample(self):
        obs = _full_season_obs('010001', 2025, daily_rain=3.0)
        station_features = compute_station_season_features(obs, min_coverage=0.5)
        station_map = pd.DataFrame({
            'station_id': ['010001'],
            'sa2_code': ['51238'],
            'sa2_name': ['Test SA2'],
            'state_name': ['Western Australia'],
        })
        sa2_df = aggregate_to_sa2(station_features, station_map)
        return build_output(sa2_df, PIPELINE_VERSION)

    def test_all_required_columns_present(self):
        out = self._build_sample()
        missing = [c for c in self.REQUIRED_COLUMNS if c not in out.columns]
        self.assertEqual(missing, [], f"Missing columns: {missing}")

    def test_season_year_is_integer(self):
        out = self._build_sample()
        self.assertTrue(pd.api.types.is_integer_dtype(out['season_year']),
                        f"season_year dtype: {out['season_year'].dtype}")

    def test_station_count_is_integer(self):
        out = self._build_sample()
        self.assertTrue(pd.api.types.is_integer_dtype(out['station_count']),
                        f"station_count dtype: {out['station_count'].dtype}")

    def test_pipeline_version_present(self):
        out = self._build_sample()
        self.assertEqual(out['pipeline_version'].iloc[0], PIPELINE_VERSION)

    def test_aggregation_method_value(self):
        out = self._build_sample()
        self.assertEqual(out['aggregation_method'].iloc[0], 'simple_mean')


class TestDataQualityScore(unittest.TestCase):

    def test_all_observed_gives_score_1(self):
        df = pd.DataFrame({'rainfall_quality': [0, 0, 0, 0]})
        self.assertAlmostEqual(_quality_score(df), 1.0)

    def test_all_interpolated_gives_score_08(self):
        df = pd.DataFrame({'rainfall_quality': [15, 15, 15]})
        self.assertAlmostEqual(_quality_score(df), 0.8)

    def test_mixed_codes(self):
        # (1.0 + 0.8) / 2 = 0.9
        df = pd.DataFrame({'rainfall_quality': [0, 15]})
        self.assertAlmostEqual(_quality_score(df), 0.9)

    def test_missing_code_999_gives_zero(self):
        df = pd.DataFrame({'rainfall_quality': [999, 999]})
        self.assertAlmostEqual(_quality_score(df), 0.0)


if __name__ == '__main__':
    unittest.main()
