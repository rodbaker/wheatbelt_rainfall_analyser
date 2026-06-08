"""
Wheatbelt Stations Loader - BOM station management for SILO Wrangler

Loads and filters the comprehensive BOM wheatbelt stations dataset for
geographic and operational station selection.
"""

import numpy as np
import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StationInfo:
    """
    BOM Station metadata from wheatbelt dataset
    """
    station_id: str
    name: str
    latitude: float
    longitude: float
    sa2_code: str
    sa2_name: str
    sa3_name: str
    sa4_name: str
    state_code: int
    state_name: str
    cropping_area: int


class WheatbeltStationsLoader:
    """
    Loads and manages BOM wheatbelt stations dataset
    
    Provides filtering by state, region, cropping area, and geographic bounds
    for flexible station selection in SILO Wrangler operations.
    """
    
    def __init__(self, stations_file: str = "data/meta/wheatbelt_stations.csv"):
        """
        Initialize stations loader
        
        Args:
            stations_file: Path to wheatbelt stations CSV file
        """
        self.stations_file = Path(stations_file)
        self._stations_df = None
        self._load_stations()
    
    def _load_stations(self):
        """Load stations dataset from CSV, joining SA3/SA4 from station_regions.csv if available."""
        try:
            if not self.stations_file.exists():
                raise FileNotFoundError(f"Stations file not found: {self.stations_file}")

            self._stations_df = pd.read_csv(self.stations_file)

            # Standardize column names
            expected_columns = {
                'Station number': 'station_id',
                'Lat': 'latitude',
                'Lon': 'longitude',
                'Station name': 'name',
                'SA2_5DIG16': 'sa2_code',
                'SA2_NAME16': 'sa2_name',
                'STE_CODE16': 'state_code',
                'STE_NAME16': 'state_name',
                '2010_11_area': 'cropping_area'
            }

            self._stations_df = self._stations_df.rename(columns=expected_columns)

            # Convert station_id to string and ensure consistent formatting
            self._stations_df['station_id'] = self._stations_df['station_id'].astype(str).str.zfill(6)

            # Join SA3/SA4 from station_regions.csv if available
            regions_file = self.stations_file.parent / "station_regions.csv"
            if regions_file.exists():
                regions_df = pd.read_csv(regions_file, dtype=str).fillna('')
                regions_df['station_id'] = regions_df['station_id'].str.zfill(6)
                self._stations_df = self._stations_df.merge(
                    regions_df[['station_id', 'sa3_name', 'sa4_name']],
                    on='station_id',
                    how='left'
                )
                self._stations_df[['sa3_name', 'sa4_name']] = (
                    self._stations_df[['sa3_name', 'sa4_name']].fillna('')
                )
            else:
                self._stations_df['sa3_name'] = ''
                self._stations_df['sa4_name'] = ''

            logger.info(f"Loaded {len(self._stations_df)} wheatbelt stations from {self.stations_file}")

        except Exception as e:
            logger.error(f"Failed to load stations dataset: {e}")
            raise
    
    def get_stations_by_state(self, states: List[str]) -> Dict[str, str]:
        """
        Get stations filtered by state names
        
        Args:
            states: List of state names (e.g., ['Western Australia', 'South Australia'])
            
        Returns:
            Dict mapping station_id to station_name
        """
        if self._stations_df is None:
            return {}
        
        filtered = self._stations_df[self._stations_df['state_name'].isin(states)]
        return dict(zip(filtered['station_id'], filtered['name']))
    
    def get_stations_by_region(self, sa2_names: List[str]) -> Dict[str, str]:
        """
        Get stations filtered by SA2 region names
        
        Args:
            sa2_names: List of SA2 region names
            
        Returns:
            Dict mapping station_id to station_name
        """
        if self._stations_df is None:
            return {}
        
        filtered = self._stations_df[self._stations_df['sa2_name'].isin(sa2_names)]
        return dict(zip(filtered['station_id'], filtered['name']))
    
    def get_stations_by_area_threshold(self, min_cropping_area: int) -> Dict[str, str]:
        """
        Get stations filtered by minimum cropping area
        
        Args:
            min_cropping_area: Minimum cropping area (hectares)
            
        Returns:
            Dict mapping station_id to station_name
        """
        if self._stations_df is None:
            return {}
        
        filtered = self._stations_df[self._stations_df['cropping_area'] >= min_cropping_area]
        return dict(zip(filtered['station_id'], filtered['name']))
    
    def get_stations_by_bounds(self, 
                              lat_min: float, lat_max: float,
                              lon_min: float, lon_max: float) -> Dict[str, str]:
        """
        Get stations within geographic bounding box
        
        Args:
            lat_min, lat_max: Latitude range
            lon_min, lon_max: Longitude range
            
        Returns:
            Dict mapping station_id to station_name
        """
        if self._stations_df is None:
            return {}
        
        filtered = self._stations_df[
            (self._stations_df['latitude'] >= lat_min) &
            (self._stations_df['latitude'] <= lat_max) &
            (self._stations_df['longitude'] >= lon_min) &
            (self._stations_df['longitude'] <= lon_max)
        ]
        return dict(zip(filtered['station_id'], filtered['name']))
    
    def get_random_sample(self, n: int, seed: Optional[int] = None) -> Dict[str, str]:
        """
        Get random sample of stations for testing
        
        Args:
            n: Number of stations to sample
            seed: Random seed for reproducibility
            
        Returns:
            Dict mapping station_id to station_name
        """
        if self._stations_df is None:
            return {}
        
        if seed is not None:
            sample = self._stations_df.sample(n=min(n, len(self._stations_df)), random_state=seed)
        else:
            sample = self._stations_df.sample(n=min(n, len(self._stations_df)))
        
        return dict(zip(sample['station_id'], sample['name']))
    
    def get_station_info(self, station_id: str) -> Optional[StationInfo]:
        """
        Get detailed information for a specific station
        
        Args:
            station_id: BOM station ID
            
        Returns:
            StationInfo object or None if not found
        """
        if self._stations_df is None:
            return None
        
        # Ensure consistent formatting
        station_id = str(station_id).zfill(6)
        
        row = self._stations_df[self._stations_df['station_id'] == station_id]
        if row.empty:
            return None
        
        row = row.iloc[0]
        return StationInfo(
            station_id=row['station_id'],
            name=row['name'],
            latitude=row['latitude'],
            longitude=row['longitude'],
            sa2_code=row['sa2_code'],
            sa2_name=row['sa2_name'],
            sa3_name=row.get('sa3_name', ''),
            sa4_name=row.get('sa4_name', ''),
            state_code=row['state_code'],
            state_name=row['state_name'],
            cropping_area=row['cropping_area']
        )

    def get_region_lookup(self) -> pd.DataFrame:
        """
        Return a DataFrame mapping station_id to SA2/SA3/SA4 region names.

        Returns:
            DataFrame with columns: station_id, sa2_name, sa3_name, sa4_name
        """
        if self._stations_df is None:
            return pd.DataFrame(columns=['station_id', 'sa2_name', 'sa3_name', 'sa4_name'])

        cols = ['station_id', 'sa2_name']
        if 'sa3_name' in self._stations_df.columns:
            cols.append('sa3_name')
        if 'sa4_name' in self._stations_df.columns:
            cols.append('sa4_name')

        return self._stations_df[cols].copy()
    
    def get_nearest_sa2(self, lat: float, lon: float) -> Dict[str, str]:
        """
        Find the nearest station's SA2/SA3/SA4 region names by geographic proximity.

        Used to assign approximate region labels to Data Drill grid points (which have
        no station_id) so they can appear in reports alongside PPD station events.

        Args:
            lat: Latitude of query point
            lon: Longitude of query point

        Returns:
            Dict with sa2_name, sa3_name, sa4_name of nearest station
        """
        empty = {'sa2_name': '', 'sa3_name': '', 'sa4_name': ''}
        if self._stations_df is None or self._stations_df.empty:
            return empty

        dists = np.sqrt(
            (self._stations_df['latitude'] - lat) ** 2 +
            (self._stations_df['longitude'] - lon) ** 2
        )
        nearest = self._stations_df.loc[dists.idxmin()]
        return {
            'sa2_name': nearest.get('sa2_name', ''),
            'sa3_name': nearest.get('sa3_name', ''),
            'sa4_name': nearest.get('sa4_name', ''),
        }

    def get_all_station_coords(self) -> List[Tuple[float, float]]:
        """Return list of (lat, lon) for every station in the dataset."""
        if self._stations_df is None or self._stations_df.empty:
            return []
        return list(zip(self._stations_df['latitude'], self._stations_df['longitude']))

    def get_summary_stats(self) -> Dict[str, any]:
        """
        Get summary statistics of the stations dataset
        
        Returns:
            Dictionary with dataset statistics
        """
        if self._stations_df is None:
            return {}
        
        stats = {
            'total_stations': len(self._stations_df),
            'states': self._stations_df['state_name'].value_counts().to_dict(),
            'cropping_area_stats': {
                'min': self._stations_df['cropping_area'].min(),
                'max': self._stations_df['cropping_area'].max(),
                'mean': self._stations_df['cropping_area'].mean(),
                'median': self._stations_df['cropping_area'].median()
            },
            'geographic_bounds': {
                'lat_min': self._stations_df['latitude'].min(),
                'lat_max': self._stations_df['latitude'].max(),
                'lon_min': self._stations_df['longitude'].min(),
                'lon_max': self._stations_df['longitude'].max()
            }
        }
        
        return stats


