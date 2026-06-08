# Repository Inventory

**Date captured:** 2026-05-02
**Purpose:** Freeze and document current state before any restructuring. Nothing has been moved or deleted.

---

## How to read this table

- **Keep** — actively used; do not touch
- **Archive** — no longer needed for operations; move to `archive/` when ready
- **Review** — may need updating, replacement, or deletion; investigate before acting
- **Large data** — not deleted, but note size; review whether it belongs in git or an external store

---

## Source code — `src/`

| Path | Current role | Status | Notes |
|---|---|---|---|
| `src/agents/silo_wrangler/run_ingest.py` | CLI entry point: daily SILO ingest | Keep | Canonical ingest entrypoint |
| `src/agents/silo_wrangler/api_client.py` | SILO API HTTP calls, retry + rate-limit | Keep | |
| `src/agents/silo_wrangler/data_processor.py` | CSV formatting, cleaning, normalisation | Keep | |
| `src/agents/silo_wrangler/quality_checker.py` | SILO quality-code validation, confidence scoring | Keep | |
| `src/agents/risk_engine/run_risk_engine.py` | CLI entry point: DuckDB-backed event detection | Keep | Primary risk engine; full feature set |
| `src/agents/risk_engine/csv_risk_engine.py` | CLI entry point: CSV-backed event detection | Keep | M1 fallback; frost + heat only |
| `src/agents/risk_engine/event_detector.py` | Core threshold logic for all five event types | Keep | |
| `src/agents/insight_publisher/run_publisher.py` | CLI entry point: report generation + exports | Keep | |
| `src/agents/insight_publisher/report_generator.py` | Markdown daily digest (YYYY-MM-DD_risk_digest.md) | Keep | |
| `src/agents/insight_publisher/export_generator.py` | Power BI CSV export formatting | Keep | |
| `src/common/constants.py` | SILO quality codes, EVENT_* string constants | Keep | Single source of truth — always import from here |
| `src/common/config_loader.py` | YAML config loading with env var substitution | Keep | |
| `src/common/date_utils.py` | Crop stage detection, phenology helpers | Keep | |
| `src/common/file_utils.py` | Atomic CSV write/append operations | Keep | All CSV output must go through here |
| `src/common/logging_utils.py` | Structured logging across all agents | Keep | |
| `src/common/stations_loader.py` | BOM wheatbelt station list loader (1,376 stations) | Keep | |
| `src/data/duckdb_storage.py` | DuckDB read/write, schema init, `query_to_dataframe()` | Keep | |

---

## Scripts — `scripts/`

| Path | Current role | Status | Notes |
|---|---|---|---|
| `scripts/cron_schedule.sh` | Daily automation orchestration (runs after ingest) | Keep | Confirmed active — calls three-agent pipeline directly |
| `scripts/build_station_regions.py` | One-off: enrich station metadata with SA2 region assignments | Keep | Run once to produce `data/meta/station_regions.csv`; not part of daily pipeline |

---

## Config — `config/`

| Path | Current role | Status | Notes |
|---|---|---|---|
| `config/crop_calendars.yaml` | Wheat growth stages, month ranges, all event thresholds | Keep | Staged modified in current branch — verify changes are intentional |
| `config/assumptions.yaml` | Methodology transparency; threshold definitions; stage sensitivity | Keep | |
| `config/silo_sources.yaml` | SILO API config: base URL, credentials via env vars, 3-tier station list | Keep | Staged modified — verify changes |
| `config/silo_sources.local.yaml` | Local env overrides (gitignored) | Keep | Not tracked in git |

---

## Data — `data/`

### Live operational data

| Path | Current role | Status | Notes |
|---|---|---|---|
| `data/weather.duckdb` | Primary analytical weather store (5.8 MB) | Keep | Updated 2026-04-22 |
| `data/obs/obs_daily.csv` | SILO daily observations from 1,376+ stations | Keep | 45,535 rows; Jul 2025–present |
| `data/derived/event_log.csv` | Master event log — all event types, all dates | Keep | Primary output consumed by downstream assembler |
| `data/derived/frost_events.csv` | Frost events only | Keep | |
| `data/derived/heat_events.csv` | Heat stress events only | Keep | |
| `data/derived/rainfall_events.csv` | Damaging harvest-period rainfall events | Keep | |
| `data/derived/seeding_rain_events.csv` | Beneficial seeding rain events (Apr–Jun) | Keep | |
| `data/derived/development_rain_events.csv` | Development-stage rain events (Jul–Oct) | Keep | |
| `data/derived/*.backup.csv` | Safety copies of each event CSV | Keep | Auto-created by atomic write helpers |
| `data/exports/risk_events.csv` | Power BI historical archive | Keep | |
| `data/exports/risk_events_latest.csv` | Power BI latest-day snapshot | Keep | |

