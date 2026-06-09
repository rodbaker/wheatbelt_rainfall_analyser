"""Tests for sowing-evidence derivation: break_percentile_vs_history (R3).

Percentile is ranked against the SD's OWN historical break DOYs (built first via
the SD rollup), never rolled up from SA2 percentiles. Below MIN_HISTORY_YEARS the
derivation is still emitted but flagged insufficient (-> window_confidence low).
"""

import dataclasses
import math
import unittest

from src.sowing.crosswalk import SdBreak
from src.sowing.evidence import (
    EXTREME_MARGIN_DAYS,
    EXTREME_PERCENTILE,
    MIN_HISTORY_YEARS,
    PressureRow,
    break_percentile_vs_history,
    generate_pressure_rows,
    season_label,
)
from src.sowing.windows import SowingWindow


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


# --- evidence row generation ------------------------------------------------

def _sd_break(break_doy, *, sd="WA_MIDLANDS", year=2026, coverage_ok=True, status=None):
    from src.sowing.crosswalk import classify_break_status

    return SdBreak(
        sd_region=sd,
        season_year=year,
        break_doy=float(break_doy),
        break_status=status or classify_break_status(break_doy),
        coverage=0.9 if coverage_ok else 0.3,
        coverage_ok=coverage_ok,
        n_sa2_eligible=5,
        n_sa2_total=5,
    )


def _window(commodity="barley", *, sd="WA_MIDLANDS", source_year=2025, confidence="high",
            earliest=111, opt_start=121, opt_end=152, latest=166):
    return SowingWindow(
        state="WA",
        sd_region=sd,
        rainfall_regime="winter_dominant",
        commodity=commodity,
        season_type="winter",
        earliest_sow_doy=earliest,
        optimal_start_doy=opt_start,
        optimal_end_doy=opt_end,
        latest_viable_doy=latest,
        penalty_pct_per_week_late=2.0,
        late_penalty_note="",
        source_document="DPIRD 2026 WA Crop Sowing Guide",
        source_year=source_year,
        confidence=confidence,
    )


def _gen(sd_breaks, windows, history_by_sd=None, *, generated_at="2026-06-09",
         rainfall_run_id="rain-2026-06-09"):
    return generate_pressure_rows(
        sd_breaks, windows, history_by_sd or {},
        generated_at=generated_at, rainfall_run_id=rainfall_run_id,
    )


class TestSeasonLabel(unittest.TestCase):
    def test_winter_convention(self):
        self.assertEqual(season_label(2026), "2026/27")
        self.assertEqual(season_label(1999), "1999/00")


