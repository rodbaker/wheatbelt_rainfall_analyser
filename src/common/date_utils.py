"""
Date Utilities - Date/time functions for crop calendar and weather data

Provides:
- Crop season calculations
- Growing stage date ranges
- Date formatting utilities
- Agricultural calendar helpers
"""

from datetime import datetime, date, timedelta
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def get_crop_season(target_date: date, crop_type: str = 'wheat') -> Dict[str, date]:
    """
    Get crop season dates for a given target date
    
    Args:
        target_date: Date to determine season for
        crop_type: Type of crop ('wheat', 'barley', etc.)
        
    Returns:
        Dictionary with season start/end dates
    """
    year = target_date.year
    
    # Australian wheat season (example - adjust based on region)
    if crop_type == 'wheat':
        # If target date is before May, it's for the previous season
        if target_date.month < 5:
            year -= 1
            
        return {
            'season_year': year,
            'planting_start': date(year, 5, 1),      # May planting
            'planting_end': date(year, 7, 31),       # July end
            'flowering_start': date(year, 9, 1),     # September flowering
            'flowering_end': date(year, 10, 31),     # October end
            'harvest_start': date(year, 11, 1),      # November harvest
            'harvest_end': date(year, 12, 31),       # December end
            'season_end': date(year + 1, 4, 30)      # Following April
        }
    else:
        # Default generic crop season
        return {
            'season_year': year,
            'planting_start': date(year, 5, 1),
            'planting_end': date(year, 7, 31),
            'harvest_start': date(year, 11, 1),
            'harvest_end': date(year, 12, 31),
            'season_end': date(year + 1, 4, 30)
        }


def calculate_days_since_planting(target_date: date, planting_date: Optional[date] = None) -> Optional[int]:
    """
    Calculate days since crop planting
    
    Args:
        target_date: Date to calculate from
        planting_date: Specific planting date, or None to use season estimate
        
    Returns:
        Number of days since planting, or None if not in growing season
    """
    if planting_date is None:
        # Use season-based estimate
        season_info = get_crop_season(target_date)
        planting_date = season_info['planting_start']
        
    if target_date < planting_date:
        return None  # Before planting
        
    return (target_date - planting_date).days


def get_current_crop_stage(target_date: date, crop_type: str = 'wheat') -> str:
    """
    Determine current crop growth stage for a date
    
    Args:
        target_date: Date to check stage for
        crop_type: Type of crop
        
    Returns:
        String describing current growth stage
    """
    season_info = get_crop_season(target_date, crop_type)
    
    if target_date < season_info['planting_start']:
        return 'pre_season'
    elif target_date <= season_info['planting_end']:
        return 'planting'
    elif target_date <= season_info['flowering_start']:
        return 'vegetative'
    elif target_date <= season_info['flowering_end']:
        return 'flowering'
    elif target_date <= season_info['harvest_start']:
        return 'grain_filling'
    elif target_date <= season_info['harvest_end']:
        return 'harvest'
    else:
        return 'post_harvest'


def format_date_for_silo(date_obj: date) -> str:
    """
    Format date for SILO API (YYYYMMDD format)
    
    Args:
        date_obj: Date object to format
        
    Returns:
        Date string in YYYYMMDD format
    """
    return date_obj.strftime('%Y%m%d')


def parse_silo_date(date_str: str) -> date:
    """
    Parse SILO API date string into date object
    
    Args:
        date_str: Date string in YYYYMMDD format
        
    Returns:
        Date object
    """
    return datetime.strptime(date_str, '%Y%m%d').date()


def get_date_range(start_date: date, days: int) -> Tuple[date, date]:
    """
    Get date range from start date and number of days
    
    Args:
        start_date: Starting date
        days: Number of days in range
        
    Returns:
        Tuple of (start_date, end_date)
    """
    end_date = start_date + timedelta(days=days - 1)
    return start_date, end_date


def get_yesterday() -> date:
    """Get yesterday's date"""
    return date.today() - timedelta(days=1)


def get_rolling_window_dates(days: int) -> Tuple[date, date]:
    """
    Get start and end dates for rolling window
    
    Args:
        days: Number of days in window (ending yesterday)
        
    Returns:
        Tuple of (start_date, end_date)
    """
    end_date = get_yesterday()
    start_date = end_date - timedelta(days=days - 1)
    return start_date, end_date