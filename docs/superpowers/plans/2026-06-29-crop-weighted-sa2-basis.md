# Crop-Weighted SA2 Rainfall Basis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the per-SA2 rainfall figure (and its decile) from a single centroid grid-cell to a **crop-weighted polygon mean** — rainfall where the wheat actually is — so large SA2s stop being misrepresented by one centroid cell (e.g. Gnowangerup reading d2.9 from a dry corner when the cropping country is ~average).

**Architecture:** A new shared module (`scripts/sa2_aggregation.py`) computes a crop-fraction-weighted mean of any 0.05° rainfall grid over an SA2 polygon, using the ABARES CLUM cropland-fraction layer (`Band1` in `clum_cropfrac_005.nc`) as weights. Both extractors (`extract_sa2_monthly_rainfall.py` for history, `extract_sa2_partial_month_rainfall.py` for month-to-date) gain a `--method {centroid,crop_weighted}` switch that delegates to this module. The crop-weighted outputs are written to **new `_cropwtd` files** so the centroid products are never clobbered; the review/decile builders are pointed at them via overrides. The per-cell gridded **map shading is left unchanged** — only the SA2-level statistics and labels change. National rollout (non-WA SA2s) is deferred because the non-WA universe is keyed to 2016 boundaries; WA is keyed to 2021 codes that match the 2021 SA2 shapefile, so WA is delivered first and end-to-end.

**Tech Stack:** Python 3.10, xarray, geopandas, shapely 2.x (`shapely.contains_xy`), pandas, numpy, pytest, Poetry (`env -u VIRTUAL_ENV poetry run ...`). No scipy (not installed — use `xarray.sel(method="nearest")`, never `interp`).

---

## Background / context an implementer needs

- The per-SA2 number today comes from `extract_sa2_partial_month_rainfall.py` (MTD, from the daily grid) and `extract_sa2_monthly_rainfall.py` (history, from monthly grids), both using **`centroid_nearest_grid_cell`** — one cell at the polygon centroid.
- Deciles are produced by `build_sd_monthly_rainfall_review.py --year Y --month M`, which scales each SA2's **historical monthly median** by `through_day/days_in_month` and ranks the MTD against it. It reads `data/features/sa2_monthly_rainfall_history_national.csv` (climatology) and `data/features/sa2_{Y}_{M:02d}_mtd.csv` (current MTD), and writes `sa2_/sd_/state_{Y}_{M:02d}_rainfall_review.csv`. **The decile math is method-agnostic** — if both inputs are crop-weighted, the output deciles are crop-weighted with no formula change.
- The map (`plot_decile_grid_bom.py`) shades **per cell** ("no aggregation") and only the **callout labels** read the review CSV. So switching the basis changes labels/deciles, not the shaded field.
- Cropland layer: `data/meta/clum_cropfrac_005.nc`, variable **`Band1`** (float32, dims `lat`,`lon`), 0.05°. The `crs` variable is a non-numeric placeholder — never select it.
- SA2 polygons: `zip:///mnt/d/grains-data-store/wheatbelt_rainfall_analyser/data/meta/shapefiles/SA2_2021_AUST_SHP_GDA2020.zip`, field `SA2_CODE21`. Load with `to_crs(4326)`.
- **Validation anchors** (June 1–28 2026, crop-weighted, computed ad-hoc and confirmed):
  Gnowangerup `38.1`, Wagin `47.9`, Katanning `35.7` mm (±0.2). The centroid values for the same SA2s were 28.8 / 47.9 / 39.0.

## File Structure

- **Create** `scripts/sa2_aggregation.py` — crop-weighted spatial aggregation: load cropland layer, load SA2 polygons, precompute per-SA2 cell index masks + weights for a given grid, weighted-mean a grid slice. One responsibility: turn (polygon, grid, cropland) → one number.
- **Create** `tests/test_sa2_aggregation.py` — unit tests on synthetic grids/polygons (no network, no big files).
- **Modify** `scripts/extract_sa2_partial_month_rainfall.py` — add `--method {centroid,crop_weighted}` (default `crop_weighted`); crop-weighted path uses `sa2_aggregation`; write to `_cropwtd` output when crop-weighted.
- **Modify** `scripts/extract_sa2_monthly_rainfall.py` — same `--method` switch for the history build.
- **Modify** `scripts/build_sd_monthly_rainfall_review.py` — add a `--hist` override (it already has `--mtd`) so the WA review can be built from crop-weighted inputs without touching the centroid national file.
- **Create** `tests/test_extract_partial_crop_weighted.py` — regression test pinning the three WA anchors.
- **Modify** `docs/national_sa2_rainfall_expansion.md` — document the crop-weighted method, the WA-vs-national scoping, and the `_cropwtd` file convention.

