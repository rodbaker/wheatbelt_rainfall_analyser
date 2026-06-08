# National SA2 Rainfall Expansion

## Goal

Extend the rainfall context pipeline from WA-only outputs to wheatbelt SA2
coverage across Western Australia, South Australia, Victoria, New South Wales,
and Queensland.

## Current Setup

`scripts/extract_sa2_monthly_rainfall.py` supports three SA2 universes:

| Universe | Description |
|---|---|
| `combined` | Default. Uses the WA 2021 QGIS universe plus non-WA rows from `data/meta/SA2_ABS_Regions.geojson`. |
| `geojson` | Uses all rows directly from `data/meta/SA2_ABS_Regions.geojson`. |
| `wa_csv` | Legacy WA-only 28-region universe from `data/meta/wa_wheatbelt_sa2_universe_2021.csv`. |

The default `combined` universe currently resolves to 192 SA2s:

| State | SA2s |
|---|---:|
| New South Wales | 46 |
| Queensland | 26 |
| South Australia | 41 |
| Victoria | 51 |
| Western Australia | 28 |

## NetCDF Source Data

Monthly rainfall grids come from the SILO public S3 bucket — no AWS credentials required.

| Property | Value |
|---|---|
| S3 bucket | `s3://silo-open-data` |
| S3 key pattern | `Official/annual/monthly_rain/{year}.monthly_rain.nc` |
| HTTPS URL | `https://s3-ap-southeast-2.amazonaws.com/silo-open-data/Official/annual/monthly_rain/{year}.monthly_rain.nc` |
| Local destination | `data/meta/monthly_rain/{year}.monthly_rain.nc` |
| File size | ~14 MB per year (12 monthly grids) |

### Downloading missing years

Use `scripts/download_silo_monthly_rain.py`. It skips existing files, writes via
atomic `.tmp` rename, enforces a 1 MB minimum size guard, and validates the
`monthly_rain` variable, 12 time steps, `lat`/`lon` dimensions, and correct year
in each time coordinate.

```bash
# Download specific missing years
.venv/bin/python scripts/download_silo_monthly_rain.py \
  --years 2006 2007 2008 2009 2010

# Dry-run (no writes)
.venv/bin/python scripts/download_silo_monthly_rain.py \
  --years 2006 2007 2008 2009 2010 --dry-run
```

Alternatively, sync directly from S3 (requires `aws` CLI):

```bash
aws s3 sync \
  s3://silo-open-data/Official/annual/monthly_rain/ \
  data/meta/monthly_rain/ \
  --exact-timestamps --no-sign-request
```

## Commands

### WA-only (existing outputs — do not overwrite)

These commands write to the established WA paths consumed by downstream scripts.
Do not redirect them to the national paths.

```bash
.venv/bin/python scripts/extract_sa2_monthly_rainfall.py --universe-source combined --states "Western Australia"
.venv/bin/python scripts/build_sa2_rainfall_deciles.py
```

### National run (safe — separate output paths)

Build monthly rainfall history for all five wheatbelt states, writing to a
dedicated national file that does not touch the existing WA outputs:

```bash
.venv/bin/python scripts/extract_sa2_monthly_rainfall.py \
  --universe-source combined \
  --output data/features/sa2_monthly_rainfall_history_national.csv
```

Build deciles from the national history:

```bash
.venv/bin/python scripts/build_sa2_rainfall_deciles.py \
  --input data/features/sa2_monthly_rainfall_history_national.csv \
  --output data/features/sa2_monthly_rainfall_deciles_national.csv
```

Build deciles for a single state from the national history:

```bash
.venv/bin/python scripts/build_sa2_rainfall_deciles.py \
  --input data/features/sa2_monthly_rainfall_history_national.csv \
  --output data/features/sa2_monthly_rainfall_deciles_sa.csv \
  --states "South Australia"
```

Build state-filtered history (alternative — extracts only the requested states):

```bash
.venv/bin/python scripts/extract_sa2_monthly_rainfall.py \
  --universe-source combined \
  --states "Western Australia,South Australia" \
  --output data/features/sa2_monthly_rainfall_history_wa_sa.csv
```

## Data Contract Notes

- `sa2_code` is the full ABS SA2 code used by the selected universe.
- `state_name` is preserved in both the rainfall history and decile outputs.
- `universe_source` is preserved so mixed-boundary outputs remain auditable.
- The extraction method is `centroid_nearest_grid_cell`; values are not
  polygon-area averages.

## Climatology Key

National deciles use **`state_name + sa2_code + month`** as the climatology key.
Four SA2 codes appear in two different states within the combined universe (192
slots, 188 unique `sa2_code` values).  Without `state_name` in the key those
duplicate codes would pool history across states and produce incorrect baselines.
Legacy single-state inputs that lack a `state_name` column fall back to
`sa2_code + month` automatically.

## Known Null-Rainfall SA2s