### Station and region metadata

| Path | Current role | Status | Notes |
|---|---|---|---|
| `data/meta/wheatbelt_stations.csv` | BOM wheatbelt station list with lat/lon and SA2 codes | Keep | 1,377 rows |
| `data/meta/station_regions.csv` | Enriched station list with region assignments | Keep | 1,417 rows; produced by `build_station_regions.py` |
| `data/meta/wa_seasonal_context.yaml` | WA seasonal timing notes, disease-watch context | Keep | Wired into daily digest as of 2026-04-22 |
| `data/meta/SA2_ABS_Regions.geojson` | SA2 boundary polygons (ABS 2021) | Keep | Used for region assignment |

### Large reference data (not used by daily pipeline)

| Path | Size | Status | Notes |
|---|---|---|---|
| `data/meta/monthly_rain/` | 203 MB | Large data — Review | NetCDF annual and monthly rainfall files 2005–2025. Not consumed by agents; used in exploratory/notebook work. Consider external storage if repo size becomes an issue. |
| `data/meta/shapefiles/` | 227 MB | Large data — Review | WA wheat region and state boundary shapefiles + NetCDF masks. Not consumed by daily pipeline. Consider external storage. |
| `data/external/max_temp/` | 852 MB | Large data — Review | Annual max-temp NetCDF files (2005, 2024, 2025). Not consumed by daily pipeline. Largest single contributor to repo size. |
| `data/interim/` | ~few MB | Review | 4 GeoTIFF files from a 2025-02 visualisation run. Not part of daily pipeline. Can be regenerated. |

### Empty placeholder directories

| Path | Status | Notes |
|---|---|---|
| `data/raw/` | Review | Created but unused. Intended for immutable raw downloads. |
| `data/gridded/` | Review | Created but unused. Intended for gridded interpolations. |
| `data/colormaps/` | Review | Created but unused. |

---

## Reports and logs

| Path | Current role | Status | Notes |
|---|---|---|---|
| `reports/daily/` | Auto-generated daily risk digests | Keep | Most recent: 2026-04-21 |
| `reports/weekly/` | Weekly outlook reports | Keep | Target output for M2 automation |
| `reports/WA_Wheatbelt_Executive_Summary_2025-09-08.md` | One-off executive summary (Sep 2025) | Keep | Historical reference |
| `reports/2025-26_season_summary.md` | Full season overview Sep 2025 – Jan 2026 | Keep | Historical reference |
| `reports/figures/wa_july_percentiles.png` | Visualisation from earlier analysis | Keep | |
| `logs/ingest_runs.jsonl` | Structured log of all historical ingest runs (645 KB) | Keep | Updated 2026-04-22 |
| `logs/daily_ingest.log` | Human-readable ingest log | Review | Last entry is Sep 9, 2025 showing DRY RUN. May be stale if the log path changed. |

---

## Documentation — `docs/`

| Path | Current role | Status | Notes |
|---|---|---|---|
| `docs/Logpaddock_SILO_API_Reference.md` | SILO API reference (markdown conversion) | Keep | Preferred over PDF for in-context reading |
| `docs/Logpaddock_SILO_API_Reference.pdf` | Official SILO API spec (original) | Keep | |
| `docs/silo_api_usage_guide.md` | CropForecaster-specific SILO quickstart | Keep | |
| `docs/DPIRD-2026-WA-Crop-Sowing-Guide.md` | WA crop sowing guide (markdown) | Keep | Calibration source for `crop_calendars.yaml` |
| `docs/DPIRD-2026-WA-Crop-Sowing-Guide.pdf` | WA crop sowing guide (original) | Keep | |
| `docs/conf.py`, `docs/Makefile`, `docs/*.rst` | Sphinx skeleton (never built) | Review | Left over from cookiecutter; not actively used |

---

## Root-level files

