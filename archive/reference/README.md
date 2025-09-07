# Reference Code from Research Phase

This directory contains useful code patterns and functions from the original research notebooks that may be valuable for future development.

## Contents

### Data Download Patterns
- **`download_functions.py`**: S3 NetCDF download utilities
  - boto3 integration patterns
  - Error handling for large file downloads
  - Directory management for organized storage

- **`silo_downloader.py`**: SILO API usage examples  
  - Original API calling patterns
  - Station management approaches
  - Data validation techniques

### Analysis Functions
- **`rainfall_metrics.py`**: Statistical analysis utilities
  - Rainfall percentile calculations
  - Trend analysis functions
  - Regional aggregation methods

### NetCDF Processing
- **`modify_netcdf.py`**: NetCDF file manipulation
  - xarray usage patterns
  - Coordinate system handling
  - Data subsetting and masking

- **`rainfall_functions.py`**: NetCDF reading utilities
  - File handling patterns
  - Error checking approaches
  - Data extraction methods

### Visualization Assets
- **Colormap CSV files**: Color schemes for rainfall visualization
  - `monthly_rain.csv`: Monthly rainfall color mapping
  - `unique_rgb_colors.csv`: RGB color definitions
  - Useful for generating publication-quality visualizations

## Usage Notes

### Integration with Operational System
These files are **reference only** - they are not used by the operational CropForecaster system. However, they provide valuable patterns for:

1. **Future feature development**: When adding new data sources or analysis capabilities
2. **Debugging**: Understanding historical approaches to data processing  
3. **Validation**: Cross-checking operational results against research methods
4. **Documentation**: Examples of how specific problems were solved

### Migration to Operational Code
When adapting reference code for operational use:

1. **Update for CSV workflow**: Replace NetCDF operations with CSV equivalents
2. **Add error handling**: Operational code requires more robust error handling
3. **Use configuration**: Replace hardcoded values with config-driven parameters
4. **Add logging**: Include structured logging for monitoring
5. **Follow agent patterns**: Integrate into appropriate agent (Wrangler/Engine/Publisher)

### Dependencies
Reference code may have different dependencies than the operational system:
- `netCDF4`: For NetCDF file handling
- `xarray`: For multi-dimensional data processing  
- `boto3`: For AWS S3 integration
- `geopandas`: For spatial data processing

Check `requirements.txt` in the operational system before adding these dependencies.

## Examples

### Adapting S3 Download Pattern
```python
# Reference code (download_functions.py)
def download_nc_file(year, data_type):
    s3_bucket_name = 'silo-open-data'
    # ... hardcoded paths and error handling

# Operational adaptation (for future use)
def download_reference_data(config, year, data_type):
    bucket = config['reference_data']['s3_bucket']
    # ... config-driven, with proper logging and error handling
```

### Adapting Analysis Function
```python
# Reference code (rainfall_metrics.py)  
def calculate_percentiles(data):
    # ... basic numpy calculation

# Operational adaptation
def calculate_rainfall_percentiles(weather_df, config):
    # ... pandas-based, with quality flags and confidence scoring
```

## Maintenance

This directory is **read-only** for reference purposes. Do not modify these files as they represent the historical research approach. For new development:

1. Create new files in the appropriate operational agent directory
2. Reference these patterns but implement with operational standards
3. Update documentation to note the source of inspiration

---

*Files preserved from research phase migration - September 7, 2025*