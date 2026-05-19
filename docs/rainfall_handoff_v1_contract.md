# Rainfall Handoff v1.0 Contract

Status: approved producer contract semantics for WRA rainfall handoff v1.0.

This contract stabilises the SA2 monthly rainfall handoff before any downstream
consumer, including ACM, depends on it. It documents the current canonical
rainfall files and their semantics only; it does not approve new feature
implementation, output regeneration, extraction-method changes, or downstream
integration work.

## Canonical Outputs

The v1.0 canonical handoff files are:

| File | Role |
|---|---|
| `data/features/sa2_monthly_rainfall_history_national.csv` | Monthly SA2 rainfall history extracted from SILO monthly rainfall grids |
| `data/features/sa2_monthly_rainfall_deciles_national.csv` | Monthly SA2 rainfall deciles and anomalies computed from the history file |

Both files are generated data artefacts and are ignored by git through
`data/features/*.csv`. Contract stability is therefore assessed by local file
presence, parseability, schema, key uniqueness, and documented semantics, not by
git tracking.

Non-canonical rainfall artefacts may exist under `data/features/`, including
legacy WA-only outputs, station-derived current-year bridges, weighted rainfall
summaries, and crop-context joins. They are not part of rainfall handoff v1.0
unless promoted by a separate approval.

## Row Key

The canonical row key for both v1.0 files is:

```text
state_name + sa2_code + year + month
```

Column order is informational only. Consumers must use column names and the
canonical row key rather than positional assumptions.

## Source Method

The approved v1.0 source method is:

| Property | Value |
|---|---|
| Source dataset | SILO monthly rainfall NetCDF |
| Source variable | `monthly_rain` |
| Extraction method | `centroid_nearest_grid_cell` |

`centroid_nearest_grid_cell` means each SA2 is represented by its polygon
centroid and snapped to the nearest SILO grid cell. The v1.0 handoff is not
station daily rainfall, not Data Drill, and not polygon-area averaged.

## History Schema

Required columns for `sa2_monthly_rainfall_history_national.csv`:

| Column | Required semantics |
|---|---|
| `year` | Calendar year from the SILO monthly NetCDF time coordinate |
| `month` | Calendar month number, 1-12 |
| `sa2_code` | SA2 identifier as a string |
| `sa2_name` | SA2 display name from the selected SA2 universe |
| `state_name` | Australian state name; part of the canonical key |
| `rainfall_mm` | Monthly rainfall in millimetres; may be blank where the extracted grid value is null |
| `extraction_method` | Must be `centroid_nearest_grid_cell` for v1.0 |
| `universe_source` | SA2 universe provenance; observed values are `geojson_2016` and `wa_2021_csv` |
| `source_file` | Local SILO NetCDF filename used for the row |
| `source_variable` | Must be `monthly_rain` for v1.0 |
| `quality_flag` | Extraction quality flag emitted by the producer |

Observed allowed values in the current canonical file:

| Column | Allowed values |
|---|---|
| `state_name` | `New South Wales`, `Queensland`, `South Australia`, `Victoria`, `Western Australia` |
| `month` | Integers 1-12 |
| `extraction_method` | `centroid_nearest_grid_cell` |
| `source_variable` | `monthly_rain` |
| `universe_source` | `geojson_2016`, `wa_2021_csv` |
| `quality_flag` | `ok` |

## Decile Schema

Required columns for `sa2_monthly_rainfall_deciles_national.csv`:

| Column | Required semantics |
|---|---|
| `year` | Calendar year |
| `month` | Calendar month number, 1-12 |
| `sa2_code` | SA2 identifier as a string |
| `sa2_name` | SA2 display name |
| `state_name` | Australian state name; part of the canonical key |
| `rainfall_mm` | Monthly rainfall in millimetres copied from the history file |
| `historical_year_count` | Count of usable baseline years for the same `state_name + sa2_code + month`, excluding the target year |
| `historical_median_mm` | Median baseline rainfall in millimetres; blank when no valid decile can be computed |
| `historical_mean_mm` | Mean baseline rainfall in millimetres; blank when no valid decile can be computed |
| `anomaly_mm` | `rainfall_mm - historical_median_mm`; blank when no valid baseline exists |
| `anomaly_pct` | Percentage anomaly from historical median; blank when no valid baseline exists |
| `rainfall_decile` | Integer decile 1-10; blank when no valid decile can be computed |
| `rainfall_decile_label` | Text label for the rainfall decile; blank when no valid decile can be computed |
| `climatology_quality_flag` | Decile quality status |
| `extraction_method` | Must preserve `centroid_nearest_grid_cell` |
| `universe_source` | Must preserve history-row universe provenance |
| `source_variable` | Must preserve `monthly_rain` |

Observed allowed values in the current canonical file:

| Column | Allowed values |
|---|---|
| `rainfall_decile` | Integers 1-10, or blank |
| `rainfall_decile_label` | `very low`, `below normal`, `near normal`, `above normal`, `very high`, or blank |
| `climatology_quality_flag` | `ok`, `null_rainfall` |
| `extraction_method` | `centroid_nearest_grid_cell` |
| `source_variable` | `monthly_rain` |
| `universe_source` | `geojson_2016`, `wa_2021_csv` |

## Decile Baseline

The approved v1.0 decile baseline is:

- Group by the same `state_name + sa2_code + month`.
- Exclude the target row's own `year` from its baseline.
- Require at least 10 usable historical values before computing deciles.
- Use the available-history baseline in the canonical file, not a BOM normal
  period climatology.

