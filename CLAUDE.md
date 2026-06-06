# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**CropForecaster** is a Python-based operational weather monitoring system for daily frost, heat stress, and rainfall risk assessment across the Australian wheatbelt. Data comes from the SILO API (Bureau of Meteorology stations); output is event-based CSV logs and markdown daily digests.

**Current Status**: M1 complete. Production-ready for M2 automation deployment.

---

## Actual Project Structure

```
src/
├── agents/
│   ├── silo_wrangler/          # Agent 1: SILO API ingestion + DuckDB storage
│   │   ├── run_ingest.py       # CLI entry point
│   │   ├── api_client.py       # SILO API calls
│   │   ├── data_processor.py   # Cleaning, normalisation
│   │   └── quality_checker.py  # SILO quality code validation
│   ├── risk_engine/            # Agent 2: Event detection
│   │   ├── run_risk_engine.py  # CLI entry point (DuckDB-backed)
│   │   ├── csv_risk_engine.py  # CLI entry point (CSV-backed, M1 simplified)
│   │   └── event_detector.py   # Core threshold logic
│   └── insight_publisher/      # Agent 3: Reports + exports
│       ├── run_publisher.py    # CLI entry point
│       ├── report_generator.py # Markdown daily digest
│       └── export_generator.py # Power BI CSV exports
├── common/                     # Shared utilities
│   ├── constants.py            # SILO quality codes, EVENT_* string constants
│   ├── config_loader.py        # YAML config loading
│   ├── date_utils.py           # Crop stage + phenology helpers
│   ├── file_utils.py           # atomic_csv_write / atomic_csv_append
│   ├── logging_utils.py        # Structured logging setup
│   └── stations_loader.py      # BOM wheatbelt station list (1,376 stations)
└── data/
    ├── duckdb_storage.py       # DuckDB read/write, query_to_dataframe()
    └── silo_ingest.py          # Low-level ingestion utilities

config/
├── crop_calendars.yaml         # Stage dates, thresholds (frost/heat/rainfall)
├── assumptions.yaml            # Methodology notes, timing_critical stages
└── silo_sources.yaml           # Station tiers and API config

data/
├── weather.duckdb              # Primary weather store
├── obs/obs_daily.csv           # CSV fallback (M1 CSV engine input)
├── meta/wheatbelt_stations.csv # Station metadata
└── derived/                    # Event outputs (event_log.csv, *_events.csv)

reports/
├── daily/                      # YYYY-MM-DD_risk_digest.md
└── weekly/                     # YYYY-WW_outlook.md

scripts/
├── cron_schedule.sh            # Daily automation — calls all three agents in sequence
└── build_station_regions.py    # One-off: build data/meta/station_regions.csv
```

---

## Event Types

| event_type | Role | Active months | Severity values |
|---|---|---|---|
| `frost` | Damaging | Jul–Oct | light, moderate, severe |
| `heat` | Damaging | Oct–Dec | stress, severe |
| `rainfall` | Damaging (harvest) | Nov–Jan | moderate, high, severe |
| `seeding_rain` | Beneficial | Apr–Jun | adequate, inadequate |
| `development_rain` | Beneficial | Jul–Oct | dry_spell, moisture_stress |

All events use a consistent schema built by `WeatherEventDetector._build_event_record()`:
`station_id, date, event_type, severity, value, threshold, crop_stage, confidence, data_quality, detected_at` plus any type-specific extra fields.

---

## Event Detection Thresholds

Defined in `config/crop_calendars.yaml` under `thresholds:`.

### Frost
- Light: Tmin ≤ 2°C | Moderate: Tmin ≤ 0°C | Severe: Tmin ≤ -2°C
- Stage-specific overrides (e.g. flowering: 1°C threshold)

### Heat
- Stress: Tmax ≥ 32°C | Severe: Tmax ≥ 35°C
- Only active during `heat_critical` stages

### Harvest Rainfall
- Moderate: ≥10mm/day | High: ≥15mm over 3 days | Severe: ≥25mm

### Seeding Rainfall (Apr–Jun, beneficial)
- Germination trigger: ≥10mm/day | Adequate break: ≥25mm/7d | Dry: <5mm/7d

### Crop Development Rainfall (Jul–Oct, beneficial)
- Dry spell: <5mm/7d | Moisture stress: <10mm/14d

---

## SILO Data Quality Codes

