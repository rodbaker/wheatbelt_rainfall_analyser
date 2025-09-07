# CropForecaster Project Cleanup Plan

## Overview
Transform old Jupyter notebook research project into operational 3-agent CropForecaster system.

## 🗑️ REMOVE/ARCHIVE (No longer needed for operational system)

### Immediate Actions
```bash
# 1. Archive old research notebooks
mkdir -p archive/old_notebooks
mv notebooks/* archive/old_notebooks/

# 2. Archive old task manager (already done)
# mv task_manager.md archive/task_manager_old.md

# 3. Remove template placeholder files
rm src/models/train_model.py        # Empty template
rm src/models/predict_model.py      # Not needed for MVP  
rm src/features/build_features.py   # Template placeholder
rm src/visualization/visualize.py   # Template placeholder

# 4. Clean up cookiecutter remnants
rm src/data/make_dataset.py         # Template placeholder - will create agent-specific files
rm src/visualization/plot_temp.py   # Old plotting code
rm src/visualization/plot_data.py   # Old plotting code

# 5. Remove node_modules (not needed for Python project)
rm -rf node_modules/

# 6. Archive old NetCDF-focused code
mkdir -p archive/old_src
mv src/features/modify_netcdf.py archive/old_src/
mv src/features/rainfall_functions.py archive/old_src/  # NetCDF focused
```

### Optional Archives (keep for reference)
```bash
# Keep but move to reference location
mkdir -p archive/reference
mv src/data/download_functions.py archive/reference/    # Has S3 download logic
mv src/data/silo_downloader.py archive/reference/      # Has SILO patterns
mv src/data/rainfall_metrics.py archive/reference/     # Has analysis patterns
```

## 📁 REORGANIZE (Align with 3-agent architecture)

### Data Directory Structure
```bash
# Create 3-agent data flow structure
mkdir -p data/{obs,meta,derived,exports}
mkdir -p logs
mkdir -p reports/{daily,weekly}

# Move existing data to appropriate locations
mv data/gridded/* data/meta/            # NetCDF reference data
mv data/external/* data/meta/           # External reference data  
mv data/colormaps/* archive/reference/  # Not needed for operational system
```

### Source Code Structure  
```bash
# Create 3-agent source structure
mkdir -p src/agents/{silo_wrangler,risk_engine,insight_publisher}
mkdir -p src/common                     # Shared utilities
mkdir -p tests                         # Unit tests

# Keep existing useful utilities
mv src/data/__init__.py src/common/
mv src/features/__init__.py src/common/ 
mv src/__init__.py src/common/
```

## ✅ CREATE NEW (3-Agent specific files)

### Agent Implementation Files
```bash
# SILO Wrangler agent
src/agents/silo_wrangler/
├── __init__.py
├── api_client.py          # SILO API integration
├── data_processor.py      # CSV output formatting  
├── quality_checker.py     # Data validation
└── run_ingest.py         # Daily execution script

# Risk Engine agent  
src/agents/risk_engine/
├── __init__.py
├── event_detector.py     # Frost/heat/rain detection
├── stage_calculator.py   # Crop stage logic
├── risk_scorer.py        # Statistical Division aggregation
└── run_detection.py      # Daily execution script

# Insight Publisher agent
src/agents/insight_publisher/
├── __init__.py  
├── report_generator.py   # Markdown report creation
├── csv_exporter.py       # Power BI exports
├── change_tracker.py     # Changelog logic
└── run_publishing.py     # Daily execution script

# Common utilities
src/common/
├── __init__.py
├── config_loader.py      # YAML config handling
├── file_utils.py         # Atomic writes, CSV utilities
├── logging_utils.py      # Structured logging
└── date_utils.py         # Date handling utilities
```

## 🔧 UPDATE EXISTING FILES

### Requirements.txt - Add operational dependencies
```python
# Remove research-focused dependencies
# Add operational dependencies:
requests                 # SILO API calls
pandas                   # CSV processing  
pyyaml                   # Config files
python-dateutil          # Date handling
click                    # CLI interfaces (keep)
python-dotenv>=0.5.1     # Keep for env management

# Optional future additions:
# geopandas              # For SD boundary processing
# matplotlib             # For optional visualizations  
```

### .gitignore - Add operational patterns
```gitignore
# Add to existing .gitignore:
logs/*.jsonl
data/obs/*.csv
data/derived/*.csv  
data/exports/*.csv
reports/daily/*.md
reports/weekly/*.md
config/*.local.yaml
.env.local
```

## 🎯 PRIORITY ORDER

### Phase 1: Immediate Cleanup (This Week)
1. ✅ Archive old notebooks and task managers (done)
2. Remove template placeholder files  
3. Create 3-agent directory structure (done)
4. Update requirements.txt for operational needs

### Phase 2: New Implementation (M1 Sprint)
1. Create SILO Wrangler agent skeleton
2. Create Risk Engine agent skeleton  
3. Create Insight Publisher agent skeleton
4. Implement basic config loading

### Phase 3: Archive & Reference (Later)
1. Move old NetCDF code to archive/reference
2. Document migration from research to operational approach
3. Clean up any remaining cookiecutter artifacts

## 📊 BEFORE/AFTER STRUCTURE

### Before (Research Project)
```
notebooks/           # 13 Jupyter notebooks
src/data/           # S3/NetCDF download scripts
src/features/       # NetCDF processing  
src/models/         # Empty templates
src/visualization/  # Basic plotting
data/external/      # Mixed NetCDF files
```

### After (Operational System)
```
config/             # YAML configurations
src/agents/         # 3 specialized agents
src/common/         # Shared utilities  
data/obs/          # Daily weather CSV
data/derived/      # Event detection CSV
data/exports/      # Power BI exports
reports/daily/     # Risk digests
logs/              # Execution logs
archive/           # Old research code
```

## 🚀 BENEFITS OF CLEANUP

1. **Clear separation**: Research vs operational code
2. **Agent focus**: Each directory serves specific agent
3. **Data flow**: Clean ingest → detect → communicate pipeline
4. **Maintainability**: Remove unused research artifacts
5. **Deployment ready**: Operational structure for production

## ⚠️ PRESERVE FOR REFERENCE

Keep these in `archive/reference/` for learning:
- Old SILO download patterns (`silo_downloader.py`)
- NetCDF processing examples (`modify_netcdf.py`)
- Research notebooks (moved to `archive/old_notebooks/`)
- Original cookiecutter structure documentation