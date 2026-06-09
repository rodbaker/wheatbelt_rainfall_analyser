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

import csv
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ABS 2011 SD state code for Western Australia (column ``SD_STATE_CODE``).
WA_SD_STATE_CODE = "5"

# Break-status day-of-year cutoffs, matching _detect_autumn_break in
# scripts/build_sa2_rainfall_features.py: early < May 15, on_time May 15-Jun 15,
# late > Jun 15. DOY on a non-leap basis (break dates fall Apr-Jun, so the <=1-day
# leap shift is immaterial; see R2/R3 notes).
EARLY_CUTOFF_DOY = 135  # May 15 (non-leap)
LATE_CUTOFF_DOY = 166   # Jun 15 (non-leap)

# Default minimum valid break-date weight coverage for a high-confidence SD break
# (R2 guard): below this share of the SD's broadacre weight, confidence -> low.
COVERAGE_THRESHOLD_DEFAULT = 0.60

_ELIGIBLE_STATUSES = {"early", "on_time", "late"}

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


def classify_break_status(break_doy: float) -> str:
    """Map an aggregated break day-of-year to early / on_time / late (R2)."""
    if break_doy < EARLY_CUTOFF_DOY:
        return "early"
    if break_doy <= LATE_CUTOFF_DOY:
        return "on_time"
    return "late"


@dataclass(frozen=True)
class Sa2Break:
    """One SA2's autumn-break feature plus its SA2->SD weight ingredients."""

    sa2_key: str
    sd_code11: str
    sd_state_code: str
    allocation_ratio: float        # SA2->SD area share (concordance)
    broadacre_area_ha: float       # SA2 crop weight (coverage report)
    break_doy: Optional[int]       # None when status is absent/not_assessed
    status: str                    # early | on_time | late | absent | not_assessed
    season_year: int


@dataclass(frozen=True)
class SdBreak:
    """Area-weighted autumn break rolled up to a BEN Agri SD (per season)."""

    sd_region: str                 # crop-forecast region_code
    season_year: int
    break_doy: float               # area-weighted mean DOY over eligible SA2s
    break_status: str              # derived from break_doy (early/on_time/late)
    coverage: float                # eligible break weight / total SD broadacre weight
    coverage_ok: bool              # coverage >= threshold
    n_sa2_eligible: int
    n_sa2_total: int


_BREAK_DATE_STATUSES = {"early", "on_time", "late"}


def _break_date_to_doy(iso: str) -> Optional[int]:
    iso = (iso or "").strip()
    if not iso:
        return None
    return date.fromisoformat(iso).timetuple().tm_yday


def load_sa2_breaks(
    features_path: Union[str, Path],
    concordance_path: Union[str, Path],
    broadacre_path: Union[str, Path],
    state_name: str = "Western Australia",
) -> List[Sa2Break]:
    """Assemble ``Sa2Break`` records from the three vendored/feature files (R6).

    Joins per the approved keys: break features <-> concordance on the **9-digit**
    code (``sa2_code_9dig`` == ``SA2_CODE21``); break features <-> broadacre weight
    on the **5-digit** code (``sa2_code``). One record per feature-SA2 x
    concordance-SD overlap (splits emit multiple). ``break_doy`` is the
    ``autumn_break_date`` day-of-year, ``None`` for absent/not_assessed.

    Failure behavior: **fail loud** (``KeyError``) if a feature SA2's 9-digit code
    is absent from the concordance; **warn + weight 0** if a feature SA2 has no
    broadacre weight (the missing SA2 is named, and its zero weight flows into the
    SD coverage metric).
    """
    # concordance: SA2_CODE21 -> list of overlap rows
    conc: Dict[str, List[dict]] = {}
    with open(concordance_path, newline="") as fh:
        for row in csv.DictReader(fh):
            conc.setdefault(row["SA2_CODE21"].strip(), []).append(row)

    # broadacre: 5-digit sa2_code -> broadacre_area_ha
    broad: Dict[str, float] = {}
    with open(broadacre_path, newline="") as fh:
        for row in csv.DictReader(fh):
            raw = (row.get("broadacre_area_ha") or "").strip()
            broad[row["sa2_code"].strip()] = float(raw) if raw else 0.0

    missing_broadacre: set = set()
    out: List[Sa2Break] = []
    with open(features_path, newline="") as fh:
        for row in csv.DictReader(fh):
            if (row.get("state_name") or "").strip() != state_name:
                continue
            code5 = (row.get("sa2_code") or "").strip()
            code9 = (row.get("sa2_code_9dig") or "").strip()

            overlaps = conc.get(code9)
            if overlaps is None:
                raise KeyError(
                    f"feature SA2 sa2_code_9dig={code9!r} (sa2_code={code5!r}) "
                    f"not found in concordance -- cannot map to an SD"
                )

            if code5 not in broad:
                missing_broadacre.add(code5)
            broadacre = broad.get(code5, 0.0)

            status = (row.get("autumn_break_status") or "").strip()
            break_doy = (
                _break_date_to_doy(row.get("autumn_break_date"))
                if status in _BREAK_DATE_STATUSES
                else None
            )
            season_year = int((row.get("season_year") or "").strip())

            for o in overlaps:
                out.append(
                    Sa2Break(
                        sa2_key=code9,
                        sd_code11=o["SD_CODE11"].strip(),
                        sd_state_code=o["SD_STATE_CODE"].strip(),
                        allocation_ratio=float(o["allocation_ratio"]),
                        broadacre_area_ha=broadacre,
                        break_doy=break_doy,
                        status=status,
                        season_year=season_year,
                    )
                )

    if missing_broadacre:
        logger.warning(
            "no broadacre weight for %d feature SA2(s): %s -- assigned weight 0 "
            "(they drop from SD valid-weight coverage)",
            len(missing_broadacre),
            ", ".join(sorted(missing_broadacre)),
        )
    return out


