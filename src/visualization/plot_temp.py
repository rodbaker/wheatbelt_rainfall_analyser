import netCDF4
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

def extract_and_plot_temp_data(lat, lon):
    """Extracts and plots monthly maximum temperature data for September 2024 to January 2025.

    Args:
        lat (float): Latitude of the location.
        lon (float): Longitude of the location.
    """

    start_year = 2024
    start_month = 9  # September
    end_year = 2025
    end_month = 1  # January

    temp_data = []
    month_labels = []

    current_year = start_year
    current_month = start_month

    while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
        file_path = f"/home/roddyb/projects/wheatbelt_rainfall_analyser/data/gridded/max_temp/{current_year}.max_temp.nc"
        try:
            dataset = netCDF4.Dataset(file_path, 'r')

            # Print latitude and longitude ranges
            lat_range = [dataset.variables['lat'][:].min(), dataset.variables['lat'][:].max()]
            lon_range = [dataset.variables['lon'][:].min(), dataset.variables['lon'][:].max()]


            # Extract the temperature data for the specified month
            # Ensure month_index is within valid range (0-11)
            month_index = current_month - 1

            # Check if the month_index is valid for the current year's file
            time_var = dataset.variables['time']
            if month_index < 0 or month_index >= len(time_var[:]):
                print(f"Warning: Month {current_month} is out of range for year {current_year}. Skipping.")
                temp = np.nan  # Assign NaN if the month is out of range
            else:
                temp = dataset.variables['max_temp'][month_index, lat_index, lon_index]
                # Unmask the data and fill with NaN if masked
                if hasattr(temp, 'filled'):
                    temp = temp.filled(np.nan)

            temp_data.append(temp)
            month_labels.append(f'{current_month:02d}-{current_year}')
            dataset.close()

        except Exception as e:
            print(f"Error processing {current_year}-{current_month}: {e}")
            temp_data.append(np.nan)  # Append NaN in case of error
            month_labels.append(f'{current_month:02d}-{current_year}')

        current_month += 1
        if current_month > 12:
            current_month = 1
            current_year += 1

    # Convert to numpy array for easier handling of NaNs
    temp_data = np.array(temp_data)

    # Print the extracted temperature data


    # Plot the data, excluding NaN values
    valid_indices = ~np.isnan(temp_data)
    if np.any(valid_indices):
        plt.plot(np.array(month_labels)[valid_indices], temp_data[valid_indices], marker='o')
        plt.xlabel("Month")
        plt.ylabel("Maximum Temperature (°C)")
        plt.title(f"Monthly Maximum Temperature at Lat:{lat}, Lon:{lon}")
        plt.grid(True)
        plt.savefig("temp_plot.png")
    else:
        print("No valid temperature data to plot.")


if __name__ == "__main__":
    latitude = -27.54
    longitude = 151.91
    extract_and_plot_temp_data(latitude, longitude)