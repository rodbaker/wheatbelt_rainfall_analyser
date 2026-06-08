"""
SILO API Client - Handles all SILO API interactions

Implements:
- Robust API calling with retries and rate limiting
- Configuration-driven station and variable selection
- Error handling and timeout management
- Response validation and quality flag processing
"""

import requests
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)


class SILOAPIClient:
    """Client for interacting with SILO weather API"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize SILO API client
        
        Args:
            config: Configuration dictionary from silo_sources.yaml
        """
        self.base_url = config['api']['base_url']
        self.username = config['api']['username']
        self.rate_limit_seconds = config['api']['rate_limit_seconds']
        self.timeout_seconds = config['api']['timeout_seconds']
        self.max_retries = config['api']['max_retries']
        self.variables = config['variables']

        # Build variable comment string (e.g., "RXN" for rain, max_temp, min_temp)
        self.variable_codes = ''.join(self.variables.keys())

        # Data Drill endpoint (grid-based interpolation — no station required)
        dd_config = config.get('data_drill', {})
        self.data_drill_url = dd_config.get(
            'endpoint',
            'https://www.longpaddock.qld.gov.au/cgi-bin/silo/DataDrillDataset.php'
        )
        
    def get_daily_data(self, station_id: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        Get daily weather data for a station and date range
        
        Args:
            station_id: BOM station number (e.g., "040241")
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            
        Returns:
            DataFrame with daily weather observations or None if failed
        """
        params = {
            'station': station_id,
            'start': start_date, 
            'finish': end_date,
            'format': 'csv',
            'comment': self.variable_codes,
            'username': self.username
        }
        
        for attempt in range(self.max_retries):
            try:
                # Rate limiting
                time.sleep(self.rate_limit_seconds)
                
                logger.info(f"Requesting SILO data: station={station_id}, dates={start_date}-{end_date}, attempt={attempt+1}")
                
                response = requests.get(
                    self.base_url,
                    params=params,
                    timeout=self.timeout_seconds
                )
                response.raise_for_status()
                
                # Parse CSV response into DataFrame
                from io import StringIO
                df = pd.read_csv(
                    StringIO(response.text),
                    comment='#',  # Skip comment lines
                    skipinitialspace=True
                )
                
                # Filter out metadata rows - keep only rows with valid dates in YYYY-MM-DD column
                if 'YYYY-MM-DD' in df.columns:
                    # Keep only rows where YYYY-MM-DD matches date format (YYYY-MM-DD)
                    df = df[df['YYYY-MM-DD'].str.match(r'^\d{4}-\d{2}-\d{2}$', na=False)]
                    df = df.reset_index(drop=True)
                
                logger.info(f"Successfully retrieved {len(df)} weather records for station {station_id}")
                return df
                
            except requests.RequestException as e:
                logger.warning(f"API request failed for station {station_id}, attempt {attempt+1}: {e}")
                if attempt == self.max_retries - 1:
                    logger.error(f"All retry attempts failed for station {station_id}")
                    return None
                    
                # Exponential backoff
                time.sleep(2 ** attempt)
                
        return None
        
    def get_yesterday_data(self, station_id: str) -> Optional[pd.DataFrame]:
        """
        Get yesterday's data for a station (common operational pattern)
        
        Args:
            station_id: BOM station number
            
        Returns:
            DataFrame with yesterday's weather data or None if failed
        """
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
        return self.get_daily_data(station_id, yesterday, yesterday)
        
    def get_rolling_window_data(self, station_id: str, days: int = 90) -> Optional[pd.DataFrame]:
        """
        Get recent rolling window of data (for updates and gap filling)
        
        Args:
            station_id: BOM station number
            days: Number of recent days to retrieve
            
        Returns:
            DataFrame with recent weather data or None if failed
        """
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        return self.get_daily_data(station_id, start_date, end_date)
        
    def get_data_drill_data(self, lat: float, lon: float, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        Get daily weather data for any lat/lon point via SILO Data Drill.

        Data Drill uses SILO's 5km climate interpolation surface — no physical station
        required. All returned values will have quality code 15 (interpolated).

        Args:
            lat: Latitude (negative = south)
            lon: Longitude
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format

        Returns:
            DataFrame with daily weather data (same schema as PPD) or None if failed
        """
        params = {
            'lat': f'{lat:.4f}',
            'lon': f'{lon:.4f}',
            'start': start_date,
            'finish': end_date,
            'format': 'csv',
            'comment': self.variable_codes,
            'username': self.username
        }

        for attempt in range(self.max_retries):
            try:
                time.sleep(self.rate_limit_seconds)

                logger.info(f"Requesting Data Drill: lat={lat:.4f}, lon={lon:.4f}, dates={start_date}-{end_date}, attempt={attempt+1}")

                response = requests.get(
                    self.data_drill_url,
                    params=params,
                    timeout=self.timeout_seconds
                )
                response.raise_for_status()

                from io import StringIO
                df = pd.read_csv(
                    StringIO(response.text),
                    comment='#',
                    skipinitialspace=True
                )

                if 'YYYY-MM-DD' in df.columns:
                    # Cast to str first: ocean/no-data points leave YYYY-MM-DD as float NaN
                    df = df[df['YYYY-MM-DD'].astype(str).str.match(r'^\d{4}-\d{2}-\d{2}$', na=False)]
                    df = df.reset_index(drop=True)

                logger.info(f"Data Drill retrieved {len(df)} records for ({lat:.4f}, {lon:.4f})")
                return df

            except requests.RequestException as e:
                logger.warning(f"Data Drill request failed for ({lat:.4f}, {lon:.4f}), attempt {attempt+1}: {e}")
                if attempt == self.max_retries - 1:
                    logger.error(f"All retry attempts failed for Data Drill ({lat:.4f}, {lon:.4f})")
                    return None

                time.sleep(2 ** attempt)

        return None

    def validate_response_data(self, df: pd.DataFrame, station_id: str) -> Dict[str, Any]:
        """
        Validate API response data and extract quality metrics
        
        Args:
            df: DataFrame from SILO API response
            station_id: Station ID for logging
            
        Returns:
            Dictionary with validation results and quality metrics
        """
        if df is None or df.empty:
            return {
                'valid': False,
                'error': 'Empty or null data',
                'record_count': 0
            }
            
        # Check for required columns based on variable configuration
        expected_cols = set()
        for code, name in self.variables.items():
            if code == 'R':
                expected_cols.add('daily_rain')
            elif code == 'X': 
                expected_cols.add('max_temp')
            elif code == 'N':
                expected_cols.add('min_temp')
            elif code == 'V':
                expected_cols.add('vp')
            elif code == 'J':
                expected_cols.add('solar_radiation')
            elif code == 'H':
                expected_cols.add('rh_at_max_temp')
            elif code == 'G':
                expected_cols.add('rh_at_min_temp')
            # Add other variable mappings as needed
                
        missing_cols = expected_cols - set(df.columns)
        if missing_cols:
            return {
                'valid': False,
                'error': f'Missing columns: {missing_cols}',
                'record_count': len(df)
            }
            
        # Calculate data completeness by quality flags
        quality_stats = {}
        for col in df.columns:
            if col.endswith('_Quality'):
                var_col = col.replace('_Quality', '')
                if var_col in df.columns:
                    quality_counts = df[col].value_counts()
                    quality_stats[var_col] = {
                        'total': len(df),
                        'observed': quality_counts.get(0, 0),        # Quality 0 = observed
                        'interpolated': quality_counts.get(15, 0),   # Quality 15 = interpolated  
                        'synthetic': quality_counts.get(35, 0)       # Quality 35 = synthetic
                    }
                    
        return {
            'valid': True,
            'record_count': len(df),
            'date_range': f"{df['Date'].min()} to {df['Date'].max()}" if 'Date' in df.columns else None,
            'quality_stats': quality_stats
        }