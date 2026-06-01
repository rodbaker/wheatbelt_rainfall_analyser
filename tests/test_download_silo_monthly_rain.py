"""Tests for the hardened SILO monthly_rain installer (mirror of the daily one).

The download is injected as a `fetch` callable so these run offline against real
tiny NetCDF fixtures (real xarray validation, no mocks).
"""

import numpy as np
import pandas as pd
import xarray as xr

from scripts import download_silo_monthly_rain as dl


def _write_monthly_rain_nc(path, year, n_months=12, value=1.0):
    """Minimal but structurally-real monthly_rain NetCDF fixture."""
    times = pd.date_range(f"{year}-01-01", periods=n_months, freq="MS")
    lat = np.array([-31.0, -30.95])
    lon = np.array([115.0, 115.05])
    data = np.full((n_months, lat.size, lon.size), value, dtype="float64")
    ds = xr.Dataset(
        {"monthly_rain": (("time", "lat", "lon"), data)},
        coords={"time": times, "lat": lat, "lon": lon},
    )
    ds.to_netcdf(path)
    ds.close()


def _good_fetch(year, n_months=12, value=1.0):
    seen = {}

    def fetch(tmp_path):
        seen["tmp"] = tmp_path
        _write_monthly_rain_nc(tmp_path, year, n_months, value=value)

    fetch.seen = seen
    return fetch


def test_temp_file_created_inside_dest_dir(tmp_path):
    fetch = _good_fetch(2000)
    status = dl.install_year(2000, fetch, dest_dir=tmp_path, min_bytes=0)
    assert status == "installed"
    assert fetch.seen["tmp"].parent == tmp_path
    assert (tmp_path / "2000.monthly_rain.nc").exists()


def test_validation_failure_preserves_existing_file(tmp_path):
    year = 2000
    dest = tmp_path / f"{year}.monthly_rain.nc"
    _write_monthly_rain_nc(dest, year, 12, value=7.0)
    original = dest.read_bytes()

    def bad_fetch(tmp_):  # only 5 months -> incomplete year
        _write_monthly_rain_nc(tmp_, year, 5, value=99.0)

    status = dl.install_year(year, bad_fetch, dest_dir=tmp_path,
                             allow_replace=True, min_bytes=0)
    assert status.startswith("invalid")
    assert dest.read_bytes() == original
    assert not (tmp_path / f"{year}.monthly_rain.nc.tmp").exists()


def test_successful_replace_installs_new_file(tmp_path):
    year = 2000
    dest = tmp_path / f"{year}.monthly_rain.nc"
    _write_monthly_rain_nc(dest, year, 12, value=7.0)
    fetch = _good_fetch(year, 12, value=42.0)
    status = dl.install_year(year, fetch, dest_dir=tmp_path,
                             allow_replace=True, min_bytes=0)
    assert status == "installed"
    with xr.open_dataset(dest) as ds:
        assert float(ds["monthly_rain"].isel(time=0, lat=0, lon=0).values) == 42.0


def test_temp_cleaned_up_on_fetch_error(tmp_path):
    year = 2000
    dest = tmp_path / f"{year}.monthly_rain.nc"
    _write_monthly_rain_nc(dest, year, 12, value=7.0)
    original = dest.read_bytes()

    def exploding_fetch(tmp_):
        tmp_.write_bytes(b"partial")
        raise RuntimeError("connection reset")

    status = dl.install_year(year, exploding_fetch, dest_dir=tmp_path,
                             allow_replace=True)
    assert status.startswith("error")
    assert not (tmp_path / f"{year}.monthly_rain.nc.tmp").exists()
    assert dest.read_bytes() == original


def test_skip_when_existing_file_is_valid(tmp_path):
    """validate-before-skip: an existing VALID file is skipped, fetch not called."""
    year = 2000
    _write_monthly_rain_nc(tmp_path / f"{year}.monthly_rain.nc", year, 12, value=7.0)
    called = {"fetch": False}

    def fetch(tmp_):
        called["fetch"] = True

    status = dl.install_year(year, fetch, dest_dir=tmp_path, allow_replace=False)
    assert status == "skipped"
    assert called["fetch"] is False


def test_existing_invalid_file_not_silently_accepted(tmp_path):
    """validate-before-skip: an existing INVALID file fails without --replace."""
    year = 2000
    # 6-month (truncated) existing file == invalid for a completed year
    _write_monthly_rain_nc(tmp_path / f"{year}.monthly_rain.nc", year, 6, value=7.0)
    called = {"fetch": False}

    def fetch(tmp_):
        called["fetch"] = True

    status = dl.install_year(year, fetch, dest_dir=tmp_path, allow_replace=False)
    assert status.startswith("invalid")
    assert called["fetch"] is False


def test_partial_year_allowed_when_not_require_complete(tmp_path):
    """Current-year partial files validate when require_complete=False."""
    year = 2026
    fetch = _good_fetch(year, 4)  # Jan-Apr only

    status = dl.install_year(
        year, fetch, dest_dir=tmp_path, require_complete=False, min_bytes=0
    )

    assert status == "installed"


def test_wrong_year_rejected_even_when_not_require_complete(tmp_path):
    """The year-coordinate check still fires when completeness is relaxed."""
    year = 2026
    # 4 months of data but timestamps belong to 2025, not the requested 2026.
    def wrong_year_fetch(tmp_):
        _write_monthly_rain_nc(tmp_, 2025, 4, value=1.0)

    status = dl.install_year(
        year, wrong_year_fetch, dest_dir=tmp_path,
        require_complete=False, min_bytes=0,
    )

    assert status.startswith("invalid")
    assert not (tmp_path / f"{year}.monthly_rain.nc").exists()
