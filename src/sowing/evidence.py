"""Sowing-window evidence derivation (Phase 2, contract swp-1).

Combines SD-aggregated autumn breaks (src.sowing.crosswalk) with the transcribed
sowing windows (src.sowing.windows) to produce directional crop-mix pressure rows.
Directional only -- no hectares, ever; no neutral rows (an on_time break emits no
row).

This module also derives ``break_percentile_vs_history`` (R3): the current SD break
day-of-year ranked against that SD's OWN historical break DOYs (built first via the
SD rollup), reusing the house-convention percentile from src.rainfall.analytics.
SA2-level percentiles are never rolled up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from src.rainfall.analytics import percentile_rank
from src.sowing.crosswalk import SdBreak, classify_break_status
from src.sowing.windows import SowingWindow

# Minimum number of historical break years for a confident percentile (R3).
# Below this the percentile is still emitted but flagged insufficient, forcing
# window_confidence -> low.
MIN_HISTORY_YEARS = 10

# Band thresholds (spec 7.6: analyser-internal, documented). "extreme" requires
# the break to be well past latest_viable AND in the late tail of the SD's own
# break-date climatology.
EXTREME_MARGIN_DAYS = 7        # "well past" latest_viable
EXTREME_PERCENTILE = 90.0      # "late tail" of break_percentile_vs_history

SCHEMA_VERSION = "swp-1"
REASON_CODE = "season_break_forced_switch"
_REASON_ABBREV = "BRK"
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _clean(values: Iterable[Optional[float]]):
    out = []
    for v in values:
        if v is None:
            continue
        if isinstance(v, float) and math.isnan(v):
            continue
        out.append(float(v))
    return out


def break_percentile_vs_history(
    current_break_doy: float,
    historical_break_doys: Iterable[Optional[float]],
) -> Tuple[float, int, bool]:
    """Rank ``current_break_doy`` against the SD's own historical break DOYs.

    Returns ``(percentile, n_years, sufficient)`` where ``percentile`` is 0-100
    (higher = later than history; ``nan`` if there is no history), ``n_years`` is
    the count of valid historical break years, and ``sufficient`` is
    ``n_years >= MIN_HISTORY_YEARS``.
    """
    history = _clean(historical_break_doys)
    percentile = percentile_rank(history, current_break_doy)
    n_years = len(history)
    return percentile, n_years, n_years >= MIN_HISTORY_YEARS


def season_label(season_year: int) -> str:
    """Winter convention: ``2026 -> '2026/27'`` (BEN Agri slash form)."""
    return f"{season_year}/{(season_year + 1) % 100:02d}"


@dataclass(frozen=True)
class PressureRow:
    """One directional sowing-window pressure signal (contract swp-1).

    Directional only -- NO hectares, NO deltas. ``pressure_direction`` is
    ``at_risk`` | ``favoured`` (never ``neutral``: no pressure -> no row).
    """

    schema_version: str
    evidence_id: str
    generated_at: str
    rainfall_run_id: str
    season: str
    season_year: int
    state: str
    sd_region: str
    commodity: str
    pressure_direction: str
    pressure_band: str
    counterparty_commodity: str
    reason_code: str
    rationale: str
    break_date: str
    break_status: str
    break_percentile_vs_history: float
    window_overlap_days: int
    days_after_latest_viable: int
    establishment_risk_flag: bool  # v1: always False = "not assessed", NOT "risk absent"
    guide_source_document: str
    guide_source_year: int
    window_confidence: str


def _doy_to_isodate(doy: int, year: int) -> str:
    return (date(year, 1, 1) + timedelta(days=doy - 1)).isoformat()


def _select_guide(windows: List[SowingWindow], season_year: int) -> Optional[SowingWindow]:
    """Latest ``source_year <= season_year`` (spec 7.4); None if all are in the future."""
    eligible = [w for w in windows if w.source_year <= season_year]
    if not eligible:
        return None
    return max(eligible, key=lambda w: w.source_year)


def _band(break_day: int, w: SowingWindow, percentile: float) -> Optional[str]:
    """Coarse band from the break day vs the commodity window (spec 7.4/7.6).

    Returns None when the break is in time (at/before ``optimal_start``) -> no row.
    """
    if break_day <= w.optimal_start_doy:
        return None  # in time -> no pressure
    if break_day <= w.optimal_end_doy:
        return "low"
    if break_day <= w.latest_viable_doy:
        return "medium"
    # past latest_viable
    well_past = break_day > w.latest_viable_doy + EXTREME_MARGIN_DAYS
    late_tail = (not math.isnan(percentile)) and percentile >= EXTREME_PERCENTILE
    if well_past and late_tail:
        return "extreme"
    return "high"


def _downgrade_confidence(window_conf: str, coverage_ok: bool, history_ok: bool) -> str:
    """Monotone downgrade to ``low`` if either guard trips; else the window's own confidence."""
    if not coverage_ok or not history_ok:
        return "low"
    return window_conf


