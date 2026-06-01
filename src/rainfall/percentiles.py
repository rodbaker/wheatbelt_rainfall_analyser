"""Per-cell monthly rainfall percentile engine (pure functions, no plotting)."""

from pathlib import Path

import numpy as np
import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[2]
GRIDS_DIR = REPO_ROOT / "data" / "meta" / "monthly_rain"


def _validate_complete_grid(path: Path, year: int) -> None:
    """Raise ValueError unless path is a complete monthly grid for year."""
    with xr.open_dataset(path) as ds:
        if "monthly_rain" not in ds:
            raise ValueError(f"{path.name}: variable 'monthly_rain' missing")
        if "lat" not in ds.dims or "lon" not in ds.dims:
            raise ValueError(f"{path.name}: dimension 'lat'/'lon' missing")
        years = [int(t.dt.year.values) for t in ds.time]
        months = [int(t.dt.month.values) for t in ds.time]
        if len(months) != 12 or sorted(months) != list(range(1, 13)):
            raise ValueError(
                f"{path.name}: expected exactly one timestamp for each calendar month"
            )
        if any(value != year for value in years):
            raise ValueError(f"{path.name}: time coordinates belong to the wrong year")


def latest_complete_year(grids_dir: Path = GRIDS_DIR) -> int:
    """Newest year whose grid has 12 timestamps all belonging to that year."""
    grids_dir = Path(grids_dir)
    best = None
    for path in grids_dir.glob("*.monthly_rain.nc"):
        try:
            year = int(path.name.split(".")[0])
        except ValueError:
            continue  # non-year prefix (e.g. a stray/renamed file) — skip
        try:
            _validate_complete_grid(path, year)
        except (OSError, ValueError):
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


def _month_grid(path: Path, month: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the (lat, lon) slice for `month` from a monthly_rain file.

    Expects exactly one timestamp for `month` in the file. Raises ValueError
    (naming the path + month) if the month is absent or duplicated, rather than
    failing with an opaque IndexError or silently taking the first match.
    """
    with xr.open_dataset(path) as ds:
        sel = ds["monthly_rain"].sel(time=ds.time.dt.month == month)
        n = sel.sizes.get("time", 0)
        if n != 1:
            raise ValueError(
                f"{path.name}: expected exactly 1 timestamp for month {month}, "
                f"found {n}"
            )
        return (
            sel.isel(time=0).values.astype("float64"),
            ds.lat.values,
            ds.lon.values,
        )


def load_month_stack(
    month: int,
    year: int,
    baseline_start: int,
    baseline_end: int,
    grids_dir: Path = GRIDS_DIR,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Load the target month grid + the same-month baseline stack across years.

    Returns (target_grid, baseline_stack, years). Raises FileNotFoundError listing
    every missing baseline-year file.
    """
    grids_dir = Path(grids_dir)
    years = list(range(baseline_start, baseline_end + 1))

    missing = [y for y in years if not (grids_dir / f"{y}.monthly_rain.nc").exists()]
    if missing:
        raise FileNotFoundError(
            f"missing monthly_rain grids for baseline years {missing}; "
            f"run scripts/download_silo_monthly_rain.py"
        )

    target_path = grids_dir / f"{year}.monthly_rain.nc"
    if not target_path.exists():
        raise FileNotFoundError(f"missing target grid {target_path}")

    target, target_lat, target_lon = _month_grid(target_path, month)
    baseline = []
    for baseline_year in years:
        path = grids_dir / f"{baseline_year}.monthly_rain.nc"
        _validate_complete_grid(path, baseline_year)
        grid, lat, lon = _month_grid(path, month)
        if not np.array_equal(lat, target_lat) or not np.array_equal(lon, target_lon):
            raise ValueError(f"{path.name}: lat/lon coordinates do not match target grid")
        baseline.append(grid)
    stack = np.stack(baseline, axis=0)
    return target, stack, years
