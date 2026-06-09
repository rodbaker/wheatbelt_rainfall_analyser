"""Assemble ``Sa2Break`` records from the three source files (R6 join keys).

Joins (per ``docs/sa2_join_key_investigation_notes.md``):
  features <-> concordance : ``sa2_code_9dig`` <-> ``SA2_CODE21``  (fail loud on miss)
  features <-> broadacre   : 5-digit ``sa2_code``                  (miss -> weight 0 + warn)

One ``Sa2Break`` is emitted per (feature SA2 x concordance SD overlap); the SD weight
ingredient is the concordance ``allocation_ratio``. Break dates are converted to
day-of-year; ``absent``/``not_assessed`` (or blank date) rows carry ``break_doy=None``.
All seasons are loaded (the historical series feeds the R3 percentile).
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from src.sowing.crosswalk import Sa2Break

logger = logging.getLogger(__name__)

_ELIGIBLE = {"early", "on_time", "late"}


@dataclass(frozen=True)
class LoadResult:
    records: List[Sa2Break]
    missing_broadacre: List[Tuple[str, str]]  # (sa2_code 5-digit, sa2_name)


def _break_doy(iso_date: str, status: str) -> Optional[int]:
    iso_date = (iso_date or "").strip()
    if status not in _ELIGIBLE or not iso_date:
        return None
    y, m, d = (int(p) for p in iso_date.split("-"))
    return date(y, m, d).timetuple().tm_yday


def _load_broadacre(path: Path) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            code = (r.get("sa2_code") or "").strip()
            raw = (r.get("broadacre_area_ha") or "").strip()
            if code and raw:
                weights[code] = float(raw)
    return weights


def _load_concordance(path: Path) -> Dict[str, List[Tuple[str, str, float]]]:
    conc: Dict[str, List[Tuple[str, str, float]]] = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            sa2 = (r.get("SA2_CODE21") or "").strip()
            conc.setdefault(sa2, []).append(
                (
                    (r.get("SD_CODE11") or "").strip(),
                    (r.get("SD_STATE_CODE") or "").strip(),
                    float(r.get("allocation_ratio") or 0.0),
                )
            )
    return conc


def load_sa2_breaks(
    features_path: Union[str, Path],
    concordance_path: Union[str, Path],
    broadacre_path: Union[str, Path],
    *,
    state: str = "Western Australia",
) -> LoadResult:
    """Build ``Sa2Break`` records joining features, concordance, and broadacre weights.

    Fails loud (``ValueError``) if a feature SA2's ``sa2_code_9dig`` has no
    concordance row. A feature SA2 with no broadacre weight is kept with
    ``broadacre_area_ha=0.0`` (not synthesized), named in ``missing_broadacre``,
    and logged as a warning.
    """
    broadacre = _load_broadacre(Path(broadacre_path))
    concordance = _load_concordance(Path(concordance_path))

    records: List[Sa2Break] = []
    missing: List[Tuple[str, str]] = []
    seen_missing = set()

    with open(features_path, newline="") as fh:
        for r in csv.DictReader(fh):
            if (r.get("state_name") or "").strip() != state:
                continue
            sa2_5 = (r.get("sa2_code") or "").strip()
            sa2_9 = (r.get("sa2_code_9dig") or "").strip()
            sa2_name = (r.get("sa2_name") or "").strip()
            season_year = int((r.get("season_year") or "").strip())
            status = (r.get("autumn_break_status") or "").strip()
            break_doy = _break_doy(r.get("autumn_break_date"), status)

            overlaps = concordance.get(sa2_9)
            if overlaps is None:
                raise ValueError(
                    f"feature SA2 {sa2_9} ({sa2_name!r}) has no concordance row -- "
                    f"unexpected 2016/2021 SA2 mismatch; investigate before joining"
                )

            if sa2_5 in broadacre:
                weight = broadacre[sa2_5]
            else:
                weight = 0.0
                if sa2_5 not in seen_missing:
                    seen_missing.add(sa2_5)
                    missing.append((sa2_5, sa2_name))
                    logger.warning(
                        "no broadacre weight for SA2 %s (%s); assigning weight 0 "
                        "(dropped from its SD rollup)",
                        sa2_5,
                        sa2_name,
                    )

            for sd_code11, sd_state_code, allocation_ratio in overlaps:
                records.append(
                    Sa2Break(
                        sa2_key=sa2_9,
                        sd_code11=sd_code11,
                        sd_state_code=sd_state_code,
                        allocation_ratio=allocation_ratio,
                        broadacre_area_ha=weight,
                        break_doy=break_doy,
                        status=status,
                        season_year=season_year,
                    )
                )

    return LoadResult(records=records, missing_broadacre=missing)
