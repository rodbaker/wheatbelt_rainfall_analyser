#!/usr/bin/env python3
"""
CSV-based Risk Engine Runner - Simplified M1 Implementation

Directly processes CSV files from SILO Wrangler for faster execution 
and simpler deployment. Implements M1 frost and heat detection requirements
from CLAUDE.md specifications.

M1 Thresholds (as per CLAUDE.md):
- Light frost: 0°C to 2°C
- Moderate frost: -2°C to 0°C  
- Severe frost: < -2°C
- Hot day: Tmax > 32°C
- Very hot: Tmax > 35°C
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.common.logging_utils import setup_logging
from src.common.constants import SILO_QUALITY_CODES, SILO_QUALITY_DEFAULT
from src.common.file_utils import atomic_csv_write

logger = logging.getLogger(__name__)


class CSVRiskEngine:
    """Simplified CSV-based Risk Engine for M1 implementation"""
    
    # M1 Thresholds from CLAUDE.md
    FROST_THRESHOLDS = {
        'light': 2.0,      # 0°C to 2°C
        'moderate': 0.0,   # -2°C to 0°C
        'severe': -2.0     # < -2°C
    }
    
    HEAT_THRESHOLDS = {
        'hot': 32.0,       # > 32°C (Hot day)
        'very_hot': 35.0   # > 35°C (Very hot)
    }
    
    def __init__(self, data_dir: Optional[str] = None):
        """Initialize CSV Risk Engine
        
        Args:
            data_dir: Path to data directory, defaults to project/data
        """
        self.data_dir = Path(data_dir) if data_dir else project_root / "data"
        self.obs_csv = self.data_dir / "obs" / "obs_daily.csv"
        self.output_dir = self.data_dir / "derived"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"CSV Risk Engine initialized with data from {self.data_dir}")
        
    def run_daily_assessment(self, target_date: str) -> Dict[str, int]:
        """Run event detection for a specific date
        
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
            return {"frost": 0, "heat": 0}
            
        # Run event detection
        all_events = []
        event_counts = {}
        
        # Frost detection (always active for M1 testing)
        frost_events = self._detect_frost_events(weather_data, target_date)
        if not frost_events.empty:
            all_events.append(frost_events)
        event_counts['frost'] = len(frost_events)
        
        # Heat detection (always active for M1 testing)
        heat_events = self._detect_heat_events(weather_data, target_date)
        if not heat_events.empty:
            all_events.append(heat_events)
        event_counts['heat'] = len(heat_events)
        
        logger.info(f"Detected {event_counts['frost']} frost events and {event_counts['heat']} heat events")
        
        # Export events
        if all_events:
            combined_events = pd.concat(all_events, ignore_index=True)
            self._export_events(combined_events, target_date)
        
        return event_counts
        
    def _load_weather_data(self, target_date: str) -> pd.DataFrame:
        """Load weather data for target date from CSV
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            DataFrame with weather data for all stations
        """
        try:
            if not self.obs_csv.exists():
                logger.error(f"CSV file not found: {self.obs_csv}")
                return pd.DataFrame()
                
            # Read full CSV and filter to target date
            df = pd.read_csv(self.obs_csv)
            weather_df = df[df['date'] == target_date].copy()
            
            if weather_df.empty:
                logger.warning(f"No weather data found for {target_date} in {self.obs_csv}")
                return pd.DataFrame()
                
            # Rename columns to match expected format
            weather_df = weather_df.rename(columns={
                'min_temperature': 'min_temp',
                'max_temperature': 'max_temp',
                'min_temperature_quality': 'min_temp_quality',
                'max_temperature_quality': 'max_temp_quality'
            })
            
            logger.info(f"Loaded weather data for {len(weather_df)} stations on {target_date}")
            return weather_df
            
        except Exception as e:
            logger.error(f"Failed to load weather data for {target_date}: {e}")
            return pd.DataFrame()
            
    def _detect_frost_events(self, weather_df: pd.DataFrame, target_date: str) -> pd.DataFrame:
        """Detect frost events using M1 thresholds
        
        Args:
            weather_df: Daily weather data
            target_date: Date being processed
            
        Returns:
            DataFrame with frost event records
        """
        if weather_df.empty or 'min_temp' not in weather_df.columns:
            return pd.DataFrame()
            
        frost_events = []
        
        for _, row in weather_df.iterrows():
            min_temp = row['min_temp']
            
            # Skip missing data
            if pd.isna(min_temp):
                continue
                
            # Apply M1 thresholds (check most severe first)
            frost_severity = None
            threshold_used = None
            
            if min_temp < self.FROST_THRESHOLDS['severe']:
                frost_severity = 'severe'
                threshold_used = self.FROST_THRESHOLDS['severe']
            elif min_temp < self.FROST_THRESHOLDS['moderate']:
                frost_severity = 'moderate'
                threshold_used = self.FROST_THRESHOLDS['moderate']
            elif min_temp <= self.FROST_THRESHOLDS['light']:
                frost_severity = 'light' 
                threshold_used = self.FROST_THRESHOLDS['light']
                
            if frost_severity:
                # Calculate confidence based on data quality
                confidence = self._calculate_confidence(row.get('min_temp_quality', 999))
                
                frost_event = {
                    'station_id': row['station_id'],
                    'date': target_date,
                    'event_type': 'frost',
                    'severity': frost_severity,
                    'value': min_temp,
                    'threshold': threshold_used,
                    'confidence': confidence,
                    'data_quality': row.get('min_temp_quality', 999),
                    'detected_at': datetime.now().isoformat()
                }
                frost_events.append(frost_event)
                
        return pd.DataFrame(frost_events)
        
    def _detect_heat_events(self, weather_df: pd.DataFrame, target_date: str) -> pd.DataFrame:
        """Detect heat events using M1 thresholds
        
        Args:
            weather_df: Daily weather data
            target_date: Date being processed
            
        Returns:
            DataFrame with heat event records
        """
        if weather_df.empty or 'max_temp' not in weather_df.columns:
            return pd.DataFrame()
            
        heat_events = []
        
        for _, row in weather_df.iterrows():
            max_temp = row['max_temp']
            
            # Skip missing data
            if pd.isna(max_temp):
                continue
                
            # Apply M1 thresholds
            heat_severity = None
            threshold_used = None
            
            if max_temp > self.HEAT_THRESHOLDS['very_hot']:
                heat_severity = 'very_hot'
                threshold_used = self.HEAT_THRESHOLDS['very_hot']
            elif max_temp > self.HEAT_THRESHOLDS['hot']:
                heat_severity = 'hot'
                threshold_used = self.HEAT_THRESHOLDS['hot']
                
            if heat_severity:
                # Calculate confidence based on data quality
                confidence = self._calculate_confidence(row.get('max_temp_quality', 999))
                
                heat_event = {
                    'station_id': row['station_id'],
                    'date': target_date,
                    'event_type': 'heat',
                    'severity': heat_severity,
                    'value': max_temp,
                    'threshold': threshold_used,
                    'confidence': confidence,
                    'data_quality': row.get('max_temp_quality', 999),
                    'detected_at': datetime.now().isoformat()
                }
                heat_events.append(heat_event)
                
        return pd.DataFrame(heat_events)
        
    def _calculate_confidence(self, quality_code: float) -> float:
        """Calculate confidence score based on SILO quality codes

        Args:
            quality_code: SILO data quality code

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if pd.isna(quality_code):
            return SILO_QUALITY_DEFAULT
        return SILO_QUALITY_CODES.get(int(quality_code), SILO_QUALITY_DEFAULT)
            
    def _export_events(self, events_df: pd.DataFrame, target_date: str):
        """Export detected events to CSV files (M1 format)

        Args:
            events_df: DataFrame with all detected events
            target_date: Date processed
        """
        try:
            # Export consolidated event log
            event_log_path = self.output_dir / "event_log.csv"

            if event_log_path.exists():
                existing_df = pd.read_csv(event_log_path)
                existing_df = existing_df[existing_df['date'] != target_date]
                combined_df = pd.concat([existing_df, events_df], ignore_index=True)
            else:
                combined_df = events_df

            atomic_csv_write(combined_df, event_log_path)
            logger.info(f"Exported {len(events_df)} events to {event_log_path}")

            # Export M1 format files
            for event_type in ['frost', 'heat']:
                type_events = events_df[events_df['event_type'] == event_type].copy()

                if not type_events.empty:
                    if event_type == 'frost':
                        m1_format = pd.DataFrame({
                            'station_id': type_events['station_id'],
                            'date': type_events['date'],
                            'min_temp': type_events['value'],
                            'risk_flag': type_events['severity']
                        })
                    else:
                        m1_format = pd.DataFrame({
                            'station_id': type_events['station_id'],
                            'date': type_events['date'],
                            'max_temp': type_events['value'],
                            'risk_flag': type_events['severity']
                        })

                    atomic_csv_write(m1_format, self.output_dir / f"{event_type}_events.csv")
                    logger.info(f"Exported {len(type_events)} {event_type} events to M1 format")

        except Exception as e:
            logger.error(f"Failed to export events: {e}")
            raise


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="CropForecaster CSV Risk Engine - M1 Frost/Heat Detection"
    )
    parser.add_argument(
        '--date', 
        help='Target date for analysis (YYYY-MM-DD)', 
        default=datetime.now().strftime('%Y-%m-%d')
    )
    parser.add_argument(
        '--data-dir',
        help='Data directory path',
        default=None
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(level=args.log_level)
    
    try:
        # Initialize Risk Engine
        engine = CSVRiskEngine(data_dir=args.data_dir)
        
        # Run analysis
        results = engine.run_daily_assessment(args.date)
        
        # Summary output
        print(f"\nDate: {args.date}")
        print(f"Frost events: {results['frost']}")
        print(f"Heat events: {results['heat']}")
        print(f"Total events: {results['frost'] + results['heat']}")
        
        logger.info("CSV Risk Engine run completed successfully")
        
    except Exception as e:
        logger.error(f"CSV Risk Engine failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()