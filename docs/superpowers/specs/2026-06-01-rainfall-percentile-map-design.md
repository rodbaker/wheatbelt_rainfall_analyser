# WA Wheatbelt Rainfall Percentile Map — Design

**Date:** 2026-06-01
**Status:** Approved design (pending user spec review)
**Goal:** Reproduce, inside the `wheatbelt_rainfall_analyser` project, the QGIS-made
"WA Wheatbelt July Rainfall Percentiles" map — as a parameterised, reproducible
Python tool — so any month/year can be regenerated from the SILO gridded data we
already hold on the HDD.

Reference artifact: `reports/figures/wa_july_percentiles.png` (made in QGIS).

---

## Decisions locked in brainstorming

| Topic | Decision |
|---|---|
| Render style | **Raster surface** (per-grid-cell percentile), not a flat per-region choropleth — matches the within-region gradients of the QGIS map. |
| Baseline | **1911 → latest complete year**, exposed as `--baseline-start` (default 1911) and `--baseline-end` (default latest complete year on disk). Requires a one-time ~1.3 GB SILO `monthly_rain` backfill to the HDD-symlinked path. |
| Target | Monthly rainfall percentile for `--month` and `--year`. |
| Ranking | Per cell, compare the target month against the **same calendar month** across baseline years. **Target year is included in its own baseline** (matches a fixed climatology dataset). |
| Percentile formula | `pct = 100 * ((baseline < target).sum(axis=0) + 1) / N`. Strict `<` so values equal to the target do **not** lift its rank (documented tie behaviour). Clamp to 100 defensively. NaN-preserving over ocean/nodata cells. |
| Colour scale | 10 fixed bins via `BoundaryNorm([0,10,20,30,40,50,60,70,80,90,100])`; discrete 10-colour palette sampled from `RdBu` (red = dry ≤10, pale mid, blue = wet >90). Bin labels `<=10, 10-20, …, 80-90, >90`. Exact BoM hex ramp is a later refinement only if visual comparison shows a meaningful mismatch. |
| Boundaries overlay | `--regions sa2|sd`, **default `sa2`**. SA2 reproduces the reference map's outlines + town labels directly. SD is a first-class option via the **same overlay function** — a region column selected by the flag, geometries **dissolved only for `sd`**. No numerical regional aggregation in scope. |
| Rendering stack | `xarray` + Matplotlib `pcolormesh` for the raster; `geopandas` for boundary outlines + labels. **No `rasterio`** unless grid metadata or export format actually requires it (it does not, for PNG). |
| Output | `reports/figures/wa_{month}_{year}_percentiles.png` — raster surface, SD/SA2 overlay, title, binned legend, source note, and **baseline period in the caption**. |
| Dependencies | Add only what the implementation needs (`geopandas` + its stack), in a **separate dependency commit**. |
| Backfill | Resumable, validate-before-install downloads, written directly through the HDD `monthly_rain/` symlink. |

---

## Components (isolated units)

Each unit has one purpose, a defined interface, and is independently testable.

### 1. Monthly backfill downloader — `scripts/download_silo_monthly_rain.py` (harden existing)

Mirror the just-hardened daily downloader. Refactor to an injectable
`fetch(tmp)` + `install_year(...)`:

- Temp file placed **inside** the destination dir (`monthly_rain/`, on `/mnt/d`)
  → `os.replace()` is an intra-filesystem atomic rename.
- `validate_monthly_rain(path, year)`: variable `monthly_rain` present, `lat`/`lon`
  dims present, 12 time steps, all timestamps in `year`. Validation runs on the
  temp file **before** the replace.
- On validation failure or fetch error: existing file preserved, temp removed.
- **Resumable:** existing valid files are skipped, so re-running the backfill after
  an interruption continues where it stopped. (No HTTP range/partial-resume within
  a single file — granularity is per-year-file, which is sufficient.)

**Interface:** `install_year(year, fetch, dest_dir=OUTPUT_DIR, allow_replace=False, require_complete=True, min_bytes=...) -> str` (`"installed"|"skipped"|"invalid: …"|"error: …"`), matching the daily downloader's contract.

**Depends on:** `xarray`, `urllib`. No project deps.

### 2. Percentile engine — `src/rainfall/percentiles.py` (new, pure functions, no plotting)

- `load_month_stack(month, year, baseline_start, baseline_end, grids_dir) -> (target_grid, baseline_stack, years)`:
  opens `{yr}.monthly_rain.nc` for each baseline year, selects the `month` slice,
  returns the target 2-D grid and the `(N, lat, lon)` baseline stack. Raises a
  clear error naming any **missing** baseline-year file (→ "run the backfill").
- `cell_percentile(target_grid, baseline_stack) -> pct_grid`:
  `100 * ((baseline_stack < target_grid).sum(axis=0) + 1) / N`, clamped to 100,
  NaN where the target cell is NaN (ocean/nodata).

**Interface:** pure NumPy/xarray in, NumPy/xarray out. No file writes, no Matplotlib.
**Most heavily tested unit.**

### 3. Boundary layer — `src/rainfall/boundaries.py` (new)

