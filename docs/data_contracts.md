# Data Contracts — CropForecaster Rainfall Modelling

## 1. Purpose

These contracts define the stable modelling and pipeline outputs for the wheat crop forecasting rainfall project. They represent the expected schema, semantics, and quality guarantees for data flowing between pipeline stages and into downstream modelling or reporting systems.

Contracts are specification documents, not implementation constraints. Code is expected to converge toward them over time.

The approved SA2 monthly rainfall producer handoff is documented separately in
`docs/rainfall_handoff_v1_contract.md`. That v1.0 contract is the authority for
the canonical national rainfall history and decile CSVs; it does not approve
growing-season rainfall, weighted rainfall expansion, extraction-method changes,
or downstream ACM integration.

---

## 2. Contract: `daily_weather_observations`

Canonical cleaned daily weather observations. One row per station per calendar date.

**Backing store**: DuckDB (`data/weather.duckdb`, table `weather_observations`). Exportable to CSV for downstream use.

| Field | Type | Description |
|---|---|---|
| `station_id` | string | Six-digit BOM station ID (e.g. `010092`) or `DD_lat_lon` for Data Drill grid points |
| `date` | ISO date | Observation date (`YYYY-MM-DD`) |
| `rainfall_mm` | float | Daily rainfall in millimetres |
| `min_temp_c` | float | Daily minimum temperature in degrees Celsius |
| `max_temp_c` | float | Daily maximum temperature in degrees Celsius |
| `rainfall_quality` | integer | SILO quality code for rainfall (see `src/common/constants.py`) |
| `min_temp_quality` | integer | SILO quality code for min temperature |
| `max_temp_quality` | integer | SILO quality code for max temperature |
| `source` | string | `silo_patched_point` or `silo_data_drill` |
| `ingested_at` | timestamp | UTC timestamp when the row was written to the store |
| `pipeline_version` | string | Semver string identifying the ingest pipeline version |

**SILO quality codes** (defined in `src/common/constants.py`):
- `0` — observed (confidence 1.0)
- `15` — interpolated (0.8)
- `25` — lower density network (0.7)
- `35` — synthetic (0.3)
- `75` — lower quality (0.6)
- `999` — missing (0.0)

---

## 3. Contract: `rainfall_features_station_season`

One row per station (or Data Drill grid point) per wheat season. This is the primary modelling feature table at station level.

| Field | Type | Description |
|---|---|---|
| `season_year` | integer | Wheat season year (e.g. `2025` = the 2025 season, Apr 2025 – Jan 2026) |
| `station_id` | string | BOM station ID or Data Drill point identifier |
| `state_name` | string | Australian state (e.g. `Western Australia`) |
| `sa2_code` | string | ABS SA2 code |
| `sa2_name` | string | ABS SA2 name |
| `sa3_name` | string | ABS SA3 name |
| `sa4_name` | string | ABS SA4 name |
| `latitude` | float | Station latitude (decimal degrees, negative south) |
| `longitude` | float | Station longitude (decimal degrees) |
| `crop_type` | string | Crop type (e.g. `wheat`, `barley`, `canola`) |
| `season_start_date` | ISO date | First day of the defined crop season |
| `season_end_date` | ISO date | Last day of the defined crop season |
| `rainfall_total_apr_oct_mm` | float | Total rainfall Apr–Oct inclusive (mm) |
| `rainfall_total_may_oct_mm` | float | Total rainfall May–Oct inclusive (mm) |
| `monthly_rainfall_jan_mm` | float | January total rainfall (mm) |
| `monthly_rainfall_feb_mm` | float | February total rainfall (mm) |
| `monthly_rainfall_mar_mm` | float | March total rainfall (mm) |
| `monthly_rainfall_apr_mm` | float | April total rainfall (mm) |
| `monthly_rainfall_may_mm` | float | May total rainfall (mm) |
| `monthly_rainfall_jun_mm` | float | June total rainfall (mm) |
| `monthly_rainfall_jul_mm` | float | July total rainfall (mm) |
| `monthly_rainfall_aug_mm` | float | August total rainfall (mm) |
| `monthly_rainfall_sep_mm` | float | September total rainfall (mm) |
| `monthly_rainfall_oct_mm` | float | October total rainfall (mm) |
| `monthly_rainfall_nov_mm` | float | November total rainfall (mm) |
| `monthly_rainfall_dec_mm` | float | December total rainfall (mm) |
| `sowing_window_rain_mm` | float | Total rainfall during sowing window (see §5) |
| `in_crop_rain_mm` | float | Total rainfall during in-crop period (see §5) |
| `flowering_rain_mm` | float | Total rainfall during flowering window (see §5) |
| `grain_fill_rain_mm` | float | Total rainfall during grain fill window (see §5) |
| `harvest_rain_mm` | float | Total rainfall during harvest window (see §5) |
| `autumn_break_date` | ISO date | Date of first qualifying autumn break event (nullable) |
| `autumn_break_7d_mm` | float | 7-day rainfall total at the autumn break (nullable) |
| `autumn_break_status` | string | `early`, `on_time`, `late`, or `absent` |
| `rainfall_anomaly_mm` | float | Deviation from baseline climatology (mm) |
| `rainfall_anomaly_pct` | float | Percentage deviation from baseline (%) |
| `rainfall_percentile` | float | Season rainfall percentile within historical distribution |
| `rainfall_decile` | integer | Season rainfall decile (1–10) |
| `dry_spell_days_7d_lt_5mm` | integer | Days where rolling 7-day rainfall < 5 mm |
| `dry_spell_days_14d_lt_10mm` | integer | Days where rolling 14-day rainfall < 10 mm |
| `observed_ratio` | float | Fraction of daily rows with quality code 0 (observed) |
| `interpolated_ratio` | float | Fraction of daily rows with quality code 15 (interpolated) |
| `synthetic_ratio` | float | Fraction of daily rows with quality code 35 (synthetic) |
| `data_quality_score` | float | Weighted composite quality score (0.0–1.0) |
| `source_dataset` | string | Origin dataset identifier (e.g. `silo_patched_point`) |
| `pipeline_version` | string | Semver string of the feature-generation pipeline |
| `created_at` | timestamp | UTC timestamp when the row was written |

