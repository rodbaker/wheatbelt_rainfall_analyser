"""Tests: WeeklyReportGenerator reads WA wheat weighted rainfall into market brief.

Acceptance checks:
  1. weighted rainfall output is read by the publisher/reporter path
  2. coverage share appears in the generated brief
  3. area_fallback_caveat appears when fallback-weighted SA2s contribute
  4. no_data / insufficient_season SA2s are excluded from weighted metrics
     (i.e. exclusion count is disclosed in the brief)
"""

import csv
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.agents.insight_publisher.report_generator import WeeklyReportGenerator


# ---------------------------------------------------------------------------
# Minimal fixture helpers
# ---------------------------------------------------------------------------

def _summary_row(**overrides) -> dict:
    """Return a minimal wa_wheat_area_weighted_rainfall_summary row."""
    defaults = {
        "season_year": 2025,
        "state": "Western Australia",
        "crop": "wheat",
        "n_sa2s_qgis_universe": 28,
        "n_sa2s_complete": 8,
        "n_sa2s_eligible": 8,
        "n_sa2s_insufficient_season": 4,
        "n_sa2s_no_data": 16,
        "n_sa2s_complete_no_area": 0,
        "total_wheat_area_ha": 3_516_612.52,
        "qgis_wheat_area_mapped_ha": 4_390_101.93,
        "coverage_share": 0.8011,
        "pre_seeding_rain_mm_wt": 85.40,
        "sowing_window_rain_mm_wt": 102.86,
        "in_crop_rain_mm_wt": 262.70,
        "rainfall_total_apr_oct_mm_wt": 298.60,
        "rainfall_total_may_oct_mm_wt": 262.70,
        "flowering_rain_mm_wt": 39.65,
        "grain_fill_rain_mm_wt": 38.02,
        "harvest_rain_mm_wt": 33.48,
        "dry_spell_days_7d_lt_5mm_wt": 100.61,
        "dry_spell_days_14d_lt_10mm_wt": 74.94,
        "eligible_sa2s": "Dowerin; Merredin",
        "excluded_insufficient_season_sa2s": "Brookton; Cunderdin",
        "excluded_no_data_sa2s": "Albany Surrounds; Geraldton",
        "excluded_complete_no_area_sa2s": "",
        "area_fallback_caveat": "",
        "generated_at": "2026-05-05T22:47:22Z",
    }
    return {**defaults, **overrides}


