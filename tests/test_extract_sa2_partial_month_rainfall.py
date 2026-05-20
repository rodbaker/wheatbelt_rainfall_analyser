"""Tests for extract_sa2_partial_month_rainfall using synthetic daily NetCDFs."""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

import scripts.extract_sa2_partial_month_rainfall as mod


def _make_daily_ds(times, lats, lons, values):
    """Build a tiny synthetic daily_rain Dataset."""
    data = np.array(values, dtype=float).reshape(len(times), len(lats), len(lons))
    return xr.Dataset(
        {"daily_rain": (["time", "lat", "lon"], data)},
        coords={
            "time": [pd.Timestamp(t) for t in times],
            "lat": lats,
            "lon": lons,
        },
    )


class TestExtractPartialMonth:
    def test_sums_only_days_up_to_through_day(self, tmp_path):
        # 5 days of May 2026; values 1..5 mm at single grid cell.
        times = [f"2026-05-{d:02d}" for d in range(1, 6)]
        ds = _make_daily_ds(times, [-30.0], [116.0], [[[v]] for v in [1.0, 2.0, 3.0, 4.0, 5.0]])
        nc_path = tmp_path / "2026.daily_rain.nc"
        ds.to_netcdf(nc_path)

        sa2_rows = [
            {"sa2_code": "501000001", "sa2_name": "Test", "state_name": "WA",
             "lat": -30.0, "lon": 116.0, "universe_source": "test"},
        ]
        df, through_day = mod.extract_partial_month(nc_path, 2026, 5, sa2_rows)

        assert through_day == 5
        assert len(df) == 1
        row = df.iloc[0]
        assert row["rainfall_mm"] == pytest.approx(15.0, abs=0.01)
        assert bool(row["is_partial_month"]) is True
        assert row["partial_month_through_day"] == 5
        assert row["extraction_method"] == "centroid_nearest_grid_cell_daily_sum"
        assert row["source_variable"] == "daily_rain"
        assert row["quality_flag"] == "partial_month_no_decile"
        assert row["year"] == 2026
        assert row["month"] == 5

    def test_through_day_detects_last_nondata(self, tmp_path):
        # Days 1..3 have data, days 4..5 are nodata-sentinel; expect through=3.
        times = [f"2026-05-{d:02d}" for d in range(1, 6)]
        values = [[[2.0]], [[3.0]], [[4.0]], [[-99999.0]], [[-99999.0]]]
        ds = _make_daily_ds(times, [-30.0], [116.0], values)
        nc_path = tmp_path / "2026.daily_rain.nc"
        ds.to_netcdf(nc_path)

        sa2_rows = [
            {"sa2_code": "X", "sa2_name": "X", "state_name": "WA",
             "lat": -30.0, "lon": 116.0, "universe_source": "test"},
        ]
        df, through_day = mod.extract_partial_month(nc_path, 2026, 5, sa2_rows)
        assert through_day == 3
        assert df.iloc[0]["rainfall_mm"] == pytest.approx(9.0, abs=0.01)
        assert df.iloc[0]["partial_month_through_day"] == 3

    def test_nodata_centroid_emits_nan(self, tmp_path):
        # All days nodata at this centroid.
        times = [f"2026-05-{d:02d}" for d in range(1, 4)]
        values = [[[-99999.0]], [[-99999.0]], [[-99999.0]]]
        ds = _make_daily_ds(times, [-30.0], [116.0], values)
        nc_path = tmp_path / "2026.daily_rain.nc"
        ds.to_netcdf(nc_path)

        sa2_rows = [
            {"sa2_code": "X", "sa2_name": "X", "state_name": "WA",
             "lat": -30.0, "lon": 116.0, "universe_source": "test"},
        ]
        # Add a second day with valid data at a different cell so through_day
        # detection succeeds — otherwise the function rightly raises.
        # Here all days are nodata everywhere, so we expect the function to
        # raise. Confirm that contract.
        with pytest.raises(ValueError, match="No day in the month slice"):
            mod.extract_partial_month(nc_path, 2026, 5, sa2_rows)

    def test_centroid_nodata_with_valid_elsewhere(self, tmp_path):
        # Two cells: one has data days 1..3, other is all nodata. SA2 maps to
        # the nodata cell → expect rainfall_mm NaN, quality_flag='nodata'.
        times = [f"2026-05-{d:02d}" for d in range(1, 4)]
        # Shape (3, 1, 2): time × lat × lon (2 lon cells)
        values = [
            [[5.0, -99999.0]],
            [[6.0, -99999.0]],
            [[7.0, -99999.0]],
        ]
        ds = _make_daily_ds(times, [-30.0], [116.0, 117.0], values)
        nc_path = tmp_path / "2026.daily_rain.nc"
        ds.to_netcdf(nc_path)

        sa2_rows = [
            {"sa2_code": "X", "sa2_name": "X", "state_name": "WA",
             "lat": -30.0, "lon": 117.0, "universe_source": "test"},
        ]
        df, through_day = mod.extract_partial_month(nc_path, 2026, 5, sa2_rows)
        assert through_day == 3  # detected via the cell that has data
        row = df.iloc[0]
        assert math.isnan(row["rainfall_mm"])
        assert row["quality_flag"] == "nodata"

    def test_rejects_wrong_month_in_slice(self, tmp_path):
        # File spans both April and May; selecting month=5 must only sum May.
        times = ["2026-04-30", "2026-05-01", "2026-05-02"]
        values = [[[100.0]], [[1.0]], [[2.0]]]
        ds = _make_daily_ds(times, [-30.0], [116.0], values)
        nc_path = tmp_path / "2026.daily_rain.nc"
        ds.to_netcdf(nc_path)

        sa2_rows = [
            {"sa2_code": "X", "sa2_name": "X", "state_name": "WA",
             "lat": -30.0, "lon": 116.0, "universe_source": "test"},
        ]
        df, through_day = mod.extract_partial_month(nc_path, 2026, 5, sa2_rows)
        # April's 100mm must not contaminate May sum.
        assert df.iloc[0]["rainfall_mm"] == pytest.approx(3.0, abs=0.01)
        assert through_day == 2