---

## Task 1: Crop-weighted aggregation module

**Files:**
- Create: `scripts/sa2_aggregation.py`
- Test: `tests/test_sa2_aggregation.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sa2_aggregation.py
"""Unit tests for crop-weighted SA2 aggregation (synthetic grids — no I/O)."""
import numpy as np
import xarray as xr
from shapely.geometry import box

from scripts.sa2_aggregation import build_cell_weights, crop_weighted_mean


def _grid(vals, lats, lons):
    return xr.DataArray(np.array(vals, dtype="float64"),
                        coords={"lat": lats, "lon": lons}, dims=["lat", "lon"])


def test_weighted_mean_uses_cropfrac_weights():
    # 1x2 cells with values 10, 20 and crop weights 0.1, 0.3 → (1+6)/0.4 = 17.5
    lats = [-33.90]
    lons = [117.00, 117.05]
    rain = _grid([[10.0, 20.0]], lats, lons)
    cf = _grid([[0.1, 0.3]], lats, lons)
    poly = box(116.97, -33.93, 117.08, -33.87)  # covers both cell centres
    w = build_cell_weights(poly, rain["lat"].values, rain["lon"].values, cf,
                           crop_floor=0.0)
    assert crop_weighted_mean(rain.values, w) == 17.5


def test_nodata_cells_excluded():
    lats = [-33.90]
    lons = [117.00, 117.05]
    rain = _grid([[np.nan, 20.0]], lats, lons)
    cf = _grid([[0.5, 0.5]], lats, lons)
    poly = box(116.97, -33.93, 117.08, -33.87)
    w = build_cell_weights(poly, rain["lat"].values, rain["lon"].values, cf,
                           crop_floor=0.0)
    # NaN cell dropped → only the 20.0 cell remains
    assert crop_weighted_mean(rain.values, w) == 20.0


def test_no_cropland_falls_back_to_centroid_cell():
    lats = [-33.90]
    lons = [117.00, 117.05]
    rain = _grid([[10.0, 20.0]], lats, lons)
    cf = _grid([[0.0, 0.0]], lats, lons)        # no cropland anywhere
    poly = box(116.97, -33.93, 117.08, -33.87)
    w = build_cell_weights(poly, rain["lat"].values, rain["lon"].values, cf,
                           crop_floor=0.05)
    assert w.fallback is True
    # fallback returns the value of the cell nearest the polygon centroid
    val = crop_weighted_mean(rain.values, w)
    assert val in (10.0, 20.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV poetry run pytest tests/test_sa2_aggregation.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.sa2_aggregation'`.

- [ ] **Step 3: Write the module**

