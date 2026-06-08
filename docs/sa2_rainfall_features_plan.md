# SA2 Rainfall Features — Design Plan

## Purpose

Produce a seasonal rainfall feature table aggregated to ABS SA2 regions.
The primary use case is joining to ABS Agricultural Census crop area/production
data to support crop-weighted yield-risk analysis for the weekly grains market
report assembler.

**Output**: `data/features/rainfall_features_sa2_season.csv`

---

## Inputs

| Source | Path | Notes |
|---|---|---|
| Daily weather observations | `data/weather.duckdb` → `weather_observations` | Primary data store |
| Station metadata | `data/meta/wheatbelt_stations.csv` | Latitude, longitude, SA2 code, state |
| Station–region crosswalk | `data/meta/station_regions.csv` | SA2/SA3/SA4 names |
| Crop calendars | `config/crop_calendars.yaml` | Phenological windows |
| ABS crop context (Phase 3) | `data/meta/crop_context_sa2.csv` | Historical area/production — join later |

### Column mapping notes

`wheatbelt_stations.csv` uses `SA2_5DIG16` (5-digit code) and `SA2_NAME16`.
`station_regions.csv` uses `station_id` + `sa2_name`. Use `station_regions.csv`
as the primary SA2 name lookup; keep `SA2_5DIG16` as the grouping key.
`station_id` must be treated as a string throughout — leading zeros are significant.

---

## Output Schema: `rainfall_features_sa2_season.csv`

One row per `(season_year, sa2_code)`.

| Column | Type | Description |
|---|---|---|
| `season_year` | integer | Wheat season year (sowing year). 2025 = Apr 2025 – Mar 2026. |
| `state_name` | string | Australian state name (e.g. `Western Australia`) |
| `sa2_code` | string | 5-digit SA2 code from `SA2_5DIG16` (kept as string) |
| `sa2_name` | string | SA2 name from `station_regions.csv` or `wheatbelt_stations.csv` |
| `station_count` | integer | Number of stations with ≥1 observation in this season |
| `contributing_station_ids` | string | Pipe-separated list of station IDs contributing to this row |
| `aggregation_method` | string | `simple_mean` (v1); `area_weighted_mean` after ABS join |
| `rainfall_total_apr_oct_mm` | float | Station-mean total rainfall Apr–Oct (mm) |
| `rainfall_total_may_oct_mm` | float | Station-mean total rainfall May–Oct (mm) |
| `monthly_rainfall_jan_mm` | float | Station-mean January total (mm) |
| `monthly_rainfall_feb_mm` | float | Station-mean February total (mm) |
| `monthly_rainfall_mar_mm` | float | Station-mean March total (mm) |
| `monthly_rainfall_apr_mm` | float | Station-mean April total (mm) |
| `monthly_rainfall_may_mm` | float | Station-mean May total (mm) |
| `monthly_rainfall_jun_mm` | float | Station-mean June total (mm) |
| `monthly_rainfall_jul_mm` | float | Station-mean July total (mm) |
| `monthly_rainfall_aug_mm` | float | Station-mean August total (mm) |
| `monthly_rainfall_sep_mm` | float | Station-mean September total (mm) |
| `monthly_rainfall_oct_mm` | float | Station-mean October total (mm) |
| `monthly_rainfall_nov_mm` | float | Station-mean November total (mm) |
| `monthly_rainfall_dec_mm` | float | Station-mean December total (mm) |
| `sowing_window_rain_mm` | float | Apr–Jun total (mm) |
| `in_crop_rain_mm` | float | May–Oct total (mm) |
| `flowering_rain_mm` | float | Sep–Oct total (mm) |
| `grain_fill_rain_mm` | float | Oct–Nov total (mm) |
| `harvest_rain_mm` | float | Nov–Jan total (mm) |
| `autumn_break_date` | ISO date | Date of first qualifying break event (nullable) |
| `autumn_break_7d_mm` | float | 7-day rainfall total at the break date (nullable) |
| `autumn_break_status` | string | `early`, `on_time`, `late`, or `absent` |
| `dry_spell_days_7d_lt_5mm` | float | Station-average days with rolling 7d rainfall < 5 mm (in-season) |
| `dry_spell_days_14d_lt_10mm` | float | Station-average days with rolling 14d rainfall < 10 mm (in-season) |
| `data_quality_score` | float | Weighted composite quality score (0.0–1.0) across contributing stations |
| `source_dataset` | string | `silo_patched_point` |
| `pipeline_version` | string | Semver string of the feature pipeline |
| `created_at` | timestamp | UTC ISO timestamp when the row was written |

