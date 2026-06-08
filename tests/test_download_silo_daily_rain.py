"""Tests for the hardened SILO daily_rain installer.

Scope (narrow, per migration follow-up): the place -> validate -> atomic-replace
logic that protects data/meta/daily_rain/ now that it lives on the HDD via a
symlink. The download itself is injected as a `fetch` callable so these tests
run offline against real tiny NetCDF fixtures (real xarray validation, no mocks).

Behaviors covered:
  1. Temp file is created INSIDE the destination directory (so os.replace is an
     intra-filesystem atomic rename, valid on /mnt/d).
  2. Validation failure PRESERVES the existing final file and removes the temp.
  3. Successful download atomically REPLACES the existing file.
  4. Temp file is cleaned up on failure (validation failure and fetch error).
"""

import numpy as np
import pandas as pd
import xarray as xr
import pytest

from scripts import download_silo_daily_rain as dl


def _write_daily_rain_nc(path, year, n_days, value=1.0):
    """Write a minimal but structurally-real daily_rain NetCDF fixture."""
    times = pd.date_range(f"{year}-01-01", periods=n_days, freq="D")
    lat = np.array([-31.0, -30.95])
    lon = np.array([115.0, 115.05])
    data = np.full((n_days, lat.size, lon.size), value, dtype="float64")
    ds = xr.Dataset(
        {"daily_rain": (("time", "lat", "lon"), data)},
        coords={"time": times, "lat": lat, "lon": lon},
    )
    ds.to_netcdf(path)
    ds.close()


def _good_fetch(year, n_days, value=1.0):
    """Return a fetch(tmp_path) that writes a valid fixture and records the path."""
    seen = {}

    def fetch(tmp_path):
        seen["tmp"] = tmp_path
        _write_daily_rain_nc(tmp_path, year, n_days, value=value)

    fetch.seen = seen
    return fetch


def test_temp_file_created_inside_dest_dir(tmp_path):
    """Temp must live in the destination dir so the rename stays intra-filesystem."""
    year = 2025  # non-leap -> 365 days = complete
    fetch = _good_fetch(year, 365)

    status = dl.install_year(
        year, fetch, dest_dir=tmp_path, require_complete=True, min_bytes=0
    )

    assert status == "installed"
    assert fetch.seen["tmp"].parent == tmp_path, "temp file not placed inside dest_dir"
    assert (tmp_path / f"{year}.daily_rain.nc").exists()


def test_validation_failure_preserves_existing_file(tmp_path):
    """A bad new download must NOT clobber a good existing file."""
    year = 2025
    dest = tmp_path / f"{year}.daily_rain.nc"
    # Pre-existing GOOD file with a known marker value.
    _write_daily_rain_nc(dest, year, 365, value=7.0)
    original_bytes = dest.read_bytes()

    # New download is structurally broken (truncated to 10 days -> incomplete year).
    def bad_fetch(tmp_path_):
        _write_daily_rain_nc(tmp_path_, year, 10, value=99.0)

    status = dl.install_year(
        year, bad_fetch, dest_dir=tmp_path, allow_replace=True, require_complete=True
    )

    assert status.startswith("invalid"), f"expected invalid, got {status!r}"
    assert dest.read_bytes() == original_bytes, "existing file was modified on failure"
    assert not (tmp_path / f"{year}.daily_rain.nc.tmp").exists(), "temp not cleaned up"


def test_successful_replace_installs_new_file(tmp_path):
    """With allow_replace, a valid new download atomically replaces the old file."""
    year = 2025
    dest = tmp_path / f"{year}.daily_rain.nc"
    _write_daily_rain_nc(dest, year, 365, value=7.0)

    fetch = _good_fetch(year, 365, value=42.0)
    status = dl.install_year(
        year, fetch, dest_dir=tmp_path, allow_replace=True,
        require_complete=True, min_bytes=0,
    )

    assert status == "installed"
    assert not (tmp_path / f"{year}.daily_rain.nc.tmp").exists(), "temp not cleaned up"
    with xr.open_dataset(dest) as ds:
        assert float(ds["daily_rain"].isel(time=0, lat=0, lon=0).values) == 42.0


def test_temp_cleaned_up_on_fetch_error(tmp_path):
    """If the download itself raises, no temp file is left behind and dest is intact."""
    year = 2025
    dest = tmp_path / f"{year}.daily_rain.nc"
    _write_daily_rain_nc(dest, year, 365, value=7.0)
    original_bytes = dest.read_bytes()

    def exploding_fetch(tmp_path_):
        # Simulate a partial write then a network failure.
        tmp_path_.write_bytes(b"partial")
        raise RuntimeError("connection reset")

    status = dl.install_year(
        year, exploding_fetch, dest_dir=tmp_path, allow_replace=True
    )

    assert status.startswith("error"), f"expected error, got {status!r}"
    assert not (tmp_path / f"{year}.daily_rain.nc.tmp").exists(), "temp not cleaned up"
    assert dest.read_bytes() == original_bytes, "existing file was modified on fetch error"


def test_skip_when_exists_and_replace_not_allowed(tmp_path):
    """Default (allow_replace=False): existing file is left untouched and fetch is not called."""
    year = 2025
    dest = tmp_path / f"{year}.daily_rain.nc"
    _write_daily_rain_nc(dest, year, 365, value=7.0)
    called = {"fetch": False}

    def fetch(tmp_path_):
        called["fetch"] = True

    status = dl.install_year(year, fetch, dest_dir=tmp_path, allow_replace=False)

    assert status == "skipped"
    assert called["fetch"] is False, "fetch should not run when file exists and replace disallowed"


def test_partial_year_allowed_when_not_require_complete(tmp_path):
    """Current-year partial files validate when require_complete=False."""
    year = 2026
    fetch = _good_fetch(year, 120)  # ~4 months of data

    status = dl.install_year(
        year, fetch, dest_dir=tmp_path, require_complete=False, min_bytes=0
    )

    assert status == "installed"
