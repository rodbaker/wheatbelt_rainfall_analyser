"""Tests for extract_sa2_monthly_rainfall using synthetic xarray datasets."""

import math
import types
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import xarray as xr

import scripts.extract_sa2_monthly_rainfall as mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ds(times, lats, lons, values):
    """Build a tiny synthetic xarray Dataset matching the real file schema."""
    data = np.array(values, dtype=float).reshape(len(times), len(lats), len(lons))
    return xr.Dataset(
        {"monthly_rain": (["time", "lat", "lon"], data)},
        coords={
            "time": [pd.Timestamp(t) for t in times],
            "lat": lats,
            "lon": lons,
        },
    )


# ---------------------------------------------------------------------------
# Unit: centroid / nearest-cell helpers
# ---------------------------------------------------------------------------

class TestPolycentroid:
    def test_simple_square(self):
        # Closed ring: [110,-30], [112,-30], [112,-32], [110,-32], [110,-30]
        # Vertex-average (closing point counts): lat avg = (-30*3 + -32*2)/5 = -30.8
        # lon avg = (110*3 + 112*2)/5 = 110.8
        geom = {
            "type": "Polygon",
            "coordinates": [
                [[110.0, -30.0], [112.0, -30.0], [112.0, -32.0], [110.0, -32.0], [110.0, -30.0]]
            ],
        }
        lat, lon = mod._poly_centroid(geom)
        assert lat == pytest.approx(-30.8, abs=0.01)
        assert lon == pytest.approx(110.8, abs=0.01)

    def test_result_within_bounding_box(self):
        # Centroid must fall inside the polygon's bounding box
        geom = {
            "type": "Polygon",
            "coordinates": [
                [[115.0, -28.0], [120.0, -28.0], [120.0, -35.0], [115.0, -35.0], [115.0, -28.0]]
            ],
        }
        lat, lon = mod._poly_centroid(geom)
        assert -35.0 <= lat <= -28.0
        assert 115.0 <= lon <= 120.0

    def test_multipolygon_within_combined_bbox(self):
        geom = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[110.0, -30.0], [110.0, -32.0], [112.0, -32.0], [110.0, -30.0]]],
                [[[114.0, -30.0], [114.0, -32.0], [116.0, -32.0], [114.0, -30.0]]],
            ],
        }
        lat, lon = mod._poly_centroid(geom)
        assert -32.0 <= lat <= -30.0
        assert 110.0 <= lon <= 116.0


class TestNearestGridValue:
    def _make_da(self, lats, lons, values):
        data = np.array(values, dtype=float).reshape(len(lats), len(lons))
        return xr.DataArray(data, coords={"lat": lats, "lon": lons}, dims=["lat", "lon"])

    def test_exact_match(self):
        da = self._make_da([-30.0, -31.0], [116.0, 117.0], [[10.0, 20.0], [30.0, 40.0]])
        assert mod.nearest_grid_value(da, -31.0, 117.0) == 40.0

    def test_snaps_to_nearest(self):
        da = self._make_da([-30.0, -31.0], [116.0, 117.0], [[10.0, 20.0], [30.0, 40.0]])
        # -30.4 is closer to -30.0 than -31.0
        val = mod.nearest_grid_value(da, -30.4, 116.0)
        assert val == 10.0


# ---------------------------------------------------------------------------
# Integration: extract_one_file with synthetic data
# ---------------------------------------------------------------------------

