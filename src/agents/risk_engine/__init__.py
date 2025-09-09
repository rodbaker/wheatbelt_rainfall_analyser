"""
Risk Engine Agent - Event Detection and Risk Assessment

Mission: Transform weather data into crop risk events with auditable thresholds.

Key Responsibilities:
- Frost detection: Tmin thresholds with consecutive nights and intensity buckets
- Heat stress: Tmax thresholds during sensitive crop phases  
- Harvest rain: Rolling rainfall sums with downgrade risk tags
- Statistical Division aggregation with crop mix weights and severity scoring
"""

from .event_detector import WeatherEventDetector

__all__ = [
    'WeatherEventDetector'
]