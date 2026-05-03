# CropForecaster

Operational weather monitoring for daily frost, heat stress, and rainfall risk assessment across the Australian wheatbelt. Pulls daily observations from the SILO API (Bureau of Meteorology stations), detects agronomic risk events, and generates markdown risk digests.

---

## Architecture

Three agents run in sequence each day:

```
SILO Wrangler  →  Risk Engine  →  Insight Publisher
(ingest)          (detect)         (report)
```

| Agent | Entry point | Role |
|---|---|---|
| SILO Wrangler | `src/agents/silo_wrangler/run_ingest.py` | Fetch daily SILO data → DuckDB + CSV |
| Risk Engine | `src/agents/risk_engine/run_risk_engine.py` | Detect frost / heat / rainfall events |
| Insight Publisher | `src/agents/insight_publisher/run_publisher.py` | Generate daily markdown digest + Power BI exports |

Daily automation: `scripts/cron_schedule.sh` runs all three in order (crontab entry inside the script).

---

## Setup

```bash
pip install -e .
cp .env.example .env          # add your SILO_EMAIL
```

`.env` requires one variable:
```
SILO_EMAIL=your.email@example.com
```

---

## Running

```bash
# Full daily pipeline (ingest → detect → report) for a specific date
./scripts/cron_schedule.sh --date 2026-05-02

# Individual agents
python src/agents/silo_wrangler/run_ingest.py --date 2026-05-02
python src/agents/risk_engine/run_risk_engine.py --date 2026-05-02
python src/agents/insight_publisher/run_publisher.py --date 2026-05-02

# Date-range ingest (backfill or catch-up)
python src/agents/silo_wrangler/run_ingest.py --date-range 2026-04-01 2026-04-30

# Broader station coverage
python src/agents/silo_wrangler/run_ingest.py --use-bom-dataset --states "Western Australia" --days 40
python src/agents/silo_wrangler/run_ingest.py --use-bom-dataset --states "Western Australia" --hybrid
```

---

## Outputs

| Path | Contents |
|---|---|
| `data/weather.duckdb` | Primary weather store (DuckDB) |
| `data/obs/obs_daily.csv` | Daily observations (CSV mirror) |
| `data/derived/event_log.csv` | All risk events — consumed by downstream assembler |
| `data/derived/*_events.csv` | Per-type event logs (frost, heat, rainfall, seeding_rain, development_rain) |
| `reports/daily/YYYY-MM-DD_risk_digest.md` | Daily markdown risk digest |
| `reports/weekly/YYYY-WW_outlook.md` | Weekly outlook (M2 automation target) |

The `event_log.csv` and `reports/weekly/` outputs feed a downstream weekly grains market update assembler at `../claude-notebooklm-research/projects/weekly-grains-market/`.

---

## Configuration

| File | Purpose |
|---|---|
| `config/silo_sources.yaml` | SILO API config, station tiers, Data Drill grid settings |
| `config/crop_calendars.yaml` | Growth stages, event thresholds (frost/heat/rainfall) |
| `config/assumptions.yaml` | Methodology notes |
| `config/crop_context.yaml` | ABS crop commodity codes and baseline year for SA2 context integration |
| `.env` | SILO credentials (gitignored) |

Station tiers (`active`, `unverified`, `inactive`) control which stations are queried. Override credentials via `config/silo_sources.local.yaml` (gitignored).

---

## Event types

| Type | Role | Active window | Severities |
|---|---|---|---|
| `frost` | Damaging | Jul–Oct | light, moderate, severe |
| `heat` | Damaging | Oct–Dec | stress, severe |
| `rainfall` | Damaging (harvest) | Nov–Jan | moderate, high, severe |
| `seeding_rain` | Beneficial | Apr–Jun | adequate, marginal, inadequate |
| `development_rain` | Beneficial | Jul–Oct | dry_spell, moisture_stress |

All events share a consistent schema — see `CLAUDE.md` for field definitions.

---

## Current limitations

- WA wheatbelt coverage only (SA/VIC/NSW expansion ready but not activated)
- No test suite (M2 backlog)
- `data/external/` contains large NetCDF reference files (~1 GB) not used by the daily pipeline — consider external storage
- Weekly outlook report (`reports/weekly/`) requires a manual trigger; cron automation is the M2 goal