```python
# scripts/sa2_aggregation.py
"""Crop-weighted spatial aggregation of a rainfall grid over SA2 polygons.

A single SA2 figure is the mean of every 0.05° grid cell whose centre falls
inside the SA2 polygon, weighted by the ABARES CLUM cropland fraction of each
cell (rainfall *where the wheat is*). Cells below `crop_floor` contribute zero
weight. If an SA2 has no cropland cells, we fall back to the single grid cell
nearest the polygon centroid and flag it.

No scipy: grid alignment uses xarray.sel(method="nearest"), never interp.
"""
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import xarray as xr
from shapely import contains_xy

REPO_ROOT = Path(__file__).resolve().parents[1]
CROPFRAC_NC = REPO_ROOT / "data" / "meta" / "clum_cropfrac_005.nc"
SA2_SHP = ("zip:///mnt/d/grains-data-store/wheatbelt_rainfall_analyser/"
           "data/meta/shapefiles/SA2_2021_AUST_SHP_GDA2020.zip")
CROP_FLOOR = 0.05  # CLUM cropland fraction threshold (matches the map's --crop-mask)


@dataclass
class CellWeights:
    """Precomputed cell selection + weights for one SA2 on one grid."""
    ji: np.ndarray        # lat indices of selected cells
    ii: np.ndarray        # lon indices of selected cells
    weights: np.ndarray   # cropland-fraction weight per selected cell
    fallback: bool        # True when no cropland → single centroid cell


def load_cropfrac() -> xr.DataArray:
    """Return the CLUM cropland-fraction grid (Band1)."""
    return xr.open_dataset(CROPFRAC_NC)["Band1"]


def load_sa2_polygons(codes: set[str] | None = None) -> dict[str, object]:
    """Return {sa2_code(2021): shapely geometry in EPSG:4326}."""
    g = gpd.read_file(SA2_SHP)[["SA2_CODE21", "geometry"]].to_crs(4326)
    g["SA2_CODE21"] = g["SA2_CODE21"].astype(str)
    if codes is not None:
        g = g[g["SA2_CODE21"].isin(codes)]
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    return dict(zip(g["SA2_CODE21"], g.geometry))


def build_cell_weights(geom, lat: np.ndarray, lon: np.ndarray,
                       cropfrac: xr.DataArray,
                       crop_floor: float = CROP_FLOOR) -> CellWeights:
    """Precompute the inside-polygon cells and their cropland weights.

    Cells are selected by centre-in-polygon test within the polygon bbox.
    Cropland fraction is sampled at each cell via nearest-index lookup.
    Weights below `crop_floor` are zeroed. If the total weight is zero,
    fall back to the single cell nearest the polygon centroid (fallback=True,
    weight 1.0) so the SA2 still gets a value.
    """
    minx, miny, maxx, maxy = geom.bounds
    ji = np.where((lat >= miny) & (lat <= maxy))[0]
    ii = np.where((lon >= minx) & (lon <= maxx))[0]
    if ji.size == 0 or ii.size == 0:
        return _centroid_fallback(geom, lat, lon)
    LON, LAT = np.meshgrid(lon[ii], lat[ji])
    inside = contains_xy(geom, LON, LAT)
    if not inside.any():
        return _centroid_fallback(geom, lat, lon)
    sub_ji = np.repeat(ji, ii.size).reshape(ji.size, ii.size)[inside]
    sub_ii = np.tile(ii, ji.size).reshape(ji.size, ii.size)[inside]
    cf = cropfrac.sel(lat=lat[sub_ji], lon=lon[sub_ii], method="nearest").values
    cf = np.nan_to_num(np.asarray(cf, dtype="float64"), nan=0.0)
    cf[cf < crop_floor] = 0.0
    if cf.sum() <= 0:
        return _centroid_fallback(geom, lat, lon)
    return CellWeights(ji=sub_ji, ii=sub_ii, weights=cf, fallback=False)


def _centroid_fallback(geom, lat: np.ndarray, lon: np.ndarray) -> CellWeights:
    c = geom.representative_point()
    cj = int(np.abs(lat - c.y).argmin())
    ci = int(np.abs(lon - c.x).argmin())
    return CellWeights(ji=np.array([cj]), ii=np.array([ci]),
                       weights=np.array([1.0]), fallback=True)


def crop_weighted_mean(grid2d: np.ndarray, w: CellWeights) -> float:
    """Weighted mean of grid2d over the precomputed cells, dropping NaN cells."""
    vals = grid2d[w.ji, w.ii]
    wt = w.weights.copy()
    good = np.isfinite(vals)
    vals, wt = vals[good], wt[good]
    if wt.sum() <= 0:
        return float("nan")
    return float((vals * wt).sum() / wt.sum())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV poetry run pytest tests/test_sa2_aggregation.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/sa2_aggregation.py tests/test_sa2_aggregation.py
git commit -m "feat(sa2): crop-weighted polygon aggregation module"
```

---

## Task 2: Crop-weighted month-to-date extractor

**Files:**
- Modify: `scripts/extract_sa2_partial_month_rainfall.py`
- Test: `tests/test_extract_partial_crop_weighted.py`

- [ ] **Step 1: Write the failing regression test (real data, WA anchors)**

