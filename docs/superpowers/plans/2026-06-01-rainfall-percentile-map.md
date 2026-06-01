# WA Wheatbelt Rainfall Percentile Map (SA2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a parameterised Python tool that reproduces the QGIS "WA Wheatbelt July Rainfall Percentiles" map from local SILO monthly grids, for any `--month`/`--year`, with an SA2 boundary overlay.

**Architecture:** Four isolated units + a CLI. A pure percentile engine (`src/rainfall/percentiles.py`) computes per-cell rank-fraction percentiles against a 1911→latest-complete-year baseline; a boundary loader (`src/rainfall/boundaries.py`) returns the 26 WA SA2 polygons + clip mask; a renderer (`src/rainfall/render.py`) draws the discrete-binned raster + overlay; a CLI (`scripts/plot_rainfall_percentiles.py`) wires them. A separately-hardened monthly downloader backfills 1911–2004 to the HDD-symlinked `monthly_rain/`. SA2-only — no `sd` code path this release.

**Tech Stack:** Python 3.10, xarray + netCDF4 (already present), NumPy (`<2.0.0`), Matplotlib + geopandas (new), pytest. Repo uses `.venv/bin/python -m pytest`; tests import via `from scripts import …` / `from src.… import …` (pytest adds rootdir to path).

**Spec:** `docs/superpowers/specs/2026-06-01-rainfall-percentile-map-design.md`

**Reference artifact:** `reports/figures/wa_july_percentiles.png` (the QGIS map to reproduce).

---

## File structure

| File | Responsibility |
|---|---|
| `requirements.txt`, `pyproject.toml` | Add `matplotlib`, `geopandas` deps |
| `scripts/download_silo_monthly_rain.py` (modify) | Harden: `install_year` (temp-inside-dest → validate → atomic replace), `validate_monthly_rain`, `--replace`, validate-before-skip |
| `tests/test_download_silo_monthly_rain.py` (create) | 6 downloader tests (mirror the daily ones) |
| `src/rainfall/__init__.py` (create) | New package marker |
| `src/rainfall/percentiles.py` (create) | `latest_complete_year`, `load_month_stack`, `cell_percentile` — pure, no plotting |
| `tests/test_rainfall_percentiles.py` (create) | Engine + helper tests on toy grids |
| `src/rainfall/boundaries.py` (create) | `load_wheatbelt_regions` (26 WA SA2), `clip_mask` |
| `tests/test_rainfall_boundaries.py` (create) | Boundary subset + CRS + mask tests |
| `src/rainfall/render.py` (create) | `render_percentile_map` — discrete-binned raster + SA2 overlay → PNG |
| `tests/test_rainfall_render.py` (create) | Renderer smoke + binning test |
| `scripts/plot_rainfall_percentiles.py` (create) | CLI wiring units together |

**Commit grouping:** Task 1 = deps commit. Tasks 2–3 = backfill commit. Tasks 4–8 = feature commit(s). The ~1.3 GB backfill *run* (Task 3b) is operational, not committed.

---

## Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml` (dependencies list)
- Modify: `requirements.txt`

- [ ] **Step 1: Add matplotlib + geopandas to `pyproject.toml`**

Change the `dependencies` array (currently ends `"xarray", "netCDF4"`) to append the two libs:

```toml
dependencies = [
    "numpy<2.0.0",
    "pandas",
    "click",
    "requests",
    "pyyaml",
    "python-dotenv>=0.5.1",
    "python-dateutil>=2.8.0",
    "duckdb>=0.8.0",
    "xarray",
    "netCDF4",
    "matplotlib",
    "geopandas"
]
```

- [ ] **Step 2: Uncomment/add the same in `requirements.txt`**

`requirements.txt` currently has commented `# geopandas>=0.13.0` and `# matplotlib>=3.7.0` lines. Replace those two comment lines with active pins:

```
geopandas>=0.13.0
matplotlib>=3.7.0
```

- [ ] **Step 3: Install into the venv**

Run: `.venv/bin/pip install "geopandas>=0.13.0" "matplotlib>=3.7.0"`
Expected: resolves and installs geopandas + shapely + pyproj + fiona; matplotlib already present (3.10.9) so it is a no-op upgrade check. No `numpy>=2` pulled in (we pin `<2.0.0`).

- [ ] **Step 4: Verify imports**

