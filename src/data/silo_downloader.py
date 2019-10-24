#  import packages
import pandas as pd
import numpy as np
import requests
import csv
import json
from pandas.io.json import json_normalize
import re
import time
import os
from dotenv import load_dotenv, find_dotenv

# find .env automagically by walking up directories until it's found
dotenv_path = find_dotenv()

# load up the entries as environment variables
load_dotenv(dotenv_path)

silo_username = os.environ.get("SILO_USERNAME")
silo_password = os.environ.get("SILO_PASSWORD")
silo_email = os.environ.get("SILO_EMAIL")

def random_wait():
    """fn: randomly choose a wait time based on
    probability"""
    wait_times = [0.2, 0.5, 1, 2]
    probs = [0.3, 0.4, 0.2, 0.1]
    choice = np.random.choice(wait_times, size = 1, p = probs)
    return choice

def url_list(station_list, start_date, finish_date):
    """fn: create list of URL's with different 
    station numbers and corresponding start date"""
    url_list = []
    for stat in station_list:
        url = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php?start={0}&finish={1}&station={2}&format=Monthly&username={3}".format(start_date, finish_date,stat, silo_email)
        url_list.append(url)
    return url_list


def download_weather_data(station_list, start_date, finish_date):
    """fn: downloads weather data from SILO api"""
    colnames = ['date', 'max_temp', 'min_temp', 'rain', 'evap', 'radiation', 'vp']
    df_list = []
    for url in url_list(station_list, start_date, finish_date):
        df_stat = pd.read_csv(url, skiprows = 26,sep = r'\s+', header = None, names = colnames)
        df_stat['station'] = int(re.findall("station=(\\d+)",url)[0]) #regex finds station number
        df_list.append(df_stat)
        time.sleep(random_wait())
    return df_list

def create_df(station_list, start_date, finish_date):
    """fn: Creates a pandas dataframe from the weather data downloaded from SILO Api"""
    # concatenate list of dfs into one
    df_concat = pd.concat(download_weather_data(station_list, start_date, finish_date))
    # make string version of original column
    df_concat['date'] = df_concat['date'].astype(str)
    # make the new columns using string indexing
    df_concat['year'] = df_concat['date'].str[0:4].astype('int64')
    df_concat['month'] = df_concat['date'].str[4:6].astype('int64')
    # get rid of the extra variable (if you want)
    df_concat.drop('date', axis=1, inplace=True)
    return df_concat