Two SA2s in the combined universe persistently return null rainfall for all
months.  They are retained in the output and flagged with
`climatology_quality_flag = "null_rainfall"` rather than imputed or removed.
This preserves auditability and keeps the universe count stable.

## 2025 NetCDF Refresh

The 2025 SILO NetCDF was refreshed to full Jan–Dec coverage.  The original
file (Jan-only) has been retained as:

    data/meta/monthly_rain/2025.monthly_rain.nc.stale_jan_only.bak

## Remaining Work

1. Decide whether the long-term national canonical universe should use ASGS
   2016, ASGS 2021, or a mixed compatibility layer.
2. Optimise `scripts/build_sa2_rainfall_deciles.py`. The current row-wise
   implementation produces correct national output, but the 48,384-row national
   build takes several minutes. Rewrite it around grouped/vectorised operations
   while preserving exact output columns and legacy behaviour.
3. Replace centroid nearest-cell extraction with polygon-area averaging if the
   extra precision is required.
4. Add crop-specific seasonal windows by state instead of reusing WA timing
   assumptions everywhere.
5. Add state-level weighted rainfall summaries for wheat, barley, and canola.
6. Wire national SA2 deciles into downstream seasonal cross-check outputs with
   cautious non-causal language.

## Next Engineering TODO

Optimise the national decile builder before wiring these outputs downstream.

Current status:

- `data/features/sa2_monthly_rainfall_history_national.csv` has 48,384 rows.
- `data/features/sa2_monthly_rainfall_deciles_national.csv` has 48,384 rows.
- QA passed: 47,880 `ok` rows and 504 persistent `null_rainfall` rows.
- Duplicate cross-state SA2 codes are handled by using
  `state_name + sa2_code + month` as the climatology key.
- The build is correct but slow because `compute_deciles()` loops row by row.

Acceptance criteria for the optimisation:

- Preserve existing CLI behaviour for legacy WA inputs.
- Preserve `--states`, `--input`, and `--output`.
- Preserve output schema and column order.
- Preserve the national climatology key:
  `state_name + sa2_code + month` when `state_name` is present, otherwise
  `sa2_code + month`.
- Preserve `null_rainfall` and `insufficient_history(...)` semantics.
- Existing tests in `tests/test_build_sa2_rainfall_deciles.py` must pass.
- Add a regression test comparing vectorised output to the current row-wise
  logic on a small mixed-state fixture.
- Target runtime for the 48,384-row national file should be seconds, not minutes.

## National Rainfall Features Builder (T-20260520-001, 2026-05-20)

`scripts/build_sa2_rainfall_features.py` now supports three `--source` modes:

| Source | Behaviour | Coverage |
|---|---|---|
| `canonical-monthly` | Reads `data/features/sa2_monthly_rainfall_history_national.csv`. Monthly + window-total features only. Daily-derived columns null. | All 188 grain SA2s, every year in canonical file |
| `duckdb-stations` | Legacy behaviour. Daily station data from DuckDB → SA2 mean. | Dense in WA, sparse elsewhere |
| `hybrid` (default) | `canonical-monthly` base + `duckdb-stations` overlay on the four `autumn_break_*` / `dry_spell_*` columns where station data exists. Monthly columns always come from the canonical source. | All 188 grain SA2s monthly + WA daily |

**Schema additions to `data/features/rainfall_features_sa2_season.csv`:**

| Column | Values |
|---|---|
| `sa2_code_9dig` | 9-digit SA2_MAIN form (`sa2_code` remains the 5-digit join key) |
| `monthly_features_source` | `canonical_national` (new) or `duckdb_stations` (legacy) |
| `daily_features_status` | `monthly_only`, `duckdb_stations`, or future `daily_grid` |
| `partial_through_day` | Last day-of-month included in a partial-month value (e.g. 19 for May 2026 MTD); null for full-month rows |

**SA2 code convention:**
`sa2_code` is the 5-digit ABS form (state-first-digit + last-4-digits of the 9-digit MAIN16 code). This preserves the join contract with `crop_context.station_sa2_5dig16`. Example: `501021007` → `51007`.

**Coverage (after rollout):**
- Features file: 4,180 rows = 190 SA2s × 22 calendar years (2 SA2s have centroid-on-ocean nodata cells)
- Crop-context join: 186/188 SA2s matched (99%): NSW 46/46, QLD 26/26, VIC 47/47, WA 28/28, SA 39/41
- Weighted summary 2026: all 5 states populated with real Pre-seeding / Sowing-window / In-crop / Apr–Oct / May–Oct metrics
- Weekly outlook renders five per-state sections under the `# Australian Wheat Rainfall` H1

**Deferred (backlog T-20260520-002):** Centroid-based daily extraction from historical `{year}.daily_rain.nc` tiles so dry-spell and autumn-break columns populate for non-WA SA2s and for all 192 SA2s pre-2026. Unlocked by the same ~8 GB historical daily NC download already parked under v1.2 like-for-like deciles.
