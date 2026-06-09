"""Tests for the explicit WA BEN Agri SD allowlist + SD_CODE11 resolver.

These guard the SA2->SD rollup boundary (Phase 2, D2 corollary / R6): only the 7
BEN Agri WA grain SDs map to a region_code; non-grain WA SDs (Pilbara/Kimberley)
and interstate edge overlaps are dropped with rationale; anything unexpected
fails loud. No silent pass-through. Written BEFORE any rollup code.
"""

import unittest
from pathlib import Path

from src.sowing.crosswalk import (
    EXCLUDED_WA_SD_BY_CODE,
    WA_BEN_AGRI_SD_BY_CODE,
    WA_SD_STATE_CODE,
    SdExcluded,
    UnknownSdError,
    resolve_sd_region,
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


if __name__ == "__main__":
    unittest.main()
