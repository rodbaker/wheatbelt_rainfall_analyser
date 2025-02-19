import netCDF4
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

def extract_and_plot_data(lat, lon, data_type, variable_name):
    """Extracts and plots monthly data for a specified variable from September 2024 to January 2025.

    Args:
        lat (float): Latitude of the location.
        lon (float): Longitude of the location.
        data_type (str):  'max_temp' or 'monthly_rain'
        variable_name (str): The name of the variable to extract (e.g., 'max_temp', 'monthly_rain').
    """

    start_year = 2024
    start_month = 9  # September
    end_year = 2025
    end_month = 1  # January

    data = []
    month_labels = []

    current_year = start_year
    current_month = start_month

    while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
        if data_type == 'max_temp':
            file_path = f"/home/roddyb/projects/wheatbelt_rainfall_analyser/data/gridded/max_temp/{current_year}.max_temp.nc"
        elif data_type == 'monthly_rain':
            file_path = f"/home/roddyb/projects/wheatbelt_rainfall_analyser/data/gridded/monthly_rain/{current_year}.monthly_rain.nc"
        else:
            print("Invalid data_type. Choose 'max_temp' or 'monthly_rain'.")
            return

        try:
            dataset = netCDF4.Dataset(file_path, 'r')

            # Find the index of the latitude and longitude
            lat_vals = dataset.variables['lat'][:]
            lon_vals = dataset.variables['lon'][:]
            lat_index = np.argmin(np.abs(lat_vals - lat))
            lon_index = np.argmin(np.abs(lon_vals - lon))

            # Extract the data for the specified month
            month_index = current_month - 1

            # Check if the month_index is valid for the current year's file
            time_var = dataset.variables['time']

            if month_index < 0 or month_index >= len(time_var[:]):
                print(f"Warning: Month {current_month} is out of range for year {current_year}. Skipping.")
                value = np.nan
            else:
                value = dataset.variables[variable_name][month_index, lat_index, lon_index]
                if hasattr(value, 'filled'):
                    value = value.filled(np.nan)

            data.append(value)
            month_labels.append(f'{current_month:02d}-{current_year}')
            dataset.close()

        except Exception as e:
            print(f"Error processing {current_year}-{current_month}: {e}")
            data.append(np.nan)
            month_labels.append(f'{current_month:02d}-{current_year}')

        current_month += 1
        if current_month > 12:
            current_month = 1
            current_year += 1

    # Convert to numpy array for easier handling of NaNs
    data = np.array(data)

    # Plot the data, excluding NaN values
    valid_indices = ~np.isnan(data)
    if np.any(valid_indices):
        plt.plot(np.array(month_labels)[valid_indices], data[valid_indices], marker='o')
        plt.xlabel("Month")
        plt.ylabel(variable_name)
        plt.title(f"Monthly {variable_name} at Lat:{lat}, Lon:{lon}")
        plt.grid(True)
        plt.savefig("plot.png")
    else:
        print("No valid data to plot.")


if __name__ == "__main__":
    latitude = -27.54
    longitude = 151.91
    data_type = 'monthly_rain'  # Choose 'max_temp' or 'monthly_rain'
    variable_name = 'monthly_rain'  #  'max_temp' or 'monthly_rain'
    extract_and_plot_data(latitude, longitude, data_type, variable_name)