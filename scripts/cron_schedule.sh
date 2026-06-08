#!/bin/bash
# CropForecaster Daily Automation
#
# Timing: Run at 6am AEST (8pm UTC previous day) — SILO data typically
# available ~5am AEST for the previous day.
#
# Crontab entry:
#   0 20 * * * /home/roddyb/projects/wheatbelt_rainfall_analyser/scripts/cron_schedule.sh >> /home/roddyb/projects/wheatbelt_rainfall_analyser/logs/cron.log 2>&1
#
# Or with explicit date override (e.g. for backfill):
#   ./cron_schedule.sh --date 2026-03-24

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# Parse optional --date argument; default to yesterday (SILO lag)
TARGET_DATE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --date) TARGET_DATE="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

if [[ -z "$TARGET_DATE" ]]; then
    TARGET_DATE=$(date -d "yesterday" +%Y-%m-%d 2>/dev/null || date -v-1d +%Y-%m-%d)
fi

echo "============================================"
echo "CropForecaster daily run — $TARGET_DATE"
echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

cd "$PROJECT_ROOT"

# Activate virtual environment if present
if [[ -f ".venv/bin/activate" ]]; then
    source .venv/bin/activate
elif [[ -f "venv/bin/activate" ]]; then
    source venv/bin/activate
fi

# Step 1: Ingest SILO data
echo ""
echo "--- Step 1: SILO Wrangler ---"
# Daily coverage = broadacre-cropping SA2s (~1,293 stations at the 5,000 ha default),
# up from the legacy 16 active-tier stations. Fallback: --coverage-mode active_tier.
python src/agents/silo_wrangler/run_ingest.py --date "$TARGET_DATE" --coverage-mode sa2_broadacre

# Step 2: Run risk engine
echo ""
echo "--- Step 2: Risk Engine ---"
python src/agents/risk_engine/run_risk_engine.py --date "$TARGET_DATE"

# Step 3: Generate daily report
echo ""
echo "--- Step 3: Insight Publisher ---"
python src/agents/insight_publisher/run_publisher.py --date "$TARGET_DATE"

echo ""
echo "============================================"
echo "Completed: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"
