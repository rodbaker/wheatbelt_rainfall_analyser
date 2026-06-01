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


def test_latest_complete_year_ignores_non_grid_files(tmp_path):
    # A concurrent download writes *.monthly_rain.nc.tmp temp files; the glob
    # excludes them, and a non-year-prefixed grid must not raise.
    _write_grid(tmp_path / "2024.monthly_rain.nc", 2024, 12, 10)
    (tmp_path / "2025.monthly_rain.nc.tmp").write_bytes(b"partial download")
    _write_grid(tmp_path / "backup.monthly_rain.nc", 2099, 12, 10)
    assert pc.latest_complete_year(tmp_path) == 2024


def test_cell_percentile_formula_and_clamp():
    # One cell. Baseline = [1,2,3,4]; target = 5 (the max).
    # count(<5)=4 -> pct = 100*(4+1)/4 = 125 -> clamp to 100.
    baseline = np.array([1.0, 2.0, 3.0, 4.0]).reshape(4, 1, 1)
    target = np.array([5.0]).reshape(1, 1)
    out = pc.cell_percentile(target, baseline)
    assert out.shape == (1, 1)
    assert out[0, 0] == 100.0


def test_cell_percentile_tie_does_not_lift_rank():
    # Baseline = [10,20,30]; target = 20 (a tie). count(<20)=1 -> 100*(1+1)/3 = 66.67
    baseline = np.array([10.0, 20.0, 30.0]).reshape(3, 1, 1)
    target = np.array([20.0]).reshape(1, 1)
    out = pc.cell_percentile(target, baseline)
    assert abs(out[0, 0] - (100 * 2 / 3)) < 1e-9


def test_cell_percentile_target_nan_is_nan():
    baseline = np.array([1.0, 2.0, 3.0]).reshape(3, 1, 1)
    target = np.array([np.nan]).reshape(1, 1)
    out = pc.cell_percentile(target, baseline)
    assert np.isnan(out[0, 0])


def test_cell_percentile_divides_by_valid_count():
    # Baseline = [5, NaN, 15, 25]; target = 20. valid baseline = [5,15,25] -> n_valid=3.
    # count(<20)=2 -> pct = 100*(2+1)/3 = 100.0
    baseline = np.array([5.0, np.nan, 15.0, 25.0]).reshape(4, 1, 1)
    target = np.array([20.0]).reshape(1, 1)
    out = pc.cell_percentile(target, baseline)
    assert abs(out[0, 0] - 100.0) < 1e-9


def test_cell_percentile_all_baseline_nan_is_nan():
    baseline = np.array([np.nan, np.nan]).reshape(2, 1, 1)
    target = np.array([10.0]).reshape(1, 1)
    out = pc.cell_percentile(target, baseline)
    assert np.isnan(out[0, 0])


def test_cell_percentile_mid_rank_value():
    # Plain non-clamped path: baseline [10,20,30,40]; target 25.
    # count(<25)=2 -> pct = 100*(2+1)/4 = 75.0
    baseline = np.array([10.0, 20.0, 30.0, 40.0]).reshape(4, 1, 1)
    target = np.array([25.0]).reshape(1, 1)
    out = pc.cell_percentile(target, baseline)
    assert abs(out[0, 0] - 75.0) < 1e-9


def test_cell_percentile_multicell_grid_axis_contract():
    # 2x2 grid, distinct per-cell targets, to lock the (year, lat, lon) axis handling.
    # Baseline years stacked on axis 0; each cell baseline = [0,10,20,30].
    baseline = (np.arange(4).reshape(4, 1, 1) * 10.0) * np.ones((4, 2, 2))
    target = np.array([[5.0, 15.0], [25.0, 35.0]])  # ranks differ per cell
    out = pc.cell_percentile(target, baseline)
    assert out.shape == (2, 2)
    # count(<t)/4 *100 with +1: 5->1, 15->2, 25->3, 35->4 valid-below
    expected = np.array([[100 * 2 / 4, 100 * 3 / 4],
                         [100 * 4 / 4, 100 * 5 / 4]])
    expected = np.clip(expected, None, 100.0)
    assert np.allclose(out, expected)