def rollup_breaks_to_sd(
    sa2_breaks,
    coverage_threshold: float = COVERAGE_THRESHOLD_DEFAULT,
) -> List[SdBreak]:
    """Aggregate per-SA2 autumn breaks to BEN Agri SD per season (R2).

    SA2s are mapped to SDs via ``resolve_sd_region`` (non-grain WA SDs and
    interstate edge overlaps are dropped; unknown SD codes fail loud). For each
    ``(sd_region, season_year)``:

    - weight ``w = allocation_ratio * broadacre_area_ha``
    - ``break_doy`` = weighted mean DOY over *eligible* SA2s (status in
      early/on_time/late); ``absent``/``not_assessed`` SA2s are excluded from the
      mean but still count in the coverage denominator
    - ``coverage`` = eligible weight / total SD broadacre weight; ``coverage_ok``
      is ``coverage >= coverage_threshold``

    SDs whose total broadacre weight is zero are skipped (no croppable area).
    """
    # group key -> accumulators
    elig_wsum: Dict[Tuple[str, int], float] = {}      # Σ w over eligible
    elig_wdoy: Dict[Tuple[str, int], float] = {}      # Σ w*doy over eligible
    total_wsum: Dict[Tuple[str, int], float] = {}     # Σ w over all (in SD)
    n_elig: Dict[Tuple[str, int], int] = {}
    n_total: Dict[Tuple[str, int], int] = {}
    order: List[Tuple[str, int]] = []

    for rec in sa2_breaks:
        try:
            sd_region = resolve_sd_region(rec.sd_code11, rec.sd_state_code)
        except SdExcluded:
            continue  # non-grain WA SD or interstate edge -- drop with rationale
        # UnknownSdError intentionally propagates (fail loud)

        key = (sd_region, rec.season_year)
        if key not in total_wsum:
            total_wsum[key] = 0.0
            elig_wsum[key] = 0.0
            elig_wdoy[key] = 0.0
            n_elig[key] = 0
            n_total[key] = 0
            order.append(key)

        w = rec.allocation_ratio * rec.broadacre_area_ha
        total_wsum[key] += w
        n_total[key] += 1
        if rec.status in _ELIGIBLE_STATUSES and rec.break_doy is not None:
            elig_wsum[key] += w
            elig_wdoy[key] += w * rec.break_doy
            n_elig[key] += 1

    out: List[SdBreak] = []
    for key in order:
        sd_region, season_year = key
        total_w = total_wsum[key]
        if total_w <= 0.0:
            continue  # no croppable area in this SD
        elig_w = elig_wsum[key]
        if elig_w <= 0.0:
            continue  # no valid break dates to average
        break_doy = elig_wdoy[key] / elig_w
        coverage = elig_w / total_w
        out.append(
            SdBreak(
                sd_region=sd_region,
                season_year=season_year,
                break_doy=break_doy,
                break_status=classify_break_status(break_doy),
                coverage=coverage,
                coverage_ok=coverage >= coverage_threshold,
                n_sa2_eligible=n_elig[key],
                n_sa2_total=n_total[key],
            )
        )
    return out
