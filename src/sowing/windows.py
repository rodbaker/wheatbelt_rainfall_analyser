"""Load + validate the transcribed WA sowing-windows table (SD grain).

Per D2 the windows are keyed by ``sd_region`` (crop-forecast ``region_code``),
overriding spec 7.1's ``dpird_agzone`` grain (agzone->SA2 is unavailable in v1).
Windows are recurring **calendar** day-of-year ranges (they recur yearly), one
row per (sd_region, commodity, season_type).

Validation enforces the spec 8 acceptance: DOY ordering
``earliest <= optimal_start <= optimal_end <= latest_viable`` (all in 1..366) and
``rainfall_regime`` / ``season_type`` / ``confidence`` vocab; plus the D2
``sd_region`` gate against crop-forecast's ``region_reference.csv``.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Union

from src.sowing.region_ref import sd_region_codes

REQUIRED_COLUMNS = [
    "state",
    "sd_region",
    "rainfall_regime",
    "commodity",
    "season_type",
    "earliest_sow_doy",
    "optimal_start_doy",
    "optimal_end_doy",
    "latest_viable_doy",
    "penalty_pct_per_week_late",
    "late_penalty_note",
    "source_document",
    "source_year",
    "confidence",
]

RAINFALL_REGIMES = {"winter_dominant", "mediterranean", "uniform", "summer_dominant"}
SEASON_TYPES = {"winter", "summer"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
_DOY_FIELDS = [
    "earliest_sow_doy",
    "optimal_start_doy",
    "optimal_end_doy",
    "latest_viable_doy",
]


@dataclass(frozen=True)
class SowingWindow:
    state: str
    sd_region: str
    rainfall_regime: str
    commodity: str
    season_type: str
    earliest_sow_doy: int
    optimal_start_doy: int
    optimal_end_doy: int
    latest_viable_doy: int
    penalty_pct_per_week_late: Optional[float]
    late_penalty_note: str
    source_document: str
    source_year: int
    confidence: str


def _doy(value: str, field: str, where: str) -> int:
    try:
        d = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{where}: {field} is not an integer: {value!r}")
    if not 1 <= d <= 366:
        raise ValueError(f"{where}: {field} out of range 1..366: {d}")
    return d


def load_sowing_windows(
    path: Union[str, Path],
    valid_sd_regions: Optional[Set[str]] = None,
) -> List[SowingWindow]:
    """Load and validate ``sowing_windows_wa.csv``; return a list of ``SowingWindow``.

    ``valid_sd_regions`` is the allowed BEN Agri SD ``region_code`` set; when None it
    defaults to crop-forecast's WA SD codes (``region_reference.csv``). Raises
    ``ValueError`` on any schema, vocab, DOY-ordering, or unknown-sd_region violation.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"sowing_windows not found: {path}")
    if valid_sd_regions is None:
        valid_sd_regions = sd_region_codes(state="WA")

    windows: List[SowingWindow] = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            raise ValueError(f"sowing_windows {path} missing required columns: {missing}")

        for i, row in enumerate(reader, start=2):  # row 1 is the header
            where = f"{path}:{i}"

            state = (row["state"] or "").strip()
            if state != "WA":
                raise ValueError(f"{where}: state must be 'WA' (v1 WA-only), got {state!r}")

            sd_region = (row["sd_region"] or "").strip()
            if sd_region not in valid_sd_regions:
                raise ValueError(
                    f"{where}: unknown sd_region {sd_region!r}: not a BEN Agri WA SD"
                )

            regime = (row["rainfall_regime"] or "").strip()
            if regime not in RAINFALL_REGIMES:
                raise ValueError(f"{where}: rainfall_regime {regime!r} not in {RAINFALL_REGIMES}")

            season_type = (row["season_type"] or "").strip()
            if season_type not in SEASON_TYPES:
                raise ValueError(f"{where}: season_type {season_type!r} not in {SEASON_TYPES}")

            confidence = (row["confidence"] or "").strip()
            if confidence not in CONFIDENCE_LEVELS:
                raise ValueError(f"{where}: confidence {confidence!r} not in {CONFIDENCE_LEVELS}")

            doys = {f: _doy(row[f], f, where) for f in _DOY_FIELDS}
            ordered = [doys[f] for f in _DOY_FIELDS]
            if not (ordered[0] <= ordered[1] <= ordered[2] <= ordered[3]):
                raise ValueError(
                    f"{where}: DOY ordering must be earliest <= optimal_start <= "
                    f"optimal_end <= latest_viable, got {ordered}"
                )

            penalty_raw = (row["penalty_pct_per_week_late"] or "").strip()
            if penalty_raw == "":
                penalty: Optional[float] = None
            else:
                try:
                    penalty = float(penalty_raw)
                except ValueError:
                    raise ValueError(
                        f"{where}: penalty_pct_per_week_late not a float: {penalty_raw!r}"
                    )

            source_year_raw = (row["source_year"] or "").strip()
            try:
                source_year = int(source_year_raw)
            except ValueError:
                raise ValueError(f"{where}: source_year not an integer: {source_year_raw!r}")

            windows.append(
                SowingWindow(
                    state=state,
                    sd_region=sd_region,
                    rainfall_regime=regime,
                    commodity=(row["commodity"] or "").strip(),
                    season_type=season_type,
                    earliest_sow_doy=doys["earliest_sow_doy"],
                    optimal_start_doy=doys["optimal_start_doy"],
                    optimal_end_doy=doys["optimal_end_doy"],
                    latest_viable_doy=doys["latest_viable_doy"],
                    penalty_pct_per_week_late=penalty,
                    late_penalty_note=(row["late_penalty_note"] or "").strip(),
                    source_document=(row["source_document"] or "").strip(),
                    source_year=source_year,
                    confidence=confidence,
                )
            )

    return windows