- `load_wheatbelt_regions(level: str) -> GeoDataFrame` where `level in {"sa2","sd"}`:
  - Source: `data/meta/SA2_ABS_Regions.geojson`. **This file is national** (190
    features across all states), so first **filter to the wheatbelt subset** that
    matches the reference map's region set (the QGIS map shows the WA wheatbelt
    SA2s — Northampton…Esperance/Albany). The filter must be made explicit and
    verified against the reference; candidate keys present in the geojson are
    `STE_NAME16 == "Western Australia"` plus an SA3/SA4 grain-belt filter, but the
    authoritative subset is whatever reproduces the reference extent.
  - `sa2`: keep the SA2 name column (`SA2_NAME16`) for labels.
  - `sd`: **dissolve to Statistical Division using the project's existing
    convention** — the SA2→SD correspondence already used by
    `scripts/build_sd_sa2_breakdown.py` (`SD_CODE11`/`SD_NAME11`), NOT an ad-hoc
    SA3/SA4 dissolve. Region/label column = `SD_NAME11`.
  - One overlay function, region/label column selected by `level`; dissolve only
    when `sd`. Returns geometries in EPSG:4326 to match the SILO grid.
- `clip_mask(regions) -> geometry`: union of the wheatbelt polygons, used to blank
  raster cells outside the wheatbelt (reproduce the reference map's hard clip).

**Open detail for implementation:** the exact wheatbelt subset filter and the
precise SA2→SD correspondence file path must be pinned down by reading
`build_sd_sa2_breakdown.py` and comparing the resulting extent to the reference
PNG before the boundary unit is considered done. Flagged as the first task's
acceptance check.

**Depends on:** `geopandas` (new dependency).

### 4. Renderer — `src/rainfall/render.py` (new)

- `render_percentile_map(pct_grid, regions, *, month, year, baseline_start, baseline_end, out_path, level)`:
  - `pcolormesh(lon, lat, pct_grid)` with `BoundaryNorm([0,10,…,100])` + discrete
    10-colour RdBu (`ListedColormap` sampled from `RdBu`).
  - Cells outside `clip_mask` masked → white, matching the reference.
  - Boundary outlines from `regions`; region labels at polygon representative points.
  - Title `WA Wheatbelt {Month name} Rainfall Percentiles`.
  - Discrete legend `<=10 … >90`.
  - Caption: `Baseline: {baseline_start}–{baseline_end} · Source: SILO (LongPaddock), monthly_rain`.
  - Writes PNG to `out_path` (default `reports/figures/wa_{month:02d}_{year}_percentiles.png`).

**Depends on:** Matplotlib, geopandas. Runs headless (`Agg`).

### 5. CLI — `scripts/plot_rainfall_percentiles.py` (new)

```
python scripts/plot_rainfall_percentiles.py \
    --month 7 --year 2024 \
    [--baseline-start 1911] [--baseline-end 2025] [--regions sa2|sd] [--out PATH]
```

Wires units 2→3→4. `--baseline-end` defaults to the latest complete year present
on disk. Fails clearly (naming the missing years) if the baseline is incomplete,
directing the user to run the backfill.

---

## Data flow

```
CLI (--month --year --baseline-* --regions)
  → boundaries.load_wheatbelt_regions(level)   → regions + clip_mask
  → percentiles.load_month_stack(...)          → target_grid, baseline_stack
  → percentiles.cell_percentile(...)           → pct_grid  (clipped to mask)
  → render.render_percentile_map(...)          → reports/figures/*.png
```

---

## Error handling

- **Missing baseline year(s):** `load_month_stack` raises `FileNotFoundError`
  listing the absent years; CLI surfaces it with "run download_silo_monthly_rain.py".
- **Partial target month** (e.g. current month incomplete): out of scope — the tool
  targets completed months; document that the target year/month must be present and
  complete in `monthly_rain`.
- **All-NaN / ocean cells:** preserved as NaN → masked white, never coloured.
- **Backfill:** validate-before-replace guarantees a bad download never lands.

---

## Testing strategy (TDD)

| Unit | Tests |
|---|---|
| Percentile engine | Hand-computed 3×3×N toy stack: formula correctness; **tie** (baseline value == target does not lift rank); **clamp** to 100 (target is max); NaN target → NaN out; known mid-rank value. |
| Backfill downloader | Reuse the daily-downloader test pattern: temp inside dest dir; validation failure preserves existing file; successful atomic replace; temp cleanup on failure; **resume** (skip existing valid file). |
| Boundary layer | `sa2` returns expected wheatbelt polygon count with label column; `sd` dissolves to the expected (smaller) SD count with valid geometry; CRS is EPSG:4326. |
| Renderer | Smoke: runs headless, writes a non-empty PNG; correct number of legend bins. Visual fidelity to the reference is eyeballed, **not** asserted pixel-wise. |

---

## Commit plan (separate, per instruction)

1. **deps:** add `geopandas` (+ resolved stack) to `requirements.txt` / `pyproject.toml`.
2. **feat: 1911 monthly_rain backfill** — harden monthly downloader + tests. (The
   ~1.3 GB backfill *run* is an operational step to the HDD, not part of a commit.)
3. **feat: rainfall percentile map** — engine + boundaries + renderer + CLI + tests.

`daily_rain.bak-premigrate/` stays in place (unrelated to this work; awaits one real
daily refresh as already documented).

---

## Out of scope (YAGNI)

- Numerical per-region aggregation (SD/SA2 mean percentiles).
- Exact BoM hex palette (later refinement if visual mismatch).
- `rasterio` / GeoTIFF export.
- Animations / multi-panel figures.
- Daily or seasonal (multi-month) percentile windows.
