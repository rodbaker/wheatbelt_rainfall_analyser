# CropForecaster - Task Manager (3-Agent Architecture)
*Australian Weather Risk Monitoring for Winter Crops*

## Project Overview
A Python-based system that monitors frost, heat stress, and harvest rainfall risks across the Australian wheatbelt using SILO data (1990-ongoing). Provides daily weather event detection and risk assessment for grain growers and agronomists.

**Architecture**: **Ingest → Detect → Communicate** flow with specialized agents

## Current Sprint Status
**Target**: M1 (Sep 10) - Basic frost and heat monitoring logic working on sample stations
**Next**: M2 (Sep 20) - Full station set with daily automation
**Launch**: Sept 25-30 (aligned with peak heat risk window)

## MVP Scope (v1)
- [x] Project structure established
- [x] SILO data exploration and download utilities
- [ ] **3-Agent architecture implementation**
- [ ] **Daily automated SILO data ingestion (Wrangler)**
- [ ] **Event detection and risk scoring (Risk Engine)**
- [ ] **Daily reports and data exports (Insight Publisher)**

## Task Categories (3-Agent Architecture)

### 1. SILO Wrangler - Data Ingest + QC
**Priority**: CRITICAL - Foundation for all downstream processing

#### M1 Starter Tasks (This Week)
- [ ] Load `config/silo_sources.yaml` (stations or grid points, date range policy)
- [ ] Pull/update recent window data via SILO API
- [ ] Append clean data to `data/obs/obs_daily.parquet`
- [ ] Record run metadata to `logs/ingest_runs.jsonl` with counts and data gaps
- [ ] Implement quality flag preservation (observed vs interpolated)

#### M2 Enhancement Tasks
- [ ] DuckDB integration for fast SQL queries on Parquet files
- [ ] Rolling window optimization (3-12 month updates only)
- [ ] Station metadata management (`data/meta/stations.parquet`)
- [ ] Optional: NetCDF mirroring for gridded data access
- [ ] Rate limiting and API resilience improvements

### 2. Risk Engine - Event Detection  
**Priority**: CRITICAL - Core business logic

#### M1 Starter Tasks (This Week)
- [ ] Read `obs_daily.parquet` and apply frost/heat thresholds
- [ ] Implement stage windows from `config/crop_calendars.yaml`
- [ ] Write `data/derived/event_log.parquet` + `sd_risk_rollup.parquet`
- [ ] Save `config/assumptions.yaml` alongside outputs for auditability
- [ ] Basic Statistical Division aggregation logic

#### M2 Enhancement Tasks  
- [ ] Consecutive night frost counting and intensity buckets
- [ ] Multi-day rainfall accumulation (3/5/7 day rolling sums)
- [ ] Crop mix weighting and severity scoring by region
- [ ] Confidence scoring for data gap handling
- [ ] Optional: GeoJSON export for mapping (`events.geojson`)

### 3. Insight Publisher - Reports + Alerts
**Priority**: HIGH - User-facing deliverables

#### M1 Starter Tasks (This Week)
- [ ] Generate daily `reports/daily/YYYY-MM-DD_risk_digest.md`
- [ ] Update `data/exports/risk_events_latest.csv` (current day only)
- [ ] Create basic markdown templates for risk summaries
- [ ] Implement changelog tracking (what changed vs yesterday)

#### M2 Enhancement Tasks
- [ ] Weekly outlook generation (`reports/weekly/YYYY-WW_outlook.md`) 
- [ ] Power BI export optimization with stable column schemas
- [ ] PDF generation for weekly summaries (optional)
- [ ] Reports index maintenance and archival

### 4. SUPPORTING INFRASTRUCTURE
**Priority**: MEDIUM - Cross-Agent Requirements

#### Configuration Management
- [ ] Create `config/silo_sources.yaml` template
- [ ] Create `config/crop_calendars.yaml` with Australian wheat seasons
- [ ] Create `config/assumptions.yaml` template for transparency
- [ ] Environment-specific config support (dev/staging/prod)

#### Data Architecture
- [ ] Set up directory structure: `data/obs/`, `data/derived/`, `data/exports/`
- [ ] Implement Parquet file standards and naming conventions
- [ ] Create logging standards (`logs/ingest_runs.jsonl`)
- [ ] Backup and recovery procedures

## Current Week Focus
**M1 Milestone Tasks (Due Sep 10)**

### SILO Wrangler Must Complete
- [ ] Basic SILO API integration with config-driven station lists
- [ ] Parquet output working for daily weather observations
- [ ] Run logging and gap tracking functional

### Risk Engine Must Complete  
- [ ] Frost detection (Tmin < 2°C/0°C) working on sample data
- [ ] Heat detection (Tmax > 32°C/35°C) working on sample data
- [ ] Event log output in structured format

### Insight Publisher Must Complete
- [ ] Daily risk digest generation (markdown format)
- [ ] CSV export for current day events
- [ ] Basic template structure for reports

## Risk Mitigation (3-Agent Context)
- **SILO Wrangler**: API reliability, data completeness validation, atomic file operations
- **Risk Engine**: Threshold accuracy validation, data gap confidence scoring
- **Insight Publisher**: Stable file naming, downstream system compatibility
- **Cross-Agent**: Config management, data format standards, error propagation

## Success Metrics (KPIs)
- [ ] All 3 agents working in pipeline by M1 deadline
- [ ] End-to-end daily run completing successfully
- [ ] Clean data artifacts produced by each agent
- [ ] Event detection accuracy validation on sample data
- [ ] Performance targets met (<10 sec total pipeline time)

## Technical Architecture (Updated)
- **Execution**: Agent-specific CLI scripts + coordination workflows
- **Storage**: Parquet files + DuckDB (optional), structured configs (YAML)
- **Data Flow**: `obs_daily.parquet` → `event_log.parquet` → `risk_digest.md` + CSV exports
- **APIs**: SILO weather data API (Wrangler agent only)
- **Environment**: Python 3.9+ on WSL Ubuntu
- **Automation**: Cron for daily 3-agent pipeline execution

## Data Exports (Agent-Specific)
**SILO Wrangler Outputs**: Clean weather observations, station metadata, run logs
**Risk Engine Outputs**: Event logs, Statistical Division rollups, confidence scores
**Insight Publisher Outputs**: Daily/weekly reports, Power BI CSVs, changelog

## Quick Reference Documentation

**For Development Work**:
- [`docs/silo_api_usage_guide.md`](docs/silo_api_usage_guide.md) - API integration examples and best practices
- [`docs/Logpaddock_SILO_API_Reference.pdf`](docs/Logpaddock_SILO_API_Reference.pdf) - Complete SILO API specification
- [`prd.md`](prd.md) - Event thresholds and system requirements
- [`CLAUDE.md`](CLAUDE.md) - Architecture overview and 3-agent guidance

---
*Last updated: September 7, 2025*
*Architecture: 3-Agent (Ingest → Detect → Communicate)*
*Next milestone review: September 10, 2025 (M1)*
*Launch target: September 25-30, 2025*