class TestGeneratePressureRows(unittest.TestCase):
    def test_in_time_break_emits_no_row(self):
        # break at/before optimal_start -> in time -> no pressure, no row
        rows = _gen([_sd_break(115)], [_window(opt_start=121)])
        self.assertEqual(rows, [])

    def test_no_window_for_commodity_emits_nothing(self):
        # national-safety gating: no guide loaded for this sd/commodity
        rows = _gen([_sd_break(170, sd="WA_CENTRAL")], [_window(sd="WA_MIDLANDS")])
        self.assertEqual(rows, [])

    def test_late_break_emits_at_risk_row(self):
        (row,) = _gen([_sd_break(160)], [_window()])
        self.assertIsInstance(row, PressureRow)
        self.assertEqual(row.pressure_direction, "at_risk")
        self.assertEqual(row.reason_code, "season_break_forced_switch")
        self.assertEqual(row.commodity, "barley")
        self.assertEqual(row.sd_region, "WA_MIDLANDS")
        self.assertEqual(row.state, "WA")
        self.assertEqual(row.schema_version, "swp-1")

    def test_band_low_inside_optimal_late(self):
        (row,) = _gen([_sd_break(148)], [_window(opt_start=121, opt_end=152)])
        self.assertEqual(row.pressure_band, "low")

    def test_band_medium_between_optimal_end_and_latest_viable(self):
        (row,) = _gen([_sd_break(160)], [_window(opt_end=152, latest=166)])
        self.assertEqual(row.pressure_band, "medium")

    def test_band_high_past_latest_viable_within_margin(self):
        (row,) = _gen([_sd_break(170)], [_window(latest=166)])  # 170 <= 166+margin
        self.assertEqual(row.pressure_band, "high")

    def test_band_extreme_well_past_and_late_tail(self):
        # break well past latest_viable AND percentile in the late tail
        hist = {"WA_MIDLANDS": [120, 125, 130, 135, 140]}  # all earlier -> pct 100
        (row,) = _gen([_sd_break(166 + EXTREME_MARGIN_DAYS + 1)], [_window(latest=166)], hist)
        self.assertEqual(row.pressure_band, "extreme")
        self.assertGreaterEqual(row.break_percentile_vs_history, EXTREME_PERCENTILE)

    def test_well_past_but_not_late_tail_is_high_not_extreme(self):
        hist = {"WA_MIDLANDS": [200, 205, 210]}  # all later -> pct 0
        (row,) = _gen([_sd_break(166 + EXTREME_MARGIN_DAYS + 1)], [_window(latest=166)], hist)
        self.assertEqual(row.pressure_band, "high")

    def test_direction_never_neutral(self):
        rows = _gen(
            [_sd_break(160, sd="WA_MIDLANDS"), _sd_break(115, sd="WA_CENTRAL")],
            [_window(sd="WA_MIDLANDS"), _window(sd="WA_CENTRAL")],
        )
        self.assertTrue(all(r.pressure_direction in {"at_risk", "favoured"} for r in rows))
        self.assertTrue(all(r.pressure_direction != "neutral" for r in rows))

    def test_no_hectare_or_delta_fields(self):
        names = {f.name for f in dataclasses.fields(PressureRow)}
        banned = ("ha", "delta", "hectare", "area", "value")
        offenders = [n for n in names if any(b in n.lower() for b in banned)]
        self.assertEqual(offenders, [])

    def test_evidence_id_is_key_derived_and_stable(self):
        (row,) = _gen([_sd_break(160)], [_window()])
        self.assertEqual(row.evidence_id, "SWP-2026-WA_MIDLANDS-barley-BRK")
        # band-moving input keeps the same id (key-derived, not value-derived)
        (row2,) = _gen([_sd_break(180)], [_window()])
        self.assertEqual(row2.evidence_id, row.evidence_id)

    def test_window_confidence_downgraded_on_low_coverage(self):
        (row,) = _gen([_sd_break(160, coverage_ok=False)], [_window(confidence="high")])
        self.assertEqual(row.window_confidence, "low")

    def test_window_confidence_downgraded_on_insufficient_history(self):
        hist = {"WA_MIDLANDS": [120, 130]}  # < MIN_HISTORY_YEARS
        (row,) = _gen([_sd_break(160)], [_window(confidence="high")], hist)
        self.assertEqual(row.window_confidence, "low")

    def test_window_confidence_keeps_window_value_when_guards_pass(self):
        hist = {"WA_MIDLANDS": list(range(120, 135))}  # >= 10
        (row,) = _gen([_sd_break(160, coverage_ok=True)], [_window(confidence="medium")], hist)
        self.assertEqual(row.window_confidence, "medium")

    def test_guide_year_selection_picks_latest_not_after_season(self):
        windows = [
            _window(source_year=2018),
            _window(source_year=2025),
            _window(source_year=2030),  # after season_year -> ineligible
        ]
        (row,) = _gen([_sd_break(160, year=2026)], windows)
        self.assertEqual(row.guide_source_year, 2025)

    def test_overlap_and_days_after_latest_viable_math(self):
        (row,) = _gen([_sd_break(150)], [_window(opt_start=121, opt_end=152, latest=166)])
        self.assertEqual(row.window_overlap_days, 152 - 150 + 1)  # inclusive
        self.assertEqual(row.days_after_latest_viable, 150 - 166)  # negative = in time

    def test_break_date_and_status_carried(self):
        (row,) = _gen([_sd_break(160)], [_window()])
        self.assertEqual(row.break_date, "2026-06-09")  # DOY 160 of 2026
        self.assertEqual(row.break_status, "on_time")   # 135 <= 160 <= 166
        self.assertEqual(row.season, "2026/27")
        self.assertEqual(row.counterparty_commodity, "unknown")  # v1: favoured deferred


if __name__ == "__main__":
    unittest.main()