| Path | Current role | Status | Notes |
|---|---|---|---|
| `CLAUDE.md` | CropForecaster architecture guidance for Claude Code | Keep | Primary system-level instructions |
| **`README.md`** | **Project overview** | **Review — out of date** | Still references the old cookiecutter structure (`src/models/`, `src/features/`, `src/visualization/`) which no longer exists. Should be rewritten to describe the three-agent architecture. |
| `prd.md` | Product requirements document | Keep | |
| `task_manager.md` | Detailed task tracking (M1 done; M2 backlog) | Keep | |
| `PROJECT_STRUCTURE.md` | Actual current structure (Sep 2025) | Keep | More accurate than README.md |
| `M1_DELIVERY_SUMMARY.md` | M1 milestone completion record | Keep | Historical reference |
| `CLEANUP_PLAN.md` | Migration notes from cookiecutter to 3-agent | Keep | Historical reference |
| `pyproject.toml` | Package metadata | Keep | |
| `requirements.txt` | Operational dependencies | Keep | |
| `setup.py` | Minimal pip install -e entry point | Keep | |
| `.env` | SILO credentials in plaintext | Keep (but see note) | `.gitignore` excludes this file. Do not commit. Credentials should be in env or a secrets manager for any deployed environment. |
| `.clauderules` | Claude Code development constraints | Keep | |
| `.claude/agents/*.md` | Agent definitions (silo-wrangler, risk-engine, insight-publisher) | Keep | |
| `.claude/settings.json` | Claude Code harness settings | Keep | |

---

## Archive — `archive/`

| Path | Current role | Status | Notes |
|---|---|---|---|
| `archive/old_notebooks/` | 13 Jupyter notebooks from exploratory phase | Archive — preserved | Research history; not maintained. Keep here; do not delete. Includes AWS/S3, SILO gridded data, BOM comparison, percentile, and station-metadata exploration notebooks. |
| `archive/old_src/modify_netcdf.py` | Old NetCDF editing utilities | Archive — preserved | Superseded by agent architecture |
| `archive/old_src/rainfall_functions.py` | Old rainfall metrics | Archive — preserved | Superseded by event_detector.py |
| `archive/reference/` | Old download/SILO patterns and reference CSVs | Archive — preserved | Pattern reference; not called by any active code |
| `archive/MIGRATION_NOTES.md` | Cookiecutter → 3-agent migration record | Keep | |
| `archive/task_manager_old.md` | Previous task tracking iteration | Archive — preserved | |
| `archive/deprecated_ingest_pipeline/src/data/silo_ingest.py` | Old `SILOIngestPipeline` class | Archive — preserved | Superseded by `src/agents/silo_wrangler/run_ingest.py`. Moved 2026-05-03. |
| `archive/deprecated_ingest_pipeline/scripts/daily_ingest.py` | Old daily ingest CLI | Archive — preserved | Called stale `SILOIngestPipeline`. Moved 2026-05-03. |
| `archive/deprecated_ingest_pipeline/scripts/backfill_historical.py` | Old backfill CLI | Archive — preserved | Called stale `SILOIngestPipeline`. Use `run_ingest.py --date-range`. Moved 2026-05-03. |
| `archive/deprecated_ingest_pipeline/config/cron_schedule.sh` | Old cron setup installer | Archive — preserved | Called `scripts/daily_ingest.py`. Superseded by `scripts/cron_schedule.sh`. Moved 2026-05-03. |

**Note on malformed filename:** `archive/old_notebooks/` contains a file with a Windows absolute path as its name (`C:\Users\rj71b\...`). This is a git checkout artefact from a Windows machine. It is harmless but unfixable without a `git mv`. Flag for cleanup if the archive is ever reorganised.

---

## Tests

| Path | Status | Notes |
|---|---|---|
| `tests/` | Missing — empty directory | No unit or integration tests exist. M2 backlog item. |

---

## Key findings summary

| Issue | Severity | Status |
|---|---|---|
| ~~`src/data/silo_ingest.py` — stale pipeline class~~ | High | **Archived 2026-05-03** → `archive/deprecated_ingest_pipeline/` |
| ~~`scripts/daily_ingest.py` — imports stale `SILOIngestPipeline`~~ | High | **Archived 2026-05-03** → `archive/deprecated_ingest_pipeline/` |
| ~~`scripts/backfill_historical.py` — same stale import~~ | High | **Archived 2026-05-03** → `archive/deprecated_ingest_pipeline/` |
| ~~`README.md` — describes old cookiecutter layout~~ | Medium | **Rewritten 2026-05-03** to three-agent architecture |
| `data/external/max_temp/` — 852 MB NetCDF files in git | Medium | Consider moving to external storage |
| `data/meta/shapefiles/` — 227 MB shapefiles in git | Medium | Consider moving to external storage |
| `data/meta/monthly_rain/` — 203 MB NetCDF in git | Medium | Consider moving to external storage |
| `logs/daily_ingest.log` last entry Sep 2025 (DRY RUN) | Low | Log written by archived `daily_ingest.py`; safe to ignore |
| Sphinx skeleton in `docs/` — never built | Low | Remove or adopt; currently dead weight |
| `tests/` — empty | Low | M2 backlog item |
