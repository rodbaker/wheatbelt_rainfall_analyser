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
        year = int(path.name.split(".")[0])
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