---

## 4. Contract: `rainfall_features_region_season`

One row per region per wheat season. Regions may be SA2, SA3, SA4, LGA, or DPIRD agricultural zone. Station-level rows from `rainfall_features_station_season` are aggregated into this table.

| Field | Type | Description |
|---|---|---|
| `season_year` | integer | Wheat season year |
| `region_id` | string | Region identifier (e.g. SA2 code, LGA code, DPIRD zone name) |
| `region_type` | string | `sa2`, `sa3`, `sa4`, `lga`, or `dpird_agzone` |
| `region_name` | string | Human-readable region name |
| `state_name` | string | Australian state |
| `crop_type` | string | Crop type |
| `station_count` | integer | Number of stations contributing to this region row |
| `contributing_station_ids` | string | Comma-separated list of station IDs (or JSON array) |
| `aggregation_method` | string | `area_weighted_mean`, `simple_mean`, or `median` |
| `crop_area_weighted` | boolean | Whether crop area weights were applied in aggregation |
| `rainfall_total_apr_oct_mm` | float | Area-aggregated Apr–Oct total (mm) |
| `rainfall_total_may_oct_mm` | float | Area-aggregated May–Oct total (mm) |
| `monthly_rainfall_jan_mm` … `monthly_rainfall_dec_mm` | float | Area-aggregated monthly totals (mm) |
| `sowing_window_rain_mm` | float | Aggregated sowing window rainfall (mm) |
| `in_crop_rain_mm` | float | Aggregated in-crop rainfall (mm) |
| `flowering_rain_mm` | float | Aggregated flowering rainfall (mm) |
| `grain_fill_rain_mm` | float | Aggregated grain fill rainfall (mm) |
| `harvest_rain_mm` | float | Aggregated harvest rainfall (mm) |
| `autumn_break_date` | ISO date | Modal or area-weighted autumn break date across contributing stations (nullable) |
| `autumn_break_7d_mm` | float | Area-weighted 7-day autumn break rainfall (nullable) |
| `autumn_break_status` | string | `early`, `on_time`, `late`, or `absent` |
| `rainfall_anomaly_mm` | float | Regional deviation from baseline climatology (mm) |
| `rainfall_anomaly_pct` | float | Percentage deviation from baseline (%) |
| `rainfall_percentile` | float | Regional seasonal rainfall percentile |
| `rainfall_decile` | integer | Regional seasonal rainfall decile (1–10) |
| `dry_spell_days_7d_lt_5mm` | float | Station-average days with rolling 7-day rainfall < 5 mm |
| `dry_spell_days_14d_lt_10mm` | float | Station-average days with rolling 14-day rainfall < 10 mm |
| `data_quality_score` | float | Weighted composite quality score across contributing stations |
| `source_dataset` | string | Origin dataset identifier |
| `pipeline_version` | string | Semver string of the feature-generation pipeline |
| `created_at` | timestamp | UTC timestamp when the row was written |

---

## 5. Australian Wheat Forecasting Windows

These windows define the phenological periods used to compute windowed rainfall features. Exact calendar dates vary by region, crop variety, and season. The values below are representative WA wheatbelt defaults; authoritative per-region dates should come from `config/crop_calendars.yaml`.

