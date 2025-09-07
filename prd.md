# Product Requirements Document (PRD)

## Product: CropForecaster

### One-line
A local Python-based app that monitors frost, heat stress, and harvest rainfall to assess crop yield risk across Australian winter crops.

### Problem & Why Now
- **Who has the problem**: Australian grain growers, agronomists, and analysts seeking timely alerts on weather-induced crop risks.
- **Why it matters**: Frost, heat stress, and harvest rainfall can cause severe yield and quality losses. These events are highly timing-sensitive and spatially variable.
- **Success criteria**:
  - Business: High-accuracy detection of damaging weather events, timely alert generation, improved decision-making confidence.
  - User: Easy-to-read event logs, reliable daily updates, clear categorization of risk (e.g., severe frost, hot spell, heavy rain).

### Core Use Cases / User Stories
- **UC1**: As a grower or analyst, I want to detect frost events below 2°C during flowering so I can assess yield loss risk.
- **UC2**: As an agronomist, I want to monitor hot days (>32°C) during grain fill to anticipate potential grain size or quality issues.
- **UC3**: As a consultant, I want to track heavy rainfall during harvest to flag areas at risk of downgrades.

### Scope v1 (MVP)
- **In-scope**:
  - Daily download of min/max temperature and rainfall from SILO
  - Frost event flagging
  - Heat event flagging
  - Rainfall tracking and risk thresholds
  - Simple CSV logging and optional plot generation
- **Out-of-scope**:
  - Web frontend
  - Yield model integration
  - Cloud hosting or data syncing
  - Notifications or email alerts

### System Overview
- **Frontend stack**: None (local CLI or notebook output)
- **Backend stack**: Python 3.9, WSL Ubuntu
- **Data/DB**: CSV files, optionally DuckDB for analysis
- **Auth**: None (uses public API with email)
- **Third-party APIs/keys**:
  - SILO API (https://www.longpaddock.qld.gov.au/silo/)

### Milestones & Timelines
- **M1 (Sep 10)**: Basic frost and heat monitoring logic working on sample stations
- **M2 (Sep 20)**: Full station set hooked up with daily update automation
- **Launch window**: Sept 25–30 (aligned with peak heat risk window)

### KPIs
- Number of daily event logs generated
- Event detection accuracy (compared to known frost/heat reports)
- Time-to-log after data availability

### Risks / Assumptions
- **Risks**:
  - Delays in SILO data ingestion or API changes
  - False positives from poorly sited weather stations
- **Assumptions**:
  - SILO data is updated nightly and stable
  - 2000+ stations have >95% data completeness

### Non-functional
- Performance: <10 sec per day's data for all stations
- Security: Local only, no web exposure
- Accessibility: CLI and CSV outputs
- Logging/Observability: Timestamped event logs in `processed/`
#### Event Threshold Logic
- **Frost Monitoring**:
  - Light frost: 0°C to 2°C
  - Moderate frost: -2°C to 0°C
  - Severe frost: < -2°C

- **Heat Monitoring**:
  - Hot day: Tmax > 32°C
  - Very hot: Tmax > 35°C

- **Rainfall Downgrade Risk**:
  - Heavy rain: >10mm/day
  - Risk window: Oct–Dec
  - Multi-day flag: >15mm/3-day total

#### Outputs (CSV logs per event type)
- `processed/frost_events.csv`
- `processed/heat_events.csv`
- `processed/rain_events.csv`
Each log contains: `station_id`, `date`, `value`, and a `risk_flag`

#### Daily Workflow
1. Query SILO API (station or grid) for yesterday's data
2. Apply event thresholds for frost, heat, rain
3. Append flagged events to respective CSVs
4. (Optional) Generate daily raster (QGIS-ready) or PNG heatmap

#### System Design Summary (Overriding/Enhancing Existing PRD)
- **Execution**: CLI scripts, Jupyter Notebooks or automated via `cron`
- **Frontend**: None (headless)
- **Storage**: CSV, optionally DuckDB
- **Analysis tools**: Python, matplotlib, QGIS
- **Update Frequency**: Daily (via scheduled job)