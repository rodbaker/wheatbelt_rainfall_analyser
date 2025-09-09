"""
DuckDB Storage Layer for SILO Weather Data

High-performance storage and querying layer using DuckDB.
Optimized for fast writes and analytical queries on weather time series.

Features:
- Atomic daily batch inserts
- Optimized schema for weather data
- Fast aggregation queries
- Data integrity and deduplication
- Export capabilities for downstream systems
"""

import logging
import duckdb
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)


class DuckDBStorage:
    """DuckDB-based storage manager for weather observations"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize DuckDB storage
        
        Args:
            config: Storage configuration dictionary
        """
        self.db_path = Path(config.get('database_path', 'data/weather.duckdb'))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connection will be created per operation for thread safety
        self._ensure_schema()
        
    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get a new DuckDB connection"""
        return duckdb.connect(str(self.db_path))
        
    def _ensure_schema(self):
        """Ensure database schema exists"""
        with self._get_connection() as conn:
            # Create main observations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS weather_observations (
                    station_id VARCHAR NOT NULL,
                    date DATE NOT NULL,
                    min_temp REAL,
                    max_temp REAL,
                    rainfall REAL,
                    min_temp_quality INTEGER,
                    max_temp_quality INTEGER,
                    rainfall_quality INTEGER,
                    ingested_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (station_id, date)
                )
            """)
            
            # Create ingestion log table for audit trail
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_log (
                    run_id VARCHAR PRIMARY KEY,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    target_date DATE,
                    stations_processed INTEGER,
                    records_ingested INTEGER,
                    errors INTEGER,
                    duration_seconds REAL,
                    status VARCHAR NOT NULL  -- 'running', 'completed', 'failed'
                )
            """)
            
            # Create indexes for common queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_date ON weather_observations(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_station_date ON weather_observations(station_id, date)")
            
            logger.info("DuckDB schema initialized")
            
    def store_daily_observations(self, records: List[Dict[str, Any]], target_date: str) -> bool:
        """
        Store daily weather observations with atomic transaction
        
        Args:
            records: List of weather observation dictionaries
            target_date: Target date string (YYYY-MM-DD) for logging
            
        Returns:
            True if successful, False otherwise
        """
        if not records:
            logger.warning("No records to store")
            return True
            
        try:
            with self._get_connection() as conn:
                # Convert records to DataFrame for efficient bulk insert
                df = pd.DataFrame(records)
                
                # Start transaction
                conn.begin()
                
                # Delete existing data for this date to handle reprocessing
                conn.execute("""
                    DELETE FROM weather_observations 
                    WHERE date = ?
                """, [target_date])
                
                # Insert new data
                conn.register('new_observations', df)
                conn.execute("""
                    INSERT INTO weather_observations 
                    SELECT * FROM new_observations
                """)
                
                # Commit transaction
                conn.commit()
                
                logger.info(f"Stored {len(records)} observations for {target_date}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to store observations for {target_date}: {e}")
            return False
            
    def log_ingestion_run(self, run_id: str, stats: Dict[str, Any], target_date: Optional[str] = None):
        """Log ingestion run statistics
        
        Args:
            run_id: Unique identifier for this ingestion run
            stats: Statistics dictionary from ingestion pipeline
            target_date: Target date for the run (optional)
        """
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO ingestion_log 
                    (run_id, start_time, end_time, target_date, stations_processed, 
                     records_ingested, errors, duration_seconds, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    run_id,
                    datetime.fromtimestamp(stats.get('start_time', 0)) if stats.get('start_time') else datetime.now(),
                    datetime.fromtimestamp(stats.get('end_time', 0)) if stats.get('end_time') else None,
                    target_date,
                    stats.get('stations_processed', 0),
                    stats.get('records_ingested', 0),
                    stats.get('errors', 0),
                    stats.get('duration_seconds'),
                    'completed' if stats.get('errors', 0) == 0 else 'failed'
                ])
                
        except Exception as e:
            logger.error(f"Failed to log ingestion run {run_id}: {e}")
            
    def get_station_data(self, station_id: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Get weather data for a station and date range
        
        Args:
            station_id: BOM station number
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            DataFrame with weather observations
        """
        try:
            with self._get_connection() as conn:
                df = conn.execute("""
                    SELECT station_id, date, min_temp, max_temp, rainfall,
                           min_temp_quality, max_temp_quality, rainfall_quality
                    FROM weather_observations
                    WHERE station_id = ? AND date BETWEEN ? AND ?
                    ORDER BY date
                """, [station_id, start_date, end_date]).df()
                
                return df
                
        except Exception as e:
            logger.error(f"Failed to get station data for {station_id}: {e}")
            return pd.DataFrame()
            
    def get_daily_summary(self, target_date: str) -> pd.DataFrame:
        """
        Get daily summary statistics across all stations
        
        Args:
            target_date: Date for summary (YYYY-MM-DD)
            
        Returns:
            DataFrame with daily summary statistics
        """
        try:
            with self._get_connection() as conn:
                df = conn.execute("""
                    SELECT 
                        date,
                        COUNT(*) as station_count,
                        ROUND(AVG(min_temp), 1) as avg_min_temp,
                        ROUND(AVG(max_temp), 1) as avg_max_temp,
                        ROUND(AVG(rainfall), 1) as avg_rainfall,
                        MIN(min_temp) as min_temp_extreme,
                        MAX(max_temp) as max_temp_extreme,
                        MAX(rainfall) as max_rainfall,
                        SUM(CASE WHEN min_temp < 0 THEN 1 ELSE 0 END) as frost_stations,
                        SUM(CASE WHEN max_temp > 32 THEN 1 ELSE 0 END) as hot_stations,
                        SUM(CASE WHEN rainfall > 10 THEN 1 ELSE 0 END) as heavy_rain_stations
                    FROM weather_observations
                    WHERE date = ?
                    GROUP BY date
                """, [target_date]).df()
                
                return df
                
        except Exception as e:
            logger.error(f"Failed to get daily summary for {target_date}: {e}")
            return pd.DataFrame()
            
    def export_for_risk_engine(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Export data in format suitable for Risk Engine processing
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            DataFrame optimized for risk detection algorithms
        """
        try:
            with self._get_connection() as conn:
                df = conn.execute("""
                    SELECT 
                        station_id,
                        date,
                        min_temp,
                        max_temp,
                        rainfall,
                        -- Quality flags (0=observed, 15=interpolated, 35=synthetic)
                        min_temp_quality,
                        max_temp_quality,
                        rainfall_quality,
                        -- Derived risk indicators
                        CASE WHEN min_temp < 2 THEN 'frost_risk' ELSE null END as frost_flag,
                        CASE WHEN max_temp > 32 THEN 'heat_risk' ELSE null END as heat_flag,
                        CASE WHEN rainfall > 10 THEN 'rain_risk' ELSE null END as rain_flag
                    FROM weather_observations
                    WHERE date BETWEEN ? AND ?
                      AND (min_temp IS NOT NULL OR max_temp IS NOT NULL OR rainfall IS NOT NULL)
                    ORDER BY station_id, date
                """, [start_date, end_date]).df()
                
                return df
                
        except Exception as e:
            logger.error(f"Failed to export data for risk engine: {e}")
            return pd.DataFrame()
            
    def export_to_csv(self, output_path: str, start_date: str, end_date: str) -> bool:
        """
        Export weather data to CSV for external systems
        
        Args:
            output_path: Path for output CSV file
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            df = self.export_for_risk_engine(start_date, end_date)
            
            if not df.empty:
                df.to_csv(output_path, index=False)
                logger.info(f"Exported {len(df)} records to {output_path}")
                return True
            else:
                logger.warning(f"No data to export for date range {start_date} to {end_date}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to export CSV to {output_path}: {e}")
            return False
            
    def get_data_coverage_summary(self, days: int = 30) -> pd.DataFrame:
        """
        Get data coverage summary for the last N days
        
        Args:
            days: Number of recent days to analyze
            
        Returns:
            DataFrame with coverage statistics
        """
        try:
            with self._get_connection() as conn:
                end_date = datetime.now().date()
                start_date = end_date - timedelta(days=days)
                
                df = conn.execute("""
                    SELECT 
                        date,
                        COUNT(*) as stations_reporting,
                        COUNT(min_temp) as min_temp_count,
                        COUNT(max_temp) as max_temp_count,  
                        COUNT(rainfall) as rainfall_count,
                        ROUND(100.0 * COUNT(min_temp) / COUNT(*), 1) as min_temp_coverage_pct,
                        ROUND(100.0 * COUNT(max_temp) / COUNT(*), 1) as max_temp_coverage_pct,
                        ROUND(100.0 * COUNT(rainfall) / COUNT(*), 1) as rainfall_coverage_pct
                    FROM weather_observations
                    WHERE date BETWEEN ? AND ?
                    GROUP BY date
                    ORDER BY date DESC
                """, [str(start_date), str(end_date)]).df()
                
                return df
                
        except Exception as e:
            logger.error(f"Failed to get coverage summary: {e}")
            return pd.DataFrame()
            
    def cleanup_old_logs(self, days_to_keep: int = 90):
        """
        Clean up old ingestion logs to prevent database bloat
        
        Args:
            days_to_keep: Number of days of logs to retain
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            with self._get_connection() as conn:
                result = conn.execute("""
                    DELETE FROM ingestion_log
                    WHERE start_time < ?
                """, [cutoff_date])
                
                deleted_count = result.fetchone()[0] if result else 0
                logger.info(f"Cleaned up {deleted_count} old ingestion log entries")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")
            
    def query_to_dataframe(self, query: str, params: List[Any] = None) -> pd.DataFrame:
        """
        Execute a SQL query and return results as DataFrame
        
        Args:
            query: SQL query string
            params: Optional query parameters
            
        Returns:
            DataFrame with query results
        """
        try:
            with self._get_connection() as conn:
                if params:
                    df = conn.execute(query, params).df()
                else:
                    df = conn.execute(query).df()
                return df
                
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return pd.DataFrame()