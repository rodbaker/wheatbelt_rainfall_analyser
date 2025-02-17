import xarray as xr
import os

# Define the file paths
file1_path = '/home/roddyb/projects/wheatbelt_rainfall_analyser/data/gridded/2024.monthly_rain.nc'
file2_path = '/home/roddyb/projects/wheatbelt_rainfall_analyser/data/gridded/bom_Jan.nc'

print(f"Current working directory: {os.getcwd()}")

# Open the datasets
try:
    ds1 = xr.open_dataset(file1_path)
    print(f"Successfully opened {file1_path}")
    print(ds1)
except FileNotFoundError:
    print(f"Error: {file1_path} not found.")
    ds1 = None

try:
    ds2 = xr.open_dataset(file2_path)
    print(f"Successfully opened {file2_path}")
    print(ds2)
except FileNotFoundError:
    print(f"Error: {file2_path} not found.")
    ds2 = None

# Rename the variable in the second dataset if both datasets were opened
if ds1 is not None and ds2 is not None:
    if 'precip' in ds2.variables:
        ds2 = ds2.rename({'precip': 'Monthly_rainfall'})
        ds2.to_netcdf('/home/roddyb/projects/wheatbelt_rainfall_analyser/data/gridded/bom_Jan_modified.nc') # Save modified file
        print("Renamed 'precip' to 'Monthly_rainfall' and saved to /home/roddyb/projects/wheatbelt_rainfall_analyser/data/gridded/bom_Jan_modified.nc")
    else:
        print("Variable 'precip' not found in bom_Jan.nc")