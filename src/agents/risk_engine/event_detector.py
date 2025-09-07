"""
Weather Event Detector - Core frost/heat/rain detection logic

Implements:
- Frost event detection with severity classification
- Heat stress detection during grain fill periods
- Harvest rainfall risk assessment with accumulation windows
- Event confidence scoring and data quality handling
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class WeatherEventDetector:
    """Detects frost, heat, and rainfall risk events from weather data"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize event detector with configuration
        
        Args:
            config: Configuration from crop_calendars.yaml and assumptions.yaml
        """
        self.thresholds = config['thresholds']
        self.crop_stages = config.get('wheat', {}).get('stages', {})
        self.detection_config = config.get('detection', {})
        
    def detect_frost_events(self, weather_df: pd.DataFrame, crop_stage_info: Dict[str, Any]) -> pd.DataFrame:
        """
        Detect frost events based on minimum temperature thresholds
        
        Args:
            weather_df: Daily weather data with min_temperature column
            crop_stage_info: Current crop stage information for severity assessment
            
        Returns:
            DataFrame with frost event records
        """
        if weather_df.empty or 'min_temperature' not in weather_df.columns:
            return pd.DataFrame()
            
        frost_events = []
        
        # Get stage-specific thresholds
        stage_name = crop_stage_info.get('current_stage', 'default')
        stage_thresholds = self.thresholds['frost'].get(stage_name, self.thresholds['frost']['emergence'])
        
        for idx, row in weather_df.iterrows():
            min_temp = row['min_temperature']
            
            # Skip missing data
            if pd.isna(min_temp):
                continue
                
            # Check frost thresholds (most severe first)
            frost_severity = None
            if min_temp <= stage_thresholds['severe']:
                frost_severity = 'severe'
            elif min_temp <= stage_thresholds['moderate']:
                frost_severity = 'moderate' 
            elif min_temp <= stage_thresholds['light']:
                frost_severity = 'light'
                
            if frost_severity:
                # Calculate confidence based on data quality
                confidence = self._calculate_event_confidence(row, 'min_temperature')
                
                frost_event = {
                    'station_id': row['station_id'],
                    'date': row['date'],
                    'event_type': 'frost',
                    'severity': frost_severity,
                    'value': min_temp,
                    'threshold': stage_thresholds[frost_severity],
                    'crop_stage': stage_name,
                    'confidence': confidence,
                    'data_quality': row.get('min_temperature_quality', 0),
                    'detected_at': datetime.now().isoformat()
                }
                frost_events.append(frost_event)
                
        frost_df = pd.DataFrame(frost_events)
        
        # Add consecutive night analysis if we have events
        if not frost_df.empty:
            frost_df = self._analyze_consecutive_frosts(frost_df, weather_df)
            
        logger.info(f"Detected {len(frost_events)} frost events")
        return frost_df
        
    def detect_heat_events(self, weather_df: pd.DataFrame, crop_stage_info: Dict[str, Any]) -> pd.DataFrame:
        """
        Detect heat stress events based on maximum temperature thresholds
        
        Args:
            weather_df: Daily weather data with max_temperature column
            crop_stage_info: Current crop stage information
            
        Returns:
            DataFrame with heat event records
        """
        if weather_df.empty or 'max_temperature' not in weather_df.columns:
            return pd.DataFrame()
            
        heat_events = []
        stage_name = crop_stage_info.get('current_stage', 'grain_fill')
        
        # Only detect heat events during vulnerable stages
        if not crop_stage_info.get('heat_critical', False):
            logger.info(f"Stage {stage_name} not heat-critical, skipping heat detection")
            return pd.DataFrame()
            
        heat_thresholds = self.thresholds['heat'][stage_name]
        
        for idx, row in weather_df.iterrows():
            max_temp = row['max_temperature']
            
            # Skip missing data
            if pd.isna(max_temp):
                continue
                
            # Check heat thresholds
            heat_severity = None
            if max_temp >= heat_thresholds['severe']:
                heat_severity = 'severe'
            elif max_temp >= heat_thresholds['stress']:
                heat_severity = 'stress'
                
            if heat_severity:
                confidence = self._calculate_event_confidence(row, 'max_temperature')
                
                heat_event = {
                    'station_id': row['station_id'],
                    'date': row['date'],
                    'event_type': 'heat',
                    'severity': heat_severity,
                    'value': max_temp,
                    'threshold': heat_thresholds[heat_severity],
                    'crop_stage': stage_name,
                    'confidence': confidence,
                    'data_quality': row.get('max_temperature_quality', 0),
                    'detected_at': datetime.now().isoformat()
                }
                heat_events.append(heat_event)
                
        logger.info(f"Detected {len(heat_events)} heat events")
        return pd.DataFrame(heat_events)
        
    def detect_rainfall_events(self, weather_df: pd.DataFrame, crop_stage_info: Dict[str, Any]) -> pd.DataFrame:
        """
        Detect harvest rainfall risk events with rolling accumulations
        
        Args:
            weather_df: Daily weather data with rainfall column
            crop_stage_info: Current crop stage information
            
        Returns:
            DataFrame with rainfall event records
        """
        if weather_df.empty or 'rainfall' not in weather_df.columns:
            return pd.DataFrame()
            
        # Only detect during rain-critical periods (harvest)
        if not crop_stage_info.get('rain_critical', False):
            stage_name = crop_stage_info.get('current_stage', 'unknown')
            logger.info(f"Stage {stage_name} not rain-critical, skipping rainfall detection")
            return pd.DataFrame()
            
        rain_events = []
        rain_thresholds = self.thresholds['rainfall']['harvest']
        
        # Sort by date for rolling calculations
        weather_sorted = weather_df.sort_values('date')
        
        for idx, row in weather_sorted.iterrows():
            daily_rain = row['rainfall']
            
            # Skip missing data
            if pd.isna(daily_rain):
                continue
                
            # Check single-day threshold
            if daily_rain >= rain_thresholds['moderate']:
                confidence = self._calculate_event_confidence(row, 'rainfall')
                
                rain_event = {
                    'station_id': row['station_id'],
                    'date': row['date'],
                    'event_type': 'rainfall',
                    'severity': 'moderate',
                    'value': daily_rain,
                    'threshold': rain_thresholds['moderate'],
                    'accumulation_window': 1,
                    'crop_stage': 'harvest',
                    'confidence': confidence,
                    'data_quality': row.get('rainfall_quality', 0),
                    'detected_at': datetime.now().isoformat()
                }
                rain_events.append(rain_event)
                
            # Check 3-day accumulation
            three_day_total = self._calculate_rolling_rainfall(weather_sorted, row['date'], 3)
            if three_day_total and three_day_total >= rain_thresholds['high']:
                confidence = self._calculate_event_confidence(row, 'rainfall')
                
                rain_event = {
                    'station_id': row['station_id'],
                    'date': row['date'],
                    'event_type': 'rainfall', 
                    'severity': 'high',
                    'value': three_day_total,
                    'threshold': rain_thresholds['high'],
                    'accumulation_window': 3,
                    'crop_stage': 'harvest',
                    'confidence': confidence,
                    'data_quality': row.get('rainfall_quality', 0),
                    'detected_at': datetime.now().isoformat()
                }
                rain_events.append(rain_event)
                
        logger.info(f"Detected {len(rain_events)} rainfall events")
        return pd.DataFrame(rain_events)
        
    def _calculate_event_confidence(self, weather_row: pd.Series, variable: str) -> float:
        """
        Calculate confidence score for detected event based on data quality
        
        Args:
            weather_row: Row of weather data
            variable: Variable name (min_temperature, max_temperature, rainfall)
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        quality_col = f'{variable}_quality'
        
        if quality_col not in weather_row or pd.isna(weather_row[quality_col]):
            return 0.5  # Medium confidence for unknown quality
            
        quality_code = int(weather_row[quality_col])
        
        # SILO quality codes
        if quality_code == 0:      # Observed data
            return 1.0
        elif quality_code == 15:   # Interpolated  
            return 0.8
        elif quality_code == 35:   # Synthetic
            return 0.3
        elif quality_code == 999:  # Missing
            return 0.0
        else:
            return 0.5  # Unknown code
            
    def _analyze_consecutive_frosts(self, frost_df: pd.DataFrame, weather_df: pd.DataFrame) -> pd.DataFrame:
        """
        Analyze consecutive frost nights and add sequence information
        
        Args:
            frost_df: DataFrame with detected frost events
            weather_df: Full weather data for context
            
        Returns:
            Enhanced frost DataFrame with consecutive night analysis
        """
        if frost_df.empty:
            return frost_df
            
        # Add consecutive night counters
        frost_enhanced = frost_df.copy()
        frost_enhanced['consecutive_night'] = 1
        frost_enhanced['sequence_id'] = None
        
        # Group by station for sequence analysis
        for station_id in frost_df['station_id'].unique():
            station_frosts = frost_df[frost_df['station_id'] == station_id].sort_values('date')
            
            if len(station_frosts) < 2:
                continue
                
            sequence_id = 1
            current_sequence = []
            
            for idx, (_, frost_row) in enumerate(station_frosts.iterrows()):
                current_date = pd.to_datetime(frost_row['date'])
                
                if idx == 0:
                    current_sequence = [frost_row.name]
                else:
                    prev_date = pd.to_datetime(station_frosts.iloc[idx-1]['date'])
                    
                    if (current_date - prev_date).days == 1:
                        # Consecutive night
                        current_sequence.append(frost_row.name)
                    else:
                        # End of sequence, start new one
                        if len(current_sequence) > 1:
                            # Update previous sequence
                            for seq_idx, orig_idx in enumerate(current_sequence[:-1]):
                                frost_enhanced.loc[orig_idx, 'consecutive_night'] = seq_idx + 1
                                frost_enhanced.loc[orig_idx, 'sequence_id'] = f"{station_id}_seq_{sequence_id}"
                                
                        sequence_id += 1
                        current_sequence = [frost_row.name]
                        
            # Handle final sequence
            if len(current_sequence) > 1:
                for seq_idx, orig_idx in enumerate(current_sequence):
                    frost_enhanced.loc[orig_idx, 'consecutive_night'] = seq_idx + 1
                    frost_enhanced.loc[orig_idx, 'sequence_id'] = f"{station_id}_seq_{sequence_id}"
                    
        return frost_enhanced
        
    def _calculate_rolling_rainfall(self, weather_df: pd.DataFrame, target_date: str, days: int) -> Optional[float]:
        """
        Calculate rolling rainfall total for specified number of days ending on target date
        
        Args:
            weather_df: Weather DataFrame sorted by date
            target_date: End date for rolling calculation
            days: Number of days to include in rolling total
            
        Returns:
            Rolling rainfall total or None if insufficient data
        """
        target_dt = pd.to_datetime(target_date)
        start_dt = target_dt - timedelta(days=days-1)
        
        # Filter to rolling window
        mask = (pd.to_datetime(weather_df['date']) >= start_dt) & (pd.to_datetime(weather_df['date']) <= target_dt)
        window_data = weather_df[mask]
        
        if len(window_data) < days:
            return None  # Insufficient data for full window
            
        # Calculate total, handling missing values
        rain_values = window_data['rainfall'].dropna()
        if len(rain_values) < days * 0.8:  # Require 80% data availability
            return None
            
        return rain_values.sum()