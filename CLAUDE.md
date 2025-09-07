# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CropForecaster** is a Python-based operational weather monitoring system that provides daily frost, heat stress, and harvest rainfall risk assessment for the Australian wheatbelt. The system ingests daily weather data from SILO API and generates event-based CSV logs for external system integration.

**Current Status**: MVP development targeting September 2025 launch
**Milestones**: M1 (Sep 10) - Basic event detection | M2 (Sep 20) - Full automation | Launch (Sep 25-30)

## Key Data Sources

- **SILO API**: Daily min/max temperature and rainfall data via API calls
- **Station coverage**: 2000+ weather stations across Australian wheatbelt
- **Historical data**: 1990-ongoing for validation and trend analysis
- **Geographic boundaries**: Wheatbelt region definitions for station filtering

## Core System Architecture

```
src/
├── data/           # SILO API ingestion and daily data processing
├── features/       # Event detection logic (frost/heat/rainfall)
├── models/         # Future: yield prediction models
├── visualization/  # Optional: maps and risk visualization
```

**Critical modules for MVP**:
- `src/data/silo_api.py`: Daily SILO API integration and data ingestion
- `src/features/event_detection.py`: Frost/heat/rainfall threshold logic
- `src/data/csv_logging.py`: Structured event logging system

## Event Detection Thresholds

### Frost Events
- Light frost: 0°C to 2°C
- Moderate frost: -2°C to 0°C  
- Severe frost: < -2°C

### Heat Events
- Hot day: Tmax > 32°C
- Very hot: Tmax > 35°C

### Harvest Rainfall Risk (Oct-Dec)
- Heavy rain: >10mm/day
- Multi-day risk: >15mm/3-day total

## Output Structure

Daily CSV logs in `processed/` directory:
- `frost_events.csv`: station_id, date, min_temp, risk_flag
- `heat_events.csv`: station_id, date, max_temp, risk_flag  
- `rain_events.csv`: station_id, date, rainfall, risk_flag

Performance target: <10 seconds processing time for all stations daily

## Development Commands

```bash
# Install project dependencies
pip install -r requirements.txt

# Install project as editable package
pip install -e .

# Run daily weather monitoring (MVP target)
python src/data/daily_ingest.py
python src/features/detect_events.py

# Code quality
flake8 src/

# Test event detection logic
python -m pytest tests/test_event_detection.py
```

## Three-Agent Architecture

CropForecaster follows an **ingest → detect → communicate** flow with specialized agents:

### **SILO Wrangler** (Data Ingest + QC)
**Mission**: Pull daily weather from SILO, apply quality flags, write analysis-ready tables

**Key Responsibilities**:
- Fetch SILO point data (station/grid) for variables: rain, Tmax, Tmin, VP, MSLP
- Respect rate limits; cache results; rolling window updates (3-12 months)
- Persist to CSV files: `obs_daily.csv`, `stations.csv`, `grid_meta.csv`
- Preserve provenance (source codes) for observed vs interpolated filtering
- Optional: mirror gridded NetCDF files for fast local slicing

**Inputs → Outputs**:
- In: `config/silo_sources.yaml`, station lists, date windows, variable maps
- Out: `data/obs/obs_daily.csv`, `data/meta/stations.csv`, `logs/ingest_runs.jsonl`

**Guardrails**: Atomic writes, soft failure handling, never overwrite history

### **Risk Engine** (Event Detection)
**Mission**: Transform weather into crop risk events with auditable thresholds

**Key Responsibilities**:
- Frost detection: Tmin < 2°C/0°C events, consecutive nights, intensity buckets  
- Heat stress: Tmax > 32°C/35°C counts during sensitive crop phases
- Harvest rain: Rolling sums (≥15/25/50mm in 3/5/7 days) with downgrade risk tags
- Statistical Division aggregation with crop mix weights and severity scoring
- Generate `event_log.csv`, `sd_risk_rollup.csv`, optional `events.geojson`

