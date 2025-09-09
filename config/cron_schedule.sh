#!/bin/bash
"""
CropForecaster Cron Automation Setup

This script configures daily automated weather ingestion for operational deployment.
Designed to run at 6 AM daily to ingest yesterday's weather data from SILO API.

Features:
- Daily ingestion with error handling and logging
- Environment variable management
- Lock file prevention of overlapping runs
- Email notifications on failure (optional)
- Log rotation and cleanup

Setup Instructions:
1. Copy this file to your production server
2. Update PROJECT_DIR to your installation path
3. Configure email settings (optional)
4. Run: bash config/cron_schedule.sh install
5. Verify: crontab -l

Usage:
    bash config/cron_schedule.sh install    # Install cron job
    bash config/cron_schedule.sh uninstall  # Remove cron job  
    bash config/cron_schedule.sh status     # Check status
    bash config/cron_schedule.sh run        # Manual test run
"""

# Configuration
PROJECT_DIR="/home/roddyb/projects/wheatbelt_rainfall_analyser"
PYTHON_PATH="python3"
LOG_DIR="$PROJECT_DIR/logs"
LOCK_FILE="/tmp/cropforecaster_ingest.lock"
CONFIG_FILE="$PROJECT_DIR/config/silo_sources.yaml"

# Email settings (optional - set EMAIL_ENABLED=false to disable)
EMAIL_ENABLED=false
EMAIL_TO="admin@example.com"
EMAIL_FROM="cropforecaster@example.com"

# Cron schedule (6 AM daily)
CRON_TIME="0 6 * * *"
CRON_COMMENT="CropForecaster daily weather ingestion"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

check_requirements() {
    # Check if project directory exists
    if [ ! -d "$PROJECT_DIR" ]; then
        error "Project directory not found: $PROJECT_DIR"
        exit 1
    fi
    
    # Check if Python script exists
    if [ ! -f "$PROJECT_DIR/scripts/daily_ingest.py" ]; then
        error "Daily ingest script not found: $PROJECT_DIR/scripts/daily_ingest.py"
        exit 1
    fi
    
    # Check if config file exists
    if [ ! -f "$CONFIG_FILE" ]; then
        error "Configuration file not found: $CONFIG_FILE"
        exit 1
    fi
    
    # Ensure log directory exists
    mkdir -p "$LOG_DIR"
    
    log "Requirements check passed"
}

install_cron() {
    log "Installing CropForecaster cron job..."
    
    check_requirements
    
    # Create cron entry
    CRON_COMMAND="$PROJECT_DIR/config/cron_schedule.sh run"
    CRON_ENTRY="$CRON_TIME $CRON_COMMAND # $CRON_COMMENT"
    
    # Check if cron job already exists
    if crontab -l 2>/dev/null | grep -q "CropForecaster daily weather ingestion"; then
        warning "CropForecaster cron job already exists. Updating..."
        
        # Remove existing job and add new one
        (crontab -l 2>/dev/null | grep -v "CropForecaster daily weather ingestion"; echo "$CRON_ENTRY") | crontab -
    else
        # Add new job
        (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    fi
    
    log "Cron job installed successfully"
    log "Schedule: Daily at 6:00 AM"
    log "Command: $CRON_COMMAND"
    log ""
    log "To verify installation, run: crontab -l"
    log "To view logs, check: $LOG_DIR/daily_ingest.log"
}

uninstall_cron() {
    log "Uninstalling CropForecaster cron job..."
    
    if crontab -l 2>/dev/null | grep -q "CropForecaster daily weather ingestion"; then
        crontab -l 2>/dev/null | grep -v "CropForecaster daily weather ingestion" | crontab -
        log "Cron job removed successfully"
    else
        warning "No CropForecaster cron job found"
    fi
}

check_status() {
    log "Checking CropForecaster cron status..."
    
    if crontab -l 2>/dev/null | grep -q "CropForecaster daily weather ingestion"; then
        log "✓ Cron job is installed"
        echo "Schedule details:"
        crontab -l 2>/dev/null | grep "CropForecaster daily weather ingestion"
    else
        warning "✗ Cron job is not installed"
    fi
    
    echo ""
    log "Recent log activity:"
    if [ -f "$LOG_DIR/daily_ingest.log" ]; then
        tail -10 "$LOG_DIR/daily_ingest.log"
    else
        warning "No log file found at $LOG_DIR/daily_ingest.log"
    fi
}

send_email_alert() {
    local subject="$1"
    local message="$2"
    
    if [ "$EMAIL_ENABLED" = "true" ]; then
        echo "$message" | mail -s "$subject" -r "$EMAIL_FROM" "$EMAIL_TO"
        log "Email alert sent to $EMAIL_TO"
    fi
}

run_ingestion() {
    log "Starting daily weather ingestion..."
    
    # Check for lock file to prevent overlapping runs
    if [ -f "$LOCK_FILE" ]; then
        error "Another ingestion process is running (lock file exists: $LOCK_FILE)"
        exit 1
    fi
    
    # Create lock file
    echo "$$" > "$LOCK_FILE"
    
    # Ensure lock file is removed on exit
    trap 'rm -f "$LOCK_FILE"' EXIT
    
    # Change to project directory
    cd "$PROJECT_DIR" || {
        error "Failed to change to project directory: $PROJECT_DIR"
        exit 1
    }
    
    # Set up environment
    export PYTHONPATH="$PROJECT_DIR/src:$PYTHONPATH"
    
    # Run the ingestion
    START_TIME=$(date +%s)
    log "Running: $PYTHON_PATH scripts/daily_ingest.py --config $CONFIG_FILE"
    
    if $PYTHON_PATH scripts/daily_ingest.py --config "$CONFIG_FILE" >> "$LOG_DIR/cron_output.log" 2>&1; then
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        
        log "Daily ingestion completed successfully in ${DURATION}s"
        
        # Log success to separate file for monitoring
        echo "$(date '+%Y-%m-%d %H:%M:%S') SUCCESS duration=${DURATION}s" >> "$LOG_DIR/cron_success.log"
        
    else
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        
        error "Daily ingestion failed after ${DURATION}s"
        
        # Log failure
        echo "$(date '+%Y-%m-%d %H:%M:%S') FAILED duration=${DURATION}s" >> "$LOG_DIR/cron_errors.log"
        
        # Send email alert
        send_email_alert "CropForecaster Ingestion Failed" \
            "Daily weather ingestion failed on $(hostname) at $(date).
            
Duration: ${DURATION}s
Project: $PROJECT_DIR
Log file: $LOG_DIR/daily_ingest.log

Please check the logs for details."
        
        exit 1
    fi
    
    # Cleanup old logs (keep 30 days)
    find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true
}

# Main command handler
case "$1" in
    install)
        install_cron
        ;;
    uninstall)
        uninstall_cron
        ;;
    status)
        check_status
        ;;
    run)
        run_ingestion
        ;;
    *)
        echo "CropForecaster Cron Automation Setup"
        echo ""
        echo "Usage: $0 {install|uninstall|status|run}"
        echo ""
        echo "Commands:"
        echo "  install    - Install daily cron job (6 AM)"
        echo "  uninstall  - Remove cron job"
        echo "  status     - Check cron job status and recent logs"
        echo "  run        - Manual test run (used by cron)"
        echo ""
        echo "Configuration:"
        echo "  Project Directory: $PROJECT_DIR"
        echo "  Python Path: $PYTHON_PATH"
        echo "  Config File: $CONFIG_FILE"
        echo "  Log Directory: $LOG_DIR"
        echo "  Email Alerts: $EMAIL_ENABLED"
        exit 1
        ;;
esac