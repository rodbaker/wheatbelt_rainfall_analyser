"""Tests for sowing-evidence derivation: break_percentile_vs_history (R3).

Percentile is ranked against the SD's OWN historical break DOYs (built first via
the SD rollup), never rolled up from SA2 percentiles. Below MIN_HISTORY_YEARS the
derivation is still emitted but flagged insufficient (-> window_confidence low).
"""

import math
import unittest

from src.sowing.evidence import (
    MIN_HISTORY_YEARS,
    break_percentile_vs_history,
)


class TestBreakPercentileVsHistory(unittest.TestCase):
    def test_later_than_all_history_is_100(self):
        pct, n, ok = break_percentile_vs_history(160, [120, 130, 140, 150])
        self.assertAlmostEqual(pct, 100.0)
        self.assertEqual(n, 4)
        self.assertFalse(ok)  # 4 < MIN_HISTORY_YEARS

    def test_earlier_than_all_history_is_0(self):
        pct, _, _ = break_percentile_vs_history(100, [120, 130, 140, 150])
        self.assertAlmostEqual(pct, 0.0)

    def test_mid_rank_uses_strict_less_than(self):
        # 3 of 5 strictly below 145 -> 60.0 (house convention: ties don't lift rank)
        pct, n, _ = break_percentile_vs_history(145, [120, 130, 140, 150, 160])
        self.assertAlmostEqual(pct, 60.0)
        self.assertEqual(n, 5)

    def test_min_sample_boundary(self):
        ten = list(range(120, 130))  # 10 values
        _, n, ok = break_percentile_vs_history(150, ten)
        self.assertEqual(n, 10)
        self.assertTrue(ok)
        _, n9, ok9 = break_percentile_vs_history(150, ten[:9])
        self.assertEqual(n9, 9)
        self.assertFalse(ok9)

    def test_none_values_ignored(self):
        pct, n, _ = break_percentile_vs_history(145, [120, None, 140, None, 160])
        self.assertEqual(n, 3)
        self.assertAlmostEqual(pct, (2 / 3) * 100.0)  # 120,140 < 145

    def test_empty_history_is_nan_and_insufficient(self):
        pct, n, ok = break_percentile_vs_history(150, [])
        self.assertTrue(math.isnan(pct))
        self.assertEqual(n, 0)
        self.assertFalse(ok)

    def test_min_history_years_is_ten(self):
        self.assertEqual(MIN_HISTORY_YEARS, 10)


if __name__ == "__main__":
    unittest.main()