Run: `.venv/bin/python -c "import geopandas, matplotlib; matplotlib.use('Agg'); print('geopandas', geopandas.__version__, 'mpl', matplotlib.__version__)"`
Expected: prints versions, no error.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml requirements.txt
git commit -m "deps: add matplotlib and geopandas for rainfall percentile map"
```

---

## Task 2: Harden the monthly downloader

Mirror the already-hardened `scripts/download_silo_daily_rain.py` (`install_year` + injected `fetch`). Reuse its proven test pattern.

**Files:**
- Modify: `scripts/download_silo_monthly_rain.py`
- Test: `tests/test_download_silo_monthly_rain.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_download_silo_monthly_rain.py`:

```python
"""Tests for the hardened SILO monthly_rain installer (mirror of the daily one).

The download is injected as a `fetch` callable so these run offline against real
tiny NetCDF fixtures (real xarray validation, no mocks).
"""

import numpy as np
import pandas as pd
import xarray as xr

from scripts import download_silo_monthly_rain as dl


def _write_monthly_rain_nc(path, year, n_months=12, value=1.0):
    """Minimal but structurally-real monthly_rain NetCDF fixture."""
    times = pd.date_range(f"{year}-01-15", periods=n_months, freq="MS")
    lat = np.array([-31.0, -30.95])
    lon = np.array([115.0, 115.05])
    data = np.full((n_months, lat.size, lon.size), value, dtype="float64")
    ds = xr.Dataset(
        {"monthly_rain": (("time", "lat", "lon"), data)},
        coords={"time": times, "lat": lat, "lon": lon},
    )
    ds.to_netcdf(path)
    ds.close()


def _good_fetch(year, n_months=12, value=1.0):
    seen = {}

    def fetch(tmp_path):
        seen["tmp"] = tmp_path
        _write_monthly_rain_nc(tmp_path, year, n_months, value=value)

    fetch.seen = seen
    return fetch


def test_temp_file_created_inside_dest_dir(tmp_path):
    fetch = _good_fetch(2000)
    status = dl.install_year(2000, fetch, dest_dir=tmp_path, min_bytes=0)
    assert status == "installed"
    assert fetch.seen["tmp"].parent == tmp_path
    assert (tmp_path / "2000.monthly_rain.nc").exists()


def test_validation_failure_preserves_existing_file(tmp_path):
    year = 2000
    dest = tmp_path / f"{year}.monthly_rain.nc"
    _write_monthly_rain_nc(dest, year, 12, value=7.0)
    original = dest.read_bytes()

    def bad_fetch(tmp_):  # only 5 months -> incomplete year
        _write_monthly_rain_nc(tmp_, year, 5, value=99.0)

    status = dl.install_year(year, bad_fetch, dest_dir=tmp_path,
                             allow_replace=True, min_bytes=0)
    assert status.startswith("invalid")
    assert dest.read_bytes() == original
    assert not (tmp_path / f"{year}.monthly_rain.nc.tmp").exists()


def test_successful_replace_installs_new_file(tmp_path):
    year = 2000
    dest = tmp_path / f"{year}.monthly_rain.nc"
    _write_monthly_rain_nc(dest, year, 12, value=7.0)
    fetch = _good_fetch(year, 12, value=42.0)
    status = dl.install_year(year, fetch, dest_dir=tmp_path,
                             allow_replace=True, min_bytes=0)
    assert status == "installed"
    with xr.open_dataset(dest) as ds:
        assert float(ds["monthly_rain"].isel(time=0, lat=0, lon=0).values) == 42.0


def test_temp_cleaned_up_on_fetch_error(tmp_path):
    year = 2000
    dest = tmp_path / f"{year}.monthly_rain.nc"
    _write_monthly_rain_nc(dest, year, 12, value=7.0)
    original = dest.read_bytes()

    def exploding_fetch(tmp_):
        tmp_.write_bytes(b"partial")
        raise RuntimeError("connection reset")

    status = dl.install_year(year, exploding_fetch, dest_dir=tmp_path,
                             allow_replace=True)
    assert status.startswith("error")
    assert not (tmp_path / f"{year}.monthly_rain.nc.tmp").exists()
    assert dest.read_bytes() == original


def test_skip_when_existing_file_is_valid(tmp_path):
    """validate-before-skip: an existing VALID file is skipped, fetch not called."""
    year = 2000
    _write_monthly_rain_nc(tmp_path / f"{year}.monthly_rain.nc", year, 12, value=7.0)
    called = {"fetch": False}

    def fetch(tmp_):
        called["fetch"] = True

    status = dl.install_year(year, fetch, dest_dir=tmp_path, allow_replace=False)
    assert status == "skipped"
    assert called["fetch"] is False


