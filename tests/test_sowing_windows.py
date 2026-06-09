"""Tests for the sowing_windows loader/validator (keyed at BEN Agri SD grain).

Per D2 the windows are keyed by sd_region (crop-forecast region_code), NOT agzone
(spec 7.1's agzone grain is overridden because agzone->SA2 is missing in v1).
Validation enforces the spec 8 acceptance: DOY ordering and vocab, plus the D2
sd_region gate against region_reference.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from src.sowing.windows import (
    REQUIRED_COLUMNS,
    SowingWindow,
    load_sowing_windows,
)

VALID_SD_REGIONS = {"WA_MIDLANDS", "WA_CENTRAL", "WA_SOUTH_EASTERN"}


def _row(**overrides):
    row = {
        "state": "WA",
        "sd_region": "WA_MIDLANDS",
        "rainfall_regime": "winter_dominant",
        "commodity": "barley",
        "season_type": "winter",
        "earliest_sow_doy": "111",      # ~Apr 21
        "optimal_start_doy": "121",     # ~May 1
        "optimal_end_doy": "152",       # ~Jun 1
        "latest_viable_doy": "166",     # ~Jun 15
        "penalty_pct_per_week_late": "2.5",
        "late_penalty_note": "yield falls sharply after mid-June",
        "source_document": "DPIRD 2026 WA Crop Sowing Guide",
        "source_year": "2025",
        "confidence": "high",
    }
    row.update(overrides)
    return row


def _write(rows, path, fieldnames=REQUIRED_COLUMNS):
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestLoadSowingWindows(unittest.TestCase):
    def _load(self, rows, **kw):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sowing_windows_wa.csv"
            _write(rows, p)
            return load_sowing_windows(p, valid_sd_regions=VALID_SD_REGIONS, **kw)

    def test_loads_valid_row_with_parsed_types(self):
        (w,) = self._load([_row()])
        self.assertIsInstance(w, SowingWindow)
        self.assertEqual(w.sd_region, "WA_MIDLANDS")
        self.assertEqual(w.commodity, "barley")
        self.assertEqual(w.earliest_sow_doy, 111)
        self.assertEqual(w.latest_viable_doy, 166)
        self.assertEqual(w.penalty_pct_per_week_late, 2.5)
        self.assertEqual(w.source_year, 2025)

    def test_blank_penalty_becomes_none(self):
        (w,) = self._load([_row(penalty_pct_per_week_late="")])
        self.assertIsNone(w.penalty_pct_per_week_late)

    def test_header_only_returns_empty_list(self):
        self.assertEqual(self._load([]), [])

    def test_missing_required_column_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "w.csv"
            _write([{"state": "WA"}], p, fieldnames=["state"])
            with self.assertRaises(ValueError):
                load_sowing_windows(p, valid_sd_regions=VALID_SD_REGIONS)

    def test_doy_ordering_violation_raises(self):
        with self.assertRaises(ValueError):
            self._load([_row(optimal_start_doy="160", optimal_end_doy="152")])

    def test_doy_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            self._load([_row(latest_viable_doy="400")])

    def test_bad_season_type_raises(self):
        with self.assertRaises(ValueError):
            self._load([_row(season_type="autumn")])

    def test_bad_rainfall_regime_raises(self):
        with self.assertRaises(ValueError):
            self._load([_row(rainfall_regime="tropical_monsoon")])

    def test_bad_confidence_raises(self):
        with self.assertRaises(ValueError):
            self._load([_row(confidence="certain")])

    def test_non_wa_state_raises(self):
        with self.assertRaises(ValueError):
            self._load([_row(state="SA")])

    def test_unknown_sd_region_raises(self):
        with self.assertRaises(ValueError):
            self._load([_row(sd_region="WA_PERTH")])  # not in VALID_SD_REGIONS fixture


if __name__ == "__main__":
    unittest.main()
