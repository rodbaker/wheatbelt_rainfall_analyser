#!/usr/bin/env python3
# DEPRECATED (2026-05-03): Superseded by src/agents/silo_wrangler/run_ingest.py.
# Imports SILOIngestPipeline from src/data/silo_ingest.py, which is no longer
# maintained. Use the canonical entrypoint instead:
#   python src/agents/silo_wrangler/run_ingest.py --date YYYY-MM-DD
# Scheduled for archive/ in the next cleanup pass.

"""
Daily Weather Ingest Script

CLI entry point for daily SILO weather data ingestion.
Designed for cron automation and manual execution.

Usage:
    python scripts/daily_ingest.py [--date YYYY-MM-DD] [--config CONFIG_PATH]
    
Examples:
    # Ingest yesterday's data (default)
    python scripts/daily_ingest.py
    
    # Ingest specific date
    python scripts/daily_ingest.py --date 2025-09-07
    
    # Use custom config
    python scripts/daily_ingest.py --config config/custom_silo.yaml
"""

import argparse
import logging
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Add src to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.data.silo_ingest import SILOIngestPipeline


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Setup logging configuration"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('logs/daily_ingest.log', mode='a')
        ]
    )
    
    # Ensure logs directory exists
    Path('logs').mkdir(exist_ok=True)
    
    return logging.getLogger(__name__)


def main():
    """Main entry point for daily ingestion"""
    parser = argparse.ArgumentParser(
        description="CropForecaster Daily Weather Ingestion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--date',
        type=str,
        help='Target date for ingestion (YYYY-MM-DD). Defaults to yesterday.'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config/silo_sources.yaml',
        help='Path to SILO configuration file'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate configuration and connections without ingesting data'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.log_level)
    
    # Determine target date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d').strftime('%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
            sys.exit(1)
    else:
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    logger.info(f"Starting daily ingest for {target_date}")
    logger.info(f"Using configuration: {args.config}")
    
    # Generate unique run ID for tracking
    run_id = f"daily_{target_date}_{uuid.uuid4().hex[:8]}"
    
    try:
        # Initialize ingestion pipeline
        pipeline = SILOIngestPipeline(args.config)
        
        if args.dry_run:
            logger.info("DRY RUN: Configuration loaded successfully")
            logger.info("DRY RUN: Would ingest data for stations from configuration")
            sys.exit(0)
        
        # Run daily ingestion
        start_time = datetime.now()
        stats = pipeline.ingest_daily_data(target_date)
        end_time = datetime.now()
        
        # Log results to DuckDB for audit trail
        pipeline.storage.log_ingestion_run(run_id, stats, target_date)
        
        # Print summary
        duration = stats.get('duration_seconds', 0)
        performance_ok = stats.get('performance_target_met', False)
        
        logger.info("=" * 60)
        logger.info("DAILY INGESTION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Run ID: {run_id}")
        logger.info(f"Target Date: {target_date}")
        logger.info(f"Stations Processed: {stats['stations_processed']}")
        logger.info(f"Records Ingested: {stats['records_ingested']}")
        logger.info(f"Errors: {stats['errors']}")
        logger.info(f"Duration: {duration:.2f}s")
        logger.info(f"Performance Target (<10s): {'✓ PASS' if performance_ok else '✗ FAIL'}")
        logger.info("=" * 60)
        
        # Exit with error code if there were issues
        if stats['errors'] > 0:
            logger.error(f"Ingestion completed with {stats['errors']} errors")
            sys.exit(1)
        elif not performance_ok:
            logger.warning(f"Performance target not met: {duration:.2f}s > 10s")
            # Don't exit with error - data was still ingested successfully
        
        logger.info("Daily ingestion completed successfully")
        
    except KeyboardInterrupt:
        logger.info("Ingestion interrupted by user")
        sys.exit(130)
        
    except Exception as e:
        logger.error(f"Daily ingestion failed: {e}", exc_info=True)
        
        # Try to log the failure
        try:
            if 'pipeline' in locals():
                failed_stats = {
                    'stations_processed': 0,
                    'records_ingested': 0,
                    'errors': 1,
                    'start_time': start_time.timestamp() if 'start_time' in locals() else None,
                    'end_time': datetime.now().timestamp()
                }
                pipeline.storage.log_ingestion_run(run_id, failed_stats, target_date)
        except Exception as log_error:
            logger.error(f"Failed to log error to database: {log_error}")
        
        sys.exit(1)


if __name__ == '__main__':
    main()