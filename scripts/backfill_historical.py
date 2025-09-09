#!/usr/bin/env python3
"""
Historical Data Backfill Script

Backfill SILO weather data from 2005 to present for comprehensive historical coverage.
Implements chunked processing with progress tracking and resume capability.

Usage:
    python scripts/backfill_historical.py --start 2005-01-01 --end 2024-12-31
    python scripts/backfill_historical.py --year 2023
    python scripts/backfill_historical.py --recent --days 90

Examples:
    # Full historical backfill (2005-present)
    python scripts/backfill_historical.py --start 2005-01-01
    
    # Specific year
    python scripts/backfill_historical.py --year 2023
    
    # Recent 3 months
    python scripts/backfill_historical.py --recent --days 90
    
    # Resume from checkpoint
    python scripts/backfill_historical.py --resume backfill_checkpoint.json
"""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.data.silo_ingest import SILOIngestPipeline


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Setup logging for backfill operations"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Ensure logs directory exists
    Path('logs').mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('logs/backfill_historical.log', mode='a')
        ]
    )
    
    return logging.getLogger(__name__)


def save_checkpoint(checkpoint_path: str, progress: Dict[str, Any]):
    """Save backfill progress to checkpoint file"""
    try:
        with open(checkpoint_path, 'w') as f:
            json.dump(progress, f, indent=2, default=str)
    except Exception as e:
        logging.error(f"Failed to save checkpoint: {e}")


