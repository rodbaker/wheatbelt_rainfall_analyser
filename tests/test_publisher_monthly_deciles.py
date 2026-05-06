"""Tests: WeeklyReportGenerator includes Monthly Rainfall Compared With History section.

Acceptance checks:
  1. Weekly report reads the monthly decile CSV
  2. Report includes decile label and historical median
  3. Future months render as —
  4. Active month is labelled month-to-date
  5. Baseline disclosure appears
  6. Monthly fallback caveat includes Geraldton - North when it contributes via NetCDF rainfall
"""

import csv
import shutil
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.agents.insight_publisher.report_generator import WeeklyReportGenerator


_DECILE_COLS = [
    'year', 'month', 'rainfall_mm_wt', 'historical_year_count',
    'historical_median_mm_wt', 'historical_mean_mm_wt',
    'anomaly_mm_wt', 'anomaly_pct_wt',
    'rainfall_decile', 'rainfall_decile_label',
    'climatology_quality_flag',
    'is_partial_month',
    'n_sa2s_universe', 'n_sa2s_weighted', 'n_sa2s_missing_rainfall',
    'weighting_area_ha', 'weighting_area_share',
    'fallback_area_sa2s', 'area_fallback_caveat',
    'current_rainfall_source', 'historical_baseline_source',
]

_FALLBACK_CAVEAT = (
    "Uses 2015-16 ABS fallback area for Esperance Surrounds; Geraldton - North; Morawa "
    "because 2020-21 wheat area was not published."
)


def _decile_row(year: int, month: int, **overrides) -> dict:
    defaults = {
        'year': year,
        'month': month,
        'rainfall_mm_wt': 12.5,
        'historical_year_count': 15,
        'historical_median_mm_wt': 18.5,
        'historical_mean_mm_wt': 20.0,
        'anomaly_mm_wt': -6.0,
        'anomaly_pct_wt': -32.4,
        'rainfall_decile': 4,
        'rainfall_decile_label': 'below normal',
        'climatology_quality_flag': 'ok',
        'is_partial_month': False,
        'n_sa2s_universe': 30,
        'n_sa2s_weighted': 28,
        'n_sa2s_missing_rainfall': 0,
        'weighting_area_ha': 4390101.93,
        'weighting_area_share': 0.97,
        'fallback_area_sa2s': 3,
        'area_fallback_caveat': _FALLBACK_CAVEAT,
        'current_rainfall_source': 'monthly_rain_netCDF',
        'historical_baseline_source': 'monthly_rain_netCDF',
    }
    return {**defaults, **overrides}


class _TempProject:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "data" / "features").mkdir(parents=True)
        (self.root / "reports" / "weekly").mkdir(parents=True)

    @property
    def decile_path(self) -> Path:
        return self.root / "data" / "features" / "wa_wheat_weighted_monthly_rainfall_deciles.csv"

    @property
    def weekly_dir(self) -> Path:
        return self.root / "reports" / "weekly"

    def write_deciles(self, rows: list[dict]) -> None:
        self.decile_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.decile_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_DECILE_COLS)
            writer.writeheader()
            writer.writerows(rows)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def _make_generator(project: _TempProject, season_year: int = 2026, today: date = None) -> WeeklyReportGenerator:
    gen = WeeklyReportGenerator(season_year=season_year, output_dir=str(project.weekly_dir), today=today)
    gen.weighted_summary_path = project.root / "data" / "features" / "wa_wheat_area_weighted_rainfall_summary.csv"
    gen.monthly_decile_path = project.decile_path
    return gen


# ---------------------------------------------------------------------------
# 1. Weekly report reads the monthly decile CSV
# ---------------------------------------------------------------------------

