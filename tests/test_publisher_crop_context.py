"""Tests for Phase 5 publisher ABS crop context enrichment.

Covers:
- output unchanged when crop context disabled (default)
- graceful omit when enabled + missing + required=False
- FileNotFoundError when enabled + required=True + missing
- expected ABS section content when enabled + valid CSV
- RSE/code fields preserved as strings (not coerced to float/int)
- suppressed/null estimates treated as missing, not zero
"""

import csv
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import yaml

from src.common.crop_context_loader import REQUIRED_COLUMNS


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _minimal_crop_context_rows(
    sa2_5dig="50101",
    sa2_name="Wheatlands East",
) -> list:
    return [{
        "sa2_code": "501011001",
        "station_sa2_5dig16": sa2_5dig,
        "sa2_name": sa2_name,
        "state": "Western Australia",
        "financial_year": "2020-21",
        "crop": "wheat",
        "area_ha": "8500.0",
        "production_t": "",  # suppressed
        "yield_t_ha": "2.0",
        "area_share": "0.60",
        "area_rse": "^",
        "production_rse": "np",
        "yield_rse": "",
        "source_dataset": "ABS Agricultural Census 2020-21",
        "source_commodity_area": "AGCEREAL_AHAWHT_F",
        "source_commodity_production": "AGCEREAL_ATOWHT_F",
        "source_commodity_yield": "WHEAT_YIELD_F",
        "boundary_status": "matched",
        "notes": "",
    }]


def _write_csv(rows, path: Path) -> Path:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _minimal_stations_df(
    sa2_5dig="50101",
    sa2_name="Wheatlands East",
    station_id=8002,
) -> pd.DataFrame:
    return pd.DataFrame([{
        "station_id": station_id,
        "Station name": "TEST STATION",
        "Lat": -31.5,
        "Lon": 117.5,
        "SA2_5DIG16": sa2_5dig,
        "SA2_NAME16": sa2_name,
        "STE_NAME16": "Western Australia",
    }])


def _minimal_events_df(station_id=8002, event_type="frost") -> pd.DataFrame:
    return pd.DataFrame([{
        "station_id": station_id,
        "date": date(2025, 9, 8),
        "event_type": event_type,
        "severity": "light",
        "value": 1.2,
        "threshold": 2.0,
        "confidence": 0.9,
        "data_quality": 0,
        "detected_at": "2025-09-08 06:00:00",
    }])


