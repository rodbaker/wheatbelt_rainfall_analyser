"""Tests for extract_clum_commodity_areas.py."""
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import extract_clum_commodity_areas as eca

ZIP_PATH = REPO_ROOT / "data/meta/shapefiles/clum_commodities_2023.zip"
EXPECTED_FEATURES = 176_054
AREA_TOLERANCE_HA = 1.0


@unittest.skipUnless(ZIP_PATH.exists(), "CLUM zip not present — skipping integration tests")
class TestClumExtraction(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.gdf = eca.load_shapefile(ZIP_PATH)
        cls.df = eca.aggregate(cls.gdf)

    def test_feature_count(self):
        self.assertEqual(len(self.gdf), EXPECTED_FEATURES,
                         f"Expected {EXPECTED_FEATURES:,} features, got {len(self.gdf):,}")

    def test_required_fields_present(self):
        for field in eca.REQUIRED_FIELDS:
            self.assertIn(field, self.gdf.columns, f"Missing field: {field}")

    def test_area_conservation(self):
        source_total = self.gdf["Area_ha"].sum()
        grouped_total = self.df["area_ha"].sum()
        diff = abs(source_total - grouped_total)
        self.assertLess(diff, AREA_TOLERANCE_HA,
                        f"Area mismatch: {diff:.4f} ha exceeds tolerance {AREA_TOLERANCE_HA} ha")

    def test_output_columns(self):
        expected = {"state", "broad_type", "commodity", "source_year", "feature_count", "area_ha"}
        self.assertEqual(set(self.df.columns), expected)

    def test_broad_type_animals_dominates(self):
        by_broad = self.df.groupby("broad_type")["area_ha"].sum()
        self.assertIn("Animals", by_broad.index, "Broad_type 'Animals' not found")
        top = by_broad.idxmax()
        self.assertEqual(top, "Animals",
                         f"Expected 'Animals' to dominate by area, got '{top}'")

    def test_cereals_includes_wheat(self):
        cereals = self.df[self.df["broad_type"] == "Cereals"]
        self.assertGreater(len(cereals), 0, "No Cereals rows found")
        commodities = cereals["commodity"].str.lower().tolist()
        self.assertTrue(any("wheat" in c for c in commodities),
                        f"No wheat in Cereals commodities: {commodities[:10]}")

    def test_cereals_includes_barley(self):
        cereals = self.df[self.df["broad_type"] == "Cereals"]
        commodities = cereals["commodity"].str.lower().tolist()
        self.assertTrue(any("barley" in c for c in commodities),
                        f"No barley in Cereals commodities: {commodities[:10]}")

    def test_oilseeds_includes_canola(self):
        oilseeds = self.df[self.df["broad_type"] == "Oilseeds"]
        self.assertGreater(len(oilseeds), 0, "No Oilseeds rows found")
        commodities = oilseeds["commodity"].str.lower().tolist()
        self.assertTrue(any("canola" in c for c in commodities),
                        f"No canola in Oilseeds commodities: {commodities[:10]}")

    def test_pulses_present(self):
        pulses = self.df[self.df["broad_type"] == "Pulses"]
        self.assertGreater(len(pulses), 0, "No Pulses rows found")
        commodities = pulses["commodity"].str.lower().tolist()
        pulse_crops = ["lentil", "chickpea", "lupin", "field pea"]
        found = [c for c in pulse_crops if any(c in com for com in commodities)]
        self.assertGreater(len(found), 0,
                           f"None of {pulse_crops} found in Pulses: {commodities[:10]}")

    def test_no_negative_area(self):
        neg = self.df[self.df["area_ha"] < 0]
        self.assertEqual(len(neg), 0, f"{len(neg)} rows with negative area_ha")

    def test_feature_count_column_positive(self):
        self.assertTrue((self.df["feature_count"] > 0).all(),
                        "Some rows have zero feature_count")

    def test_write_summary_returns_string(self):
        with tempfile.TemporaryDirectory() as td:
            md = eca.write_summary(self.gdf, self.df, ZIP_PATH)
        self.assertIsInstance(md, str)
        self.assertIn("CLUM Commodities 2023", md)
        self.assertIn("context only", md)


if __name__ == "__main__":
    unittest.main()