---

## Season-Year Definition

A wheat season year is the calendar year in which sowing occurs:

- **Season 2025** = Apr 2025 – Mar 2026
- For a date `d`, `season_year = year(d) if month(d) >= 4 else year(d) - 1`

Months that straddle the boundary (Jan–Mar) belong to the **previous** season year.

---

## Phenological Windows

All dates are representative WA wheatbelt defaults from `config/crop_calendars.yaml`.

| Window | Calendar months | `season_year` offset |
|---|---|---|
| Sowing | Apr–Jun | same year |
| In-crop | May–Oct | same year |
| Flowering | Sep–Oct | same year |
| Grain fill | Oct–Nov | same year |
| Harvest | Nov–Jan | Nov–Dec same year, Jan next calendar year |

Autumn break detection: first date within Apr–Jun where the trailing 7-day
rainfall ≥ 25 mm (or single-day ≥ 10 mm). Status boundaries (WA wheatbelt
defaults):
- `early` if before May 15
- `on_time` if May 15 – Jun 15
- `late` if after Jun 15
- `absent` if no qualifying event found in Apr–Jun

---

## Aggregation Method (v1)

1. Compute all features at **station level** for each season.
2. Group by `(season_year, sa2_code)` and take the **simple mean** across
   contributing stations.
3. Missing rainfall is treated as missing (not zero). Station-months with
   <80% daily coverage are excluded from the window total.
4. `data_quality_score` = mean of per-station SILO quality scores, where
   `observed(0)→1.0`, `interpolated(15)→0.8`, `lower_density(25)→0.7`,
   `lower_quality(75)→0.6`, `synthetic(35)→0.3`, `missing(999)→0.0`.

---

## Phase 3: ABS Crop-Area Weighted Aggregation

After `data/meta/crop_context_sa2.csv` is validated:
- Join on `(sa2_code, season_year)` using the most recent ABS census year as
  a proxy weight.
- Replace `aggregation_method = simple_mean` with `area_weighted_mean` for
  wheat crop area weighting.
- Add `crop_area_weighted` boolean column.

Do not implement until Phase 2 is tested.

---

## Implementation Plan

### Script: `scripts/build_sa2_rainfall_features.py`

CLI flags:
- `--season-year INTEGER` — compute for a single season (default: all available)
- `--output PATH` — override output path (default: `data/features/rainfall_features_sa2_season.csv`)
- `--min-coverage FLOAT` — minimum daily data coverage fraction to include a window (default: 0.8)
- `--pipeline-version TEXT`
- `--dry-run` — print summary without writing

Execution order:
1. Load DuckDB observations; join to station metadata for SA2 assignment.
2. Assign `season_year` to every observation row.
3. Compute monthly totals per station × season.
4. Compute windowed totals (sowing, in-crop, etc.) from monthly totals.
5. Detect autumn break per station × season.
6. Compute dry-spell metrics per station × season.
7. Compute data quality score per station × season.
8. Aggregate to SA2 via simple mean.
9. Write output with atomic CSV write.

### Tests: `tests/test_sa2_rainfall_features.py`

- `test_season_year_assignment` — boundary cases (Jan, Mar, Apr, Dec)
- `test_monthly_rainfall_aggregation` — correctness and NaN handling
- `test_dry_spell_metrics` — 7d and 14d windows
- `test_autumn_break_detection` — early/on_time/late/absent status
- `test_sa2_grouping` — multi-station SA2 averaging
- `test_station_id_normalisation` — leading-zero preservation
- `test_output_schema` — all required columns present with correct dtypes

---

## Open Decisions (from `docs/data_contracts.md` §8)

1. **DuckDB vs CSV as canonical store** — this script reads DuckDB only.
   `obs_daily.csv` is not used as input.
2. **Station-level vs SA2-first handoff** — Phase 2 produces the SA2-aggregated
   table; station-level rows are an internal intermediate only.
3. **Baseline climatology** — anomaly/percentile/decile columns are deferred;
   not in v1 output.
4. **Data Drill grid points in SA2 aggregation** — `DD_lat_lon` station IDs
   are excluded from v1. The `station_count` column reflects BOM stations only.
5. **Temperature features** — out of scope for this table. Temperature risk
   remains in `data/derived/event_log.csv`.