class _TempProject:
    """Creates a throwaway project_root with config/ and optional files."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "config").mkdir()
        (self.root / "data" / "meta").mkdir(parents=True)
        (self.root / "reports" / "daily").mkdir(parents=True)

    def write_crop_calendars(self, crop_context_cfg: dict | None) -> Path:
        """Write config/crop_calendars.yaml."""
        config = {}
        if crop_context_cfg is not None:
            config["crop_context"] = crop_context_cfg
        path = self.root / "config" / "crop_calendars.yaml"
        with open(path, "w") as f:
            yaml.dump(config, f)
        return path

    def write_crop_context_csv(
        self, rows=None, filename="crop_context_sa2.csv"
    ) -> Path:
        if rows is None:
            rows = _minimal_crop_context_rows()
        path = self.root / "data" / "meta" / filename
        return _write_csv(rows, path)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def _make_generator(
    crop_context_cfg,
    stations_df=None,
    process_date=None,
    csv_rows=None,
    csv_filename="crop_context_sa2.csv",
    write_csv=True,
):
    """Build a DailyReportGenerator with a real temp project_root.

    Args:
        crop_context_cfg: dict for 'crop_context' key (or None to omit).
        stations_df: DataFrame for stations. None → empty.
        process_date: date to process. Defaults to 2025-09-08.
        csv_rows: rows for the crop context CSV. None → default minimal rows.
        csv_filename: CSV filename under data/meta/.
        write_csv: whether to write the CSV.
    Returns:
        (generator, _TempProject).
    """
    from src.agents.insight_publisher.report_generator import (
        DailyReportGenerator,
    )

    project = _TempProject()
    csv_path = project.root / "data" / "meta" / csv_filename

    # Write config with the CSV path embedded
    cfg_copy = None
    if crop_context_cfg is not None:
        cfg_copy = dict(crop_context_cfg)
        cfg_copy.setdefault("path", str(csv_path))
    project.write_crop_calendars(cfg_copy)

    if write_csv:
        project.write_crop_context_csv(rows=csv_rows, filename=csv_filename)

    if process_date is None:
        process_date = date(2025, 9, 8)

    with (
        patch.object(DailyReportGenerator, "_load_station_metadata"),
        patch.object(DailyReportGenerator, "_load_seasonal_context"),
    ):
        gen = DailyReportGenerator.__new__(DailyReportGenerator)
        gen.date = process_date
        gen.verbose = False
        gen.project_root = project.root
        gen.data_dir = project.root / "data"
        gen.output_dir = project.root / "reports" / "daily"
        gen.event_log_path = (
            project.root / "data" / "derived" / "event_log.csv"
        )
        gen.stations_path = (
            project.root / "data" / "meta" / "wheatbelt_stations.csv"
        )
        gen.stations_df = (
            stations_df if stations_df is not None else pd.DataFrame()
        )
        gen.seasonal_context = {}
        gen._crop_context_lookup = DailyReportGenerator._load_crop_context(gen)

    return gen, project


# ---------------------------------------------------------------------------
# Tests: disabled
# ---------------------------------------------------------------------------

class TestPublisherCropContextDisabled(unittest.TestCase):

    def setUp(self):
        self._projects = []

    def tearDown(self):
        for p in self._projects:
            p.cleanup()

    def _gen(self, **kw):
        gen, proj = _make_generator(**kw)
        self._projects.append(proj)
        return gen

    def test_disabled_lookup_is_none(self):
        gen = self._gen(crop_context_cfg=None)
        self.assertIsNone(gen._crop_context_lookup)

    def test_disabled_section_returns_empty_string(self):
        gen = self._gen(crop_context_cfg=None)
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        self.assertEqual(section, "")

    def test_explicit_disabled_flag(self):
        gen = self._gen(crop_context_cfg={"enabled": False})
        self.assertIsNone(gen._crop_context_lookup)
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        self.assertEqual(section, "")


# ---------------------------------------------------------------------------
# Tests: enabled + missing CSV
# ---------------------------------------------------------------------------

class TestPublisherCropContextMissing(unittest.TestCase):

    def setUp(self):
        self._projects = []

    def tearDown(self):
        for p in self._projects:
            p.cleanup()

    def _gen(self, **kw):
        gen, proj = _make_generator(**kw)
        self._projects.append(proj)
        return gen

    def test_missing_not_required_lookup_is_none(self):
        gen = self._gen(
            crop_context_cfg={"enabled": True, "required": False},
            write_csv=False,
        )
        self.assertIsNone(gen._crop_context_lookup)

    def test_missing_not_required_section_empty(self):
        gen = self._gen(
            crop_context_cfg={"enabled": True, "required": False},
            write_csv=False,
        )
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        self.assertEqual(section, "")

    def test_missing_required_raises_file_not_found(self):
        from src.agents.insight_publisher.report_generator import (
            DailyReportGenerator,
        )

        project = _TempProject()
        self._projects.append(project)
        csv_path = project.root / "data" / "meta" / "missing.csv"
        # Do NOT write the CSV
        project.write_crop_calendars({
            "enabled": True,
            "required": True,
            "path": str(csv_path),
        })

        with (
            patch.object(DailyReportGenerator, "_load_station_metadata"),
            patch.object(DailyReportGenerator, "_load_seasonal_context"),
        ):
            gen = DailyReportGenerator.__new__(DailyReportGenerator)
            gen.date = date(2025, 9, 8)
            gen.verbose = False
            gen.project_root = project.root
            gen.data_dir = project.root / "data"
            gen.output_dir = project.root / "reports" / "daily"
            gen.event_log_path = (
                project.root / "data" / "derived" / "event_log.csv"
            )
            gen.stations_path = project.root / "data" / "meta" / "stations.csv"
            gen.stations_df = pd.DataFrame()
            gen.seasonal_context = {}

        with self.assertRaises(FileNotFoundError):
            DailyReportGenerator._load_crop_context(gen)


# ---------------------------------------------------------------------------
# Tests: enabled + valid CSV
# ---------------------------------------------------------------------------

class TestPublisherCropContextEnabled(unittest.TestCase):

    def setUp(self):
        self._projects = []

    def tearDown(self):
        for p in self._projects:
            p.cleanup()

    def _gen(self, stations_df=None, csv_rows=None):
        if stations_df is None:
            stations_df = _minimal_stations_df()
        gen, proj = _make_generator(
            crop_context_cfg={"enabled": True, "required": False},
            stations_df=stations_df,
            csv_rows=csv_rows,
        )
        self._projects.append(proj)
        return gen

    def test_section_contains_abs_header(self):
        gen = self._gen()
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        self.assertIn("ABS Crop Context", section)
        self.assertIn("2020-21", section)

    def test_section_contains_historical_caveat(self):
        gen = self._gen()
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        self.assertIn("Historical ABS census estimates", section)
        self.assertIn("not current-year", section)
        self.assertIn("Does not change risk ratings", section)

    def test_section_contains_crop_name(self):
        gen = self._gen()
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        self.assertIn("Wheat", section)

    def test_section_shows_area_share_percentage(self):
        gen = self._gen()
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        # area_share=0.60 → "60%"
        self.assertIn("60%", section)

    def test_sub_one_percent_area_share_shows_less_than_one(self):
        """area_share=0.003 → '<1%' not '0%'."""
        rows = [{**_minimal_crop_context_rows()[0], "area_share": "0.003"}]
        gen = self._gen(csv_rows=rows)
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        self.assertIn("<1%", section)
        self.assertNotIn("0% area share", section)

    def test_section_shows_sa2_name(self):
        gen = self._gen()
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        self.assertIn("Wheatlands East", section)

    def test_empty_events_returns_empty_section(self):
        gen = self._gen()
        section = gen._generate_abs_crop_context_section(pd.DataFrame())
        self.assertEqual(section, "")

    def test_station_not_in_metadata_returns_empty_section(self):
        """Station in events but not in stations_df → no SA2 → empty."""
        gen = self._gen(
            stations_df=_minimal_stations_df(station_id=9999),
        )
        events = _minimal_events_df(station_id=8002)
        section = gen._generate_abs_crop_context_section(events)
        self.assertEqual(section, "")

    def test_no_sa2_match_in_crop_context_returns_empty(self):
        """Station's SA2_5DIG16 has no matching crop context rows → empty."""
        gen = self._gen(
            stations_df=_minimal_stations_df(sa2_5dig="99999"),
        )
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        self.assertEqual(section, "")

    def test_no_sa2_column_in_stations_df_returns_empty(self):
        """stations_df without SA2_5DIG16 column → empty."""
        stations_no_sa2 = pd.DataFrame([{
            "station_id": 8002,
            "Station name": "TEST",
        }])
        gen = self._gen(stations_df=stations_no_sa2)
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        self.assertEqual(section, "")

    def test_multiple_crops_sorted_by_area_share_descending(self):
        rows = [
            {
                **_minimal_crop_context_rows()[0],
                "crop": "barley",
                "area_share": "0.25",
            },
            {
                **_minimal_crop_context_rows()[0],
                "crop": "wheat",
                "area_share": "0.60",
            },
        ]
        gen = self._gen(csv_rows=rows)
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        wheat_pos = section.find("Wheat")
        barley_pos = section.find("Barley")
        self.assertGreater(wheat_pos, 0, "Wheat not found in section")
        self.assertGreater(barley_pos, 0, "Barley not found in section")
        self.assertLess(
            wheat_pos,
            barley_pos,
            "Wheat (60%) should appear before Barley (25%)",
        )

    def test_no_events_with_station_id_returns_empty(self):
        """Events DataFrame missing station_id column → empty."""
        gen = self._gen()
        events = pd.DataFrame([{"event_type": "frost"}])
        section = gen._generate_abs_crop_context_section(events)
        self.assertEqual(section, "")