```python
# tests/test_extract_partial_crop_weighted.py
"""Crop-weighted MTD must reproduce the confirmed WA June 1-28 2026 anchors."""
import pytest
pd = pytest.importorskip("pandas")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MTD = ROOT / "data/features/sa2_2026_06_mtd_cropwtd.csv"

ANCHORS = {"Gnowangerup": 38.1, "Wagin": 47.9, "Katanning": 35.7}


@pytest.mark.skipif(not (ROOT / "data/meta/daily_rain/2026.daily_rain.nc").exists(),
                    reason="2026 daily grid not present")
def test_wa_anchors(tmp_path):
    import subprocess
    out = ROOT / "data/features/sa2_2026_06_mtd_cropwtd.csv"
    subprocess.run(
        ["python", "scripts/extract_sa2_partial_month_rainfall.py",
         "--year", "2026", "--month", "6", "--method", "crop_weighted"],
        cwd=ROOT, check=True)
    df = pd.read_csv(out)
    for name, expected in ANCHORS.items():
        got = float(df.loc[df["sa2_name"] == name, "rainfall_mm"].iloc[0])
        assert abs(got - expected) <= 0.3, f"{name}: {got} vs {expected}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u VIRTUAL_ENV poetry run pytest tests/test_extract_partial_crop_weighted.py -q`
Expected: FAIL — `error: unrecognized arguments: --method` (the flag does not exist yet).

- [ ] **Step 3: Add the `--method` switch and crop-weighted path**

In `scripts/extract_sa2_partial_month_rainfall.py`:

3a. Add the new constant near the existing `EXTRACTION_METHOD`:

```python
CROP_WEIGHTED_METHOD = "cropfrac_weighted_polygon_mean"
```

3b. Import the aggregation helpers (after the existing `from scripts.extract_sa2_monthly_rainfall import (...)` block):

```python
from scripts.sa2_aggregation import (  # noqa: E402
    load_cropfrac, load_sa2_polygons, build_cell_weights, crop_weighted_mean,
)
```

3c. Add the argparse option (alongside `--year/--month/--mtd`):

```python
    parser.add_argument("--method", choices=["centroid", "crop_weighted"],
                        default="crop_weighted",
                        help="centroid grid cell (legacy) or crop-fraction "
                             "weighted polygon mean (default, grain-relevant)")
```

3d. In the extraction routine, branch on method. The centroid branch is the
existing code. Add the crop-weighted branch, which sums the daily grid over
days 1..N to a 2D array once, precomputes per-SA2 weights once, then writes one
row per SA2. Use these exact field values so the schema matches the centroid
output (extraction_method, source_variable, is_partial_month,
partial_month_through_day):

```python
    if args.method == "crop_weighted":
        codes = {r["sa2_code"] for r in sa2_rows}
        polys = load_sa2_polygons(codes)
        cropfrac = load_cropfrac()
        with xr.open_dataset(nc_path) as ds:
            da = ds["daily_rain"]
            jun = da.sel(time=da["time"].dt.month == month)
            through_day = int(jun["time"].dt.day.max())
            grid2d = jun.sum("time", skipna=False).values
            lat = jun["lat"].values
            lon = jun["lon"].values
        records = []
        for row in sa2_rows:
            geom = polys.get(row["sa2_code"])
            if geom is None:
                # 2016-coded SA2 absent from the 2021 shapefile (non-WA): skip
                # with a flag rather than guess. WA codes are all present.
                records.append(_partial_row(row, float("nan"), through_day,
                                            CROP_WEIGHTED_METHOD,
                                            "no_2021_polygon"))
                continue
            w = build_cell_weights(geom, lat, lon, cropfrac)
            val = crop_weighted_mean(grid2d, w)
            flag = "cropfrac_centroid_fallback" if w.fallback else "ok"
            records.append(_partial_row(row, val, through_day,
                                        CROP_WEIGHTED_METHOD, flag))
```

3e. Factor the row dict into a small helper `_partial_row(row, mm, through_day,
method, flag)` that returns the same 13-column schema the centroid path emits
(`year, month, sa2_code, sa2_name, state_name, rainfall_mm, extraction_method,
universe_source, source_file, source_variable, quality_flag, is_partial_month,
partial_month_through_day`) with `is_partial_month=True`, `source_variable="daily_rain"`.

3f. Choose the output path by method so centroid output is never clobbered:

