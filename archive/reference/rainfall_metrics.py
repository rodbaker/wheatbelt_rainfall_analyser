import numpy
import netCDF4

# Define the full path to the regional mask file
mask_file_path = "/home/roddyb/projects/wheatbelt_rainfall_analyser/data/external/shapefiles/mask_qld.nc"

# Load the regional mask
with netCDF4.Dataset(mask_file_path, 'r') as mask_dataset:
    mask_data = mask_dataset.variables['mask'][:]

# Initialise the results list
results = []

# Define the directory where rainfall files are stored
rainfall_data_dir = "/home/roddyb/projects/wheatbelt_rainfall_analyser/data/external/monthly_rain/"

# Loop over years
for year in range(2011, 2024):
    # Construct the full file path for the yearly NetCDF file
    rainfall_file_path = f"{rainfall_data_dir}{year}.monthly_rain.nc"

    try:
        # Load the monthly rainfall data for all months in the year
        with netCDF4.Dataset(rainfall_file_path, 'r') as dataset:
            data = dataset.variables['monthly_rain'][:]
            # Apply regional mask to the data
            data.mask = mask_data.mask
            # Calculate the annual regional average rainfall
            # by computing the average across all months
            # and all grid points within the mask
            average = numpy.mean(data)
        
        # Append result to the list
        results.append(average)

    except FileNotFoundError:
        print(f"Warning: File not found for year {year}: {rainfall_file_path}")

# Print results
print(results)