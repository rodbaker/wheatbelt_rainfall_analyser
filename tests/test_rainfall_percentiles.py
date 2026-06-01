"""Tests for the rainfall percentile engine (pure functions, toy grids)."""

import numpy as np
import pandas as pd
import xarray as xr

from src.rainfall import percentiles as pc


def _write_grid(path, year, n_months, value):
    # NOTE: start on the 1st — "MS" (month-start) snaps forward, so a -01-15 start
    # would push the 12th month into year+1 and trip the in-year validation.
    times = pd.date_range(f"{year}-01-01", periods=n_months, freq="MS")
    lat = np.array([-31.0, -30.95])
    lon = np.array([115.0, 115.05])
    data = np.full((n_months, lat.size, lon.size), float(value))
    xr.Dataset(
        {"monthly_rain": (("time", "lat", "lon"), data)},
        coords={"time": times, "lat": lat, "lon": lon},
    ).to_netcdf(path)


def test_latest_complete_year_excludes_partial(tmp_path):
    _write_grid(tmp_path / "2023.monthly_rain.nc", 2023, 12, 10)
    _write_grid(tmp_path / "2024.monthly_rain.nc", 2024, 12, 10)
    _write_grid(tmp_path / "2025.monthly_rain.nc", 2025, 4, 10)  # partial
    assert pc.latest_complete_year(tmp_path) == 2024