The current canonical national files cover 2005-2025. For rows with non-null
rainfall and `climatology_quality_flag = ok`, the observed
`historical_year_count` is 20 because the target year is excluded from the
21-year available history.

## Observed Validation

Validation run on 2026-05-18 against the local canonical CSVs:

| Check | Result |
|---|---|
| History file parseable as CSV | Pass |
| Decile file parseable as CSV | Pass |
| History rows | 48,384 |
| Decile rows | 48,384 |
| History key duplicates on `state_name + sa2_code + year + month` | 0 |
| Decile key duplicates on `state_name + sa2_code + year + month` | 0 |
| States present | NSW, QLD, SA, VIC, WA |
| Years present | 2005-2025 |
| Months present | 1-12 |
| Decile quality counts | 47,880 `ok`; 504 `null_rainfall` |

## Caveats And Mismatches

| Observed behaviour | Approved v1.0 semantic | Affected file/output | Blocks contract stabilisation? |
|---|---|---|---|
| 504 history rows have blank `rainfall_mm` while `quality_flag = ok`; the decile output marks the corresponding rows as `climatology_quality_flag = null_rainfall`. | v1.0 requires documented semantics, parseable CSV, and allowed value vocabularies. It does not define `quality_flag` as a null-rainfall indicator. | `data/features/sa2_monthly_rainfall_history_national.csv`; `data/features/sa2_monthly_rainfall_deciles_national.csv` | No, if documented. Consumers must use `rainfall_mm` nullness and decile `climatology_quality_flag`, not history `quality_flag`, to identify null rainfall rows. |
| Producer scripts have legacy/default output paths that are not the v1.0 canonical national filenames unless explicit `--output` paths are supplied. | v1.0 canonical files are the two national CSV paths listed above. | `scripts/extract_sa2_monthly_rainfall.py`; `scripts/build_sa2_rainfall_deciles.py` | No, for documentation stabilisation. It would block automation if a downstream job assumed script defaults produce the canonical v1.0 national files. |
| `docs/national_sa2_rainfall_expansion.md` includes future-work notes such as possible polygon-area averaging and growing-season/windowed rainfall expansion. | v1.0 freezes `centroid_nearest_grid_cell` and does not add growing-season rainfall contract, weighted rainfall expansion, or downstream integration. | Documentation only | No, if treated as exploratory/non-contract planning. It must not be read as modifying this v1.0 contract. |
| The decile output includes both `historical_median_mm` and `historical_mean_mm`, but `anomaly_mm` and `anomaly_pct` are computed against `historical_median_mm`. | v1.0 documents the canonical output semantics as observed; consumers must not infer mean-based anomaly semantics from the presence of `historical_mean_mm`. | `data/features/sa2_monthly_rainfall_deciles_national.csv`; `scripts/build_sa2_rainfall_deciles.py` | No, if documented. |

## Worktree Inventory At Handoff

Observed dirty/untracked state before contract documentation edits:

| Path or group | Classification | Notes |
|---|---|---|
| `scripts/extract_sa2_monthly_rainfall.py` | Contract-relevant | Adds national/multi-state extraction options, state metadata, universe provenance, and custom output path support. |
| `scripts/build_sa2_rainfall_deciles.py` | Contract-relevant | Adds state-aware baseline key, state filtering, and provenance columns. |
| `tests/test_extract_sa2_monthly_rainfall.py` | Contract-relevant | Adds tests around WA legacy mode, state filtering, and custom output paths. |
| `tests/test_build_sa2_rainfall_deciles.py` | Contract-relevant | Adds tests around state-aware baselines and state filtering. |
| `docs/national_sa2_rainfall_expansion.md` | Exploratory / contract-adjacent | Useful implementation notes, but not the v1.0 contract authority. |
| `scripts/download_silo_monthly_rain.py` | Contract-adjacent tooling | Supports source NetCDF acquisition/validation; not part of the handoff schema. |
| `data/features/*.csv` | Generated output | Includes the two canonical national CSVs plus non-canonical artefacts; ignored by git. |
| `data/meta/monthly_rain/` | Source/generated local data | Includes monthly SILO NetCDF files and a stale 2025 backup; ignored by git except the backup appears untracked. |
| `data/meta/shapefiles/Australia_SA2_Wheat_clipped.*` | Unrelated/legacy pending deletion | Existing tracked shapefile components are deleted in the worktree. |
| `data/meta/shapefiles/CG_SA2_2011_SA2_2021.csv`, correspondence PDF, `sd11aust_shapefile/` | Exploratory/supporting metadata | Untracked shapefile/correspondence inputs. |
| `data/processed/clum_commodities_2023_*` | Exploratory generated output | Commodity-area context outputs, not part of rainfall handoff v1.0. |
| `scripts/extract_clum_commodity_areas.py`, `tests/test_extract_clum_commodity_areas.py` | Exploratory/unrelated to rainfall handoff | CLUM commodity extraction work. |
| `README.md`, `CLAUDE.md` | Contract-adjacent / operational docs | Existing edits mention national SA2 commands and downstream path changes. |
| `pyproject.toml`, `src/agents/silo_wrangler/run_ingest.py` | Unrelated/legacy operational changes | Dependency/import changes outside rainfall handoff schema. |
| `.venv/` | Local environment | Untracked local virtual environment. |

## Explicit Non-Approvals

Rainfall handoff v1.0 does not approve:

- Regenerating canonical outputs without Rod's explicit approval.
- Changing extraction method away from `centroid_nearest_grid_cell`.
- Changing decile baseline semantics.
- Adding a growing-season rainfall contract.
- Promoting current-year station-derived bridges.
- Expanding weighted rainfall outputs.
- Treating ACM as an active downstream consumer.
