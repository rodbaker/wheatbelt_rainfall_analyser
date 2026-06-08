"""
Shared constants for CropForecaster

Single source of truth for:
- SILO data quality codes and their confidence mappings
- Event type identifiers
"""

# SILO quality code → confidence score
# Source: Longpaddock SILO data quality documentation
SILO_QUALITY_CODES = {
    0: 1.0,    # Observed (actual station measurement)
    15: 0.8,   # Interpolated from nearby stations
    25: 0.7,   # Interpolated (lower spatial density)
    35: 0.3,   # Synthetic (long-term average fill)
    75: 0.6,   # Interpolated (lower quality)
    999: 0.0,  # Missing data
}
SILO_QUALITY_DEFAULT = 0.5  # Unknown code fallback

# Event type identifiers
EVENT_FROST = 'frost'
EVENT_HEAT = 'heat'
EVENT_RAINFALL = 'rainfall'
EVENT_SEEDING_RAIN = 'seeding_rain'
EVENT_DEVELOPMENT_RAIN = 'development_rain'

ALL_EVENT_TYPES = [
    EVENT_FROST,
    EVENT_HEAT,
    EVENT_RAINFALL,
    EVENT_SEEDING_RAIN,
    EVENT_DEVELOPMENT_RAIN,
]
