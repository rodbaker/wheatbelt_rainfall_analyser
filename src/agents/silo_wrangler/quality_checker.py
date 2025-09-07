"""
Data Quality Checker - Validates SILO data quality and completeness

Implements:
- Quality flag interpretation and filtering
- Data completeness assessment
- Gap detection and reporting
- Confidence scoring for downstream use
"""

import pandas as pd
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DataQualityChecker:
    """Validates and scores data quality from SILO sources"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize quality checker
        
        Args:
            config: Configuration from silo_sources.yaml
        """
        self.quality_config = config['quality']
        self.variables = config['variables']
        
    def assess_data_quality(self, df: pd.DataFrame, station_id: str) -> Dict[str, Any]:
        """
        Comprehensive data quality assessment
        
        Args:
            df: Processed weather DataFrame
            station_id: Station identifier for logging
            
        Returns:
            Dictionary with quality assessment results
        """
        if df.empty:
            return {
                'station_id': station_id,
                'assessment_time': datetime.now().isoformat(),
                'overall_quality': 'poor',
                'confidence_score': 0.0,
                'issues': ['no_data'],
                'record_count': 0
            }
            
        issues = []
        variable_scores = {}
        
        # Assess each weather variable
        for var_name in self.variables.values():
            if var_name in df.columns:
                var_assessment = self._assess_variable_quality(
                    df, var_name, f'{var_name}_quality'
                )
                variable_scores[var_name] = var_assessment
                
                # Collect issues
                if var_assessment['completeness'] < self.quality_config['min_data_completeness']:
                    issues.append(f'low_completeness_{var_name}')
                if var_assessment['synthetic_ratio'] > 0.2:  # >20% synthetic data
                    issues.append(f'high_synthetic_{var_name}')
                    
                # Check for excessive interpolation (indicates inactive/old station)
                max_interp_ratio = self.quality_config.get('max_interpolated_ratio', 0.8)
                if var_assessment['interpolated_ratio'] > max_interp_ratio:
                    issues.append(f'high_interpolation_{var_name}')
                    
                # Check for insufficient observed data
                min_obs_ratio = self.quality_config.get('min_observed_ratio', 0.3)
                if var_assessment['observed_ratio'] < min_obs_ratio:
                    issues.append(f'low_observed_data_{var_name}')
                    
        # Calculate overall confidence score
        confidence_score = self._calculate_confidence_score(variable_scores)
        
        # Determine overall quality category
        if confidence_score >= 0.8:
            overall_quality = 'high'
        elif confidence_score >= 0.5:
            overall_quality = 'medium'  
        else:
            overall_quality = 'poor'
            
        # Check for date gaps
        date_gaps = self._detect_date_gaps(df)
        if date_gaps:
            issues.append('date_gaps')
            
        return {
            'station_id': station_id,
            'assessment_time': datetime.now().isoformat(),
            'overall_quality': overall_quality,
            'confidence_score': confidence_score,
            'issues': issues,
            'record_count': len(df),
            'date_range': f"{df['date'].min()} to {df['date'].max()}",
            'variable_assessments': variable_scores,
            'date_gaps': date_gaps
        }
        
    def _assess_variable_quality(self, df: pd.DataFrame, var_col: str, quality_col: str) -> Dict[str, Any]:
        """
        Assess quality for a single weather variable
        
        Args:
            df: DataFrame with weather data
            var_col: Variable column name
            quality_col: Quality flag column name
            
        Returns:
            Quality assessment for the variable
        """
        if quality_col not in df.columns:
            return {
                'completeness': 0.0,
                'observed_ratio': 0.0,
                'interpolated_ratio': 0.0,
                'synthetic_ratio': 0.0,
                'missing_ratio': 1.0
            }
            
        quality_counts = df[quality_col].value_counts()
        total_records = len(df)
        
        # SILO quality codes (from SILO documentation):
        # 0 = Actual observation
        # 15 = Interpolated from surrounding stations
        # 23 = Interpolated from nearby day
        # 25 = Interpolated from long-term average  
        # 35 = Long-term average (synthetic)
        # 75 = Interpolated from nearby stations (secondary)
        # 999 = Missing (our custom flag)
        
        observed_count = quality_counts.get(0, 0)
        # Count all interpolation types as interpolated
        interpolated_count = (quality_counts.get(15, 0) + 
                            quality_counts.get(23, 0) + 
                            quality_counts.get(25, 0) + 
                            quality_counts.get(75, 0))
        synthetic_count = quality_counts.get(35, 0)
        missing_count = quality_counts.get(999, 0)
        
        # Calculate ratios
        observed_ratio = observed_count / total_records
        interpolated_ratio = interpolated_count / total_records  
        synthetic_ratio = synthetic_count / total_records
        missing_ratio = missing_count / total_records
        
        # Completeness = observed + interpolated (if accepting interpolated data)
        if self.quality_config['accept_interpolated']:
            completeness = observed_ratio + interpolated_ratio
        else:
            completeness = observed_ratio
            
        return {
            'completeness': completeness,
            'observed_ratio': observed_ratio,
            'interpolated_ratio': interpolated_ratio,
            'synthetic_ratio': synthetic_ratio,
            'missing_ratio': missing_ratio,
            'total_records': total_records
        }
        
    def _calculate_confidence_score(self, variable_scores: Dict[str, Dict[str, Any]]) -> float:
        """
        Calculate overall confidence score from variable assessments
        
        Args:
            variable_scores: Quality assessments for each variable
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not variable_scores:
            return 0.0
            
        # Weight variables by importance for frost/heat/rain detection
        variable_weights = {
            'rainfall': 0.4,        # Critical for harvest risk
            'min_temperature': 0.3, # Critical for frost detection
            'max_temperature': 0.3  # Critical for heat detection
        }
        
        weighted_score = 0.0
        total_weight = 0.0
        
        for var_name, assessment in variable_scores.items():
            weight = variable_weights.get(var_name, 0.1)  # Default low weight
            var_confidence = assessment['completeness']
            
            # Penalty for high synthetic data ratio
            if assessment['synthetic_ratio'] > 0.2:
                var_confidence *= 0.7
                
            # Penalty for high interpolation ratio (indicates old/inactive station)
            max_interp_ratio = self.quality_config.get('max_interpolated_ratio', 0.8)
            if assessment['interpolated_ratio'] > max_interp_ratio:
                var_confidence *= 0.3  # Heavy penalty for mostly interpolated data
                
            # Penalty for low observed data ratio 
            min_obs_ratio = self.quality_config.get('min_observed_ratio', 0.3)
            if assessment['observed_ratio'] < min_obs_ratio:
                var_confidence *= 0.5  # Penalty for insufficient observed data
                
            weighted_score += var_confidence * weight
            total_weight += weight
            
        if total_weight > 0:
            return min(weighted_score / total_weight, 1.0)
        else:
            return 0.0
            
    def _detect_date_gaps(self, df: pd.DataFrame) -> List[Dict[str, str]]:
        """
        Detect gaps in daily data sequence
        
        Args:
            df: DataFrame with date column
            
        Returns:
            List of detected gaps with start and end dates
        """
        if df.empty or 'date' not in df.columns:
            return []
            
        # Convert to datetime and sort
        df_sorted = df.copy()
        df_sorted['date'] = pd.to_datetime(df_sorted['date'])
        df_sorted = df_sorted.sort_values('date')
        
        gaps = []
        dates = df_sorted['date'].dt.date
        
        for i in range(1, len(dates)):
            current_date = dates.iloc[i]
            prev_date = dates.iloc[i-1]
            
            # Check for gap (more than 1 day difference)
            gap_days = (current_date - prev_date).days
            if gap_days > 1:
                gaps.append({
                    'gap_start': prev_date.strftime('%Y-%m-%d'),
                    'gap_end': current_date.strftime('%Y-%m-%d'),
                    'gap_days': gap_days - 1
                })
                
        return gaps
        
    def filter_by_quality(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter data based on configured quality criteria
        
        Args:
            df: DataFrame with quality flags
            
        Returns:
            Filtered DataFrame meeting quality criteria
        """
        if df.empty:
            return df
            
        filtered_df = df.copy()
        
        # Filter based on quality acceptance settings
        for var_name in self.variables.values():
            quality_col = f'{var_name}_quality'
            
            if quality_col in filtered_df.columns:
                # Build quality filter mask
                mask = pd.Series(True, index=filtered_df.index)
                
                # Always exclude missing data (quality 999)
                mask &= (filtered_df[quality_col] != 999)
                
                # Handle synthetic data (quality 35)
                if not self.quality_config['accept_synthetic']:
                    mask &= (filtered_df[quality_col] != 35)
                    
                # Handle interpolated data (quality 15)
                if not self.quality_config['accept_interpolated']:
                    mask &= (filtered_df[quality_col] != 15)
                    
                # Apply mask - set filtered values to NaN rather than removing rows
                filtered_df.loc[~mask, var_name] = None
                
        logger.info(f"Quality filtering: {len(df)} -> {len(filtered_df)} records")
        return filtered_df