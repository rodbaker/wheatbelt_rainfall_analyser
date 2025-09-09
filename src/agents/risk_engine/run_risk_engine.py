#!/usr/bin/env python3
"""
Risk Engine Runner - Orchestrates daily event detection workflow

Integrates with SILO data pipeline to:
1. Load daily weather data from DuckDB
2. Determine current crop stages 
3. Run event detection (frost/heat/rainfall)
4. Export events to CSV files for downstream systems
5. Log processing metrics and status

Usage:
    python run_risk_engine.py --date 2024-09-08
    python run_risk_engine.py --date-range 2024-09-01 2024-09-08
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import pandas as pd
import yaml

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.common.config_loader import load_config
from src.common.logging_utils import setup_logging  
from src.common.date_utils import get_current_crop_stage, get_crop_season
from src.data.duckdb_storage import DuckDBStorage
from src.agents.risk_engine.event_detector import WeatherEventDetector

logger = logging.getLogger(__name__)


class RiskEngineRunner:
    """Main orchestrator for daily risk assessment workflow"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Risk Engine with configuration
        
        Args:
            config_path: Path to config directory, defaults to project/config
        """
        self.config_path = Path(config_path) if config_path else project_root / "config"
        self.output_dir = project_root / "data" / "derived"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load configurations
        self.crop_config = self._load_crop_calendars()
        
        # Configure DuckDB storage
        storage_config = {
            'database_path': str(project_root / "data" / "weather.duckdb")
        }
        self.storage = DuckDBStorage(storage_config)
        self.detector = WeatherEventDetector(self.crop_config)
        
        logger.info(f"Risk Engine initialized with config from {self.config_path}")
        
    def _load_crop_calendars(self) -> Dict[str, Any]:
        """Load crop calendar and threshold configuration"""
        try:
            config_file = self.config_path / "crop_calendars.yaml"
            return load_config(str(config_file))
        except Exception as e:
            logger.error(f"Failed to load crop calendars: {e}")
            raise
            
    def run_daily_assessment(self, target_date: str) -> Dict[str, int]:
        """
        Run event detection for a specific date
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Dictionary with event counts by type
        """
        logger.info(f"Running risk assessment for {target_date}")
        
        # Load weather data for target date
        weather_data = self._load_weather_data(target_date)
        if weather_data.empty:
            logger.warning(f"No weather data available for {target_date}")
            return {"frost": 0, "heat": 0, "rainfall": 0}
            
        # Determine current crop stage
        crop_stage_info = self._get_crop_stage_info(target_date)
        
        # Run event detection
        all_events = []
        event_counts = {}
        
        # Frost detection
        if crop_stage_info.get('frost_critical', False):
            frost_events = self.detector.detect_frost_events(weather_data, crop_stage_info)
            all_events.append(frost_events)
            event_counts['frost'] = len(frost_events)
            logger.info(f"Detected {len(frost_events)} frost events")
        else:
            event_counts['frost'] = 0
            logger.info("Frost detection skipped - not in critical stage")
            
        # Heat detection  
        if crop_stage_info.get('heat_critical', False):
            heat_events = self.detector.detect_heat_events(weather_data, crop_stage_info)
            all_events.append(heat_events)
            event_counts['heat'] = len(heat_events)
            logger.info(f"Detected {len(heat_events)} heat events")
        else:
            event_counts['heat'] = 0
            logger.info("Heat detection skipped - not in critical stage")
            
        # Rainfall detection
        if crop_stage_info.get('rain_critical', False):
            rain_events = self.detector.detect_rainfall_events(weather_data, crop_stage_info)
            all_events.append(rain_events)
            event_counts['rainfall'] = len(rain_events)
            logger.info(f"Detected {len(rain_events)} rainfall events")
        else:
            event_counts['rainfall'] = 0
            logger.info("Rainfall detection skipped - not in critical stage")
            
        # Combine and export events
        if all_events and any(not df.empty for df in all_events):
            combined_events = pd.concat([df for df in all_events if not df.empty], ignore_index=True)
            self._export_events(combined_events, target_date)
        else:
            logger.info("No events detected for export")
            
        return event_counts
        
    def run_date_range(self, start_date: str, end_date: str) -> Dict[str, Dict[str, int]]:
        """
        Run event detection for a date range
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            Dictionary with event counts by date and type
        """
        logger.info(f"Running risk assessment for range {start_date} to {end_date}")
        
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        results = {}
        current_date = start_dt
        
        while current_date <= end_dt:
            date_str = current_date.strftime('%Y-%m-%d')
            try:
                results[date_str] = self.run_daily_assessment(date_str)
            except Exception as e:
                logger.error(f"Failed to process {date_str}: {e}")
                results[date_str] = {"frost": 0, "heat": 0, "rainfall": 0, "error": str(e)}
                
            current_date += timedelta(days=1)
            
        return results
        
    def _load_weather_data(self, target_date: str) -> pd.DataFrame:
        """
        Load weather data for target date from DuckDB storage
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            DataFrame with weather data for all stations
        """
        try:
            # Query daily observations for target date (map field names to expected format)
            query = f"""
                SELECT 
                    station_id,
                    date,
                    min_temp as min_temperature,
                    max_temp as max_temperature, 
                    rainfall,
                    min_temp_quality as min_temperature_quality,
                    max_temp_quality as max_temperature_quality,
                    rainfall_quality
                FROM weather_observations 
                WHERE date = '{target_date}'
                AND min_temp IS NOT NULL
                AND max_temp IS NOT NULL
                AND rainfall IS NOT NULL
            """
            
            weather_df = self.storage.query_to_dataframe(query)
            logger.info(f"Loaded weather data for {len(weather_df)} stations on {target_date}")
            return weather_df
            
        except Exception as e:
            logger.error(f"Failed to load weather data for {target_date}: {e}")
            return pd.DataFrame()
            
    def _get_crop_stage_info(self, target_date: str) -> Dict[str, Any]:
        """
        Determine current crop stage and critical periods for target date
        
        Uses both date-based stage detection and month-based configuration
        to provide comprehensive phenology awareness.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Dictionary with stage information and critical flags
        """
        target_dt = datetime.strptime(target_date, '%Y-%m-%d').date()
        
        # Get precise crop stage using date utilities (more accurate)
        date_based_stage = get_current_crop_stage(target_dt, 'wheat')
        
        # Get season information for context
        season_info = get_crop_season(target_dt, 'wheat')
        
        # Map date-based stages to config stages for compatibility
        stage_mapping = {
            'pre_season': 'planting',
            'planting': 'planting', 
            'vegetative': 'tillering',
            'flowering': 'flowering',
            'grain_filling': 'grain_fill',
            'harvest': 'harvest',
            'post_harvest': 'maturity'
        }
        
        config_stage = stage_mapping.get(date_based_stage, date_based_stage)
        
        # Get stage configuration from crop calendar
        wheat_stages = self.crop_config['wheat']['stages']
        stage_info = wheat_stages.get(config_stage, {})
        
        if not stage_info:
            logger.warning(f"No stage configuration found for {config_stage} (from {date_based_stage})")
            # Fallback to month-based detection
            target_month = target_dt.month
            for stage_name, stage_data in wheat_stages.items():
                if target_month in stage_data.get('months', []):
                    config_stage = stage_name
                    stage_info = stage_data.copy()
                    break
        
        # Build comprehensive stage info
        crop_stage_info = {
            'current_stage': config_stage,
            'date_based_stage': date_based_stage,
            'frost_critical': stage_info.get('frost_critical', False),
            'heat_critical': stage_info.get('heat_critical', False), 
            'rain_critical': stage_info.get('rain_critical', False),
            'description': stage_info.get('description', f'Stage: {date_based_stage}'),
            'target_date': target_date,
            'target_month': target_dt.month,
            'season_year': season_info['season_year'],
            'flowering_window': {
                'start': season_info['flowering_start'],
                'end': season_info['flowering_end'],
                'active': season_info['flowering_start'] <= target_dt <= season_info['flowering_end']
            },
            'days_since_flowering_start': (target_dt - season_info['flowering_start']).days if target_dt >= season_info['flowering_start'] else None,
            'days_until_harvest': (season_info['harvest_start'] - target_dt).days if target_dt < season_info['harvest_start'] else 0
        }
        
        # Enhanced logging with phenology context
        flowering_status = "in flowering window" if crop_stage_info['flowering_window']['active'] else "outside flowering window"
        logger.info(f"Phenology assessment for {target_date}:")
        logger.info(f"  Stage: {config_stage} ({date_based_stage}) - {flowering_status}")
        logger.info(f"  Critical periods - frost: {crop_stage_info['frost_critical']}, "
                   f"heat: {crop_stage_info['heat_critical']}, rain: {crop_stage_info['rain_critical']}")
        if crop_stage_info['days_since_flowering_start'] is not None:
            logger.info(f"  {crop_stage_info['days_since_flowering_start']} days since flowering started")
        
        return crop_stage_info
        
    def _export_events(self, events_df: pd.DataFrame, target_date: str):
        """
        Export detected events to CSV files
        
        Args:
            events_df: DataFrame with all detected events
            target_date: Date processed
        """
        try:
            # Export consolidated event log
            event_log_path = self.output_dir / "event_log.csv"
            
            # Append to existing log or create new
            if event_log_path.exists():
                # Remove existing events for this date to avoid duplicates
                existing_df = pd.read_csv(event_log_path)
                existing_df = existing_df[existing_df['date'] != target_date]
                combined_df = pd.concat([existing_df, events_df], ignore_index=True)
            else:
                combined_df = events_df
                
            combined_df.to_csv(event_log_path, index=False)
            logger.info(f"Exported {len(events_df)} events to {event_log_path}")
            
            # Export separate files by event type (for backward compatibility)
            for event_type in ['frost', 'heat', 'rainfall']:
                type_events = events_df[events_df['event_type'] == event_type]
                if not type_events.empty:
                    type_path = self.output_dir / f"{event_type}_events.csv"
                    
                    # Append or create
                    if type_path.exists():
                        existing_type = pd.read_csv(type_path)
                        existing_type = existing_type[existing_type['date'] != target_date]
                        combined_type = pd.concat([existing_type, type_events], ignore_index=True)
                    else:
                        combined_type = type_events
                        
                    combined_type.to_csv(type_path, index=False)
                    logger.info(f"Exported {len(type_events)} {event_type} events to {type_path}")
                    
        except Exception as e:
            logger.error(f"Failed to export events: {e}")
            raise


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="CropForecaster Risk Engine - Daily weather event detection"
    )
    parser.add_argument(
        '--date', 
        help='Target date for analysis (YYYY-MM-DD)', 
        default=datetime.now().strftime('%Y-%m-%d')
    )
    parser.add_argument(
        '--date-range',
        nargs=2,
        metavar=('START_DATE', 'END_DATE'),
        help='Date range for analysis (YYYY-MM-DD YYYY-MM-DD)'
    )
    parser.add_argument(
        '--config-dir',
        help='Configuration directory path',
        default=None
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )
    parser.add_argument(
        '--output-dir', 
        help='Output directory for event files',
        default=None
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(level=args.log_level)
    
    try:
        # Initialize Risk Engine
        engine = RiskEngineRunner(config_path=args.config_dir)
        
        # Override output directory if specified
        if args.output_dir:
            engine.output_dir = Path(args.output_dir)
            engine.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Run analysis
        if args.date_range:
            results = engine.run_date_range(args.date_range[0], args.date_range[1])
            
            # Summary output
            total_events = sum(
                sum(daily_counts.get(event_type, 0) for event_type in ['frost', 'heat', 'rainfall'])
                for daily_counts in results.values()
                if 'error' not in daily_counts
            )
            print(f"\nProcessed {len(results)} days")
            print(f"Total events detected: {total_events}")
            
        else:
            results = engine.run_daily_assessment(args.date)
            
            # Summary output
            total_events = sum(results.values())
            print(f"\nDate: {args.date}")
            print(f"Frost events: {results['frost']}")
            print(f"Heat events: {results['heat']}")
            print(f"Rainfall events: {results['rainfall']}")
            print(f"Total events: {total_events}")
            
        logger.info("Risk Engine run completed successfully")
        
    except Exception as e:
        logger.error(f"Risk Engine failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()