class TestExtractOneFile:
    def _patch_open_dataset(self, ds):
        """Context-manager mock for xr.open_dataset."""
        return patch.object(xr, "open_dataset", return_value=ds.__enter__() if hasattr(ds, '__enter__') else ds)

    def test_single_month_two_sa2s(self, tmp_path):
        ds = _make_ds(
            times=["2005-01-16"],
            lats=[-30.0, -31.0],
            lons=[116.0, 117.0],
            values=[[10.5, 20.3, 30.1, 40.7]],  # flattened: [lat0lon0, lat0lon1, lat1lon0, lat1lon1]
        )
        sa2_rows = [
            {"sa2_code": "501000001", "sa2_name": "Test A", "lat": -30.0, "lon": 116.0},
            {"sa2_code": "501000002", "sa2_name": "Test B", "lat": -31.0, "lon": 117.0},
        ]
        nc_path = tmp_path / "2005.monthly_rain.nc"
        ds.to_netcdf(nc_path)

        records = mod.extract_one_file(nc_path, sa2_rows)

        assert len(records) == 2
        sa2_a = next(r for r in records if r["sa2_code"] == "501000001")
        sa2_b = next(r for r in records if r["sa2_code"] == "501000002")
        assert sa2_a["rainfall_mm"] == pytest.approx(10.5, abs=0.01)
        assert sa2_b["rainfall_mm"] == pytest.approx(40.7, abs=0.01)
        assert sa2_a["year"] == 2005
        assert sa2_a["month"] == 1
        assert sa2_a["extraction_method"] == mod.EXTRACTION_METHOD
        assert sa2_a["source_variable"] == "monthly_rain"
        assert sa2_a["quality_flag"] == "ok"

    def test_full_year_row_count(self, tmp_path):
        times = [f"2005-{m:02d}-15" for m in range(1, 13)]
        ds = _make_ds(
            times=times,
            lats=[-30.0],
            lons=[116.0],
            values=[[[v]] for v in range(12)],
        )
        sa2_rows = [
            {"sa2_code": "501000001", "sa2_name": "Test A", "lat": -30.0, "lon": 116.0},
        ]
        nc_path = tmp_path / "2005.monthly_rain.nc"
        ds.to_netcdf(nc_path)

        records = mod.extract_one_file(nc_path, sa2_rows)
        assert len(records) == 12

    def test_nodata_masked(self, tmp_path):
        ds = _make_ds(
            times=["2005-01-16"],
            lats=[-30.0],
            lons=[116.0],
            values=[[[-99999.0]]],
        )
        sa2_rows = [{"sa2_code": "501000001", "sa2_name": "Test", "lat": -30.0, "lon": 116.0}]
        nc_path = tmp_path / "2005.monthly_rain.nc"
        ds.to_netcdf(nc_path)

        records = mod.extract_one_file(nc_path, sa2_rows)
        assert len(records) == 1
        assert math.isnan(records[0]["rainfall_mm"])
        assert records[0]["quality_flag"] == "nodata"

    def test_partial_year(self, tmp_path):
        ds = _make_ds(
            times=["2025-01-16"],
            lats=[-30.0],
            lons=[116.0],
            values=[[[5.0]]],
        )
        sa2_rows = [{"sa2_code": "501000001", "sa2_name": "Test", "lat": -30.0, "lon": 116.0}]
        nc_path = tmp_path / "2025.monthly_rain.nc"
        ds.to_netcdf(nc_path)

        records = mod.extract_one_file(nc_path, sa2_rows)
        assert len(records) == 1
        assert records[0]["year"] == 2025
        assert records[0]["month"] == 1


# ---------------------------------------------------------------------------
# Integration: run() with 28 synthetic SA2s
# ---------------------------------------------------------------------------

