#!/usr/bin/env python3
"""
Build station → region lookup CSV.

Joins wheatbelt_stations.csv with SA2_ABS_Regions.geojson on SA2_5DIG16
to extract SA3/SA4 hierarchy for each station.

Output: data/meta/station_regions.csv
  station_id, sa2_name, sa3_name, sa4_name

Run once (or after stations/GeoJSON changes):
  python scripts/build_station_regions.py
"""

import sys
from pathlib import Path
import pandas as pd
import geopandas as gpd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

STATIONS_PATH = project_root / "data" / "meta" / "wheatbelt_stations.csv"
GEOJSON_PATH = project_root / "data" / "meta" / "SA2_ABS_Regions.geojson"
OUTPUT_PATH = project_root / "data" / "meta" / "station_regions.csv"


def build_region_lookup():
    # Load stations
    stations = pd.read_csv(STATIONS_PATH)
    stations = stations.rename(columns={'Station number': 'station_id'})
    stations['station_id'] = stations['station_id'].astype(str).str.zfill(6)
    stations['SA2_5DIG16'] = stations['SA2_5DIG16'].astype(str).str.strip()

    # Load GeoJSON attribute table only (drop geometry to avoid PROJ issues)
    gdf = gpd.read_file(GEOJSON_PATH)
    regions = pd.DataFrame(gdf.drop(columns='geometry'))
    regions['SA2_5DIG16'] = regions['SA2_5DIG16'].astype(str).str.strip()

    # Merge on SA2_5DIG16 — only pull SA3/SA4 from GeoJSON; SA2_NAME16 is already in stations
    merged = stations.merge(
        regions[['SA2_5DIG16', 'SA3_NAME16', 'SA4_NAME16']],
        on='SA2_5DIG16',
        how='left'
    )

    # Build output lookup
    lookup = merged[['station_id', 'SA2_NAME16', 'SA3_NAME16', 'SA4_NAME16']].copy()
    lookup = lookup.rename(columns={
        'SA2_NAME16': 'sa2_name',
        'SA3_NAME16': 'sa3_name',
        'SA4_NAME16': 'sa4_name'
    })

    # Fill missing with empty string
    lookup = lookup.fillna('')

    matched = (lookup['sa3_name'] != '').sum()
    total = len(lookup)
    print(f"Matched {matched}/{total} stations to SA2/SA3/SA4 regions")

    unmatched = lookup[lookup['sa3_name'] == '']
    if not unmatched.empty:
        print(f"Unmatched ({len(unmatched)} stations): {unmatched['station_id'].tolist()[:10]}")

    lookup.to_csv(OUTPUT_PATH, index=False)
    print(f"Written: {OUTPUT_PATH}")


if __name__ == '__main__':
    build_region_lookup()
