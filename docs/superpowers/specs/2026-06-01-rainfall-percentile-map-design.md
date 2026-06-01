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
| Baseline | **1911 → latest complete year**, exposed as `--baseline-start` (default 1911) and `--baseline-end` (default = latest *structurally complete* year, see CLI §5 — a grid with 12 timestamps all in that year). Requires a one-time ~1.3 GB SILO `monthly_rain` backfill to the HDD-symlinked path. |
| Target | Monthly rainfall percentile for `--month` and `--year`. |
| Ranking | Per cell, compare the target month against the **same calendar month** across baseline years. **The target year is included in the baseline only when it falls inside the selected complete-year interval** (`baseline_start..baseline_end`). A completed month in a partial current-year file (e.g. Mar 2026) can still be mapped against the latest *complete* annual baseline that excludes 2026. |
| Percentile formula | Per cell: `pct = 100 * (count(baseline < target) + 1) / n_valid`, where `n_valid` is the number of **non-NaN** baseline values **in that cell** (not a global N). Strict `<` so values equal to the target do **not** lift its rank (documented tie behaviour). Clamp to 100 defensively. Return NaN if the target cell is NaN **or** the cell has zero valid baseline values. |
| Colour scale / bins | 10 right-closed bins. Compute bin index with `np.digitize(pct, [10,20,30,40,50,60,70,80,90], right=True)` → indices 0–9, rendered categorically with a discrete 10-colour `ListedColormap` sampled from `RdBu` (red = dry, pale mid, blue = wet). Legend labels `<=10, 10-20, …, 80-90, >90`. (Right-closed so exactly 10 → the `<=10` bin, matching the label.) Exact BoM hex ramp is a later refinement only if visual comparison shows a meaningful mismatch. |
| Boundaries overlay | `--regions sa2|sd`, **default `sa2`**. SA2 reproduces the reference map's outlines + town labels directly. SD is a first-class option via the **same overlay function** (region/label column selected by the flag; geometries **dissolved only for `sd`**). **SD dissolve strategy is unresolved** — the only in-repo concordance is 2021-SA2→2011-SD keyed differently from the 2016-SA2 geojson, and it lives at an external absolute path. A repo-managed SD mapping or SD boundary asset must be pinned before SD is implementable (see Open Items). No numerical regional aggregation in scope. |
| Rendering stack | `xarray` + **Matplotlib** `pcolormesh` for the raster; `geopandas` for boundary outlines + labels. **No `rasterio`** (PNG output does not require it). |
| Output | `reports/figures/wa_{month}_{year}_percentiles.png` — raster surface, SA2/SD overlay, title, binned legend, source note, and **baseline period in the caption**. |
| Dependencies | Add **`matplotlib` and `geopandas`** (let resolution provide the GeoPandas stack: shapely, pyproj, fiona), in a **separate dependency commit**. |
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
- **Resumable, validate-before-skip:** an existing file is skipped **only if it
  passes `validate_monthly_rain`**. An existing file that is present but invalid
  (truncated/partial from an interrupted run) does **not** silently count as done —
  it fails clearly and requires `--replace` to re-fetch. Re-running the backfill
  thus continues from where it stopped without trusting half-written files. (No HTTP
  range/partial-resume within a single file — granularity is per-year-file.)

**Interface:** `install_year(year, fetch, dest_dir=OUTPUT_DIR, allow_replace=False, require_complete=True, min_bytes=...) -> str` (`"installed"|"skipped"|"invalid: …"|"error: …"`), matching the daily downloader's contract.

**Depends on:** `xarray`, `urllib`. No project deps.

### 2. Percentile engine — `src/rainfall/percentiles.py` (new, pure functions, no plotting)

- `load_month_stack(month, year, baseline_start, baseline_end, grids_dir) -> (target_grid, baseline_stack, years)`:
  opens `{yr}.monthly_rain.nc` for each baseline year, selects the `month` slice,
  returns the target 2-D grid and the `(N, lat, lon)` baseline stack. Raises a
  clear error naming any **missing** baseline-year file (→ "run the backfill").
- `cell_percentile(target_grid, baseline_stack) -> pct_grid`:
  per cell, `100 * (count(baseline < target) + 1) / n_valid`, where `n_valid`
  counts the **non-NaN** baseline values **in that cell** (NaNs in the stack are
  ignored, not counted in the denominator and never counted as `< target`).
  Clamp to 100. Return NaN where the target cell is NaN **or** `n_valid == 0`.

**Interface:** pure NumPy/xarray in, NumPy/xarray out. No file writes, no Matplotlib.
**Most heavily tested unit.**

### 3. Boundary layer — `src/rainfall/boundaries.py` (new)

- `load_wheatbelt_regions(level: str) -> GeoDataFrame` where `level in {"sa2","sd"}`:
  - Source: `data/meta/SA2_ABS_Regions.geojson`. **This file is national** (190
    features across all states). The wheatbelt subset is **exactly the 26 WA
    features** — these match the reference PNG's region set one-for-one — selected
    explicitly with:
    ```python
    regions[regions["STE_NAME16"] == "Western Australia"]
    ```
    No additional SA3/SA4 filter is needed.
  - `sa2`: keep the SA2 name column (`SA2_NAME16`) for labels. **This is the
    default and reproduces the reference map.**
  - `sd`: dissolve the 26 WA SA2 features to Statistical Division. **The mapping
    is unresolved (blocking for SD only):** the in-repo concordance used by
    `scripts/build_sd_sa2_breakdown.py` is keyed on **2021** SA2 codes
    (`SA2_CODE21`) → **2011** SD (`SD_CODE11`), but the overlay geojson carries
    **2016** SA2 keys (`SA2_MAIN16`), so the keys do not align; that concordance
    also lives at an **external absolute path** outside the repo. Before SD is
    implemented, pin one of: (a) a small repo-managed `SA2_2016 → SD` lookup
    committed under `data/meta/`, or (b) a repo-managed SD boundary asset to load
    directly. Region/label column = SD name.
  - One overlay function, region/label column selected by `level`; dissolve only
    when `sd`. Returns geometries in EPSG:4326 to match the SILO grid.