class TestWeeklyReportReadsMonthlyDecileCSV:

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_section_heading_appears_when_csv_present(self):
        self.project.write_deciles([_decile_row(2026, 1)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Monthly Rainfall Compared With History" in content

    def test_section_heading_appears_even_when_csv_absent(self):
        # CSV does not exist — section still renders (all —)
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Monthly Rainfall Compared With History" in content

    def test_section_appears_when_no_data_for_season_year(self):
        # CSV exists but only has past-year data
        self.project.write_deciles([_decile_row(2025, 1)])
        gen = _make_generator(self.project, season_year=2026, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Monthly Rainfall Compared With History" in content


# ---------------------------------------------------------------------------
# 2. Report includes decile label and historical median
# ---------------------------------------------------------------------------

class TestMonthlyDecileSectionContent:

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_decile_label_appears(self):
        self.project.write_deciles([_decile_row(2026, 3, rainfall_decile_label='above normal')])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "above normal" in content

    def test_historical_median_appears(self):
        self.project.write_deciles([_decile_row(2026, 3, historical_median_mm_wt=22.7)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "22.7" in content

    def test_rainfall_value_appears(self):
        self.project.write_deciles([_decile_row(2026, 2, rainfall_mm_wt=8.3)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "8.3" in content

    def test_decile_number_appears(self):
        self.project.write_deciles([_decile_row(2026, 1, rainfall_decile=9)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "| 9 |" in content

    def test_diff_from_median_positive(self):
        self.project.write_deciles([_decile_row(2026, 1, rainfall_mm_wt=25.0, historical_median_mm_wt=18.0)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "+7.0" in content

    def test_diff_from_median_negative(self):
        self.project.write_deciles([_decile_row(2026, 1, rainfall_mm_wt=10.0, historical_median_mm_wt=18.0)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "-8.0" in content

    def test_period_label_pre_seeding_for_jan(self):
        self.project.write_deciles([_decile_row(2026, 1)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "pre-seeding" in content

    def test_period_label_growing_season_for_may(self):
        self.project.write_deciles([_decile_row(2026, 5)])
        gen = _make_generator(self.project, today=date(2026, 6, 1))
        content = gen.generate_report().read_text()
        assert "growing season" in content

    def test_period_label_harvest_for_nov(self):
        self.project.write_deciles([_decile_row(2026, 11)])
        gen = _make_generator(self.project, today=date(2026, 12, 1))
        content = gen.generate_report().read_text()
        assert "harvest" in content


# ---------------------------------------------------------------------------
# 3. Future months render as —
# ---------------------------------------------------------------------------

class TestFutureMonthsRenderAsDash:

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_months_after_current_show_dashes(self):
        # today = May 6; Jun–Dec should be —
        self.project.write_deciles([_decile_row(2026, 1), _decile_row(2026, 4)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        # Jun is month 6 — must appear with all dashes
        assert "Jun (growing season) | — | — | — | — | — |" in content

    def test_december_shows_dashes_when_current_month_is_may(self):
        self.project.write_deciles([_decile_row(2026, 1)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Dec (harvest) | — | — | — | — | — |" in content

    def test_no_dashes_for_months_before_current(self):
        # Jan–Apr have data; May is MTD — none of these should show all-dashes
        rows = [_decile_row(2026, m) for m in range(1, 5)]
        self.project.write_deciles(rows)
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        # Jan row must have numeric values
        assert "Jan (pre-seeding) | — | — | — | — | — |" not in content

    def test_past_season_year_shows_all_months_with_data(self):
        # For a completed year, no future months — all 12 months are in the past
        rows = [_decile_row(2025, m) for m in range(1, 13)]
        self.project.write_deciles(rows)
        gen = _make_generator(self.project, season_year=2025, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Dec (harvest) | — | — | — | — | — |" not in content


# ---------------------------------------------------------------------------
# 4. Active month is labelled month-to-date
# ---------------------------------------------------------------------------

class TestActiveMonthLabelledMTD:

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_current_month_has_mtd_label(self):
        self.project.write_deciles([_decile_row(2026, 5)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "May (growing season, MTD)" in content

    def test_mtd_label_only_on_current_month(self):
        rows = [_decile_row(2026, m) for m in range(1, 6)]
        self.project.write_deciles(rows)
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Apr (growing season, MTD)" not in content
        assert "Jan (pre-seeding, MTD)" not in content

    def test_mtd_label_absent_for_past_season(self):
        rows = [_decile_row(2025, m) for m in range(1, 13)]
        self.project.write_deciles(rows)
        gen = _make_generator(self.project, season_year=2025, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "MTD" not in content

    def test_current_month_with_no_data_still_shows_mtd_as_dash(self):
        # May has no data row — shows — but still has MTD label
        self.project.write_deciles([_decile_row(2026, 1)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "May (growing season, MTD) | — | — | — | — | — |" in content


# ---------------------------------------------------------------------------
# 5. Baseline disclosure appears
# ---------------------------------------------------------------------------

class TestBaselineDisclosure:

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_baseline_disclosure_present(self):
        self.project.write_deciles([_decile_row(2026, 1)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Historical comparison uses available local monthly rainfall files: 2005 and 2011" in content

    def test_baseline_disclosure_mentions_2005(self):
        self.project.write_deciles([_decile_row(2026, 1)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "2005" in content

    def test_baseline_disclosure_present_even_when_no_data(self):
        # CSV absent — section still includes disclosure
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Historical comparison uses available local monthly rainfall files" in content


# ---------------------------------------------------------------------------
# 6. Monthly fallback caveat includes Geraldton - North when it contributes
# ---------------------------------------------------------------------------

class TestMonthlyFallbackCaveat:

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_monthly_caveat_appears_when_geraldton_north_present(self):
        caveat = (
            "Uses 2015-16 ABS fallback area for Geraldton - North "
            "because 2020-21 wheat area was not published."
        )
        self.project.write_deciles([_decile_row(2026, 1, area_fallback_caveat=caveat)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Geraldton - North" in content
        assert "Monthly area caveat" in content

    def test_monthly_caveat_appears_with_full_default_caveat(self):
        self.project.write_deciles([_decile_row(2026, 1)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Geraldton - North" in content

    def test_monthly_caveat_absent_when_no_fallback(self):
        self.project.write_deciles([_decile_row(2026, 1, area_fallback_caveat="")])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Monthly area caveat" not in content

    def test_monthly_caveat_separate_from_station_based_caveat(self):
        """Monthly fallback caveat must appear in monthly section, not mixed with
        the area-weighted summary fallback caveat."""
        self.project.write_deciles([_decile_row(2026, 1)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        # Monthly section caveat has its own prefix
        assert "Monthly area caveat:" in content


# ---------------------------------------------------------------------------
# 7. Low-coverage months show rainfall but suppress decile/median/diff
# ---------------------------------------------------------------------------

class TestLowCoverageRendering:

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_low_coverage_shows_rainfall_but_suppresses_decile(self):
        row = _decile_row(
            2026, 3,
            climatology_quality_flag='low_coverage(0.72)',
            rainfall_mm_wt=8.3,
            rainfall_decile=None,
            rainfall_decile_label=None,
            historical_median_mm_wt=None,
        )
        self.project.write_deciles([row])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        # Rainfall appears; decile/median columns are —
        assert "8.3 mm | — | — | — | — |" in content

    def test_low_coverage_adds_coverage_caveat_note(self):
        row = _decile_row(
            2026, 2,
            climatology_quality_flag='low_coverage(0.55)',
            rainfall_mm_wt=5.0,
            rainfall_decile=None,
            rainfall_decile_label=None,
            historical_median_mm_wt=None,
        )
        self.project.write_deciles([row])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Coverage caveat" in content
        assert "80%" in content

    def test_low_coverage_caveat_absent_when_no_low_coverage_months(self):
        self.project.write_deciles([_decile_row(2026, 1)])
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        assert "Coverage caveat" not in content

    def test_ok_months_still_show_full_row_alongside_low_coverage_month(self):
        rows = [
            _decile_row(2026, 1, rainfall_mm_wt=25.0, historical_median_mm_wt=18.0),
            _decile_row(
                2026, 2,
                climatology_quality_flag='low_coverage(0.65)',
                rainfall_mm_wt=7.0,
                rainfall_decile=None,
                rainfall_decile_label=None,
                historical_median_mm_wt=None,
            ),
        ]
        self.project.write_deciles(rows)
        gen = _make_generator(self.project, today=date(2026, 5, 6))
        content = gen.generate_report().read_text()
        # Jan is ok → shows +7.0 diff
        assert "+7.0" in content
        # Feb is low_coverage → suppresses decile
        assert "7.0 mm | — | — | — | — |" in content