class TestRunAcceptance:
    def test_28_sa2s_full_year(self, tmp_path, monkeypatch):
        """run() with 28 SA2s and a single 12-month file → 336 rows."""
        # Patch constants to point at tmp dirs
        monkeypatch.setattr(mod, "MONTHLY_RAIN_DIR", tmp_path / "monthly_rain")
        monkeypatch.setattr(mod, "SA2_UNIVERSE_CSV", tmp_path / "universe.csv")
        monkeypatch.setattr(mod, "OUTPUT_CSV", tmp_path / "out.csv")
        monkeypatch.setattr(mod, "GEOJSON_PATH", tmp_path / "geo.geojson")

        rain_dir = tmp_path / "monthly_rain"
        rain_dir.mkdir()

        # Build 28 fake SA2 rows
        n = 28
        codes = [f"5{i:08d}" for i in range(n)]
        names = [f"SA2 Region {i}" for i in range(n)]
        lats = np.linspace(-30.0, -33.0, n).tolist()
        lons = np.linspace(116.0, 120.0, n).tolist()

        # Write universe CSV
        pd.DataFrame({"SA2_CODE21": codes, "SA2_NAME21": names}).to_csv(
            tmp_path / "universe.csv", index=False
        )

        # Write minimal GeoJSON with squares centred on each lat/lon
        features = []
        for code, name, lat, lon in zip(codes, names, lats, lons):
            features.append({
                "type": "Feature",
                "properties": {"SA2_MAIN16": code, "SA2_NAME16": name},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [lon - 0.1, lat + 0.1],
                        [lon + 0.1, lat + 0.1],
                        [lon + 0.1, lat - 0.1],
                        [lon - 0.1, lat - 0.1],
                        [lon - 0.1, lat + 0.1],
                    ]],
                },
            })
        import json
        with open(tmp_path / "geo.geojson", "w") as fh:
            json.dump({"type": "FeatureCollection", "features": features}, fh)

        # Write 12-month NetCDF with unique rainfall per grid cell
        grid_lats = np.round(np.linspace(-30.0, -33.0, n), 4)
        grid_lons = np.round(np.linspace(116.0, 120.0, n), 4)
        times = [f"2005-{m:02d}-15" for m in range(1, 13)]
        data = np.ones((12, n, n), dtype=float)
        for i in range(n):
            data[:, i, i] = float(i + 10)

        ds = xr.Dataset(
            {"monthly_rain": (["time", "lat", "lon"], data)},
            coords={
                "time": [pd.Timestamp(t) for t in times],
                "lat": grid_lats,
                "lon": grid_lons,
            },
        )
        ds.to_netcdf(rain_dir / "2005.monthly_rain.nc")

        df = mod.run(dry_run=True)

        assert len(df) == 28 * 12
        assert set(df["sa2_code"].unique()) == set(codes)
        assert set(df["month"].unique()) == set(range(1, 13))
        assert (df["rainfall_mm"] >= 0).all()
        assert df["extraction_method"].eq(mod.EXTRACTION_METHOD).all()

    def test_2025_partial_year(self, tmp_path, monkeypatch):
        """A single-month 2025 file → 28 rows."""
        monkeypatch.setattr(mod, "MONTHLY_RAIN_DIR", tmp_path / "monthly_rain")
        monkeypatch.setattr(mod, "SA2_UNIVERSE_CSV", tmp_path / "universe.csv")
        monkeypatch.setattr(mod, "OUTPUT_CSV", tmp_path / "out.csv")
        monkeypatch.setattr(mod, "GEOJSON_PATH", tmp_path / "geo.geojson")

        rain_dir = tmp_path / "monthly_rain"
        rain_dir.mkdir()

        n = 28
        codes = [f"5{i:08d}" for i in range(n)]
        names = [f"SA2 Region {i}" for i in range(n)]
        lats = np.linspace(-30.0, -33.0, n).tolist()
        lons = np.linspace(116.0, 120.0, n).tolist()

        pd.DataFrame({"SA2_CODE21": codes, "SA2_NAME21": names}).to_csv(
            tmp_path / "universe.csv", index=False
        )

        features = []
        for code, name, lat, lon in zip(codes, names, lats, lons):
            features.append({
                "type": "Feature",
                "properties": {"SA2_MAIN16": code, "SA2_NAME16": name},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [lon - 0.1, lat + 0.1], [lon + 0.1, lat + 0.1],
                        [lon + 0.1, lat - 0.1], [lon - 0.1, lat - 0.1],
                        [lon - 0.1, lat + 0.1],
                    ]],
                },
            })
        import json
        with open(tmp_path / "geo.geojson", "w") as fh:
            json.dump({"type": "FeatureCollection", "features": features}, fh)

        grid_lats = np.round(np.linspace(-30.0, -33.0, n), 4)
        grid_lons = np.round(np.linspace(116.0, 120.0, n), 4)
        data = np.ones((1, n, n), dtype=float)
        ds = xr.Dataset(
            {"monthly_rain": (["time", "lat", "lon"], data)},
            coords={
                "time": [pd.Timestamp("2025-01-16")],
                "lat": grid_lats,
                "lon": grid_lons,
            },
        )
        ds.to_netcdf(rain_dir / "2025.monthly_rain.nc")

        df = mod.run(dry_run=True)
        assert len(df) == 28
        assert df["year"].eq(2025).all()
        assert df["month"].eq(1).all()