def load_wheatbelt_stations_for_config(filter_params: Dict[str, any]) -> Dict[str, str]:
    """
    Convenience function to load stations based on configuration parameters
    
    Args:
        filter_params: Dictionary with filter criteria:
            - states: List of state names
            - regions: List of SA2 region names  
            - min_cropping_area: Minimum cropping area
            - bounds: Geographic bounds dict with lat_min, lat_max, lon_min, lon_max
            - sample_size: Random sample size for testing
            - sample_seed: Random seed for reproducible sampling
    
    Returns:
        Dict mapping station_id to station_name
    """
    loader = WheatbeltStationsLoader()
    
    # Start with all stations
    stations = dict(zip(loader._stations_df['station_id'], loader._stations_df['name']))
    
    # Apply filters
    if 'states' in filter_params:
        stations = loader.get_stations_by_state(filter_params['states'])
    
    if 'regions' in filter_params:
        region_stations = loader.get_stations_by_region(filter_params['regions'])
        stations = {k: v for k, v in stations.items() if k in region_stations}
    
    if 'min_cropping_area' in filter_params:
        area_stations = loader.get_stations_by_area_threshold(filter_params['min_cropping_area'])
        stations = {k: v for k, v in stations.items() if k in area_stations}
    
    if 'bounds' in filter_params:
        bounds = filter_params['bounds']
        bounds_stations = loader.get_stations_by_bounds(
            bounds['lat_min'], bounds['lat_max'],
            bounds['lon_min'], bounds['lon_max']
        )
        stations = {k: v for k, v in stations.items() if k in bounds_stations}
    
    # Apply sampling if requested
    if 'sample_size' in filter_params:
        # Convert back to DataFrame for sampling
        df = pd.DataFrame(list(stations.items()), columns=['station_id', 'name'])
        sample_seed = filter_params.get('sample_seed')
        
        if sample_seed is not None:
            sample = df.sample(n=min(filter_params['sample_size'], len(df)), random_state=sample_seed)
        else:
            sample = df.sample(n=min(filter_params['sample_size'], len(df)))
        
        stations = dict(zip(sample['station_id'], sample['name']))
    
    logger.info(f"Filtered to {len(stations)} stations based on criteria: {list(filter_params.keys())}")
    return stations