**Inputs → Outputs**:
- In: `obs_daily.csv`, `config/crop_calendars.yaml`, SD boundary data
- Out: `data/derived/event_log.csv`, `data/derived/sd_risk_rollup.csv`

**Guardrails**: Explicit assumptions in YAML, confidence scoring for data gaps

### **Insight Publisher** (Reports + Alerts)  
**Mission**: Package detections into human-ready updates and reusable exports

**Key Responsibilities**:
- Daily Risk Digest: key events, top SDs at risk, sparkline tables (markdown)
- Weekly Outlook: 7/14-day summaries, agronomic implications, PDF export
- Power BI exports: `risk_events.csv`, `risk_events_latest.csv` (current day)
- Changelog tracking, maintain `/reports/` index

**Inputs → Outputs**:
- In: `event_log`, `sd_risk_rollup`, prior reports
- Out: `reports/daily/YYYY-MM-DD_risk_digest.md`, `reports/weekly/YYYY-WW_outlook.md`, `data/exports/*.csv`

**Guardrails**: Stable file names for automation, no price analysis

## Critical Success Factors

1. **Daily reliability**: Zero missed daily runs during critical crop periods
2. **API resilience**: Robust handling of SILO API delays or changes  
3. **Accuracy**: Event detection validation against known frost/heat reports
4. **Performance**: Sub-10 second processing for operational requirements
5. **Data exports**: Clean CSV format for downstream system integration

## Current Development Focus

**This Week (M1 Sprint)**: 
- SILO API daily ingestion working
- Basic frost/heat detection on sample stations
- CSV logging functionality tested

**Next Phase**: Full wheatbelt station coverage with automated daily workflow

The system prioritizes operational reliability over research flexibility, with all development focused on the September launch window for peak heat risk season.

---

## Session Log

### 2025-09-07: BOM Wheatbelt Stations Integration

**Files Changed:**
- `src/common/stations_loader.py` - New comprehensive BOM dataset loader with geographic filtering
- `src/agents/silo_wrangler/run_ingest.py` - Added CLI options for BOM dataset integration
- `config/silo_sources.yaml` - Updated with BOM dataset configuration and usage examples
- `pyproject.toml` - Fixed TOML syntax error and added missing dependencies

**Summary:**
Successfully integrated comprehensive BOM wheatbelt stations dataset (1,376 stations) into SILO Wrangler. System now supports:
- Three operational modes: config tiers, BOM dataset, direct CLI override
- Geographic filtering: state-based, cropping area thresholds, random sampling
- Quality-based automatic station exclusion with override capability
- Complete M1→M2 scalability from 9 to 1,000+ stations

**Testing Completed:**
✅ Tiered station classification (active/unverified/inactive)  
✅ BOM dataset random sampling (5 stations)  
✅ State filtering (Western Australia only)  
✅ Cropping area filtering (>400,000ha regions)  
✅ Quality assessment and automatic exclusion  

**Next Steps:**
1. **Risk Engine Implementation** - Core M1 milestone requirement
   - Frost detection thresholds (Tmin < 2°C/0°C)
   - Heat stress detection (Tmax > 32°C/35°C)  
   - Event logging system (`data/derived/event_log.csv`)
   - Crop calendar integration for seasonal context

2. **Insight Publisher** - Complete M1 deliverables
   - Daily risk digest generation
   - Export CSV files for downstream systems

**Blockers:** None - SILO Wrangler foundation complete and production-ready

**M1 Status:** SILO Wrangler ✅ Complete | Risk Engine 🔄 Ready to Begin | Insight Publisher ⏳ Pending

## Essential Documentation

**API Integration References**:
- `docs/Logpaddock_SILO_API_Reference.pdf` - Official SILO API documentation
- `docs/silo_api_usage_guide.md` - CropForecaster-specific API examples and best practices

**Project Planning**:
- `prd.md` - Product requirements and event detection thresholds
- `task_manager.md` - Current sprint tasks and development priorities

**Development Guidance**:
- `README.md` - Setup instructions and project overview
- `CLAUDE.md` - This file (system architecture and agent guidance)