- `clip_mask(regions) -> geometry`: union of the 26 wheatbelt polygons, used to
  blank raster cells outside the wheatbelt (reproduce the reference map's hard clip).

**Depends on:** `geopandas` (new dependency).

### 4. Renderer — `src/rainfall/render.py` (new)

- `render_percentile_map(pct_grid, regions, *, month, year, baseline_start, baseline_end, out_path, level)`:
  - Convert `pct_grid` → bin index `np.digitize(pct, [10,20,…,90], right=True)`
    (0–9), then `pcolormesh(lon, lat, bin_index)` with a discrete 10-colour
    `ListedColormap` sampled from `RdBu` (red = dry, blue = wet). NaN cells stay
    masked. (Right-closed so pct == 10 → bin 0, the `<=10` class.)
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

Wires units 2→3→4. `--baseline-end` defaults to the **latest complete year**
present on disk, defined **structurally**, not by filename existence: a year is
"complete" iff its `{yr}.monthly_rain.nc` holds **12 timestamps all belonging to
that year**. (Concretely, `2026.monthly_rain.nc` exists but holds only Jan–Apr
2026, so it is *not* complete → the default `--baseline-end` is 2025.) A
`latest_complete_year(grids_dir)` helper encapsulates this and is unit-tested.
Fails clearly (naming the missing years) if the baseline interval is incomplete,
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
- **Target in a partial-year file:** a *completed* month inside a current-year
  partial file (e.g. Mar 2026, where `2026.monthly_rain.nc` holds Jan–Apr) **is
  mappable** — its month slice is read from the partial file and ranked against the
  latest *complete* annual baseline (which excludes the partial year). What is out
  of scope is an *incomplete* target month (the requested month not present in the
  target file) → fail clearly.
- **All-NaN / ocean cells:** preserved as NaN → masked white, never coloured.
- **Backfill:** validate-before-replace guarantees a bad download never lands.

---

## Testing strategy (TDD)

| Unit | Tests |
|---|---|
| Percentile engine | Hand-computed 3×3×N toy stack: formula correctness; **tie** (baseline value == target does not lift rank); **clamp** to 100 (target is max); NaN target → NaN out; known mid-rank value; **baseline-NaN policy** (a cell with some NaN baseline years divides by `n_valid`, not global N; a cell with all-NaN baseline → NaN out). |
| Latest-complete-year helper | `latest_complete_year` returns the newest year whose grid has 12 timestamps all in that year; a partial current-year file (Jan–Apr only) is excluded. |
| Backfill downloader | Reuse the daily-downloader test pattern: temp inside dest dir; validation failure preserves existing file; successful atomic replace; temp cleanup on failure; **validate-before-skip** (an existing *valid* file is skipped; an existing *invalid* file is not silently accepted — fails without `--replace`). |
| Boundary layer | `sa2` returns **exactly 26** WA polygons with the `SA2_NAME16` label column; CRS is EPSG:4326. (`sd` tests deferred until the SD mapping is pinned — see Open Items.) |
| Renderer | Smoke: runs headless, writes a non-empty PNG; **right-closed binning** (pct == 10 lands in the `<=10` bin via `np.digitize(..., right=True)`); correct number of legend bins. Visual fidelity to the reference is eyeballed, **not** asserted pixel-wise. |

---

## Commit plan (separate, per instruction)

1. **deps:** add **`matplotlib` and `geopandas`** to `requirements.txt` /
   `pyproject.toml`; let resolution provide the GeoPandas stack (shapely, pyproj,
   fiona).
2. **feat: 1911 monthly_rain backfill** — harden monthly downloader + tests. (The
   ~1.3 GB backfill *run* is an operational step to the HDD, not part of a commit.)
3. **feat: rainfall percentile map** — engine + `latest_complete_year` helper +
   SA2 boundaries + renderer + CLI + tests. SD overlay lands here **only if** the
   SD mapping (Open Items) is pinned first; otherwise SD ships in a follow-up and
   this commit is SA2-only (which fully reproduces the reference map).

`daily_rain.bak-premigrate/` stays in place (unrelated to this work; awaits one real
daily refresh as already documented).

---

## Open items (resolve before / during planning)

1. **SD overlay mapping — blocking for SD only (not for the reference map).**
   The 2016-SA2 overlay geojson cannot be dissolved with the existing
   2021-SA2→2011-SD concordance (key mismatch) and that concordance is at an
   external absolute path. Decide before SD is implemented: (a) commit a small
   repo-managed `SA2_2016 → SD` lookup under `data/meta/`, or (b) commit a
   repo-managed SD boundary asset to load directly. **SA2 (the default) is fully
   unblocked** and reproduces the reference map, so SD can be deferred to a
   follow-up without holding up the main deliverable.

---

## Out of scope (YAGNI)

- Numerical per-region aggregation (SD/SA2 mean percentiles).
- Exact BoM hex palette (later refinement if visual mismatch).
- `rasterio` / GeoTIFF export.
- Animations / multi-panel figures.
- Daily or seasonal (multi-month) percentile windows.
