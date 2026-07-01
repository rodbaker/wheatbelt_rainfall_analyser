"""End-to-end contract test for sowing_window_area_pressure.csv (swp-1).

Drives the orchestration (scripts/build_sowing_window_pressure.py) over synthetic
fixtures and asserts the export contract: exact swp-1 columns in order, WA-only,
no hectare/delta fields, no neutral rows, and latest + dated archive both written
with identical content. Plus a real-data smoke that the pipeline runs.
"""

import csv
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_sowing_window_pressure as build  # noqa: E402
from src.sowing.evidence import SWP_COLUMNS  # noqa: E402

# the swp-1 contract column order (spec 9), asserted independently of PressureRow
EXPECTED_SWP_COLUMNS = [
    "schema_version", "evidence_id", "generated_at", "rainfall_run_id", "season",
    "season_year", "state", "sd_region", "commodity", "pressure_direction",
    "pressure_band", "counterparty_commodity", "reason_code", "rationale",
    "break_date", "break_status", "break_percentile_vs_history", "window_overlap_days",
    "days_after_latest_viable", "establishment_risk_flag", "guide_source_document",
    "guide_source_year", "window_confidence",
]


def _w(path, fieldnames, rows):
    with open(path, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fieldnames)
        wr.writeheader()
        wr.writerows(rows)


def _make_fixtures(d):
    d = Path(d)
    region_reference = d / "region_reference.csv"
    windows = d / "windows.csv"
    features = d / "features.csv"
    concordance = d / "conc.csv"
    broadacre = d / "broad.csv"

    _w(region_reference, ["region_code", "state", "region_name", "region_level"], [
        {"region_code": "WA_MIDLANDS", "state": "WA", "region_name": "Midlands", "region_level": "sd"},
        {"region_code": "WA", "state": "WA", "region_name": "Western Australia", "region_level": "state_total"},
        {"region_code": "AUS", "state": "AUS", "region_name": "Australia", "region_level": "national"},
    ])
    _w(windows, [
        "state", "sd_region", "rainfall_regime", "commodity", "season_type",
        "earliest_sow_doy", "optimal_start_doy", "optimal_end_doy", "latest_viable_doy",
        "penalty_pct_per_week_late", "late_penalty_note", "source_document",
        "source_year", "confidence"], [
        {"state": "WA", "sd_region": "WA_MIDLANDS", "rainfall_regime": "winter_dominant",
         "commodity": "wheat_incl_durum", "season_type": "winter",
         "earliest_sow_doy": "91", "optimal_start_doy": "111", "optimal_end_doy": "134",
         "latest_viable_doy": "166", "penalty_pct_per_week_late": "",
         "late_penalty_note": "", "source_document": "DPIRD 2026", "source_year": "2026",
         "confidence": "high"},
    ])
    # 10 history years (early breaks ~DOY 125) + a late 2026 break (2026-06-25 ~DOY 176)
    feat_rows = []
    for yr in range(2016, 2026):
        feat_rows.append(dict(season_year=str(yr), state_name="Western Australia",
                              sa2_code="51240", sa2_code_9dig="509021240",
                              autumn_break_date=f"{yr}-05-05", autumn_break_status="on_time"))
    feat_rows.append(dict(season_year="2026", state_name="Western Australia",
                          sa2_code="51240", sa2_code_9dig="509021240",
                          autumn_break_date="2026-06-25", autumn_break_status="late"))
    _w(features, ["season_year", "state_name", "sa2_code", "sa2_code_9dig",
                  "autumn_break_date", "autumn_break_status"], feat_rows)
    _w(concordance, ["SA2_CODE21", "SD_CODE11", "SD_NAME11", "SD_STATE_CODE",
                     "allocation_ratio"], [
        {"SA2_CODE21": "509021240", "SD_CODE11": "525", "SD_NAME11": "Midlands",
         "SD_STATE_CODE": "5", "allocation_ratio": "1.0"}])
    _w(broadacre, ["sa2_code", "broadacre_area_ha"], [
        {"sa2_code": "51240", "broadacre_area_ha": "1000.0"}])
    return dict(features=str(features), concordance=str(concordance),
                broadacre=str(broadacre), windows=str(windows),
                region_reference=str(region_reference))


class TestContractExport(unittest.TestCase):
    def _run(self, d):
        paths = _make_fixtures(d)
        return build.run(out_dir=str(Path(d) / "out"), generated_at="2026-06-09",
                         rainfall_run_id="rain-test", season_year=2026, **paths)

    def test_swp_columns_match_contract(self):
        self.assertEqual(SWP_COLUMNS, EXPECTED_SWP_COLUMNS)

    def test_header_is_exactly_the_contract_in_order(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            _rows, latest, _archive = self._run(d)
            with open(latest, newline="") as fh:
                header = next(csv.reader(fh))
            self.assertEqual(header, EXPECTED_SWP_COLUMNS)

    def test_emits_expected_at_risk_extreme_row(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            rows, latest, _ = self._run(d)
            with open(latest, newline="") as fh:
                out = list(csv.DictReader(fh))
            self.assertEqual(len(out), 1)
            r = out[0]
            self.assertEqual(r["state"], "WA")
            self.assertEqual(r["sd_region"], "WA_MIDLANDS")
            self.assertEqual(r["commodity"], "wheat_incl_durum")
            self.assertEqual(r["pressure_direction"], "at_risk")
            self.assertEqual(r["pressure_band"], "extreme")
            self.assertEqual(r["counterparty_commodity"], "unknown")
            self.assertEqual(r["season"], "2026/27")
            self.assertEqual(float(r["break_percentile_vs_history"]), 100.0)
            self.assertEqual(r["window_confidence"], "high")  # guards pass

    def test_no_hectare_or_neutral(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            _rows, latest, _ = self._run(d)
            with open(latest, newline="") as fh:
                reader = csv.DictReader(fh)
                cols = reader.fieldnames
                out = list(reader)
        banned = ("ha", "delta", "hectare", "area", "value")
        self.assertEqual([c for c in cols if any(b in c.lower() for b in banned)], [])
        self.assertTrue(all(r["pressure_direction"] != "neutral" for r in out))
        self.assertTrue(all(r["state"] == "WA" for r in out))

    def test_latest_and_dated_archive_identical(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            _rows, latest, archive = self._run(d)
            self.assertTrue(Path(latest).exists() and Path(archive).exists())
            self.assertEqual(Path(archive).name,
                             "sowing_window_area_pressure_2026-06-09.csv")
            self.assertEqual(Path(latest).read_text(), Path(archive).read_text())


class TestRealDataSmoke(unittest.TestCase):
    def test_real_build_runs_and_emits_valid_contract(self):
        import logging
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            logging.disable(logging.WARNING)  # silence expected Geraldton warning
            try:
                rows, latest, archive = build.run(
                    out_dir=str(Path(d) / "out"),
                    generated_at="2026-06-09", rainfall_run_id="rain-real",
                )
            finally:
                logging.disable(logging.NOTSET)
            with open(latest, newline="") as fh:
                header = next(csv.reader(fh))
            self.assertEqual(header, EXPECTED_SWP_COLUMNS)
            # every emitted row is WA, at_risk, no hectares (by construction)
            with open(latest, newline="") as fh:
                for r in csv.DictReader(fh):
                    self.assertEqual(r["state"], "WA")
                    self.assertIn(r["pressure_direction"], {"at_risk", "favoured"})


if __name__ == "__main__":
    unittest.main()
