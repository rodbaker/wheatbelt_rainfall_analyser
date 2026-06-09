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
from typing import Iterable, Optional, Tuple

from src.rainfall.analytics import percentile_rank

# Minimum number of historical break years for a confident percentile (R3).
# Below this the percentile is still emitted but flagged insufficient, forcing
# window_confidence -> low.
MIN_HISTORY_YEARS = 10


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