Defined in `src/common/constants.py` — always import from there:

```python
from src.common.constants import SILO_QUALITY_CODES, SILO_QUALITY_DEFAULT
# 0=observed(1.0), 15=interpolated(0.8), 25=lower density(0.7),
# 35=synthetic(0.3), 75=lower quality(0.6), 999=missing(0.0)
```

---

## CLI Entry Points

```bash
# 1. Ingest SILO data for a date
python src/agents/silo_wrangler/run_ingest.py --date 2026-03-25

# 2a. Run risk engine (DuckDB-backed, full feature set)
python src/agents/risk_engine/run_risk_engine.py --date 2026-03-25
python src/agents/risk_engine/run_risk_engine.py --date-range 2026-03-01 2026-03-25

# 2b. Run risk engine (CSV-backed, M1 simplified, frost/heat only)
python src/agents/risk_engine/csv_risk_engine.py --date 2026-03-25

# 3. Generate daily report
python src/agents/insight_publisher/run_publisher.py --date 2026-03-25

# Code quality
flake8 src/
python -m pytest tests/
```

---

## Key Design Decisions

- **Atomic writes everywhere**: Use `atomic_csv_write()` / `atomic_csv_append()` from `src/common/file_utils.py` for all CSV output. Never call `.to_csv()` directly on output paths.
- **All event dicts via `_build_event_record()`**: Ensures consistent schema across all event types. Extra fields (accumulation_window, rainfall_role, etc.) passed as `**kwargs`.
- **Seeding/development detection is self-gating**: Methods check `target_month` internally — no external flag needed in `run_risk_engine.py`.
- **DuckDB column aliases**: `run_risk_engine.py` SQL query aliases `min_temp as min_temperature` etc. to match what `event_detector.py` expects.
- **CSV engine uses renamed columns**: `csv_risk_engine.py` renames to `min_temp`/`max_temp` (post-rename from obs_daily.csv).

---

## Output Files

```
data/derived/
├── event_log.csv               # All events, all types, all dates
├── frost_events.csv
├── heat_events.csv
├── rainfall_events.csv
├── seeding_rain_events.csv
└── development_rain_events.csv
```

---

## Three-Agent Architecture

### SILO Wrangler
Pulls SILO API data → DuckDB + `data/obs/obs_daily.csv`. Respects rate limits, atomic writes, preserves quality codes.

### Risk Engine
Reads DuckDB → `WeatherEventDetector` → `data/derived/event_log.csv`. Phenology-aware: flowering window active → 3x frost risk multiplier. Stage detection via `get_current_crop_stage()` with month-based fallback.

### Insight Publisher
Reads `event_log.csv` → markdown daily digest + Power BI CSV exports. Report includes Seasonal Moisture Status section for seeding/development rainfall.

---

## M1 Status: Complete

- ✅ SILO Wrangler: DuckDB-backed ingestion, 1,376 stations
- ✅ Risk Engine: Frost + heat + harvest rainfall + seeding/development rainfall detection
- ✅ Insight Publisher: Daily digest with phenology context and seasonal moisture tracker
- ✅ Quality code constants centralised in `src/common/constants.py`
- ✅ Atomic CSV writes throughout

---

## Downstream Integration

This project is one of several data sources feeding the **WA Grain Trade Monitor brief assemblers**:

- Interactive: `/monitor-brief` slash command in `/home/roddyb/projects/claude-notebooklm-research/`
- Headless / source-pack: `/home/roddyb/projects/reporter/` (`wheatbelt_risk_glob` in its `config.json`)

The assemblers read this project's output to populate the **crop conditions** section of a weekly draft for an agricultural bank analyst audience (farm advisors, ag lending).

### What the assembler reads

| File | Purpose |
|---|---|
| `data/derived/event_log.csv` | Recent risk events (past 7 days) — primary source |
| `reports/weekly/YYYY-WW_outlook.md` | Weekly summary — used directly in draft if available |

### Fields the assembler depends on

From `event_log.csv`: `date`, `event_type`, `severity`, `station_name`, `region_name`, `value`

**Do not rename these columns or change the `data/derived/` or `reports/weekly/` paths without also updating the assembler.**

### M2 goal

Ensure `reports/weekly/YYYY-WW_outlook.md` is generated automatically each week (via cron or manual trigger). The assembler will use this file directly as the crop conditions narrative — reducing the need to query NotebookLM for weather context.