def generate_pressure_rows(
    sd_breaks: Iterable[SdBreak],
    windows: Iterable[SowingWindow],
    history_by_sd: Dict[str, Iterable[Optional[float]]],
    *,
    generated_at: str,
    rainfall_run_id: str,
) -> List[PressureRow]:
    """Join SD breaks with sowing windows to emit directional pressure rows (v1).

    v1 emits ``at_risk`` rows only (the window-closing signal), with
    ``counterparty_commodity='unknown'``; the ``favoured`` switch-pairing leg is
    deferred. No row is emitted for an in-time break (spec: no neutral rows), nor
    where no state-native guide is loaded for the SD/commodity (national-safety
    gating, spec 7.5).

    ``establishment_risk_flag`` is **not assessed in v1** (the SD rollup does not
    yet carry autumn_break_7d_mm / dry-spell features). The swp-1 contract types it
    as bool, so it is emitted as ``False`` meaning "not assessed" -- NOT "risk
    absent". Consumers must not read False as a cleared establishment risk.
    """
    # index windows by (sd_region, commodity) -> list (for guide-year selection)
    by_key: Dict[Tuple[str, str], List[SowingWindow]] = {}
    for w in windows:
        if w.season_type != "winter":
            continue  # v1: winter autumn-break crops only
        by_key.setdefault((w.sd_region, w.commodity), []).append(w)

    rows: List[PressureRow] = []
    for sb in sd_breaks:
        break_day = int(round(sb.break_doy))
        for (sd_region, commodity), wins in by_key.items():
            if sd_region != sb.sd_region:
                continue
            w = _select_guide(wins, sb.season_year)
            if w is None:
                continue  # no guide at/<= season_year -> nothing

            percentile, _n, history_ok = break_percentile_vs_history(
                sb.break_doy, history_by_sd.get(sd_region, [])
            )
            band = _band(break_day, w, percentile)
            if band is None:
                continue  # in time -> no row

            overlap_start = max(break_day, w.optimal_start_doy)
            window_overlap_days = (
                max(0, w.optimal_end_doy - overlap_start + 1)
                if overlap_start <= w.optimal_end_doy
                else 0
            )
            days_after = break_day - w.latest_viable_doy
            window_confidence = _downgrade_confidence(w.confidence, sb.coverage_ok, history_ok)

            rationale = (
                f"{commodity} break in {sd_region} fell on "
                f"{_doy_to_isodate(break_day, sb.season_year)} "
                f"({sb.break_status}); {days_after:+d}d vs latest viable sow date -> "
                f"{band} downward pressure on area."
            )

            rows.append(
                PressureRow(
                    schema_version=SCHEMA_VERSION,
                    evidence_id=f"SWP-{sb.season_year}-{sd_region}-{commodity}-{_REASON_ABBREV}",
                    generated_at=generated_at,
                    rainfall_run_id=rainfall_run_id,
                    season=season_label(sb.season_year),
                    season_year=sb.season_year,
                    state=w.state,
                    sd_region=sd_region,
                    commodity=commodity,
                    pressure_direction="at_risk",
                    pressure_band=band,
                    counterparty_commodity="unknown",
                    reason_code=REASON_CODE,
                    rationale=rationale,
                    break_date=_doy_to_isodate(break_day, sb.season_year),
                    break_status=sb.break_status,
                    break_percentile_vs_history=percentile,
                    window_overlap_days=window_overlap_days,
                    days_after_latest_viable=days_after,
                    establishment_risk_flag=False,  # "not assessed" in v1 (see docstring)
                    guide_source_document=w.source_document,
                    guide_source_year=w.source_year,
                    window_confidence=window_confidence,
                )
            )
    return rows
