"""Tests for runtime crop context CSV loader helpers."""

import csv
import tempfile
import unittest
from pathlib import Path

from src.common.crop_context_loader import (
    REQUIRED_COLUMNS,
    CropContextLookup,
    crop_context_exists,
    load_crop_context,
    load_crop_context_lookup,
)


def _row(**overrides):
    row = {
        "sa2_code": "012345678",
        "station_sa2_5dig16": "01234",
        "sa2_name": "Test SA2",
        "state": "Western Australia",
        "financial_year": "2020-21",
        "crop": "wheat",
        "area_ha": "100.5",
        "production_t": "",
        "yield_t_ha": "2.2",
        "area_share": "0.75",
        "area_rse": "^",
        "production_rse": "np",
        "yield_rse": "",
        "source_dataset": "ABS Agricultural Census 2020-21",
        "source_commodity_area": "AGCEREAL_AHAWHT_F",
        "source_commodity_production": "AGCEREAL_ATOWHT_F",
        "source_commodity_yield": "WHEAT_YIELD_F",
        "boundary_status": "matched",
        "notes": "",
    }
    row.update(overrides)
    return row


def _write_csv(rows, columns=None) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        suffix=".csv", delete=False, mode="w", newline=""
    )
    path = Path(tmp.name)
    with tmp:
        writer = csv.DictWriter(tmp, fieldnames=columns or REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


class TestCropContextLoader(unittest.TestCase):

    def tearDown(self):
        for path in getattr(self, "_paths", []):
            if path.exists():
                path.unlink()

    def _track(self, path):
        self._paths = getattr(self, "_paths", [])
        self._paths.append(path)
        return path

    def test_load_crop_context_preserves_code_and_rse_strings(self):
        path = self._track(_write_csv([_row()]))

        record = load_crop_context(path)[0]

        self.assertEqual(record.sa2_code, "012345678")
        self.assertEqual(record.station_sa2_5dig16, "01234")
        self.assertEqual(record.area_rse, "^")
        self.assertEqual(record.production_rse, "np")
        self.assertEqual(record.yield_rse, "")

    def test_load_crop_context_converts_numeric_fields_and_blanks(self):
        path = self._track(_write_csv([_row()]))

        record = load_crop_context(path)[0]

        self.assertAlmostEqual(record.area_ha, 100.5)
        self.assertIsNone(record.production_t)
        self.assertAlmostEqual(record.yield_t_ha, 2.2)
        self.assertAlmostEqual(record.area_share, 0.75)

    def test_load_crop_context_missing_file(self):
        missing = Path(tempfile.gettempdir()) / "missing_crop_context_sa2.csv"
        if missing.exists():
            missing.unlink()

        with self.assertRaises(FileNotFoundError):
            load_crop_context(missing)

    def test_crop_context_exists(self):
        path = self._track(_write_csv([_row()]))

        self.assertTrue(crop_context_exists(path))
        self.assertFalse(crop_context_exists(path.with_name("missing.csv")))

    def test_load_crop_context_rejects_missing_columns(self):
        columns = [
            column for column in REQUIRED_COLUMNS if column != "area_rse"
        ]
        row = _row()
        row.pop("area_rse")
        path = self._track(_write_csv([row], columns=columns))

        with self.assertRaisesRegex(ValueError, "area_rse"):
            load_crop_context(path)

    def test_load_crop_context_rejects_invalid_numeric_values(self):
        path = self._track(_write_csv([_row(area_ha="not-a-number")]))

        with self.assertRaisesRegex(ValueError, "area_ha"):
            load_crop_context(path)

    def test_lookup_by_full_sa2_code_and_station_sa2(self):
        path = self._track(
            _write_csv(
                [
                    _row(crop="wheat", area_share="0.75"),
                    _row(crop="barley", area_share="0.25"),
                    _row(
                        sa2_code="087654321",
                        station_sa2_5dig16="08765",
                        crop="canola",
                        area_share="0.4",
                    ),
                ]
            )
        )

        lookup = load_crop_context_lookup(path)

        wheat = lookup.get_by_sa2_crop("012345678", "wheat")
        self.assertIsNotNone(wheat)
        self.assertEqual(wheat.station_sa2_5dig16, "01234")
        station_crops = lookup.crops_for_station_sa2("01234")
        self.assertEqual(set(station_crops), {"wheat", "barley"})
        self.assertEqual(
            [record.crop for record in lookup.for_state("Western Australia")],
            ["wheat", "barley", "canola"],
        )

    def test_lookup_returns_none_when_absent(self):
        path = self._track(_write_csv([_row()]))
        lookup = CropContextLookup([load_crop_context(path)[0]])

        self.assertIsNone(lookup.get_by_sa2_crop("999999999", "wheat"))
        self.assertEqual(lookup.for_station_sa2("99999"), [])

    def test_lookup_requires_financial_year_when_match_is_ambiguous(self):
        path = self._track(
            _write_csv(
                [
                    _row(financial_year="2020-21"),
                    _row(financial_year="2021-22"),
                ]
            )
        )
        lookup = load_crop_context_lookup(path)

        with self.assertRaisesRegex(ValueError, "financial_year"):
            lookup.get_by_sa2_crop("012345678", "wheat")

        record = lookup.get_by_sa2_crop(
            "012345678", "wheat", financial_year="2021-22"
        )
        self.assertEqual(record.financial_year, "2021-22")


if __name__ == "__main__":
    unittest.main()