def test_existing_invalid_file_not_silently_accepted(tmp_path):
    """validate-before-skip: an existing INVALID file fails without --replace."""
    year = 2000
    # 6-month (truncated) existing file == invalid for a completed year
    _write_monthly_rain_nc(tmp_path / f"{year}.monthly_rain.nc", year, 6, value=7.0)
    called = {"fetch": False}

    def fetch(tmp_):
        called["fetch"] = True

    status = dl.install_year(year, fetch, dest_dir=tmp_path, allow_replace=False)
    assert status.startswith("invalid")
    assert called["fetch"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_download_silo_monthly_rain.py -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'scripts.download_silo_monthly_rain' has no attribute 'install_year'` (import succeeds, attribute missing).

- [ ] **Step 3: Add `validate_monthly_rain` + `install_year` to the downloader**

In `scripts/download_silo_monthly_rain.py`, change the imports block to add `os` and `Callable`:

```python
import argparse
import os
import sys
import urllib.request
from pathlib import Path
from typing import Callable

import xarray as xr
```

Then, immediately after the `MIN_FILE_BYTES = ...` line, insert these two functions:

```python
def validate_monthly_rain(path: Path, year: int, require_complete: bool = True) -> None:
    """Raise ValueError if `path` is not a valid monthly_rain grid for `year`."""
    with xr.open_dataset(path) as ds:
        if "monthly_rain" not in ds:
            raise ValueError("variable 'monthly_rain' missing")
        if "lat" not in ds.dims or "lon" not in ds.dims:
            raise ValueError("dimension 'lat'/'lon' missing")
        n_time = len(ds.time)
        if n_time == 0:
            raise ValueError("time axis is empty")
        if require_complete and n_time != 12:
            raise ValueError(f"expected 12 time steps, got {n_time}")
        bad_years = [
            str(t.values) for t in ds.time if int(str(t.dt.year.values)) != year
        ]
        if bad_years:
            raise ValueError(f"time coordinates with wrong year: {bad_years[:3]}")


def install_year(
    year: int,
    fetch: Callable[[Path], None],
    dest_dir: Path = OUTPUT_DIR,
    allow_replace: bool = False,
    require_complete: bool = True,
    min_bytes: int = MIN_FILE_BYTES,
) -> str:
    """Fetch one monthly grid: fetch -> temp (inside dest_dir) -> validate -> replace.

    Returns "installed", "skipped", "invalid: <reason>", or "error: <reason>".
    Validate-before-skip: an existing file is "skipped" only if it is valid; an
    existing invalid file returns "invalid: ..." unless allow_replace re-fetches.
    """
    dest_dir = Path(dest_dir)
    dest = dest_dir / f"{year}.monthly_rain.nc"

    if dest.exists() and not allow_replace:
        try:
            validate_monthly_rain(dest, year, require_complete=require_complete)
            return "skipped"
        except Exception as exc:
            return f"invalid: existing file {exc}"

    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / f"{year}.monthly_rain.nc.tmp"

    try:
        fetch(tmp)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        return f"error: {exc}"

    try:
        size = tmp.stat().st_size
        if size < min_bytes:
            raise ValueError(
                f"downloaded file too small ({size} bytes < {min_bytes} minimum)"
            )
        validate_monthly_rain(tmp, year, require_complete=require_complete)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        return f"invalid: {exc}"

    os.replace(tmp, dest)
    return "installed"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_download_silo_monthly_rain.py -p no:cacheprovider`
Expected: PASS — 6 passed (1 numpy RuntimeWarning is pre-existing, ignore).

- [ ] **Step 5: Commit**

```bash
git add scripts/download_silo_monthly_rain.py tests/test_download_silo_monthly_rain.py
git commit -m "feat: harden monthly_rain installer (temp-inside-dest, validate-before-replace)"
```

---

## Task 3: Wire the hardened installer into the monthly CLI

Replace the old `download_year` + post-rename `validate_year` + `main` with a CLI that drives `install_year` and adds `--replace`.

**Files:**
- Modify: `scripts/download_silo_monthly_rain.py`

- [ ] **Step 1: Replace `download_year`, `validate_year`, and `main`**

Delete the existing `download_year(...)`, `validate_year(...)`, and `main()` functions in full, and replace them with:

```python
def _urlretrieve_fetch(year: int):
    url = f"{BASE_URL}/{year}.monthly_rain.nc"

    def fetch(tmp: Path) -> None:
        print(f"  GET  {url}")
        urllib.request.urlretrieve(url, tmp)

    return fetch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, required=True,
                        help="Years to download")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip actual download and write")
    parser.add_argument("--replace", action="store_true",
                        help="Re-download and atomically replace an existing file "
                             "(validated before it overwrites the prior version)")
    parser.add_argument("--skip-validate", action="store_true",
                        help="Accept partial files (no 12-month completeness check)")
    args = parser.parse_args()

    require_complete = not args.skip_validate
    installed: list[int] = []
    skipped: list[int] = []
    failed: list[int] = []

    print(f"\n=== Installing {len(args.years)} year(s) -> {OUTPUT_DIR} ===\n")
    for year in sorted(args.years):
        dest = OUTPUT_DIR / f"{year}.monthly_rain.nc"
        if args.dry_run:
            action = "replace" if (dest.exists() and args.replace) else (
                "skip (exists)" if dest.exists() else "download"
            )
            print(f"  [dry-run] {year}: would {action}")
            continue

        status = install_year(
            year,
            _urlretrieve_fetch(year),
            allow_replace=args.replace,
            require_complete=require_complete,
        )
        if status == "installed":
            installed.append(year)
            print(f"  OK   {year}.monthly_rain.nc ({dest.stat().st_size / 1e6:.1f} MB)")
        elif status == "skipped":
            skipped.append(year)
            print(f"  SKIP {year} — already exists and valid (use --replace to refresh)")
        else:
            failed.append(year)
            print(f"  FAIL {year}: {status}", file=sys.stderr)

    print("\n=== Summary ===")
    print(f"  Installed : {installed if installed else '(none)'}")
    print(f"  Skipped   : {skipped if skipped else '(none)'}")
    if failed:
        print(f"  Failed    : {failed}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update the module docstring**

Replace the existing module docstring's "Existing files are never overwritten." sentence and Usage block with:

```
Files are saved to data/meta/monthly_rain/{year}.monthly_rain.nc (on the HDD via
symlink). Each file is downloaded to a .tmp inside the destination dir, validated
(variable + lat/lon + 12 months in-year), and only then atomically replaced via
os.replace(). A bad download can never clobber a good grid. An existing file is
skipped only if it is itself valid; pass --replace to refresh.

Usage:
    python scripts/download_silo_monthly_rain.py --years 1990 1991 1992
    python scripts/download_silo_monthly_rain.py --years 1990 --replace
    python scripts/download_silo_monthly_rain.py --years 2026 --skip-validate
```

- [ ] **Step 3: Verify tests still green + CLI smoke + no dead imports**

Run: `.venv/bin/python -m pytest tests/test_download_silo_monthly_rain.py -p no:cacheprovider -q`
Expected: 6 passed.

Run: `.venv/bin/python scripts/download_silo_monthly_rain.py --years 2025 --dry-run`
Expected: prints `[dry-run] 2025: would skip (exists)` and a Summary (2025 already on disk).

Run: `.venv/bin/python -c "import ast; src=open('scripts/download_silo_monthly_rain.py').read(); ast.parse(src); print('parse OK; calendar used:', 'calendar.' in src)"`
Expected: `parse OK; calendar used: False` (the old `import calendar` is unused now — if present, remove the `import calendar` line; monthly years are never leap-checked).

- [ ] **Step 4: Commit**

```bash
git add scripts/download_silo_monthly_rain.py
git commit -m "feat: drive monthly_rain CLI through hardened install_year + --replace"
```

- [ ] **Step 3b (OPERATIONAL, not a commit): run the 1911 backfill**

This downloads ~1.3 GB to the HDD-symlinked `monthly_rain/`. Run it as an operational step (resumable — re-run if interrupted):

Run: `.venv/bin/python scripts/download_silo_monthly_rain.py --years $(seq 1911 2004)`
Expected: each year `OK   {year}.monthly_rain.nc (~13–14 MB)`; existing 2005–2025 untouched. Confirm afterwards:
`ls data/meta/monthly_rain/*.nc | wc -l` → expected `116` (1911–2026).

> Note: the engine (Tasks 4–8) is testable on toy grids without this backfill. The backfill is only needed to render a *real* full-baseline map. If running the plan before the backfill completes, the engine/render tests still pass.

---

## Task 4: Percentile engine — `latest_complete_year`

**Files:**
- Create: `src/rainfall/__init__.py`
- Create: `src/rainfall/percentiles.py`
- Test: `tests/test_rainfall_percentiles.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rainfall_percentiles.py`:

```python
"""Tests for the rainfall percentile engine (pure functions, toy grids)."""

import numpy as np
import pandas as pd
import xarray as xr

from src.rainfall import percentiles as pc


def _write_grid(path, year, n_months, value):
    times = pd.date_range(f"{year}-01-15", periods=n_months, freq="MS")
    lat = np.array([-31.0, -30.95])
    lon = np.array([115.0, 115.05])
    data = np.full((n_months, lat.size, lon.size), float(value))
    xr.Dataset(
        {"monthly_rain": (("time", "lat", "lon"), data)},
        coords={"time": times, "lat": lat, "lon": lon},
    ).to_netcdf(path)


def test_latest_complete_year_excludes_partial(tmp_path):
    _write_grid(tmp_path / "2023.monthly_rain.nc", 2023, 12, 10)
    _write_grid(tmp_path / "2024.monthly_rain.nc", 2024, 12, 10)
    _write_grid(tmp_path / "2025.monthly_rain.nc", 2025, 4, 10)  # partial
    assert pc.latest_complete_year(tmp_path) == 2024
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_rainfall_percentiles.py::test_latest_complete_year_excludes_partial -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.rainfall'`.

- [ ] **Step 3: Create the package + `latest_complete_year`**

Create `src/rainfall/__init__.py` (empty file).

Create `src/rainfall/percentiles.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_rainfall_percentiles.py::test_latest_complete_year_excludes_partial -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/rainfall/__init__.py src/rainfall/percentiles.py tests/test_rainfall_percentiles.py
git commit -m "feat: latest_complete_year helper for rainfall baseline"
```

---

## Task 5: Percentile engine — `cell_percentile`

**Files:**
- Modify: `src/rainfall/percentiles.py`
- Test: `tests/test_rainfall_percentiles.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rainfall_percentiles.py`:

```python
def test_cell_percentile_formula_and_clamp():
    # One cell. Baseline = [1,2,3,4]; target = 5 (the max).
    # count(<5)=4 -> pct = 100*(4+1)/4 = 125 -> clamp to 100.
    baseline = np.array([1.0, 2.0, 3.0, 4.0]).reshape(4, 1, 1)
    target = np.array([5.0]).reshape(1, 1)
    out = pc.cell_percentile(target, baseline)
    assert out.shape == (1, 1)
    assert out[0, 0] == 100.0


def test_cell_percentile_tie_does_not_lift_rank():
    # Baseline = [10,20,30]; target = 20 (a tie). count(<20)=1 -> 100*(1+1)/3 = 66.67
    baseline = np.array([10.0, 20.0, 30.0]).reshape(3, 1, 1)
    target = np.array([20.0]).reshape(1, 1)
    out = pc.cell_percentile(target, baseline)
    assert abs(out[0, 0] - (100 * 2 / 3)) < 1e-9


def test_cell_percentile_target_nan_is_nan():
    baseline = np.array([1.0, 2.0, 3.0]).reshape(3, 1, 1)
    target = np.array([np.nan]).reshape(1, 1)
    out = pc.cell_percentile(target, baseline)
    assert np.isnan(out[0, 0])


def test_cell_percentile_divides_by_valid_count():
    # Baseline = [5, NaN, 15, 25]; target = 20. valid baseline = [5,15,25] -> n_valid=3.
    # count(<20)=2 -> pct = 100*(2+1)/3 = 100.0
    baseline = np.array([5.0, np.nan, 15.0, 25.0]).reshape(4, 1, 1)
    target = np.array([20.0]).reshape(1, 1)
    out = pc.cell_percentile(target, baseline)
    assert abs(out[0, 0] - 100.0) < 1e-9


def test_cell_percentile_all_baseline_nan_is_nan():
    baseline = np.array([np.nan, np.nan]).reshape(2, 1, 1)
    target = np.array([10.0]).reshape(1, 1)
    out = pc.cell_percentile(target, baseline)
    assert np.isnan(out[0, 0])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_rainfall_percentiles.py -k cell_percentile -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'src.rainfall.percentiles' has no attribute 'cell_percentile'`.

- [ ] **Step 3: Implement `cell_percentile`**

Append to `src/rainfall/percentiles.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_rainfall_percentiles.py -k cell_percentile -p no:cacheprovider`
Expected: PASS — 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rainfall/percentiles.py tests/test_rainfall_percentiles.py
git commit -m "feat: per-cell rainfall percentile (rank-fraction, valid-count denom)"
```

---

## Task 6: Percentile engine — `load_month_stack`

**Files:**
- Modify: `src/rainfall/percentiles.py`
- Test: `tests/test_rainfall_percentiles.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rainfall_percentiles.py`:

```python
def test_load_month_stack_selects_month_and_baseline(tmp_path):
    # Three baseline years, distinct values; target year 2002.
    for yr, val in [(2000, 10), (2001, 20), (2002, 30)]:
        _write_grid(tmp_path / f"{yr}.monthly_rain.nc", yr, 12, val)
    target, stack, years = pc.load_month_stack(
        month=7, year=2002, baseline_start=2000, baseline_end=2002, grids_dir=tmp_path
    )
    assert target.shape == (2, 2)            # lat x lon
    assert stack.shape == (3, 2, 2)          # 3 baseline years
    assert years == [2000, 2001, 2002]
    assert target[0, 0] == 30.0              # 2002's July value
    assert sorted(stack[:, 0, 0].tolist()) == [10.0, 20.0, 30.0]


def test_load_month_stack_missing_year_raises(tmp_path):
    _write_grid(tmp_path / "2000.monthly_rain.nc", 2000, 12, 10)
    # baseline asks for 2000-2002 but only 2000 exists
    try:
        pc.load_month_stack(7, 2000, 2000, 2002, grids_dir=tmp_path)
    except FileNotFoundError as exc:
        assert "2001" in str(exc) and "2002" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError naming missing years")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_rainfall_percentiles.py -k load_month_stack -p no:cacheprovider`
Expected: FAIL — `AttributeError: ... has no attribute 'load_month_stack'`.

- [ ] **Step 3: Implement `load_month_stack`**

Append to `src/rainfall/percentiles.py`:

```python
def _month_grid(path: Path, month: int) -> np.ndarray:
    """Return the (lat, lon) slice for `month` from a monthly_rain file."""
    with xr.open_dataset(path) as ds:
        sel = ds["monthly_rain"].sel(
            time=ds.time.dt.month == month
        ).isel(time=0)
        return sel.values.astype("float64")


def load_month_stack(month, year, baseline_start, baseline_end, grids_dir=GRIDS_DIR):
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

    target = _month_grid(target_path, month)
    stack = np.stack([_month_grid(grids_dir / f"{y}.monthly_rain.nc", month)
                      for y in years], axis=0)
    return target, stack, years
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_rainfall_percentiles.py -k load_month_stack -p no:cacheprovider`
Expected: PASS — 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rainfall/percentiles.py tests/test_rainfall_percentiles.py
git commit -m "feat: load_month_stack — target + same-month baseline grids"
```

---

## Task 7: Boundary layer

**Files:**
- Create: `src/rainfall/boundaries.py`
- Test: `tests/test_rainfall_boundaries.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rainfall_boundaries.py`:

```python
"""Tests for the SA2 wheatbelt boundary loader."""

from shapely.geometry import MultiPolygon, Polygon

from src.rainfall import boundaries as bd


def test_load_wheatbelt_regions_returns_26_wa_sa2():
    regions = bd.load_wheatbelt_regions()
    assert len(regions) == 26
    assert (regions["STE_NAME16"] == "Western Australia").all()
    assert "SA2_NAME16" in regions.columns
    # Reference-map landmarks present
    names = set(regions["SA2_NAME16"])
    assert {"Moora", "Dowerin", "Merredin", "Esperance Region"} <= names


def test_regions_crs_is_wgs84():
    regions = bd.load_wheatbelt_regions()
    assert regions.crs is not None
    assert regions.crs.to_epsg() == 4326


def test_clip_mask_is_single_geometry():
    regions = bd.load_wheatbelt_regions()
    mask = bd.clip_mask(regions)
    assert isinstance(mask, (Polygon, MultiPolygon))
    assert mask.is_valid
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_rainfall_boundaries.py -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.rainfall.boundaries'`.

- [ ] **Step 3: Implement the boundary loader**

Create `src/rainfall/boundaries.py`:

```python
"""WA wheatbelt SA2 boundaries for the rainfall percentile map (SA2-only)."""

from pathlib import Path

import geopandas as gpd
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON = REPO_ROOT / "data" / "meta" / "SA2_ABS_Regions.geojson"


def load_wheatbelt_regions(geojson_path: Path = GEOJSON) -> gpd.GeoDataFrame:
    """The 26 WA wheatbelt SA2 polygons in EPSG:4326, with SA2_NAME16 labels."""
    gdf = gpd.read_file(geojson_path)
    wa = gdf[gdf["STE_NAME16"] == "Western Australia"].copy()
    if gdf.crs is None:
        wa = wa.set_crs(epsg=4326)
    else:
        wa = wa.to_crs(epsg=4326)
    return wa.reset_index(drop=True)


def clip_mask(regions: gpd.GeoDataFrame):
    """Union of the wheatbelt polygons — used to blank raster cells outside it."""
    return unary_union(regions.geometry.values)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_rainfall_boundaries.py -p no:cacheprovider`
Expected: PASS — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rainfall/boundaries.py tests/test_rainfall_boundaries.py
git commit -m "feat: WA wheatbelt SA2 boundary loader + clip mask"
```

---

## Task 8: Renderer + CLI

**Files:**
- Create: `src/rainfall/render.py`
- Create: `scripts/plot_rainfall_percentiles.py`
- Test: `tests/test_rainfall_render.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rainfall_render.py`:

```python
"""Renderer tests: binning correctness + headless PNG smoke."""

import numpy as np

from src.rainfall import render as rd


def test_bin_index_right_closed():
    # pct == 10 must land in bin 0 (the <=10 class); 10.0001 -> bin 1.
    pct = np.array([[0.0, 10.0, 10.5, 95.0, 100.0]])
    idx = rd.bin_index(pct)
    assert idx.tolist() == [[0, 0, 1, 9, 9]]


def test_clip_to_regions_blanks_outside_cells():
    from shapely.geometry import box
    # Unit square mask at lon 0-1, lat 0-1. Grid centres: one inside, one outside.
    mask = box(0.0, 0.0, 1.0, 1.0)
    lon = np.array([0.5, 5.0])
    lat = np.array([0.5])
    pct = np.array([[40.0, 60.0]])
    out = rd.clip_to_regions(pct, lon, lat, mask)
    assert out[0, 0] == 40.0          # inside the mask -> kept
    assert np.isnan(out[0, 1])         # outside the mask -> blanked


def test_render_writes_png(tmp_path):
    from src.rainfall import boundaries as bd
    regions = bd.load_wheatbelt_regions()
    # Toy percentile grid over a small lon/lat window inside WA.
    lon = np.linspace(114.0, 124.0, 20)
    lat = np.linspace(-35.0, -27.0, 16)
    pct = np.random.default_rng(0).uniform(0, 100, size=(lat.size, lon.size))
    out = tmp_path / "test_map.png"
    rd.render_percentile_map(
        pct, regions, lon=lon, lat=lat, month=7, year=2024,
        baseline_start=1911, baseline_end=2023, out_path=out,
        mask_geom=bd.clip_mask(regions),
    )
    assert out.exists() and out.stat().st_size > 0
```

> Note on randomness: workflow scripts forbid `Math.random`, but this is a Python
> test using NumPy's seeded `default_rng(0)` — deterministic, allowed.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_rainfall_render.py -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.rainfall.render'`.

- [ ] **Step 3: Implement the renderer**

Create `src/rainfall/render.py`:

```python
"""Render the discrete-binned rainfall percentile raster + SA2 overlay to PNG."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from shapely.geometry import Point
from shapely.prepared import prep

REPO_ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = REPO_ROOT / "reports" / "figures"

_BIN_EDGES = [10, 20, 30, 40, 50, 60, 70, 80, 90]  # right-closed
_BIN_LABELS = ["<=10", "10-20", "20-30", "30-40", "40-50",
               "50-60", "60-70", "70-80", "80-90", ">90"]
_MONTHS = ["", "January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


def bin_index(pct: np.ndarray) -> np.ndarray:
    """Map a percentile array to 10 right-closed bin indices 0-9 (NaN-safe)."""
    return np.digitize(pct, _BIN_EDGES, right=True)


def _palette() -> ListedColormap:
    base = plt.get_cmap("RdBu")
    return ListedColormap([base(i / 9) for i in range(10)])


def clip_to_regions(pct, lon, lat, mask_geom):
    """Set cells whose centre falls outside `mask_geom` to NaN (hard wheatbelt clip)."""
    prepared = prep(mask_geom)
    out = np.array(pct, dtype="float64")
    for j, la in enumerate(lat):
        for i, lo in enumerate(lon):
            if not prepared.contains(Point(float(lo), float(la))):
                out[j, i] = np.nan
    return out


def render_percentile_map(pct, regions, *, lon, lat, month, year,
                          baseline_start, baseline_end, out_path=None,
                          mask_geom=None):
    """Draw the percentile raster with SA2 overlay; write PNG; return the path.

    If `mask_geom` is given, cells outside it are blanked (reproduce the
    reference map's hard clip to the wheatbelt).
    """
    out_path = Path(out_path) if out_path else (
        FIG_DIR / f"wa_{month:02d}_{year}_percentiles.png"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if mask_geom is not None:
        pct = clip_to_regions(pct, lon, lat, mask_geom)

    cmap = _palette()
    idx = bin_index(pct).astype("float64")
    idx[np.isnan(pct)] = np.nan
    masked = np.ma.masked_invalid(idx)

    fig, ax = plt.subplots(figsize=(11, 9))
    ax.pcolormesh(lon, lat, masked, cmap=cmap, vmin=0, vmax=9, shading="auto")
    regions.boundary.plot(ax=ax, color="black", linewidth=0.6)
    for _, row in regions.iterrows():
        pt = row.geometry.representative_point()
        ax.annotate(row["SA2_NAME16"], (pt.x, pt.y), fontsize=7,
                    ha="center", va="center")

    ax.set_title(f"WA Wheatbelt {_MONTHS[month]} Rainfall Percentiles", fontsize=16)
    ax.set_axis_off()
    handles = [Patch(facecolor=cmap(i), edgecolor="black", label=_BIN_LABELS[i])
               for i in range(10)]
    ax.legend(handles=handles, title="Percentiles", loc="center left",
              bbox_to_anchor=(1.01, 0.5), frameon=True)
    fig.text(0.5, 0.02,
             f"Baseline: {baseline_start}-{baseline_end}  |  "
             f"Source: SILO (LongPaddock) monthly_rain",
             ha="center", fontsize=8)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_rainfall_render.py -p no:cacheprovider`
Expected: PASS — 3 passed (bin index, clip-to-regions, PNG smoke).

- [ ] **Step 5: Write the CLI**

Create `scripts/plot_rainfall_percentiles.py`:

```python
#!/usr/bin/env python3
"""Plot WA wheatbelt monthly rainfall percentiles (SA2 overlay) to a PNG.

Per-cell percentile of the target month vs the same calendar month across the
1911-latest-complete-year baseline, rendered as a discrete-binned raster clipped
to the 26 WA wheatbelt SA2s.

Usage:
    python scripts/plot_rainfall_percentiles.py --month 7 --year 2024
    python scripts/plot_rainfall_percentiles.py --month 7 --year 2024 \
        --baseline-start 1911 --baseline-end 2023 --out reports/figures/jul24.png
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rainfall import boundaries as bd
from src.rainfall import percentiles as pc
from src.rainfall import render as rd


def _lon_lat(grids_dir: Path, year: int):
    with xr.open_dataset(grids_dir / f"{year}.monthly_rain.nc") as ds:
        return ds.lon.values, ds.lat.values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", type=int, required=True, choices=range(1, 13))
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--baseline-start", type=int, default=1911)
    parser.add_argument("--baseline-end", type=int, default=None)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    baseline_end = args.baseline_end or pc.latest_complete_year()
    try:
        target, stack, years = pc.load_month_stack(
            args.month, args.year, args.baseline_start, baseline_end
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    pct = pc.cell_percentile(target, stack)
    regions = bd.load_wheatbelt_regions()
    lon, lat = _lon_lat(pc.GRIDS_DIR, args.year)

    out = rd.render_percentile_map(
        pct, regions, lon=lon, lat=lat, month=args.month, year=args.year,
        baseline_start=args.baseline_start, baseline_end=baseline_end,
        out_path=args.out, mask_geom=bd.clip_mask(regions),
    )
    print(f"Wrote {out} (baseline {args.baseline_start}-{baseline_end}, {len(years)} yrs)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Verify the CLI end-to-end (requires the backfill OR a narrowed baseline)**

If the 1911 backfill (Task 3b) is done:
Run: `.venv/bin/python scripts/plot_rainfall_percentiles.py --month 7 --year 2024`
Expected: `Wrote reports/figures/wa_07_2024_percentiles.png (...)`; open the PNG and **eyeball against `reports/figures/wa_july_percentiles.png`** — colours (red dry / blue wet), 10-bin legend, SA2 outlines + labels, title, baseline caption.

If the backfill is NOT yet done, validate against the local 2005+ years:
Run: `.venv/bin/python scripts/plot_rainfall_percentiles.py --month 7 --year 2024 --baseline-start 2005 --baseline-end 2023`
Expected: writes the PNG (baseline differs from the final 1911 product, but proves the full pipeline).

- [ ] **Step 7: Run the full test suite (no regressions)**

Run: `.venv/bin/python -m pytest tests/ -p no:cacheprovider -q`
Expected: all new tests pass; the only pre-existing failure is `test_run_yield_analogue.py::test_2026_nsw_analogues` (unrelated, documented). No other failures.

- [ ] **Step 8: Commit**

```bash
git add src/rainfall/render.py scripts/plot_rainfall_percentiles.py tests/test_rainfall_render.py
git commit -m "feat: rainfall percentile renderer + plot_rainfall_percentiles CLI (SA2)"
```

---

## Done criteria

- [ ] `matplotlib` + `geopandas` in deps; venv imports clean.
- [ ] Monthly downloader hardened (6 tests) with `--replace` + validate-before-skip.
- [ ] 1911–2004 backfill run to the HDD (operational): `ls data/meta/monthly_rain/*.nc | wc -l` → 116.
- [ ] Engine: `latest_complete_year`, `cell_percentile` (formula/tie/clamp/NaN/valid-count), `load_month_stack` (select + missing-year) — all green.
- [ ] Boundaries: 26 WA SA2, EPSG:4326, valid clip mask — green.
- [ ] Renderer: right-closed binning + clip-to-regions + headless PNG — green.
- [ ] CLI produces `reports/figures/wa_07_2024_percentiles.png`, eyeballed against the reference.
- [ ] Full suite green except the one pre-existing unrelated failure.
- [ ] No `sd`/`--regions` code path shipped (SD is the tracked follow-up in the spec).
```
