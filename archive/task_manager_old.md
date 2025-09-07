# CropForecaster - Task Manager
*Australian Weather Risk Monitoring for Winter Crops*

## Project Overview
A Python-based system that monitors frost, heat stress, and harvest rainfall risks across the Australian wheatbelt using SILO data (1990-ongoing). Provides daily weather event detection and risk assessment for grain growers and agronomists.

## Current Sprint Status
**Target**: M1 (Sep 10) - Basic frost and heat monitoring logic working on sample stations
**Next**: M2 (Sep 20) - Full station set with daily automation
**Launch**: Sept 25-30 (aligned with peak heat risk window)

## MVP Scope (v1)
- [x] Project structure established
- [x] SILO data exploration and download utilities
- [ ] **Daily automated SILO data ingestion**
- [ ] **Frost event detection and flagging**
- [ ] **Heat event detection and flagging** 
- [ ] **Rainfall tracking during harvest period**
- [ ] **CSV logging system for all events**
- [ ] **Optional plot/map generation**

## Task Categories

### 1. CORE SYSTEM - Daily Weather Monitoring
**Priority**: CRITICAL - MVP Deliverable

#### Immediate (This Week)
- [ ] Set up SILO API daily data ingestion pipeline
- [ ] Implement frost detection logic:
  - Light frost: 0�C to 2�C
  - Moderate frost: -2�C to 0�C  
  - Severe frost: < -2�C
- [ ] Implement heat event detection:
  - Hot day: Tmax > 32�C
  - Very hot: Tmax > 35�C
- [ ] Create CSV logging structure:
  - `processed/frost_events.csv`
  - `processed/heat_events.csv`
  - `processed/rain_events.csv`

#### Next Week (M1 Completion)
- [ ] Test event detection on sample weather stations
- [ ] Validate threshold logic against known events
- [ ] Set up automated daily workflow
- [ ] Performance optimization (<10 sec per day's data)

### 2. RAINFALL RISK MONITORING
**Priority**: HIGH - Harvest Risk Assessment

#### Harvest Season Focus (Oct-Dec)
- [ ] Implement rainfall downgrade risk detection:
  - Heavy rain: >10mm/day
  - Multi-day risk: >15mm/3-day total
- [ ] Create harvest period monitoring dashboard
- [ ] Set up risk flagging system for vulnerable areas
- [ ] Generate daily rainfall risk summaries

### 3. DATA INFRASTRUCTURE
**Priority**: HIGH - System Reliability

#### Data Pipeline
- [ ] Robust SILO API integration (handle API changes/delays)
- [ ] Data validation and quality checks (>95% completeness target)
- [ ] Historical data backfill (1990-2024)
- [ ] Backup and recovery procedures

#### Station Management  
- [ ] Complete Australian wheatbelt station coverage (2000+ stations)
- [ ] Filter poorly sited stations (reduce false positives)
- [ ] Geographic boundary validation
- [ ] Station metadata management

### 4. AUTOMATION & DEPLOYMENT
**Priority**: MEDIUM - Operational Efficiency

#### Daily Operations
- [ ] Cron job setup for daily data ingestion
- [ ] Automated event detection workflow
- [ ] Log rotation and archival
- [ ] Error handling and alerting

#### Optional Enhancements
- [ ] QGIS-ready raster generation
- [ ] PNG heatmap creation
- [ ] DuckDB integration for faster queries
- [ ] Basic CLI interface

### 5. ANALYSIS & REPORTING
**Priority**: MEDIUM - Decision Support

#### Event Analysis
- [ ] Historical frost/heat event patterns
- [ ] Regional risk mapping
- [ ] Seasonal trend analysis
- [ ] Event frequency statistics

#### Validation & Accuracy
- [ ] Compare detection against known frost/heat reports
- [ ] False positive analysis and threshold tuning
- [ ] Regional accuracy assessment
- [ ] Performance KPI tracking

### 6. FUTURE DEVELOPMENT
**Priority**: LOW - Post-MVP

#### Model Development (Future Phases)
- [ ] Yield prediction model framework
- [ ] Historical yield correlation analysis
- [ ] Machine learning risk assessment
- [ ] Advanced forecasting capabilities

#### System Expansion
- [ ] Web frontend development
- [ ] Cloud deployment options
- [ ] Email/SMS alert system
- [ ] API development for external systems

## Current Week Focus
**M1 Milestone Tasks (Due Sep 10)**

### Must Complete
- [ ] SILO daily data download automation
- [ ] Basic frost detection (sample stations)
- [ ] Basic heat detection (sample stations)
- [ ] CSV logging functionality
- [ ] Test on 10-20 representative stations

### Should Complete
- [ ] Rainfall detection logic
- [ ] Performance benchmarking
- [ ] Error handling basics
- [ ] Documentation of threshold logic

## Risk Mitigation
- **SILO API reliability**: Implement retry logic and fallback strategies
- **Data quality**: Station filtering and validation checks
- **Performance**: Optimize for 2000+ stations daily processing
- **Accuracy**: Continuous validation against known events

## Success Metrics (KPIs)
- [ ] Daily event logs generated successfully
- [ ] <10 second processing time per day
- [ ] >95% station data completeness
- [ ] Event detection accuracy validation
- [ ] Zero missed daily runs during critical periods

## Technical Architecture
- **Execution**: CLI scripts + Jupyter notebooks
- **Storage**: CSV files, optional DuckDB
- **APIs**: SILO weather data API
- **Environment**: Python 3.9+ on WSL Ubuntu
- **Automation**: Cron for daily scheduling

## Data Exports
All outputs designed for external system integration:
- Timestamped CSV event logs
- Geographic coordinates for mapping
- Risk flags for decision support
- Historical trend data

## Quick Reference Documentation

**For Development Work**:
- [`docs/silo_api_usage_guide.md`](docs/silo_api_usage_guide.md) - API integration examples and best practices
- [`docs/Logpaddock_SILO_API_Reference.pdf`](docs/Logpaddock_SILO_API_Reference.pdf) - Complete SILO API specification
- [`prd.md`](prd.md) - Event thresholds and system requirements
- [`CLAUDE.md`](CLAUDE.md) - Architecture overview and agent guidance

---
*Last updated: September 6, 2025*
*Next milestone review: September 10, 2025 (M1)*
*Launch target: September 25-30, 2025*