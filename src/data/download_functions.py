import boto3
import os

def download_nc_file(year, data_type):
    """Downloads a NetCDF file from an S3 bucket and saves it to a local directory.

    Args:
        year (int): The year of the data to download.
        data_type (str): The type of data to download. Must be 'monthly_rain' or 'max_temp'.

    Returns:
        str: The path to the downloaded file if successful, otherwise None.
    """
    s3_bucket_name = 'silo-open-data'

    if data_type == 'monthly_rain':
        s3_key = f'Official/annual/monthly_rain/{year}.monthly_rain.nc'
        save_dir = "/home/roddyb/projects/wheatbelt_rainfall_analyser/data/gridded/monthly_rain"
    elif data_type == 'max_temp':
        s3_key = f'Official/annual/max_temp/{year}.max_temp.nc'
        save_dir = "/home/roddyb/projects/wheatbelt_rainfall_analyser/data/gridded/max_temp"
    else:
        print("Invalid data_type. Choose 'monthly_rain' or 'max_temp'")
        return None
        
    file_path = os.path.join(save_dir, f'{year}.{data_type}.nc')

    s3 = boto3.client('s3')

    try:
        os.makedirs(save_dir, exist_ok=True)  # Create directory if it doesn't exist
        s3.download_file(s3_bucket_name, s3_key, file_path)
        return file_path
    except Exception as e:
        print(f"Error downloading {year}.{data_type}.nc: {e}")
        return None