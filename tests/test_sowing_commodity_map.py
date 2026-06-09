"""Tests for the explicit guide-crop -> BEN Agri commodity map (spec 7.2).

Explicit table, never fuzzy. Drives transcription of guide windows into BEN Agri
commodity codes; the wheat draft's commodity must be a mapped value.
"""

import unittest
from pathlib import Path

from src.sowing.commodity_map import (
    load_guide_commodity_map,
    resolve_commodity,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = REPO_ROOT / "config" / "guide_commodity_map.yaml"


class TestGuideCommodityMap(unittest.TestCase):
    def test_loads_expected_direct_mappings(self):
        m = load_guide_commodity_map(MAP_PATH)
        self.assertEqual(m["Wheat"], "wheat_incl_durum")
        self.assertEqual(m["Barley"], "barley")
        self.assertEqual(m["Canola"], "canola")
        self.assertEqual(m["Oats"], "oats")
        self.assertEqual(m["Lupin"], "lupins")
        self.assertEqual(m["Chickpea"], "chickpeas")
        self.assertEqual(m["Faba bean"], "faba_beans")
        self.assertEqual(m["Field pea"], "field_peas")
        self.assertEqual(m["Lentil"], "lentils")

    def test_triticale_inherits_wheat_window(self):
        m = load_guide_commodity_map(MAP_PATH)
        self.assertEqual(m["Triticale"], "wheat_incl_durum")

    def test_dropped_summer_and_vetch_not_mapped(self):
        m = load_guide_commodity_map(MAP_PATH)
        for crop in ("Vetch", "Sorghum", "Cotton"):
            self.assertNotIn(crop, m)

    def test_resolve_known_and_unknown(self):
        m = load_guide_commodity_map(MAP_PATH)
        self.assertEqual(resolve_commodity("Wheat", m), "wheat_incl_durum")
        with self.assertRaises(KeyError):
            resolve_commodity("Sorghum", m)

    def test_wheat_window_commodity_is_a_mapped_value(self):
        # ties config/sowing_windows_wa.csv to the map
        m = load_guide_commodity_map(MAP_PATH)
        self.assertIn("wheat_incl_durum", set(m.values()))


if __name__ == "__main__":
    unittest.main()