def load_checkpoint(checkpoint_path: str) -> Dict[str, Any]:
    """Load backfill progress from checkpoint file"""
    try:
        with open(checkpoint_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.error(f"Failed to load checkpoint: {e}")
        return {}


def calculate_date_chunks(start_date: datetime, end_date: datetime, chunk_days: int = 30) -> list:
    """Split date range into manageable chunks"""
    chunks = []
    current_date = start_date
    
    while current_date <= end_date:
        chunk_end = min(current_date + timedelta(days=chunk_days - 1), end_date)
        chunks.append((current_date, chunk_end))
        current_date = chunk_end + timedelta(days=1)
        
    return chunks


def main():
    """Main backfill entry point"""
    parser = argparse.ArgumentParser(
        description="CropForecaster Historical Data Backfill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Date range options (mutually exclusive)
    date_group = parser.add_mutually_exclusive_group(required=True)
    
    date_group.add_argument(
        '--start',
        type=str,
        help='Start date for backfill (YYYY-MM-DD). End defaults to yesterday.'
    )
    
    date_group.add_argument(
        '--year',
        type=int,
        help='Backfill specific year (e.g., 2023)'
    )
    
    date_group.add_argument(
        '--recent',
        action='store_true',
        help='Backfill recent period (use with --days)'
    )
    
    date_group.add_argument(
        '--resume',
        type=str,
        help='Resume from checkpoint file'
    )
    
    parser.add_argument(
        '--end',
        type=str,
        help='End date for backfill (YYYY-MM-DD). Defaults to yesterday.'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=90,
        help='Number of recent days to backfill (use with --recent)'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config/silo_sources.yaml',
        help='Path to SILO configuration file'
    )
    
    parser.add_argument(
        '--chunk-days',
        type=int,
        default=30,
        help='Number of days per processing chunk (default: 30)'
    )
    
    parser.add_argument(
        '--checkpoint',
        type=str,
        default='backfill_checkpoint.json',
        help='Checkpoint file for resume capability'
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
        help='Show what would be backfilled without processing'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.log_level)
    
    # Determine date range
    yesterday = datetime.now() - timedelta(days=1)
    
    if args.resume:
        # Resume from checkpoint
        checkpoint = load_checkpoint(args.resume)
        if not checkpoint:
            logger.error(f"No valid checkpoint found at {args.resume}")
            sys.exit(1)
            
        start_date = datetime.fromisoformat(checkpoint['start_date'])
        end_date = datetime.fromisoformat(checkpoint['end_date'])
        last_completed = checkpoint.get('last_completed_date')
        
        if last_completed:
            start_date = datetime.fromisoformat(last_completed) + timedelta(days=1)
            
        logger.info(f"Resuming backfill from {start_date.date()}")
        
    elif args.year:
        # Specific year
        start_date = datetime(args.year, 1, 1)
        end_date = datetime(args.year, 12, 31)
        
    elif args.recent:
        # Recent period
        end_date = yesterday
        start_date = end_date - timedelta(days=args.days - 1)
        
    elif args.start:
        # Start date provided
        try:
            start_date = datetime.strptime(args.start, '%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid start date format: {args.start}")
            sys.exit(1)
            
        if args.end:
            try:
                end_date = datetime.strptime(args.end, '%Y-%m-%d')
            except ValueError:
                logger.error(f"Invalid end date format: {args.end}")
                sys.exit(1)
        else:
            end_date = yesterday
    
    # Validate date range
    if start_date > end_date:
        logger.error("Start date cannot be after end date")
        sys.exit(1)
        
    total_days = (end_date - start_date).days + 1
    chunks = calculate_date_chunks(start_date, end_date, args.chunk_days)
    
    logger.info("=" * 70)
    logger.info("HISTORICAL BACKFILL PLAN")
    logger.info("=" * 70)
    logger.info(f"Date Range: {start_date.date()} to {end_date.date()}")
    logger.info(f"Total Days: {total_days}")
    logger.info(f"Processing Chunks: {len(chunks)} ({args.chunk_days} days each)")
    logger.info(f"Configuration: {args.config}")
    logger.info("=" * 70)
    
    if args.dry_run:
        logger.info("DRY RUN: Would process the following chunks:")
        for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
            chunk_days = (chunk_end - chunk_start).days + 1
            logger.info(f"  Chunk {i}: {chunk_start.date()} to {chunk_end.date()} ({chunk_days} days)")
        sys.exit(0)
    
    # Confirm with user for large backfills
    if total_days > 365 and not args.resume:
        response = input(f"This will backfill {total_days} days of data. Continue? (y/N): ")
        if response.lower() != 'y':
            logger.info("Backfill cancelled by user")
            sys.exit(0)
    
    # Initialize pipeline
    try:
        pipeline = SILOIngestPipeline(args.config)
        logger.info("Backfill pipeline initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize pipeline: {e}")
        sys.exit(1)
    
    # Initialize progress tracking
    run_id = f"backfill_{start_date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
    overall_stats = {
        'run_id': run_id,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'total_chunks': len(chunks),
        'completed_chunks': 0,
        'total_stations_processed': 0,
        'total_records_ingested': 0,
        'total_errors': 0,
        'start_time': datetime.now().isoformat(),
        'last_completed_date': None
    }
    
    try:
        # Process chunks
        for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
            chunk_start_str = chunk_start.strftime('%Y-%m-%d')
            chunk_end_str = chunk_end.strftime('%Y-%m-%d')
            
            logger.info(f"Processing chunk {i}/{len(chunks)}: {chunk_start_str} to {chunk_end_str}")
            
            chunk_stats = pipeline.ingest_date_range(chunk_start_str, chunk_end_str)
            
            # Update overall progress
            overall_stats['completed_chunks'] += 1
            overall_stats['total_stations_processed'] += chunk_stats['stations_processed']
            overall_stats['total_records_ingested'] += chunk_stats['records_ingested'] 
            overall_stats['total_errors'] += chunk_stats['errors']
            overall_stats['last_completed_date'] = chunk_end_str
            
            # Save checkpoint after each chunk
            save_checkpoint(args.checkpoint, overall_stats)
            
            # Progress report
            progress_pct = (i / len(chunks)) * 100
            logger.info(f"Chunk {i} complete: {chunk_stats['records_ingested']} records, "
                       f"{chunk_stats['errors']} errors ({progress_pct:.1f}% total progress)")
            
            # Respect API limits between chunks
            if i < len(chunks):
                logger.info("Pausing between chunks...")
                import time
                time.sleep(2)
        
        # Final summary
        overall_stats['end_time'] = datetime.now().isoformat()
        total_duration = datetime.now() - datetime.fromisoformat(overall_stats['start_time'])
        
        logger.info("=" * 70)
        logger.info("BACKFILL COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Run ID: {run_id}")
        logger.info(f"Total Records Ingested: {overall_stats['total_records_ingested']:,}")
        logger.info(f"Total Stations Processed: {overall_stats['total_stations_processed']:,}")
        logger.info(f"Total Errors: {overall_stats['total_errors']}")
        logger.info(f"Duration: {total_duration}")
        logger.info(f"Average: {overall_stats['total_records_ingested'] / total_duration.total_seconds():.1f} records/sec")
        logger.info("=" * 70)
        
        # Clean up checkpoint on success
        if Path(args.checkpoint).exists():
            Path(args.checkpoint).unlink()
            logger.info("Checkpoint file removed after successful completion")
        
    except KeyboardInterrupt:
        logger.info("Backfill interrupted by user")
        logger.info(f"Progress saved to {args.checkpoint}")
        sys.exit(130)
        
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        logger.info(f"Progress saved to {args.checkpoint}")
        sys.exit(1)


if __name__ == '__main__':
    main()