| Window | Typical WA dates | Significance |
|---|---|---|
| **Autumn break** | Apr–Jun | First sustained rainfall ≥ 10 mm/day (or ≥ 25 mm/7d) that triggers germination. Timing relative to the long-term median (typically ~mid-May in the WA wheatbelt) determines `autumn_break_status`. |
| **Sowing window** | Apr–Jun | Period in which growers sow seed following the autumn break. Overlaps with autumn break detection. |
| **In-crop rainfall** | May–Oct | Growing season total — the primary yield correlate across the wheatbelt. |
| **Flowering** | Sep–Oct | Highest yield-sensitivity period. Frost risk (Tmin ≤ 2°C) and late-season heat stress (Tmax ≥ 32°C) are most damaging here. |
| **Grain fill** | Oct–Nov | Kernel development. Rainfall supports yield but excess increases disease pressure. |
| **Harvest rainfall** | Nov–Jan | Rain during harvest is damaging. Events ≥ 10 mm/day, ≥ 15 mm/3d, or ≥ 25 mm are tracked as risk events. |
| **Crop year / season year** | Apr–Mar | The conventional label for a wheat season. The 2025 season runs approximately Apr 2025 – Mar 2026. `season_year` is the calendar year in which sowing occurs. |

WA wheatbelt terminology note: "break of season" and "autumn break" are used interchangeably in DPIRD literature. This project uses `autumn_break` as the canonical term.

---

## 6. Current-State Mapping

| Current file / table | Closest contract | Gap |
|---|---|---|
| `data/weather.duckdb` → `weather_observations` table | `daily_weather_observations` | Missing `pipeline_version`; column names use `min_temp`/`max_temp` rather than the canonical `min_temp_c`/`max_temp_c`; `source` field not always populated |
| `data/obs/obs_daily.csv` | `daily_weather_observations` (partial) | Operational export only; station IDs and names not normalised; no `ingested_at` or `pipeline_version`; not canonical until alignment with DuckDB schema |
| `data/derived/event_log.csv` | None | This is an event/risk output, not a modelling feature table. Fields like `severity`, `threshold`, and `detected_at` have no counterpart in the feature contracts. |
| `data/derived/*_events.csv` | None | Type-specific event logs. Same classification as `event_log.csv` — operational risk output, not feature input. |
| `data/meta/station_regions.csv` | Supporting lookup only | Maps station IDs to SA2/SA3/SA4 regions. Required for `rainfall_features_region_season` aggregation but is not itself a contract table. |

No current file fully satisfies `rainfall_features_station_season` or `rainfall_features_region_season`. Both tables require windowed aggregation logic and baseline climatology that does not yet exist in the pipeline.

---

## 7. Contract: `crop_context_sa2` (ABS Agricultural Census)

SA2-level historical crop area, production, and yield context derived from the ABS Agricultural Census. One row per SA2 per financial year per crop.

**Backing store**: `data/meta/crop_context_sa2.csv` (generated artefact — not committed to repo).  
**Source**: ABS Agricultural Census (`/home/roddyb/projects/ABS Census Data/ag_census.db`).  
**Config**: `config/crop_context.yaml` (commodity codes, baseline year, output schema).  
**Baseline year**: 2020-21.

| Field | Type | Description |
|---|---|---|
| `sa2_code` | string | Full 9-digit ABS SA2 code (`SA2_MAIN16`); treat as string — leading zeros are significant. Empty string if the SA2 could not be resolved (see `boundary_status`). |
| `station_sa2_5dig16` | string | 5-digit SA2 code from BOM station metadata (`SA2_5DIG16`); always populated. Use for traceability back to `data/meta/wheatbelt_stations.csv`. |
| `sa2_name` | string | SA2 name |
| `state` | string | Australian state name |
| `financial_year` | string | ABS financial year (e.g. `2020-21`) |
| `crop` | string | Crop key matching `config/crop_context.yaml` (e.g. `wheat`) |
| `area_ha` | float | Harvested area (hectares); null if suppressed by ABS |
| `production_t` | float | Production (tonnes); null if suppressed |
| `yield_t_ha` | float | Yield (t/ha); null if suppressed |
| `area_share` | float | This crop's share of total cropped area in the SA2 (0–1); null if `area_ha` is null or total across configured crops is zero |
| `area_rse` | string | ABS RSE/quality flag preserved as source text (may be blank, `^`, `*`, `**`, `np`, `..`, dash, or numeric %) |
| `production_rse` | string | ABS RSE/quality flag preserved as source text |
| `yield_rse` | string | ABS RSE/quality flag preserved as source text |
| `source_dataset` | string | Dataset identifier (e.g. `ABS Agricultural Census 2020-21`) |
| `source_commodity_area` | string | ABS commodity code used for area |
| `source_commodity_production` | string | ABS commodity code used for production |
| `source_commodity_yield` | string | ABS commodity code used for yield |
| `boundary_status` | string | SA2 resolution status — see vocabulary below |
| `notes` | string | Free-text notes (suppression reason, outliers, etc.) |