```python
    suffix = "_cropwtd" if args.method == "crop_weighted" else ""
    out_path = (Path(args.mtd) if args.mtd
                else OUTPUT_DIR / f"sa2_{year}_{month:02d}_mtd{suffix}.csv")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `env -u VIRTUAL_ENV poetry run pytest tests/test_extract_partial_crop_weighted.py -q`
Expected: PASS — Gnowangerup≈38.1, Wagin≈47.9, Katanning≈35.7.

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_sa2_partial_month_rainfall.py tests/test_extract_partial_crop_weighted.py
git commit -m "feat(sa2): crop-weighted month-to-date extraction (--method)"
```

---

## Task 3: Crop-weighted history extractor

**Files:**
- Modify: `scripts/extract_sa2_monthly_rainfall.py`
- Test: `tests/test_extract_monthly_crop_weighted.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extract_monthly_crop_weighted.py
"""Crop-weighted monthly history tags rows and differs from centroid for WA."""
import pytest
pd = pytest.importorskip("pandas")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not list((ROOT / "data/meta/monthly_rain").glob("*.monthly_rain.nc")),
                    reason="monthly grids not present")
def test_crop_weighted_history_method_tag(tmp_path):
    import subprocess
    out = tmp_path / "wa_hist_cw.csv"
    subprocess.run(
        ["python", "scripts/extract_sa2_monthly_rainfall.py",
         "--states", "Western Australia", "--method", "crop_weighted",
         "--output", str(out)],
        cwd=ROOT, check=True)
    df = pd.read_csv(out)
    assert (df["extraction_method"] == "cropfrac_weighted_polygon_mean").all()
    # Gnowangerup June rows should exist and be finite
    g = df[(df["sa2_name"] == "Gnowangerup") & (df["month"] == 6)]
    assert g["rainfall_mm"].notna().any()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u VIRTUAL_ENV poetry run pytest tests/test_extract_monthly_crop_weighted.py -q`
Expected: FAIL — `unrecognized arguments: --method`.

- [ ] **Step 3: Add `--method` to the history extractor**

In `scripts/extract_sa2_monthly_rainfall.py`:

3a. Add constant `CROP_WEIGHTED_METHOD = "cropfrac_weighted_polygon_mean"` and
import `load_cropfrac, load_sa2_polygons, build_cell_weights, crop_weighted_mean`
from `scripts.sa2_aggregation`.

3b. Add `--method {centroid,crop_weighted}` (default `crop_weighted`) to argparse
and thread it through `run(...)` → `extract_one_file(...)`.

3c. In `extract_one_file`, when `method == "crop_weighted"`: load polygons +
cropfrac once per call; **precompute `CellWeights` per SA2 once** (the grid is
constant within a file), then for each monthly time-slice compute
`crop_weighted_mean(slice.values, w)`. Reuse the same NODATA handling
(`crop_weighted_mean` already drops NaN; mask cells `< NODATA_THRESHOLD` to NaN
before weighting):

```python
def extract_one_file(nc_path, sa2_rows, method="crop_weighted"):
    if method == "centroid":
        return _extract_centroid(nc_path, sa2_rows)   # existing body, renamed
    polys = load_sa2_polygons({r["sa2_code"] for r in sa2_rows})
    cropfrac = load_cropfrac()
    records = []
    with xr.open_dataset(nc_path) as ds:
        da = ds[SOURCE_VARIABLE]
        lat, lon = da["lat"].values, da["lon"].values
        weights = {r["sa2_code"]: (build_cell_weights(polys[r["sa2_code"]],
                                                       lat, lon, cropfrac)
                                   if r["sa2_code"] in polys else None)
                   for r in sa2_rows}
        for time_step in da.time:
            dt = pd.Timestamp(time_step.values)
            grid = da.sel(time=time_step).values
            grid = np.where(grid < NODATA_THRESHOLD, np.nan, grid)
            for row in sa2_rows:
                w = weights[row["sa2_code"]]
                if w is None:
                    mm, flag = float("nan"), "no_2021_polygon"
                else:
                    mm = crop_weighted_mean(grid, w)
                    flag = "cropfrac_centroid_fallback" if w.fallback else "ok"
                records.append(_monthly_row(dt, row, mm, CROP_WEIGHTED_METHOD,
                                            nc_path.name, flag))
    return records
```

3d. Factor the existing row dict (lines ~207–223) into `_monthly_row(dt, row, mm,
method, source_file, flag)` and have both branches use it (DRY), preserving the
exact 13-column schema.

