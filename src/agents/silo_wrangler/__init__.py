"""
SILO Wrangler Agent - Data Ingest + Quality Control

Mission: Pull daily weather from SILO API, apply quality flags, write analysis-ready CSV files.

Key Responsibilities:
- Fetch SILO point data for variables: rain, Tmax, Tmin, VP, MSLP  
- Respect rate limits; cache results; rolling window updates
- Persist to CSV files with quality flag preservation
- Record run metadata and data gaps to logs
"""

from .api_client import SILOAPIClient
from .data_processor import WeatherDataProcessor  
from .quality_checker import DataQualityChecker
from .run_ingest import run_daily_ingest

__all__ = [
    'SILOAPIClient',
    'WeatherDataProcessor', 
    'DataQualityChecker',
    'run_daily_ingest'
]