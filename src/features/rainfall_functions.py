import netCDF4

def read_nc_data(file_path):
    try:
        dataset = netCDF4.Dataset(file_path, 'r')
        return dataset
    except Exception as e:
        print(f"Error reading NetCDF file: {e}")
        return None