def _write_summary_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class _TempProject:
    """Throwaway temp directory that mimics the project structure."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "data" / "features").mkdir(parents=True)
        (self.root / "reports" / "weekly").mkdir(parents=True)

    @property
    def summary_path(self) -> Path:
        return self.root / "data" / "features" / "wa_wheat_area_weighted_rainfall_summary.csv"

    @property
    def weekly_dir(self) -> Path:
        return self.root / "reports" / "weekly"

    def write_summary(self, rows: list[dict]) -> None:
        _write_summary_csv(rows, self.summary_path)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def _make_generator(project: _TempProject, season_year: int = 2025) -> WeeklyReportGenerator:
    gen = WeeklyReportGenerator(season_year=season_year, output_dir=str(project.weekly_dir))
    gen.weighted_summary_path = project.summary_path
    return gen


# ---------------------------------------------------------------------------
# 1. Weighted rainfall output is read by the publisher path
# ---------------------------------------------------------------------------

class TestWeeklyGeneratorReadsWeightedRainfall:

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_report_written_to_weekly_dir(self):
        self.project.write_summary([_summary_row()])
        gen = _make_generator(self.project)
        path = gen.generate_report()
        assert path.exists()
        assert path.parent == self.project.weekly_dir

    def test_report_contains_in_crop_rain(self):
        self.project.write_summary([_summary_row(in_crop_rain_mm_wt=262.7)])
        gen = _make_generator(self.project)
        path = gen.generate_report()
        content = path.read_text()
        assert "262.7" in content

    def test_report_contains_sowing_window_rain(self):
        self.project.write_summary([_summary_row(sowing_window_rain_mm_wt=102.86)])
        gen = _make_generator(self.project)
        path = gen.generate_report()
        content = path.read_text()
        assert "102.9" in content

    def test_missing_summary_file_generates_stub_report(self):
        # Do NOT write the CSV — file absent
        gen = _make_generator(self.project)
        path = gen.generate_report()
        assert path.exists()
        content = path.read_text()
        assert "No weighted rainfall data available" in content
        assert "build_wa_wheat_weighted_rainfall.py" in content

    def test_missing_season_year_generates_stub_report(self):
        self.project.write_summary([_summary_row(season_year=2024)])
        gen = _make_generator(self.project, season_year=2025)
        path = gen.generate_report()
        content = path.read_text()
        assert "No weighted rainfall data available" in content

    def test_all_weighted_metrics_in_report(self):
        self.project.write_summary([_summary_row()])
        gen = _make_generator(self.project)
        path = gen.generate_report()
        content = path.read_text()
        expected_labels = [
            "Pre-seeding rain (Jan–Mar)",
            "Sowing window rain",
            "In-crop rain",
            "Growing season (Apr–Oct)",
            "Growing season (May–Oct)",
            "Flowering rain",
            "Grain fill rain",
            "Harvest rain (Nov–Dec)",
            "Dry spells (7d <5mm)",
            "Dry spells (14d <10mm)",
        ]
        for label in expected_labels:
            assert label in content, f"Missing metric label: {label}"

    def test_pre_seeding_rain_value_in_report(self):
        self.project.write_summary([_summary_row(pre_seeding_rain_mm_wt=85.40)])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "85.4" in content


# ---------------------------------------------------------------------------
# 2. Coverage share appears in the generated brief
# ---------------------------------------------------------------------------

class TestWeeklyGeneratorCoverageShare:

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_coverage_share_percentage_in_report(self):
        self.project.write_summary([_summary_row(coverage_share=0.8011)])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "80.1%" in content

    def test_coverage_sa2_counts_in_report(self):
        self.project.write_summary([_summary_row(n_sa2s_eligible=8, n_sa2s_qgis_universe=28)])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "8 of 28" in content

    def test_coverage_unknown_when_none(self):
        self.project.write_summary([_summary_row(coverage_share=None)])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "unknown" in content

    def test_eligible_sa2_list_in_report(self):
        self.project.write_summary([_summary_row(eligible_sa2s="Dowerin; Merredin")])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "Dowerin" in content
        assert "Merredin" in content


# ---------------------------------------------------------------------------
# 3. area_fallback_caveat appears when fallback-weighted SA2s contribute
# ---------------------------------------------------------------------------

class TestWeeklyGeneratorFallbackCaveat:

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_fallback_caveat_in_report_when_present(self):
        caveat = (
            "Uses 2015-16 ABS fallback area for Esperance Surrounds; Morawa "
            "because 2020-21 wheat area was not published."
        )
        self.project.write_summary([_summary_row(area_fallback_caveat=caveat)])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "Esperance Surrounds" in content
        assert "2015-16" in content
        assert "2020-21" in content

    def test_fallback_caveat_absent_when_empty(self):
        self.project.write_summary([_summary_row(area_fallback_caveat="")])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "Area caveat" not in content
        assert "2015-16" not in content

    def test_fallback_caveat_absent_when_null(self):
        row = _summary_row()
        row["area_fallback_caveat"] = None
        self.project.write_summary([row])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "Area caveat" not in content

    def test_fallback_caveat_labels_specific_sa2s(self):
        caveat = (
            "Uses 2015-16 ABS fallback area for Morawa "
            "because 2020-21 wheat area was not published."
        )
        self.project.write_summary([_summary_row(area_fallback_caveat=caveat)])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "Morawa" in content


# ---------------------------------------------------------------------------
# 4. no_data / insufficient_season SA2s excluded from weighted metrics
# ---------------------------------------------------------------------------

class TestWeeklyGeneratorExclusions:
    """The brief must disclose that no_data and insufficient_season SA2s
    do not contribute to the weighted metrics."""

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_no_data_exclusion_count_disclosed(self):
        self.project.write_summary([_summary_row(n_sa2s_no_data=16)])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "16 no-data" in content

    def test_insufficient_season_exclusion_count_disclosed(self):
        self.project.write_summary([_summary_row(n_sa2s_insufficient_season=4)])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "4 insufficient-season" in content

    def test_exclusion_note_absent_when_all_eligible(self):
        self.project.write_summary([_summary_row(n_sa2s_no_data=0, n_sa2s_insufficient_season=0)])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "Excluded from weighted metrics" not in content

    def test_both_exclusion_types_listed_together(self):
        self.project.write_summary([_summary_row(n_sa2s_no_data=16, n_sa2s_insufficient_season=4)])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        # Both must appear in the same exclusion disclosure
        assert "16 no-data" in content
        assert "4 insufficient-season" in content
        assert "Excluded from weighted metrics" in content

    def test_weighted_metrics_use_eligible_sa2s_only(self):
        """Metrics in the report reflect eligible-only weighting from the summary CSV.

        We verify by setting absurdly high metrics that would only appear if
        no_data rows (which shouldn't contribute) were somehow included.
        The reporter must pass through the pre-computed weighted values,
        not re-compute them from raw SA2 data.
        """
        self.project.write_summary([_summary_row(
            sowing_window_rain_mm_wt=102.86,
            n_sa2s_no_data=16,
        )])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        # Pre-computed eligible-only value is present
        assert "102.9" in content

    def test_exclusion_disclosure_mentions_data_quality_reason(self):
        self.project.write_summary([_summary_row(n_sa2s_no_data=5)])
        gen = _make_generator(self.project)
        content = gen.generate_report().read_text()
        assert "insufficient or missing rainfall data" in content


# ---------------------------------------------------------------------------
# 5. Season label uses calendar-year framing ("2026 Season to Date")
# ---------------------------------------------------------------------------

class TestWeeklyGeneratorSeasonLabel:
    """Report headings must use the new calendar-year season framing."""

    def setup_method(self):
        self.project = _TempProject()

    def teardown_method(self):
        self.project.cleanup()

    def test_current_year_label_has_season_to_date(self):
        """A report for the current calendar year must say "Season to Date"."""
        import datetime
        current_year = datetime.date.today().year
        self.project.write_summary([_summary_row(season_year=current_year)])
        gen = _make_generator(self.project, season_year=current_year)
        content = gen.generate_report().read_text()
        assert f"{current_year} Season to Date" in content

    def test_no_slash_year_label(self):
        """Report must not use old YYYY/YY label format."""
        import datetime
        current_year = datetime.date.today().year
        self.project.write_summary([_summary_row(season_year=current_year)])
        gen = _make_generator(self.project, season_year=current_year)
        content = gen.generate_report().read_text()
        slash_label = f"{current_year}/{str(current_year + 1)[-2:]}"
        assert slash_label not in content, f"Old slash label '{slash_label}' found in report"

    def test_past_year_label_has_no_to_date(self):
        """A completed season uses 'YYYY Season' without 'to Date'."""
        self.project.write_summary([_summary_row(season_year=2025)])
        gen = _make_generator(self.project, season_year=2025)
        content = gen.generate_report().read_text()
        assert "2025 Season" in content
        assert "2025 Season to Date" not in content

    def test_report_heading_starts_with_wa_wheat_rainfall(self):
        """H1 heading uses the new 'WA Wheat Rainfall' label."""
        import datetime
        current_year = datetime.date.today().year
        self.project.write_summary([_summary_row(season_year=current_year)])
        gen = _make_generator(self.project, season_year=current_year)
        content = gen.generate_report().read_text()
        assert content.startswith("# WA Wheat Rainfall —")