- [ ] **Step 4: Run test to verify it passes**

Run: `env -u VIRTUAL_ENV poetry run pytest tests/test_extract_monthly_crop_weighted.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite (no regressions on the centroid path)**

Run: `env -u VIRTUAL_ENV poetry run pytest tests/test_silo_api_client.py tests/test_sa2_aggregation.py -q`
Expected: PASS (existing tests unaffected).

- [ ] **Step 6: Commit**

```bash
git add scripts/extract_sa2_monthly_rainfall.py tests/test_extract_monthly_crop_weighted.py
git commit -m "feat(sa2): crop-weighted monthly history extraction (--method)"
```

---

## Task 4: Review builder `--hist` override

**Files:**
- Modify: `scripts/build_sd_monthly_rainfall_review.py`

- [ ] **Step 1: Add a `--hist` argument**

The script hardcodes `SA2_HIST = ROOT / "data/features/sa2_monthly_rainfall_history_national.csv"`.
Add an argparse option (it already has `--mtd`):

```python
    parser.add_argument("--hist", default=None,
                        help="SA2 monthly history CSV (default: "
                             "data/features/sa2_monthly_rainfall_history_national.csv). "
                             "Pass the _cropwtd history to produce crop-weighted deciles.")
```

and use `Path(args.hist) if args.hist else SA2_HIST` wherever `SA2_HIST` is read.

- [ ] **Step 2: Smoke-test it still runs centroid by default**

Run: `env -u VIRTUAL_ENV poetry run python scripts/build_sd_monthly_rainfall_review.py --year 2026 --month 6`
Expected: writes `sa2_/sd_/state_2026_06_rainfall_review.csv`, `through_day=28`, no error.

- [ ] **Step 3: Commit**

```bash
git add scripts/build_sd_monthly_rainfall_review.py
git commit -m "feat(review): --hist override to feed crop-weighted SA2 history"
```

---

## Task 5: Regenerate WA crop-weighted products (data task)

**Files (data outputs, no code):**
- Create: `data/features/sa2_monthly_rainfall_history_wa_cropwtd.csv`
- Create: `data/features/sa2_2026_06_mtd_cropwtd.csv`
- Create: `data/features/sa2_2026_06_rainfall_review_cropwtd.csv` (+ sd_/state_ siblings)
- Create: `reports/figures/decile_grid_bom_WA_2026_06_sa2statewide_crop05_cropwtd.png`

- [ ] **Step 1: Build crop-weighted WA history**

Run:
```bash
env -u VIRTUAL_ENV poetry run python scripts/extract_sa2_monthly_rainfall.py \
  --states "Western Australia" --method crop_weighted \
  --output data/features/sa2_monthly_rainfall_history_wa_cropwtd.csv
```
Expected: `Written → data/features/sa2_monthly_rainfall_history_wa_cropwtd.csv`,
all `extraction_method=cropfrac_weighted_polygon_mean`.

- [ ] **Step 2: Build crop-weighted MTD (already produced by Task 2's test, rebuild explicitly)**

Run:
```bash
env -u VIRTUAL_ENV poetry run python scripts/extract_sa2_partial_month_rainfall.py \
  --year 2026 --month 6 --method crop_weighted
```
Expected: `sa2_2026_06_mtd_cropwtd.csv`, Gnowangerup≈38.1, Wagin≈47.9, Katanning≈35.7.

- [ ] **Step 3: Build crop-weighted review/deciles for WA**

Run:
```bash
env -u VIRTUAL_ENV poetry run python scripts/build_sd_monthly_rainfall_review.py \
  --year 2026 --month 6 \
  --hist data/features/sa2_monthly_rainfall_history_wa_cropwtd.csv \
  --mtd data/features/sa2_2026_06_mtd_cropwtd.csv
```
Then **rename** the three review outputs to `_cropwtd` siblings so they don't
clobber the centroid review:
```bash
for f in sa2 sd state; do
  mv data/features/${f}_2026_06_rainfall_review.csv \
     data/features/${f}_2026_06_rainfall_review_cropwtd.csv
