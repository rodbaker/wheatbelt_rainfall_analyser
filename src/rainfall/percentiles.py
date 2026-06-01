"""Per-cell monthly rainfall percentile engine (pure functions, no plotting)."""

from pathlib import Path

import numpy as np
import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[2]
GRIDS_DIR = REPO_ROOT / "data" / "meta" / "monthly_rain"


def latest_complete_year(grids_dir: Path = GRIDS_DIR) -> int:
    """Newest year whose grid has 12 timestamps all belonging to that year."""
    grids_dir = Path(grids_dir)
    best = None
    for path in grids_dir.glob("*.monthly_rain.nc"):
        try:
            year = int(path.name.split(".")[0])
        except ValueError:
            continue  # non-year prefix (e.g. a stray/renamed file) — skip
        with xr.open_dataset(path) as ds:
            if len(ds.time) != 12:
                continue
            if any(int(str(t.dt.year.values)) != year for t in ds.time):
                continue
        if best is None or year > best:
            best = year
    if best is None:
        raise FileNotFoundError(f"no complete-year grids in {grids_dir}")
    return best


def cell_percentile(target_grid: np.ndarray, baseline_stack: np.ndarray) -> np.ndarray:
    """Per-cell rank-fraction percentile of target vs baseline (same calendar month).

    pct = 100 * (count(baseline < target) + 1) / n_valid, where n_valid is the
    per-cell count of non-NaN baseline values. Strict `<` (ties don't lift rank).
    Clamped to 100. NaN where the target cell is NaN or n_valid == 0.
    """
    target = np.asarray(target_grid, dtype="float64")
    stack = np.asarray(baseline_stack, dtype="float64")

    valid = ~np.isnan(stack)
    n_valid = valid.sum(axis=0)  # (lat, lon)

    # count baseline strictly below target, ignoring NaN baseline cells
    below = np.where(valid & (stack < target[np.newaxis, ...]), 1.0, 0.0).sum(axis=0)

    with np.errstate(invalid="ignore", divide="ignore"):
        pct = 100.0 * (below + 1.0) / n_valid
    pct = np.clip(pct, None, 100.0)

    pct[np.isnan(target)] = np.nan
    pct[n_valid == 0] = np.nan
    return pct
