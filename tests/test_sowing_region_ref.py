"""Tests for the region_reference.csv consumer (sd_region validation gate).

region_ref.py loads crop-forecast's vendored region_reference.csv (the BEN Agri
SD region_code source of truth) and validates that any emitted sd_region is a
known member, so codes cannot drift (Phase 2, contract swp-1; spec 5.9 / 8).
"""

import csv
import tempfile
import unittest
from pathlib import Path

from src.sowing.region_ref import (
    REQUIRED_COLUMNS,
    UnknownRegionError,
    assert_sd_known,
    load_region_reference,
    sd_region_codes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDORED_REFERENCE = REPO_ROOT / "data" / "meta" / "region_reference.csv"

WA_BEN_AGRI_SDS = {
    "WA_SOUTH_EASTERN",
    "WA_LOWER_GREAT_SOUTHERN",
    "WA_UPPER_GREAT_SOUTHERN",
    "WA_MIDLANDS",
    "WA_CENTRAL",
    "WA_SOUTH_WEST",
    "WA_PERTH",
}


def _row(region_code, state, region_name, region_level):
    return {
        "region_code": region_code,
        "state": state,
        "region_name": region_name,
        "region_level": region_level,
    }


def _write_reference(rows, path, fieldnames=REQUIRED_COLUMNS):
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestLoadRegionReference(unittest.TestCase):
    def test_returns_set_of_region_codes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ref.csv"
            _write_reference(
                [
                    _row("WA_MIDLANDS", "WA", "Midlands", "sd"),
                    _row("SA_EYRE", "SA", "Eyre", "sd"),
                    _row("WA", "WA", "Western Australia", "state_total"),
                    _row("AUS", "AUS", "Australia", "national"),
                ],
                p,
            )
            self.assertEqual(
                load_region_reference(p),
                {"WA_MIDLANDS", "SA_EYRE", "WA", "AUS"},
            )

    def test_missing_file_raises_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            load_region_reference(Path("/nonexistent/region_reference.csv"))

    def test_missing_required_column_raises_valueerror(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ref.csv"
            _write_reference(
                [{"region_code": "WA_MIDLANDS", "state": "WA"}],
                p,
                fieldnames=["region_code", "state"],
            )
            with self.assertRaises(ValueError):
                load_region_reference(p)

    def test_empty_reference_raises_valueerror(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ref.csv"
            _write_reference([], p)
            with self.assertRaises(ValueError):
                load_region_reference(p)


class TestSdRegionCodes(unittest.TestCase):
    def _fixture(self, p):
        _write_reference(
            [
                _row("WA_MIDLANDS", "WA", "Midlands", "sd"),
                _row("WA_PERTH", "WA", "Perth", "sd"),
                _row("SA_EYRE", "SA", "Eyre", "sd"),
                _row("WA", "WA", "Western Australia", "state_total"),
                _row("AUS", "AUS", "Australia", "national"),
            ],
            p,
        )

    def test_filters_to_sd_level_and_state(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ref.csv"
            self._fixture(p)
            self.assertEqual(
                sd_region_codes(p, state="WA"), {"WA_MIDLANDS", "WA_PERTH"}
            )

    def test_sd_level_across_all_states_when_state_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ref.csv"
            self._fixture(p)
            self.assertEqual(
                sd_region_codes(p), {"WA_MIDLANDS", "WA_PERTH", "SA_EYRE"}
            )

    def test_vendored_wa_sd_codes_are_the_seven_ben_agri_sds(self):
        self.assertEqual(sd_region_codes(VENDORED_REFERENCE, state="WA"), WA_BEN_AGRI_SDS)


class TestAssertSdKnown(unittest.TestCase):
    def test_known_code_passes(self):
        assert_sd_known("WA_MIDLANDS", {"WA_MIDLANDS", "WA_CENTRAL"})

    def test_unknown_code_raises_unknownregionerror(self):
        with self.assertRaises(UnknownRegionError):
            assert_sd_known("WA_KIMBERLEY", {"WA_MIDLANDS"})

    def test_unknownregionerror_is_a_valueerror(self):
        self.assertTrue(issubclass(UnknownRegionError, ValueError))


class TestVendoredReference(unittest.TestCase):
    def test_vendored_file_contains_all_seven_wa_ben_agri_sds(self):
        codes = load_region_reference(VENDORED_REFERENCE)
        self.assertTrue(
            WA_BEN_AGRI_SDS.issubset(codes),
            f"missing from vendored region_reference.csv: {WA_BEN_AGRI_SDS - codes}",
        )


if __name__ == "__main__":
    unittest.main()