**`boundary_status` vocabulary**:

| Value | Meaning |
|---|---|
| `matched` | `SA2_5DIG16` found directly in `SA2_ABS_Regions.geojson`; `SA2_MAIN16` taken from GeoJSON properties |
| `matched_via_label` | `SA2_5DIG16` absent from GeoJSON; `SA2_MAIN16` resolved by matching `region_label` + state prefix in the ABS `regions` table |
| `unmatched` | SA2 could not be resolved to a 9-digit ABS code; `sa2_code` is empty and no ABS observations are included |

**Constraints**:
- Suppressed or null ABS estimates must be treated as missing, not zero.
- Both `sa2_code` (9-digit) and `station_sa2_5dig16` (5-digit) must remain as strings throughout the pipeline — do not cast to integer.
- RSE fields (`area_rse`, `production_rse`, `yield_rse`) must not be coerced to numeric — preserve ABS source text.
- Values are historical census estimates; they do not reflect current-year planted area.

**Crops covered**: wheat, barley, canola, lupins, oats (see `config/crop_context.yaml` for ABS commodity codes).

---

## 8. Open Decisions

The following decisions are needed before contract tables can be generated:

1. **DuckDB vs CSV as canonical daily store** — `daily_weather_observations` is defined as DuckDB-primary, but `data/obs/obs_daily.csv` currently serves as the CSV engine input. A decision is needed on whether the CSV is an export artefact or a co-equal source of truth, and which takes precedence on conflict.

2. **Station-level vs SA2-first modelling handoff** — Should the downstream modelling pipeline receive `rainfall_features_station_season` rows and aggregate internally, or should this pipeline produce `rainfall_features_region_season` as the primary handoff? Affects join complexity and regional coverage decisions.

3. **Baseline climatology period for anomalies, percentiles, and deciles** — A historical reference period must be chosen (e.g. 1981–2010, 1991–2020, or a custom wheatbelt-specific window). This determines the meaning of `rainfall_anomaly_mm`, `rainfall_percentile`, and `rainfall_decile` fields. SILO data availability and BOM climatological conventions should inform this choice.

4. **Handling Data Drill grid points in regional aggregation** — Data Drill points (`DD_lat_lon` station IDs) cover areas with no BOM station. The contract allows for them, but the aggregation logic for mixing BOM station records and Data Drill records within the same SA2 is undefined. A weighting or exclusion rule is needed.

5. **Temperature features in the same modelling table or a separate weather feature table** — The current contracts are rainfall-focused. Temperature (frost, heat) features are tracked via the event log. A decision is needed on whether a `weather_features_station_season` table should be defined alongside the rainfall contracts, or whether temperature features are out of scope for the modelling handoff.

---

## N. Contract: `abares_crop_production_normalized`

**File**: `data/meta/abares/abares_crop_production_normalized.csv`
**Source**: ABARES Agricultural Commodities bulletin, March 2026 (No. 217)
**Original path**: `/home/roddyb/projects/ABS Census Data/Modernised_Census_2022_2025/comparison_2020_21_to_2022_23/acf_historical/stock_and_production_context/abares_crop_production_normalized.csv`
**Coverage**: 1989–2025, 7 jurisdictions (AUS, NSW, QLD, SA, VIC, WA, TAS), wheat Area + Production
**Update cadence**: Annual (March bulletin). Replace file when No. 218+ released.

| Field | Type | Description |
|---|---|---|
| state | string | State code (AUS, NSW, QLD, SA, VIC, WA, TAS) |
| crop | string | Crop name (filter to "Wheat") |
| metric | string | "Area" or "Production" |
| crop_season | integer | Calendar year the crop was grown (join key against rainfall year) |
| value_normalized | float | Area in ha, Production in tonnes |
| status | string | "final", "estimate", or "forecast" |

**Join key**: `ABARES.crop_season == rainfall_data.year` (no offset — ABARES labels season by financial-year start, but harvest falls in the same calendar year as sowing)

**Notes**:
- 2025 data has `status='forecast'` — use as area base for implied 2026 production
- AUS rows (`is_national=True`) are the national rollup; state rows are used for per-state analysis
- Derived yield = `Production (t) / Area (ha)` computed at query time; not stored in this file