done
```
Expected: crop-weighted `sa2_2026_06_rainfall_review_cropwtd.csv`. Sanity-check
Gnowangerup's decile rose materially from the centroid 2.9 (crop-weighted ~38 mm
vs its scaled median should land mid-pack, not bottom-decile).

- [ ] **Step 4: Compare centroid vs crop-weighted deciles for the three SA2s**

Run:
```bash
env -u VIRTUAL_ENV poetry run python - <<'PY'
import pandas as pd
c = pd.read_csv("data/features/sa2_2026_06_rainfall_review.csv")
w = pd.read_csv("data/features/sa2_2026_06_rainfall_review_cropwtd.csv")
for n in ["Gnowangerup","Wagin","Katanning"]:
    cc = c.loc[c.sa2_name==n,["rain_mm","decile_decimal"]].iloc[0]
    ww = w.loc[w.sa2_name==n,["rain_mm","decile_decimal"]].iloc[0]
    print(f"{n:12} centroid {cc.rain_mm:5.1f}mm d{cc.decile_decimal:.1f}  ->  "
          f"crop-wtd {ww.rain_mm:5.1f}mm d{ww.decile_decimal:.1f}")
PY
```
Expected: a printed before/after table confirming the basis shift (no hard
assert — this is the human review gate before adopting crop-weighting as default).

- [ ] **Step 5: Commit the data products**

```bash
git add data/features/*_cropwtd.csv
git commit -m "data(sa2): crop-weighted WA history, MTD and June review"
```

---

## Task 6: Documentation + house-style

**Files:**
- Modify: `docs/national_sa2_rainfall_expansion.md`

- [ ] **Step 1: Document the method, scoping, and `_cropwtd` convention**

Add a "Crop-weighted SA2 basis" section covering: (a) what crop-weighted means
vs centroid vs whole-polygon, with the Gnowangerup worked example (centroid
28.8 → crop-weighted 38.1); (b) the `--method crop_weighted` flag on both
extractors and the `_cropwtd` output convention; (c) the `--hist` review override;
(d) **WA is delivered; national is deferred** because non-WA SA2 rows are keyed to
2016 GeoJSON codes that do not all match the 2021 SA2 shapefile — national
rollout requires a 2016→2021 polygon reconciliation (see Phase 2 below).

- [ ] **Step 2: Commit**

```bash
git add docs/national_sa2_rainfall_expansion.md
git commit -m "docs(sa2): crop-weighted basis, scoping and file conventions"
```

---

## Phase 2 (follow-on, NOT in this plan): national rollout & default switch

Out of scope here; capture as issues:

1. **2016→2021 polygon reconciliation** for the non-WA universe so `load_sa2_polygons`
   resolves every `sa2_code` (the non-WA rows come from `SA2_ABS_Regions.geojson`
   with 2016 `SA2_MAIN16` codes). Until then crop-weighted national rows for
   unmatched codes carry `quality_flag="no_2021_polygon"` and NaN.
2. **Rebuild `sa2_monthly_rainfall_history_national.csv` crop-weighted** for all
   states, and re-run `build_sa2_rainfall_deciles.py` off it.
3. **Switch defaults**: once validated nationally, make `_cropwtd` the canonical
   filenames (drop the suffix) and retire the centroid path, or keep `--method`
   with `crop_weighted` default and the centroid path as a documented legacy mode.
4. **Map default**: decide whether `plot_decile_grid_bom.py` labels/deciles read
   the crop-weighted review by default.

---

## Self-Review notes (author)

- **Spec coverage:** capability (Task 1), MTD basis (Task 2), history basis (Task 3),
  decile plumbing (Task 4), WA regeneration + before/after gate (Task 5), docs (Task 6).
  National default-switch intentionally deferred to Phase 2 — flagged, not silently dropped.
- **No clobber:** every crop-weighted output uses a `_cropwtd` suffix; centroid
  products and the existing map are untouched until Phase 2 chooses to switch.
- **Type consistency:** `CellWeights` (ji, ii, weights, fallback) is produced by
  `build_cell_weights` and consumed by `crop_weighted_mean` in every task; the row
  schema is the same 13 columns across centroid and crop-weighted paths via the
  `_partial_row`/`_monthly_row` helpers.
- **Validation anchors** (Gnowangerup 38.1, Wagin 47.9, Katanning 35.7) are pinned
  by the Task 2 regression test, tying the pipeline output to the confirmed ad-hoc figures.
