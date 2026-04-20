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

from src.common.constants import SILO_QUALITY_CODES, SILO_QUALITY_DEFAULT

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
                confidence = self._calculate_event_confidence(row, 'min_temperature')
                phenology_risk_multiplier = self._get_phenology_risk_multiplier(crop_stage_info, 'frost')

                frost_events.append(self._build_event_record(
                    row=row,
                    event_type='frost',
                    severity=frost_severity,
                    value=min_temp,
                    threshold=stage_thresholds[frost_severity],
                    crop_stage=stage_name,
                    confidence=confidence,
                    quality_col='min_temperature_quality',
                    phenology_risk_multiplier=phenology_risk_multiplier,
                    flowering_window_active=crop_stage_info.get('flowering_window', {}).get('active', False),
                    days_since_flowering_start=crop_stage_info.get('days_since_flowering_start'),
                ))
                
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

                heat_events.append(self._build_event_record(
                    row=row,
                    event_type='heat',
                    severity=heat_severity,
                    value=max_temp,
                    threshold=heat_thresholds[heat_severity],
                    crop_stage=stage_name,
                    confidence=confidence,
                    quality_col='max_temperature_quality',
                ))
                
        logger.info(f"Detected {len(heat_events)} heat events")
        return pd.DataFrame(heat_events)
        
    def detect_rainfall_events(self, weather_df: pd.DataFrame, crop_stage_info: Dict[str, Any],
                               weather_window: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Detect harvest rainfall risk events with rolling accumulations.

        Args:
            weather_df: Target-date weather rows (one per station)
            crop_stage_info: Current crop stage information
            weather_window: Multi-day lookback DataFrame for rolling sums (falls back to weather_df)

        Returns:
            DataFrame with rainfall event records
        """
        if weather_df.empty or 'rainfall' not in weather_df.columns:
            return pd.DataFrame()

        if not crop_stage_info.get('rain_critical', False):
            stage_name = crop_stage_info.get('current_stage', 'unknown')
            logger.info(f"Stage {stage_name} not rain-critical, skipping rainfall detection")
            return pd.DataFrame()

        window = weather_window if weather_window is not None else weather_df
        rain_events = []
        rain_thresholds = self.thresholds['rainfall']['harvest']

        for idx, row in weather_df.iterrows():
            daily_rain = row['rainfall']
            if pd.isna(daily_rain):
                continue

            station_id = row['station_id']

            # Single-day threshold
            if daily_rain >= rain_thresholds['moderate']:
                confidence = self._calculate_event_confidence(row, 'rainfall')
                rain_events.append(self._build_event_record(
                    row=row,
                    event_type='rainfall',
                    severity='moderate',
                    value=daily_rain,
                    threshold=rain_thresholds['moderate'],
                    crop_stage='harvest',
                    confidence=confidence,
                    quality_col='rainfall_quality',
                    accumulation_window=1,
                ))

            # 3-day accumulation — station-specific rolling window
            three_day_total = self._calculate_rolling_rainfall(window, row['date'], 3, station_id=station_id)
            if three_day_total and three_day_total >= rain_thresholds['high']:
                confidence = self._calculate_event_confidence(row, 'rainfall')
                rain_events.append(self._build_event_record(
                    row=row,
                    event_type='rainfall',
                    severity='high',
                    value=three_day_total,
                    threshold=rain_thresholds['high'],
                    crop_stage='harvest',
                    confidence=confidence,
                    quality_col='rainfall_quality',
                    accumulation_window=3,
                ))

        logger.info(f"Detected {len(rain_events)} rainfall events")
        return pd.DataFrame(rain_events)
        
    def detect_seeding_rainfall(self, weather_df: pd.DataFrame, crop_stage_info: Dict[str, Any],
                                weather_window: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Detect seeding window rainfall events (April–June).

        Args:
            weather_df: Target-date weather rows (one per station)
            crop_stage_info: Current crop stage information
            weather_window: Multi-day lookback DataFrame for rolling sums
        """
        if weather_df.empty or 'rainfall' not in weather_df.columns:
            return pd.DataFrame()

        target_month = crop_stage_info.get('target_month', 0)
        if target_month not in [4, 5, 6]:
            return pd.DataFrame()

        window = weather_window if weather_window is not None else weather_df
        rain_thresholds = self.thresholds['rainfall']['seeding']
        rain_events = []

        for idx, row in weather_df.iterrows():
            daily_rain = row['rainfall']
            if pd.isna(daily_rain):
                continue

            station_id = row['station_id']
            confidence = self._calculate_event_confidence(row, 'rainfall')

            # Single-day germination trigger
            if daily_rain >= rain_thresholds['germination_trigger']:
                rain_events.append(self._build_event_record(
                    row=row,
                    event_type='seeding_rain',
                    severity='adequate',
                    value=daily_rain,
                    threshold=rain_thresholds['germination_trigger'],
                    crop_stage='seeding',
                    confidence=confidence,
                    quality_col='rainfall_quality',
                    accumulation_window=1,
                    rainfall_role='beneficial',
                ))

            # 7-day rolling window — four-band severity classification:
            #   adequate     >= 25mm  (sufficient autumn break)
            #   marginal     >= 15mm, < 25mm  (near-miss)
            #   marginal_low >= 10mm, < 15mm  (borderline)
            #   inadequate    < 10mm  (dry spell alarm — only fired from May onwards;
            #                          April dryness is normal before the break arrives)
            adequate_break = rain_thresholds['adequate_break']          # 25mm
            marginal_break = rain_thresholds['marginal_break_mm_7d']    # 15mm
            marginal_low_break = rain_thresholds['marginal_low_break_mm_7d']  # 10mm

            seven_day_total = self._calculate_rolling_rainfall(window, row['date'], 7, station_id=station_id)
            if seven_day_total is not None:
                if seven_day_total >= adequate_break:
                    severity_7d = 'adequate'
                    threshold_7d = adequate_break
                elif seven_day_total >= marginal_break:
                    severity_7d = 'marginal'
                    threshold_7d = marginal_break
                elif seven_day_total >= marginal_low_break:
                    severity_7d = 'marginal_low'
                    threshold_7d = marginal_low_break
                elif target_month >= 5:
                    # Only raise a dry-spell alarm from May onwards — April is too
                    # early in the seeding window to flag the absence of a break.
                    severity_7d = 'inadequate'
                    threshold_7d = rain_thresholds['inadequate_week']
                else:
                    severity_7d = None  # April dryness — suppress

                if severity_7d is not None:
                    rain_events.append(self._build_event_record(
                        row=row,
                        event_type='seeding_rain',
                        severity=severity_7d,
                        value=seven_day_total,
                        threshold=threshold_7d,
                        crop_stage='seeding',
                        confidence=confidence,
                        quality_col='rainfall_quality',
                        accumulation_window=7,
                        rainfall_role='beneficial',
                    ))

        result = pd.DataFrame(rain_events)
        if not result.empty:
            result = result.drop_duplicates(subset=['station_id', 'date', 'event_type', 'severity', 'accumulation_window'])
        logger.info(f"Detected {len(result)} seeding rainfall events")
        return result

    def detect_development_rainfall(self, weather_df: pd.DataFrame, crop_stage_info: Dict[str, Any],
                                    weather_window: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Detect crop development window rainfall events (July–October).

        Args:
            weather_df: Target-date weather rows (one per station)
            crop_stage_info: Current crop stage information
            weather_window: Multi-day lookback DataFrame for rolling sums
        """
        if weather_df.empty or 'rainfall' not in weather_df.columns:
            return pd.DataFrame()

        target_month = crop_stage_info.get('target_month', 0)
        if target_month not in [7, 8, 9, 10]:
            return pd.DataFrame()

        window = weather_window if weather_window is not None else weather_df
        rain_thresholds = self.thresholds['rainfall']['crop_development']
        rain_events = []

        for idx, row in weather_df.iterrows():
            daily_rain = row['rainfall']
            if pd.isna(daily_rain):
                continue

            station_id = row['station_id']
            confidence = self._calculate_event_confidence(row, 'rainfall')

            # 7-day dry spell
            seven_day_total = self._calculate_rolling_rainfall(window, row['date'], 7, station_id=station_id)
            if seven_day_total is not None and seven_day_total < rain_thresholds['dry_spell_7day']:
                rain_events.append(self._build_event_record(
                    row=row,
                    event_type='development_rain',
                    severity='dry_spell',
                    value=seven_day_total,
                    threshold=rain_thresholds['dry_spell_7day'],
                    crop_stage=crop_stage_info.get('current_stage', 'crop_development'),
                    confidence=confidence,
                    quality_col='rainfall_quality',
                    accumulation_window=7,
                    rainfall_role='beneficial',
                ))

            # 14-day moisture stress
            fourteen_day_total = self._calculate_rolling_rainfall(window, row['date'], 14, station_id=station_id)
            if fourteen_day_total is not None and fourteen_day_total < rain_thresholds['dry_spell_14day']:
                rain_events.append(self._build_event_record(
                    row=row,
                    event_type='development_rain',
                    severity='moisture_stress',
                    value=fourteen_day_total,
                    threshold=rain_thresholds['dry_spell_14day'],
                    crop_stage=crop_stage_info.get('current_stage', 'crop_development'),
                    confidence=confidence,
                    quality_col='rainfall_quality',
                    accumulation_window=14,
                    rainfall_role='beneficial',
                ))

        result = pd.DataFrame(rain_events)
        if not result.empty:
            result = result.drop_duplicates(subset=['station_id', 'date', 'event_type', 'severity', 'accumulation_window'])
        logger.info(f"Detected {len(result)} development rainfall events")
        return result

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
            return SILO_QUALITY_DEFAULT

        quality_code = int(weather_row[quality_col])
        return SILO_QUALITY_CODES.get(quality_code, SILO_QUALITY_DEFAULT)

    def _build_event_record(
        self,
        row: pd.Series,
        event_type: str,
        severity: str,
        value: float,
        threshold: float,
        crop_stage: str,
        confidence: float,
        quality_col: str,
        **extra_fields
    ) -> dict:
        """
        Build a standardised event record dictionary.

        All event types share this structure so downstream consumers
        (CSV export, report generator, Power BI) get consistent columns.

        Args:
            row: Weather data row
            event_type: One of the EVENT_* constants
            severity: Severity label for this event
            value: Measured value that triggered the event
            threshold: Threshold that was crossed
            crop_stage: Current crop stage name
            confidence: Pre-calculated confidence score
            quality_col: Column name for the raw quality code
            **extra_fields: Any additional fields (accumulation_window, rainfall_role, etc.)

        Returns:
            Event record dictionary
        """
        record = {
            'station_id': row['station_id'],
            'date': row['date'],
            'event_type': event_type,
            'severity': severity,
            'value': value,
            'threshold': threshold,
            'crop_stage': crop_stage,
            'confidence': confidence,
            'data_quality': row.get(quality_col, 0),
            'detected_at': datetime.now().isoformat(),
        }
        record.update(extra_fields)
        return record
            
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
        
    def _calculate_rolling_rainfall(self, weather_df: pd.DataFrame, target_date: str, days: int,
                                    station_id: Optional[str] = None) -> Optional[float]:
        """
        Calculate rolling rainfall total for N days ending on target_date for a single station.

        Args:
            weather_df: Multi-day weather DataFrame (may contain multiple stations)
            target_date: End date for rolling calculation
            days: Number of days to include in rolling total
            station_id: Filter to this station before computing (required for multi-station DataFrames)

        Returns:
            Rolling rainfall total or None if insufficient data
        """
        target_dt = pd.to_datetime(target_date)
        start_dt = target_dt - timedelta(days=days - 1)

        df = weather_df
        if station_id is not None:
            df = df[df['station_id'] == station_id]

        # Filter to rolling window
        mask = (pd.to_datetime(df['date']) >= start_dt) & (pd.to_datetime(df['date']) <= target_dt)
        window_data = df[mask]

        if len(window_data) < days:
            return None  # Insufficient data for full window

        # Calculate total, handling missing values
        rain_values = window_data['rainfall'].dropna()
        if len(rain_values) < days * 0.8:  # Require 80% data availability
            return None
            
        return rain_values.sum()
    
    def _get_phenology_risk_multiplier(self, crop_stage_info: Dict[str, Any], event_type: str) -> float:
        """
        Calculate phenology-based risk multiplier for events
        
        Adjusts risk assessment based on crop development stage and timing
        within the growing season. More critical stages get higher multipliers.
        
        Args:
            crop_stage_info: Crop stage information from risk engine
            event_type: Type of weather event ('frost', 'heat', 'rainfall')
            
        Returns:
            Risk multiplier (1.0 = baseline, >1.0 = elevated risk, <1.0 = reduced risk)
        """
        current_stage = crop_stage_info.get('current_stage', 'unknown')
        flowering_active = crop_stage_info.get('flowering_window', {}).get('active', False)
        days_since_flowering = crop_stage_info.get('days_since_flowering_start', 0)
        
        if event_type == 'frost':
            # Frost risk multipliers by stage
            stage_multipliers = {
                'emergence': 1.5,     # Young plants vulnerable
                'stem_elongation': 1.8,  # Growing points exposed
                'flowering': 2.5,     # Most critical stage
                'grain_fill': 2.0,    # Still very vulnerable
                'tillering': 1.0,     # More frost tolerant
                'maturity': 0.5,      # Crop nearly finished
                'harvest': 0.2        # Minimal impact
            }
            
            base_multiplier = stage_multipliers.get(current_stage, 1.0)
            
            # Extra weighting for flowering window
            if flowering_active:
                base_multiplier *= 1.3  # 30% increase during flowering
                
                # Peak vulnerability in early flowering
                if days_since_flowering is not None and days_since_flowering <= 7:
                    base_multiplier *= 1.2  # Additional 20% in first week
                    
        elif event_type == 'heat':
            # Heat stress risk multipliers
            stage_multipliers = {
                'flowering': 1.5,     # Pollen viability affected
                'grain_fill': 2.0,    # Most critical for grain quality
                'maturity': 1.2,      # Some impact on final filling
                'emergence': 0.8,     # Less heat sensitive when young
                'tillering': 0.8,
                'stem_elongation': 1.0,
                'harvest': 1.0        # Quality impacts during harvest
            }
            
            base_multiplier = stage_multipliers.get(current_stage, 1.0)
            
        elif event_type == 'rainfall':
            # Rainfall risk mainly during harvest
            stage_multipliers = {
                'harvest': 2.0,       # Quality downgrades
                'maturity': 1.5,      # Pre-harvest risk
                'grain_fill': 0.8,    # Generally beneficial
                'flowering': 0.7,     # Usually beneficial
                'emergence': 0.5,     # Can be beneficial for establishment
                'tillering': 0.6,
                'stem_elongation': 0.8
            }
            
            base_multiplier = stage_multipliers.get(current_stage, 1.0)
            
        else:
            base_multiplier = 1.0  # Unknown event type
            
        # Cap multipliers to reasonable range
        return max(0.1, min(base_multiplier, 3.0))