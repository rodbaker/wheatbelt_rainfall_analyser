"""
Weather Data Processor - Converts SILO API data to clean CSV format

Handles:
- SILO API response parsing and standardization
- CSV output formatting for downstream agents
- Data type conversions and validation
- Atomic file writing operations
"""

import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import tempfile
import shutil

logger = logging.getLogger(__name__)


class WeatherDataProcessor:
    """Processes SILO API data into standardized CSV format"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize data processor
        
        Args:
            config: Configuration from silo_sources.yaml
        """
        self.output_config = config['output']
        self.quality_config = config['quality']
        self.variables = config['variables']
        
    def process_station_data(self, raw_df: pd.DataFrame, station_id: str) -> pd.DataFrame:
        """
        Process raw SILO API data into standardized format
        
        Args:
            raw_df: Raw DataFrame from SILO API
            station_id: Station identifier
            
        Returns:
            Processed DataFrame ready for CSV output
        """
        if raw_df is None or raw_df.empty:
            return pd.DataFrame()
            
        # Create standardized DataFrame structure with proper length
        num_rows = len(raw_df)
        processed_df = pd.DataFrame()
        
        # Add metadata columns (properly sized)
        # Normalise station_id: BOM numbers are 6-digit zero-padded; Data Drill IDs (DD_lat_lon) are left as-is
        if not station_id.startswith('DD_'):
            station_id = station_id.zfill(6)
        processed_df['station_id'] = [station_id] * num_rows
        processed_df['date'] = pd.to_datetime(raw_df['YYYY-MM-DD']).dt.strftime('%Y-%m-%d')
        processed_df['timestamp_processed'] = [datetime.now().isoformat()] * num_rows
        
        # Process each configured variable
        for code, name in self.variables.items():
            silo_col, quality_col = self._get_silo_column_names(code)
            
            if silo_col in raw_df.columns:
                # Extract value and quality
                processed_df[name] = raw_df[silo_col]
                processed_df[f'{name}_quality'] = raw_df.get(quality_col, 0)
                processed_df[f'{name}_source'] = 'silo_api'
            else:
                logger.warning(f"Expected column {silo_col} not found for station {station_id}")
                processed_df[name] = None
                processed_df[f'{name}_quality'] = 999  # Missing data flag
                processed_df[f'{name}_source'] = 'missing'
                
        return processed_df
        
    def _get_silo_column_names(self, variable_code: str) -> tuple:
        """
        Map variable codes to SILO API column names
        
        Args:
            variable_code: Single letter code (R, X, N, etc.)
            
        Returns:
            Tuple of (data_column, quality_column)
        """
        column_mapping = {
            'R': ('daily_rain', 'daily_rain_source'),
            'X': ('max_temp', 'max_temp_source'),
            'N': ('min_temp', 'min_temp_source'),
            'V': ('vp', 'vp_source'),
            'J': ('solar_radiation', 'solar_radiation_source'),  # J = solar radiation (MJ/m²)
            'D': ('vp_deficit', 'vp_deficit_source'),            # D = vapour pressure deficit (not solar)
            'E': ('evaporation', 'evaporation_source'),
            'H': ('rh_at_max_temp', 'rh_at_max_temp_source'),
            'G': ('rh_at_min_temp', 'rh_at_min_temp_source'),
            'F': ('et_fao56', 'et_fao56_source'),
            'M': ('msl_pressure', 'msl_pressure_source'),
        }
        return column_mapping.get(variable_code, (f'Unknown_{variable_code}', f'Unknown_{variable_code}_Quality'))
        
    def append_to_daily_observations(self, processed_df: pd.DataFrame) -> bool:
        """
        Append processed data to main daily observations CSV file
        
        Args:
            processed_df: Processed DataFrame to append
            
        Returns:
            True if successful, False otherwise
        """
        if processed_df.empty:
            logger.warning("No data to append - empty DataFrame")
            return False
            
        output_path = Path(self.output_config['daily_observations'])
        
        try:
            # Create directory if it doesn't exist
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Use atomic write pattern for data integrity
            return self._atomic_csv_append(processed_df, output_path)
            
        except Exception as e:
            logger.error(f"Failed to append data to {output_path}: {e}")
            return False
            
    def update_station_metadata(self, station_data: List[Dict[str, Any]]) -> bool:
        """
        Update station metadata CSV file
        
        Args:
            station_data: List of station metadata dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        if not station_data:
            return True
            
        metadata_path = Path(self.output_config['station_metadata'])
        
        try:
            metadata_df = pd.DataFrame(station_data)
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            
            return self._atomic_csv_write(metadata_df, metadata_path)
            
        except Exception as e:
            logger.error(f"Failed to update station metadata {metadata_path}: {e}")
            return False
            
    def _atomic_csv_append(self, df: pd.DataFrame, file_path: Path) -> bool:
        """
        Atomically append DataFrame to CSV file
        
        Args:
            df: DataFrame to append
            file_path: Path to CSV file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if file exists to determine if we need headers
            write_header = not file_path.exists()
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                
                # If file exists, read existing data and combine
                if file_path.exists():
                    existing_df = pd.read_csv(file_path)
                    combined_df = pd.concat([existing_df, df], ignore_index=True)
                    
                    # Remove duplicates based on station_id and date
                    combined_df = combined_df.drop_duplicates(subset=['station_id', 'date'], keep='last')
                else:
                    combined_df = df
                    
                # Write combined data to temp file
                combined_df.to_csv(temp_path, index=False)
                
            # Atomic move
            shutil.move(str(temp_path), str(file_path))
            logger.info(f"Successfully appended {len(df)} records to {file_path}")
            return True
            
        except Exception as e:
            # Cleanup temp file if it exists
            if 'temp_path' in locals() and temp_path.exists():
                temp_path.unlink()
            logger.error(f"Atomic CSV append failed: {e}")
            return False
            
    def _atomic_csv_write(self, df: pd.DataFrame, file_path: Path) -> bool:
        """
        Atomically write DataFrame to CSV file
        
        Args:
            df: DataFrame to write
            file_path: Path to CSV file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                df.to_csv(temp_path, index=False)
                
            # Atomic move
            shutil.move(str(temp_path), str(file_path))
            logger.info(f"Successfully wrote {len(df)} records to {file_path}")
            return True
            
        except Exception as e:
            # Cleanup temp file if it exists
            if 'temp_path' in locals() and temp_path.exists():
                temp_path.unlink()
            logger.error(f"Atomic CSV write failed: {e}")
            return False