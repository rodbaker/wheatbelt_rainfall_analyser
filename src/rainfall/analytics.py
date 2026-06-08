"""Shared tabular rainfall analytics helpers."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def percentile_rank(values: Iterable[float], target: float) -> float:
    """Return strict percentile rank of target against valid baseline values.

    The house convention matches the gridded percentile engine: ties do not
    lift rank. NaN values are ignored.
    """
    arr = np.asarray(list(values), dtype="float64")
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0 or np.isnan(target):
        return float("nan")
    return float((arr < target).sum() / len(arr) * 100.0)


def decile_rank(values: Iterable[float], target: float) -> int | None:
    """Return the 1-10 decile of target within values (the house convention).

    This reproduces the canonical decile producer
    (``scripts/build_sa2_rainfall_deciles.py::_compute_decile``) exactly:
    ``rank = #(values < target) + 1`` then ``ceil(rank / n * 10)`` clamped to
    1-10. Ties do not lift rank. NaN values are ignored. Returns ``None`` for an
    empty/all-NaN baseline or a NaN target.

    Use this — not a percentile-floor bucket — for any reported rainfall decile,
    so report scripts and the v1.0 deciles contract never disagree.
    """
    arr = np.asarray(list(values), dtype="float64")
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0 or np.isnan(target):
        return None
    rank = int((arr < target).sum()) + 1
    decile = int(np.ceil(rank / len(arr) * 10))
    return max(1, min(10, decile))


def decile_score(values: Iterable[float], target: float) -> float | None:
    """Continuous 1.0-10.0 decile score on the canonical rank basis.

    ``score = (#(values < target) + 1) / n * 10`` clamped to [1.0, 10.0] and
    rounded to 1 dp. This is the decimal companion to :func:`decile_rank` (which
    is ``ceil`` of the unclamped score) — use it for any reported decile-like
    decimal so printed/exported values never disagree with the integer decile or
    the canonical producer. Ties do not lift rank. NaN values are ignored;
    returns ``None`` for an empty/all-NaN baseline or a NaN target.
    """
    arr = np.asarray(list(values), dtype="float64")
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0 or np.isnan(target):
        return None
    rank = int((arr < target).sum()) + 1
    score = rank / len(arr) * 10.0
    return round(max(1.0, min(10.0, score)), 1)


def weighted_mean(values_weights: Iterable[tuple[float, float]]) -> float | None:
    """Return weighted mean, ignoring non-positive weights and NaN values."""
    valid = []
    for value, weight in values_weights:
        if value is None or weight is None:
            continue
        value_f = float(value)
        weight_f = float(weight)
        if weight_f > 0 and not np.isnan(value_f):
            valid.append((value_f, weight_f))
    total_weight = sum(weight for _, weight in valid)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in valid) / total_weight


def area_weighted(
    df: pd.DataFrame,
    weights: pd.DataFrame,
    value_col: str,
    group_cols: list[str],
) -> pd.DataFrame:
    """Area-weight value_col after merging SA2/state wheat weights."""
    merged = df.merge(weights, on=["sa2_code", "state_name"], how="inner")
    merged = merged.dropna(subset=[value_col, "weight"])
    merged = merged[merged["weight"] > 0].copy()
    merged["__wx"] = merged[value_col] * merged["weight"]
    grouped = merged.groupby(group_cols, dropna=False).agg(
        __wx=("__wx", "sum"),
        __w=("weight", "sum"),
    )
    grouped[value_col] = grouped["__wx"] / grouped["__w"]
    return grouped.reset_index()[group_cols + [value_col]]
