"""Explicit WA BEN Agri SD allowlist + SD_CODE11 resolver.

Scope (Phase 2, D2 corollary): SA2 -> BEN Agri SD rollup + SD validation ONLY.
This module is **not** a national regionalisation layer and contains **no agzone
logic**. v1 is WA-only; SD is the contract grain.

The SA2->SD concordance covers all 61 national SDs, so a WA-SA2 rollup surfaces
three kinds of SD: (1) the 7 BEN Agri WA grain SDs, (2) non-grain WA SDs
(Pilbara/Kimberley), and (3) interstate edge overlaps from WA SA2s that bleed
across the border. The allowlist is keyed by ABS 2011 ``SD_CODE11`` -- globally
unique, so it avoids the ``SD_NAME11`` collision (e.g. WA vs NSW "South Eastern").

``resolve_sd_region`` enforces no-silent-pass-through: grain SD -> region_code;
non-grain WA SD or interstate edge -> ``SdExcluded`` (drop, with rationale);
anything else -> ``UnknownSdError`` (fail loud -- a code we have never seen).
The mapped region_codes are reconciled against crop-forecast's
``region_reference.csv`` by ``tests/test_sowing_crosswalk.py`` (R6).
"""

from __future__ import annotations

# ABS 2011 SD state code for Western Australia (column ``SD_STATE_CODE``).
WA_SD_STATE_CODE = "5"

# The 7 BEN Agri WA grain SDs, keyed by ABS 2011 SD_CODE11 -> crop-forecast region_code.
WA_BEN_AGRI_SD_BY_CODE = {
    "505": "WA_PERTH",
    "510": "WA_SOUTH_WEST",
    "515": "WA_LOWER_GREAT_SOUTHERN",
    "520": "WA_UPPER_GREAT_SOUTHERN",
    "525": "WA_MIDLANDS",
    "530": "WA_SOUTH_EASTERN",
    "535": "WA_CENTRAL",
}

# WA SDs deliberately excluded from grain-belt evidence (pastoral, outside wheatbelt).
EXCLUDED_WA_SD_BY_CODE = {
    "540": "Pilbara: non-grain WA pastoral SD, outside the wheatbelt",
    "545": "Kimberley: non-grain WA pastoral SD, outside the wheatbelt",
}


class SdExcluded(Exception):
    """A deliberate, rationalised drop of an SD (not an error).

    Raised for non-grain WA SDs and interstate edge overlaps. Callers (the rollup)
    catch this and log ``rationale``; the SD is omitted from the evidence output.
    """

    def __init__(self, sd_code: str, rationale: str):
        self.sd_code = sd_code
        self.rationale = rationale
        super().__init__(f"SD {sd_code} excluded: {rationale}")


class UnknownSdError(ValueError):
    """Fail-loud: an SD_CODE11 we neither map nor knowingly exclude. Investigate."""


def resolve_sd_region(sd_code11, sd_state_code) -> str:
    """Map an ABS 2011 ``SD_CODE11`` (+ its ``SD_STATE_CODE``) to a BEN Agri WA region_code.

    Returns the region_code for the 7 WA grain SDs. Raises ``SdExcluded`` (with
    rationale) for non-grain WA SDs and interstate edge overlaps, and
    ``UnknownSdError`` for any unexpected WA SD code. Never returns silently for a
    non-grain SD.
    """
    code = str(sd_code11).strip()
    state = str(sd_state_code).strip()

    if state != WA_SD_STATE_CODE:
        raise SdExcluded(
            code, f"interstate edge overlap: SD resides in state {state}, not WA"
        )
    if code in WA_BEN_AGRI_SD_BY_CODE:
        return WA_BEN_AGRI_SD_BY_CODE[code]
    if code in EXCLUDED_WA_SD_BY_CODE:
        raise SdExcluded(code, EXCLUDED_WA_SD_BY_CODE[code])
    raise UnknownSdError(
        f"unknown WA SD_CODE11 {code!r}: not a BEN Agri grain SD nor a known exclusion"
    )