class TestDecilePassthrough:
    """Ensure the decile builder hands partial-month rows through unchanged."""

    def test_partial_row_not_used_as_baseline(self):
        import scripts.build_sa2_rainfall_deciles as deciles

        rows = []
        # 11 full-month historical years for SA2 X, month 5, with steady 50mm.
        for y in range(2014, 2025):
            rows.append({
                "year": y, "month": 5, "sa2_code": "X", "sa2_name": "X",
                "state_name": "WA", "rainfall_mm": 50.0,
                "extraction_method": "centroid_nearest_grid_cell",
                "universe_source": "test", "source_file": "x.nc",
                "source_variable": "monthly_rain", "quality_flag": "ok",
                "is_partial_month": False, "partial_month_through_day": None,
            })
        # One partial-month row for 2026 (must be flagged, must not contaminate
        # the median used by another row).
        rows.append({
            "year": 2026, "month": 5, "sa2_code": "X", "sa2_name": "X",
            "state_name": "WA", "rainfall_mm": 5.0,
            "extraction_method": "centroid_nearest_grid_cell_daily_sum",
            "universe_source": "test", "source_file": "2026.daily_rain.nc",
            "source_variable": "daily_rain",
            "quality_flag": "partial_month_no_decile",
            "is_partial_month": True, "partial_month_through_day": 17,
        })
        df = pd.DataFrame(rows)
        result = deciles.compute_deciles(df)

        partial = result[result["is_partial_month"] == True]
        assert len(partial) == 1
        assert partial.iloc[0]["climatology_quality_flag"] == "partial_month_no_decile"
        # Decile fields must be null.
        assert pd.isna(partial.iloc[0]["rainfall_decile"])
        assert pd.isna(partial.iloc[0]["historical_median_mm"])

        # And the 11 full-month rows still receive valid deciles.
        full = result[result["is_partial_month"] == False]
        assert len(full) == 11
        assert full["historical_median_mm"].notna().sum() == 11