def generate_data_drill_grid(
    bounds_list: List[Dict],
    resolution: float,
    existing_coords: List[Tuple[float, float]],
    proximity_threshold: float,
    geojson_path: Optional[str] = None,
) -> List[Tuple[float, float]]:
    """
    Generate a regular lat/lon grid for Data Drill gap-filling.

    For each bounding box in bounds_list, creates grid points at the given
    resolution. Two filters are applied in order:

    1. Polygon filter (if geojson_path provided): keeps only points that fall
       inside one of the SA2 wheatbelt polygons. Rectangular bounds act as a
       fast coarse pre-filter; the GeoJSON provides exact agricultural boundaries.

    2. Proximity filter: drops points within proximity_threshold (degrees) of
       any coordinate in existing_coords — those locations are already covered
       by a PPD station.

    Args:
        bounds_list: List of dicts with lat_min, lat_max, lon_min, lon_max
        resolution: Grid spacing in degrees (e.g. 0.5 ≈ 55km)
        existing_coords: (lat, lon) pairs of PPD stations already in the run
        proximity_threshold: Minimum distance from any existing coord (degrees)
        geojson_path: Optional path to a GeoJSON FeatureCollection of wheatbelt
            SA2 polygons. When supplied, only points inside the union of those
            polygons are retained.

    Returns:
        List of (lat, lon) gap-fill grid points, rounded to 4 decimal places
    """
    # Build grid across all bounding boxes (coarse rectangular pre-filter)
    candidate_points: List[Tuple[float, float]] = []
    for bounds in bounds_list:
        lats = np.arange(bounds['lat_min'], bounds['lat_max'] + resolution / 2, resolution)
        lons = np.arange(bounds['lon_min'], bounds['lon_max'] + resolution / 2, resolution)
        for lat in lats:
            for lon in lons:
                candidate_points.append((round(float(lat), 4), round(float(lon), 4)))

    # --- Polygon filter: keep only points inside wheatbelt SA2 boundaries ---
    if geojson_path and candidate_points:
        geojson_file = Path(geojson_path)
        if geojson_file.exists():
            try:
                from shapely.geometry import shape, Point
                from shapely.ops import unary_union
                import json

                with open(geojson_file) as f:
                    gj = json.load(f)

                polys = [shape(feat['geometry']) for feat in gj.get('features', [])
                         if feat.get('geometry')]
                if polys:
                    wheatbelt_union = unary_union(polys)
                    before = len(candidate_points)
                    # Point(lon, lat) — shapely uses (x=lon, y=lat)
                    candidate_points = [
                        (la, lo) for la, lo in candidate_points
                        if wheatbelt_union.contains(Point(lo, la))
                    ]
                    logger.info(
                        f"Data Drill polygon filter: {before} → {len(candidate_points)} points "
                        f"({before - len(candidate_points)} outside wheatbelt SA2s)"
                    )
            except Exception as e:
                logger.warning(f"GeoJSON polygon filter failed, using rectangular bounds only: {e}")
        else:
            logger.warning(f"GeoJSON not found at {geojson_path}, using rectangular bounds only")

    if not existing_coords or not candidate_points:
        return candidate_points

    # --- Proximity filter: suppress points near existing PPD stations ---
    station_arr = np.array(existing_coords)  # shape (N, 2)
    gap_points = []
    for lat, lon in candidate_points:
        dists = np.sqrt((station_arr[:, 0] - lat) ** 2 + (station_arr[:, 1] - lon) ** 2)
        if dists.min() > proximity_threshold:
            gap_points.append((lat, lon))

    logger.info(
        f"Data Drill grid: {len(candidate_points)} candidates → "
        f"{len(gap_points)} gap points after proximity filtering "
        f"({len(candidate_points) - len(gap_points)} suppressed by PPD stations)"
    )
    return gap_points