"""Tests for the explicit WA BEN Agri SD allowlist + SD_CODE11 resolver.

These guard the SA2->SD rollup boundary (Phase 2, D2 corollary / R6): only the 7
BEN Agri WA grain SDs map to a region_code; non-grain WA SDs (Pilbara/Kimberley)
and interstate edge overlaps are dropped with rationale; anything unexpected
fails loud. No silent pass-through. Written BEFORE any rollup code.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from src.sowing.crosswalk import (
    EARLY_CUTOFF_DOY,
    EXCLUDED_WA_SD_BY_CODE,
    LATE_CUTOFF_DOY,
    Sa2Break,
    SdBreak,
    WA_BEN_AGRI_SD_BY_CODE,
    WA_SD_STATE_CODE,
    SdExcluded,
    UnknownSdError,
    load_sa2_breaks,
    resolve_sd_region,
    rollup_breaks_to_sd,
)
from src.sowing.region_ref import sd_region_codes

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDORED_REFERENCE = REPO_ROOT / "data" / "meta" / "region_reference.csv"


class TestAllowlist(unittest.TestCase):
    def test_allowlist_has_exactly_seven_grain_sds(self):
        self.assertEqual(len(WA_BEN_AGRI_SD_BY_CODE), 7)

    def test_allowlist_codes_are_the_expected_region_codes(self):
        self.assertEqual(
            set(WA_BEN_AGRI_SD_BY_CODE.values()),
            {
                "WA_SOUTH_EASTERN",
                "WA_LOWER_GREAT_SOUTHERN",
                "WA_UPPER_GREAT_SOUTHERN",
                "WA_MIDLANDS",
                "WA_CENTRAL",
                "WA_SOUTH_WEST",
                "WA_PERTH",
            },
        )

    def test_allowlist_reconciles_exactly_with_region_reference(self):
        # R6: drift in EITHER direction (crop-forecast adds/removes a WA SD, or we
        # mis-author the allowlist) must fail this test.
        self.assertEqual(
            set(WA_BEN_AGRI_SD_BY_CODE.values()),
            sd_region_codes(VENDORED_REFERENCE, state="WA"),
        )

    def test_grain_and_excluded_sets_are_disjoint(self):
        self.assertEqual(
            set(WA_BEN_AGRI_SD_BY_CODE) & set(EXCLUDED_WA_SD_BY_CODE), set()
        )


class TestResolveSdRegion(unittest.TestCase):
    def test_grain_sd_resolves_to_region_code(self):
        self.assertEqual(resolve_sd_region("525", WA_SD_STATE_CODE), "WA_MIDLANDS")
        self.assertEqual(resolve_sd_region("530", WA_SD_STATE_CODE), "WA_SOUTH_EASTERN")
        self.assertEqual(resolve_sd_region("505", WA_SD_STATE_CODE), "WA_PERTH")

    def test_accepts_int_inputs(self):
        self.assertEqual(resolve_sd_region(535, 5), "WA_CENTRAL")

    def test_non_grain_wa_sd_dropped_with_rationale(self):
        for code in ("540", "545"):  # Pilbara, Kimberley
            with self.assertRaises(SdExcluded) as ctx:
                resolve_sd_region(code, WA_SD_STATE_CODE)
            self.assertIn("non-grain", ctx.exception.rationale.lower())

    def test_interstate_edge_dropped_with_rationale(self):
        # 430 Eyre (SA, state 4), 710 NT-Bal (NT, state 7) — WA SA2s bleeding across.
        for code, state in (("430", "4"), ("710", "7")):
            with self.assertRaises(SdExcluded) as ctx:
                resolve_sd_region(code, state)
            self.assertIn("interstate", ctx.exception.rationale.lower())

    def test_unknown_wa_sd_code_fails_loud(self):
        with self.assertRaises(UnknownSdError):
            resolve_sd_region("599", WA_SD_STATE_CODE)

    def test_unknown_is_valueerror_excluded_is_not(self):
        self.assertTrue(issubclass(UnknownSdError, ValueError))
        self.assertFalse(issubclass(SdExcluded, ValueError))


def _sa2(sd_code, state, alloc, broadacre, doy, status, season_year=2026, sa2="X"):
    return Sa2Break(
        sa2_key=sa2,
        sd_code11=sd_code,
        sd_state_code=state,
        allocation_ratio=alloc,
        broadacre_area_ha=broadacre,
        break_doy=doy,
        status=status,
        season_year=season_year,
    )


class TestRollupBreaksToSd(unittest.TestCase):
    def test_area_weighted_mean_doy_and_derived_status(self):
        # SD 525 (WA_MIDLANDS): two SA2, equal weight (1.0*100 each), doy 140 & 160.
        recs = [
            _sa2("525", "5", 1.0, 100.0, 140, "on_time", sa2="a"),
            _sa2("525", "5", 1.0, 100.0, 160, "on_time", sa2="b"),
        ]
        (sd,) = rollup_breaks_to_sd(recs)
        self.assertIsInstance(sd, SdBreak)
        self.assertEqual(sd.sd_region, "WA_MIDLANDS")
        self.assertEqual(sd.season_year, 2026)
        self.assertAlmostEqual(sd.break_doy, 150.0)
        self.assertEqual(sd.break_status, "on_time")  # 135 <= 150 <= 166
        self.assertAlmostEqual(sd.coverage, 1.0)
        self.assertTrue(sd.coverage_ok)

    def test_weights_use_allocation_times_broadacre(self):
        # doy 140 weight=0.5*200=100 ; doy 200 weight=1.0*100=100 -> mean 170 -> late
        recs = [
            _sa2("535", "5", 0.5, 200.0, 140, "on_time", sa2="a"),
            _sa2("535", "5", 1.0, 100.0, 200, "late", sa2="b"),
        ]
        (sd,) = rollup_breaks_to_sd(recs)
        self.assertAlmostEqual(sd.break_doy, 170.0)
        self.assertEqual(sd.break_status, "late")

    def test_status_thresholds(self):
        (early,) = rollup_breaks_to_sd([_sa2("525", "5", 1.0, 10.0, EARLY_CUTOFF_DOY - 1, "early")])
        self.assertEqual(early.break_status, "early")
        (ontime,) = rollup_breaks_to_sd([_sa2("525", "5", 1.0, 10.0, LATE_CUTOFF_DOY, "late")])
        self.assertEqual(ontime.break_status, "on_time")  # boundary inclusive
        (late,) = rollup_breaks_to_sd([_sa2("525", "5", 1.0, 10.0, LATE_CUTOFF_DOY + 1, "late")])
        self.assertEqual(late.break_status, "late")

    def test_absent_and_not_assessed_excluded_from_date_mean_but_count_in_coverage(self):
        recs = [
            _sa2("525", "5", 1.0, 100.0, 150, "on_time", sa2="a"),
            _sa2("525", "5", 1.0, 100.0, None, "absent", sa2="b"),
            _sa2("525", "5", 1.0, 100.0, None, "not_assessed", sa2="c"),
        ]
        (sd,) = rollup_breaks_to_sd(recs)
        self.assertAlmostEqual(sd.break_doy, 150.0)          # only the eligible SA2
        self.assertAlmostEqual(sd.coverage, 100.0 / 300.0)   # 1 of 3 by weight
        self.assertFalse(sd.coverage_ok)                     # 0.33 < 0.60

    def test_coverage_threshold_boundary(self):
        # eligible 120 of total 200 = 0.60 -> ok (>=)
        recs = [
            _sa2("525", "5", 1.0, 120.0, 150, "on_time", sa2="a"),
            _sa2("525", "5", 1.0, 80.0, None, "absent", sa2="b"),
        ]
        (sd,) = rollup_breaks_to_sd(recs)
        self.assertAlmostEqual(sd.coverage, 0.60)
        self.assertTrue(sd.coverage_ok)

    def test_non_grain_wa_sd_dropped_from_rollup(self):
        recs = [
            _sa2("540", "5", 1.0, 100.0, 150, "on_time"),  # Pilbara
            _sa2("525", "5", 1.0, 100.0, 150, "on_time"),  # Midlands
        ]
        out = rollup_breaks_to_sd(recs)
        self.assertEqual({s.sd_region for s in out}, {"WA_MIDLANDS"})

    def test_interstate_edge_dropped_from_rollup(self):
        recs = [
            _sa2("430", "4", 1.0, 100.0, 150, "on_time"),  # Eyre (SA)
            _sa2("525", "5", 1.0, 100.0, 150, "on_time"),
        ]
        out = rollup_breaks_to_sd(recs)
        self.assertEqual({s.sd_region for s in out}, {"WA_MIDLANDS"})

    def test_unknown_sd_code_fails_loud(self):
        with self.assertRaises(UnknownSdError):
            rollup_breaks_to_sd([_sa2("599", "5", 1.0, 100.0, 150, "on_time")])

    def test_zero_total_weight_sd_is_skipped(self):
        recs = [_sa2("525", "5", 1.0, 0.0, 150, "on_time")]
        self.assertEqual(rollup_breaks_to_sd(recs), [])

    def test_groups_by_sd_and_season_year(self):
        recs = [
            _sa2("525", "5", 1.0, 100.0, 150, "on_time", season_year=2025),
            _sa2("525", "5", 1.0, 100.0, 160, "on_time", season_year=2026),
        ]
        out = {(s.sd_region, s.season_year): s for s in rollup_breaks_to_sd(recs)}
        self.assertEqual(set(out), {("WA_MIDLANDS", 2025), ("WA_MIDLANDS", 2026)})
        self.assertAlmostEqual(out[("WA_MIDLANDS", 2025)].break_doy, 150.0)
        self.assertAlmostEqual(out[("WA_MIDLANDS", 2026)].break_doy, 160.0)


def _write_csv(path, fieldnames, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


class TestLoadSa2Breaks(unittest.TestCase):
    """R6-approved loader: features<->concordance on 9-digit, features<->broadacre
    on 5-digit; fail loud on unmatched SA2; warn + weight 0 on missing broadacre."""

    def _fixtures(self, d, *, feature_rows, conc_rows, broad_rows):
        feat = Path(d) / "features.csv"
        conc = Path(d) / "conc.csv"
        broad = Path(d) / "broad.csv"
        _write_csv(feat,
                   ["season_year", "state_name", "sa2_code", "sa2_code_9dig",
                    "autumn_break_date", "autumn_break_status"], feature_rows)
        _write_csv(conc,
                   ["SA2_CODE21", "SD_CODE11", "SD_NAME11", "SD_STATE_CODE",
                    "allocation_ratio"], conc_rows)
        _write_csv(broad, ["sa2_code", "broadacre_area_ha"], broad_rows)
        return feat, conc, broad

    def test_joins_compute_doy_and_weights(self):
        with tempfile.TemporaryDirectory() as d:
            feat, conc, broad = self._fixtures(
                d,
                feature_rows=[dict(season_year="2026", state_name="Western Australia",
                                   sa2_code="51240", sa2_code_9dig="509021240",
                                   autumn_break_date="2026-06-09",
                                   autumn_break_status="on_time")],
                conc_rows=[dict(SA2_CODE21="509021240", SD_CODE11="525",
                                SD_NAME11="Midlands", SD_STATE_CODE="5",
                                allocation_ratio="1.0")],
                broad_rows=[dict(sa2_code="51240", broadacre_area_ha="500.0")],
            )
            (rec,) = load_sa2_breaks(feat, conc, broad)
            self.assertEqual(rec.sd_code11, "525")
            self.assertEqual(rec.sd_state_code, "5")
            self.assertEqual(rec.allocation_ratio, 1.0)
            self.assertEqual(rec.broadacre_area_ha, 500.0)
            self.assertEqual(rec.break_doy, 160)        # 2026-06-09
            self.assertEqual(rec.status, "on_time")
            self.assertEqual(rec.season_year, 2026)

    def test_missing_broadacre_weight_zero_and_warns_naming_sa2(self):
        with tempfile.TemporaryDirectory() as d:
            feat, conc, broad = self._fixtures(
                d,
                feature_rows=[dict(season_year="2026", state_name="Western Australia",
                                   sa2_code="51285", sa2_code_9dig="511041285",
                                   autumn_break_date="2026-05-20",
                                   autumn_break_status="on_time")],
                conc_rows=[dict(SA2_CODE21="511041285", SD_CODE11="535",
                                SD_NAME11="Central", SD_STATE_CODE="5",
                                allocation_ratio="1.0")],
                broad_rows=[],  # no broadacre weight for this SA2
            )
            with self.assertLogs("src.sowing.crosswalk", level="WARNING") as cm:
                (rec,) = load_sa2_breaks(feat, conc, broad)
            self.assertEqual(rec.broadacre_area_ha, 0.0)
            self.assertTrue(any("51285" in m for m in cm.output))

    def test_unmatched_sa2_fails_loud(self):
        with tempfile.TemporaryDirectory() as d:
            feat, conc, broad = self._fixtures(
                d,
                feature_rows=[dict(season_year="2026", state_name="Western Australia",
                                   sa2_code="99999", sa2_code_9dig="999999999",
                                   autumn_break_date="2026-06-01",
                                   autumn_break_status="on_time")],
                conc_rows=[dict(SA2_CODE21="509021240", SD_CODE11="525",
                                SD_NAME11="Midlands", SD_STATE_CODE="5",
                                allocation_ratio="1.0")],
                broad_rows=[dict(sa2_code="99999", broadacre_area_ha="10.0")],
            )
            with self.assertRaises(KeyError):
                load_sa2_breaks(feat, conc, broad)

    def test_absent_status_has_none_doy(self):
        with tempfile.TemporaryDirectory() as d:
            feat, conc, broad = self._fixtures(
                d,
                feature_rows=[dict(season_year="2026", state_name="Western Australia",
                                   sa2_code="51240", sa2_code_9dig="509021240",
                                   autumn_break_date="", autumn_break_status="absent")],
                conc_rows=[dict(SA2_CODE21="509021240", SD_CODE11="525",
                                SD_NAME11="Midlands", SD_STATE_CODE="5",
                                allocation_ratio="1.0")],
                broad_rows=[dict(sa2_code="51240", broadacre_area_ha="500.0")],
            )
            (rec,) = load_sa2_breaks(feat, conc, broad)
            self.assertIsNone(rec.break_doy)
            self.assertEqual(rec.status, "absent")

    def test_splits_emit_one_record_per_sd_overlap(self):
        with tempfile.TemporaryDirectory() as d:
            feat, conc, broad = self._fixtures(
                d,
                feature_rows=[dict(season_year="2026", state_name="Western Australia",
                                   sa2_code="51275", sa2_code_9dig="511011275",
                                   autumn_break_date="2026-06-01",
                                   autumn_break_status="on_time")],
                conc_rows=[
                    dict(SA2_CODE21="511011275", SD_CODE11="530", SD_NAME11="South Eastern",
                         SD_STATE_CODE="5", allocation_ratio="0.981"),
                    dict(SA2_CODE21="511011275", SD_CODE11="515",
                         SD_NAME11="Lower Great Southern", SD_STATE_CODE="5",
                         allocation_ratio="0.019"),
                ],
                broad_rows=[dict(sa2_code="51275", broadacre_area_ha="100.0")],
            )
            recs = load_sa2_breaks(feat, conc, broad)
            self.assertEqual({r.sd_code11 for r in recs}, {"530", "515"})
            self.assertEqual({round(r.allocation_ratio, 3) for r in recs}, {0.981, 0.019})

    def test_non_wa_feature_rows_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            feat, conc, broad = self._fixtures(
                d,
                feature_rows=[dict(season_year="2026", state_name="South Australia",
                                   sa2_code="40001", sa2_code_9dig="400000001",
                                   autumn_break_date="2026-06-01",
                                   autumn_break_status="on_time")],
                conc_rows=[],
                broad_rows=[],
            )
            self.assertEqual(load_sa2_breaks(feat, conc, broad), [])


if __name__ == "__main__":
    unittest.main()
