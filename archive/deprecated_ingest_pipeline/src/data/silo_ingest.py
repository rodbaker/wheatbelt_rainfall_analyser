# DEPRECATED (2026-05-03): SILOIngestPipeline is superseded by
# src/agents/silo_wrangler/run_ingest.py (the canonical SILO ingest entrypoint).
# No active three-agent pipeline code imports this module. Only
# scripts/daily_ingest.py and scripts/backfill_historical.py reference this class,
# and both are deprecated. Scheduled for archive/ in the next cleanup pass.

"""
SILO Weather Data Ingestion Pipeline

Core module for daily weather data ingestion from SILO API.
Implements the weather ingest pipeline (SILO/S3 → DuckDB) for T-20250906-002.

Features:
- Daily automated fetching from SILO API
- Rate-limited multi-station processing
- DuckDB storage integration
- Performance target: <10 seconds for all stations
- Support for 2000+ stations with backfill capability
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import pandas as pd
import yaml

from ..agents.silo_wrangler.api_client import SILOAPIClient
from ..agents.silo_wrangler.quality_checker import DataQualityChecker
from ..common.stations_loader import load_wheatbelt_stations_for_config
from .duckdb_storage import DuckDBStorage

logger = logging.getLogger(__name__)


class SILOIngestPipeline:
    """Main ingestion pipeline for SILO weather data"""
    
    def __init__(self, config_path: str = "config/silo_sources.yaml"):
        """Initialize the ingestion pipeline
        
        Args:
            config_path: Path to SILO configuration file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # Initialize components
        self.api_client = SILOAPIClient(self.config)
        self.quality_checker = DataQualityChecker(self.config)
        self.storage = DuckDBStorage(self.config.get('storage', {}))
        
        # Performance tracking
        self.stats = {
            'stations_processed': 0,
            'records_ingested': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None
        }
        
    def _load_config(self) -> Dict[str, Any]:
        """Load SILO configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            raise
            
    def ingest_daily_data(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Ingest daily weather data for all configured stations
        
        Args:
            target_date: Date to ingest in YYYY-MM-DD format (defaults to yesterday)
            
        Returns:
            Dictionary with ingestion statistics
        """
        self.stats['start_time'] = time.time()
        
        # Default to yesterday's data
        if target_date is None:
            target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
        logger.info(f"Starting daily ingestion for {target_date}")
        
        # Load stations based on configuration
        try:
            stations_df = load_wheatbelt_stations_for_config(self.config)
            station_ids = stations_df['station_number'].astype(str).tolist()
            logger.info(f"Loaded {len(station_ids)} stations for processing")
        except Exception as e:
            logger.error(f"Failed to load stations: {e}")
            self.stats['errors'] += 1
            return self._get_stats()
            
        # Process stations in batches for performance
        batch_size = self.config.get('processing', {}).get('batch_size', 50)
        all_records = []
        
        for i in range(0, len(station_ids), batch_size):
            batch = station_ids[i:i + batch_size]
            batch_records = self._process_station_batch(batch, target_date)
            all_records.extend(batch_records)
            
            # Log progress
            logger.info(f"Processed batch {i//batch_size + 1}/{(len(station_ids) + batch_size - 1)//batch_size}")
            
        # Store all records in DuckDB
        if all_records:
            try:
                self.storage.store_daily_observations(all_records, target_date)
                self.stats['records_ingested'] = len(all_records)
                logger.info(f"Stored {len(all_records)} weather observations for {target_date}")
            except Exception as e:
                logger.error(f"Failed to store observations: {e}")
                self.stats['errors'] += 1
                
        self.stats['end_time'] = time.time()
        return self._get_stats()
        
    def _process_station_batch(self, station_ids: List[str], target_date: str) -> List[Dict[str, Any]]:
        """Process a batch of stations for the target date"""
        records = []
        date_formatted = target_date.replace('-', '')  # YYYYMMDD for API
        
        for station_id in station_ids:
            try:
                # Fetch data from SILO API
                df = self.api_client.get_daily_data(station_id, date_formatted, date_formatted)
                
                if df is not None and not df.empty:
                    # Quality check
                    quality_result = self.quality_checker.check_station_data(df, station_id)
                    
                    if quality_result['passes_quality_checks']:
                        # Convert to standardized records
                        station_records = self._convert_to_records(df, station_id, target_date)
                        records.extend(station_records)
                        self.stats['stations_processed'] += 1
                    else:
                        logger.warning(f"Station {station_id} failed quality checks: {quality_result.get('quality_summary', 'Unknown')}")
                else:
                    logger.warning(f"No data retrieved for station {station_id}")
                    
            except Exception as e:
                logger.error(f"Error processing station {station_id}: {e}")
                self.stats['errors'] += 1
                
        return records
        
    def _convert_to_records(self, df: pd.DataFrame, station_id: str, date: str) -> List[Dict[str, Any]]:
        """Convert DataFrame to standardized weather records"""
        records = []
        
        for _, row in df.iterrows():
            record = {
                'station_id': station_id,
                'date': date,
                'min_temp': row.get('min_temp'),
                'max_temp': row.get('max_temp'),
                'rainfall': row.get('daily_rain'),
                'min_temp_quality': row.get('min_temp_Quality'),
                'max_temp_quality': row.get('max_temp_Quality'),
                'rainfall_quality': row.get('daily_rain_Quality'),
                'ingested_at': datetime.now().isoformat()
            }
            
            # Only include records with at least one valid measurement
            if any(record[var] is not None for var in ['min_temp', 'max_temp', 'rainfall']):
                records.append(record)
                
        return records
        
    def _get_stats(self) -> Dict[str, Any]:
        """Get current ingestion statistics"""
        duration = None
        if self.stats['start_time'] and self.stats['end_time']:
            duration = self.stats['end_time'] - self.stats['start_time']
            
        return {
            'stations_processed': self.stats['stations_processed'],
            'records_ingested': self.stats['records_ingested'],
            'errors': self.stats['errors'],
            'duration_seconds': duration,
            'performance_target_met': duration is not None and duration < 10.0
        }
        
    def ingest_date_range(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Ingest data for a date range (used for backfilling)
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            Dictionary with ingestion statistics
        """
        logger.info(f"Starting range ingestion: {start_date} to {end_date}")
        
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        total_stats = {
            'stations_processed': 0,
            'records_ingested': 0,
            'errors': 0,
            'dates_processed': 0
        }
        
        current_dt = start_dt
        while current_dt <= end_dt:
            date_str = current_dt.strftime('%Y-%m-%d')
            logger.info(f"Processing date: {date_str}")
            
            # Reset stats for this date
            self.stats = {
                'stations_processed': 0,
                'records_ingested': 0,
                'errors': 0,
                'start_time': None,
                'end_time': None
            }
            
            # Ingest data for this date
            day_stats = self.ingest_daily_data(date_str)
            
            # Accumulate totals
            total_stats['stations_processed'] += day_stats['stations_processed']
            total_stats['records_ingested'] += day_stats['records_ingested']
            total_stats['errors'] += day_stats['errors']
            total_stats['dates_processed'] += 1
            
            current_dt += timedelta(days=1)
            
            # Respect API rate limits between days
            time.sleep(1)
            
        logger.info(f"Range ingestion complete. Processed {total_stats['dates_processed']} dates, "
                   f"{total_stats['records_ingested']} total records")
        
        return total_stats