# ---------------------------------------------------------------------------
# Tests: field types and suppressed values
# ---------------------------------------------------------------------------

class TestPublisherCropContextFieldTypes(unittest.TestCase):

    def setUp(self):
        self._projects = []

    def tearDown(self):
        for p in self._projects:
            p.cleanup()

    def _load_records(self, rows=None):
        gen, proj = _make_generator(
            crop_context_cfg={"enabled": True, "required": False},
            stations_df=_minimal_stations_df(),
            csv_rows=rows,
        )
        self._projects.append(proj)
        return gen._crop_context_lookup.records

    def test_rse_fields_are_strings_not_coerced(self):
        records = self._load_records()
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec.area_rse, "^")
        self.assertEqual(rec.production_rse, "np")
        self.assertIsInstance(rec.area_rse, str)
        self.assertIsInstance(rec.production_rse, str)

    def test_null_production_treated_as_missing_not_zero(self):
        records = self._load_records()
        rec = records[0]
        # production_t='' in the default row → None, not 0
        self.assertIsNone(rec.production_t)

    def test_sa2_code_field_is_string(self):
        records = self._load_records()
        rec = records[0]
        self.assertIsInstance(rec.sa2_code, str)
        self.assertEqual(rec.sa2_code, "501011001")

    def test_station_sa2_5dig16_is_string(self):
        records = self._load_records()
        rec = records[0]
        self.assertIsInstance(rec.station_sa2_5dig16, str)
        self.assertEqual(rec.station_sa2_5dig16, "50101")

    def test_suppressed_area_share_none_ranks_after_known(self):
        """area_share='' → None → ranks after crops with known share."""
        rows = [
            {
                **_minimal_crop_context_rows()[0],
                "crop": "canola",
                "area_share": "",
            },
            {
                **_minimal_crop_context_rows()[0],
                "crop": "wheat",
                "area_share": "0.60",
            },
        ]
        gen, proj = _make_generator(
            crop_context_cfg={"enabled": True, "required": False},
            stations_df=_minimal_stations_df(),
            csv_rows=rows,
        )
        self._projects.append(proj)
        section = gen._generate_abs_crop_context_section(_minimal_events_df())
        wheat_pos = section.find("Wheat")
        canola_pos = section.find("Canola")
        self.assertGreater(wheat_pos, 0, "Wheat not found")
        self.assertGreater(canola_pos, 0, "Canola not found")
        self.assertLess(
            wheat_pos,
            canola_pos,
            "Wheat (60%) should appear before Canola (suppressed)",
        )
        self.assertIn("area share not available", section)

    def test_suppressed_area_share_is_none_not_zero(self):
        """area_share='' must give None, not 0.0."""
        rows = [{**_minimal_crop_context_rows()[0], "area_share": ""}]
        records = self._load_records(rows=rows)
        rec = records[0]
        self.assertIsNone(rec.area_share)


if __name__ == "__main__":
    unittest.main()
