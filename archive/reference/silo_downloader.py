import pandas as pd
import numpy as np
import requests
import time
import os
import re
import io
from dotenv import load_dotenv, find_dotenv

# Load environment variables
dotenv_path = find_dotenv()
load_dotenv(dotenv_path)

silo_username = os.getenv("SILO_USERNAME")
silo_password = os.getenv("SILO_PASSWORD")
silo_email = os.getenv("SILO_EMAIL")

def random_wait():
    """Returns a random wait time based on predefined probabilities."""
    wait_times = [0.2, 0.5, 1, 2]
    probs = [0.3, 0.4, 0.2, 0.1]
    return np.random.choice(wait_times, p=probs)

def url_list(station_list, start_date, finish_date):
    """Creates a list of SILO API URLs for downloading weather data."""
    return [
        f"https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php?"
        f"start={start_date}&finish={finish_date}&station={stat}&format=Monthly&username={silo_email}"
        for stat in station_list
    ]

def fetch_data(url):
    """Fetches weather data from the SILO API, handling errors and retries."""
    try:
        response = requests.get(url, timeout=10)  # ✅ Set timeout to prevent long hangs
        response.raise_for_status()  # ✅ Raise an error for bad responses (e.g., 404, 500)
        
        colnames = ['date', 'max_temp', 'min_temp', 'rain', 'evap', 'radiation', 'vp']
        df = pd.read_csv(io.StringIO(response.text), skiprows=26, sep=r'\s+', header=None, names=colnames)
        
        match = re.search(r"station=(\d+)", url)
        df['station'] = int(match.group(1)) if match else None

        return df
    except requests.RequestException as e:
        print(f"⚠ HTTP error fetching {url}: {e}")
    except Exception as e:
        print(f"⚠ Error processing data from {url}: {e}")
    
    return None

def download_weather_data(station_list, start_date, finish_date):
    """Downloads weather data for a list of stations and returns a DataFrame list."""
    df_list = []
    urls = url_list(station_list, start_date, finish_date)

    for url in urls:
        df = fetch_data(url)
        if df is not None:
            df_list.append(df)

        # Apply random wait to avoid hitting API rate limits
        time.sleep(random_wait())

    return df_list

def create_df(station_list, start_date, finish_date):
    """Creates a pandas DataFrame from downloaded weather data."""
    df_list = download_weather_data(station_list, start_date, finish_date)

    if not df_list:  
        print("⚠ Warning: No data downloaded. Returning an empty DataFrame.")
        return pd.DataFrame()

    df_concat = pd.concat(df_list, ignore_index=True)
    df_concat['date'] = df_concat['date'].astype(str)
    df_concat['year'] = df_concat['date'].str[:4].astype(int)
    df_concat['month'] = df_concat['date'].str[4:6].astype(int)
    df_concat.drop(columns=['date'], inplace=True)

    return df_concat