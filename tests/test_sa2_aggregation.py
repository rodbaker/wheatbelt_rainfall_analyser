"""Unit tests for crop-weighted SA2 aggregation (synthetic grids — no I/O)."""
import numpy as np
import xarray as xr
from shapely.geometry import box

from scripts.sa2_aggregation import build_cell_weights, crop_weighted_mean


def _grid(vals, lats, lons):
    return xr.DataArray(np.array(vals, dtype="float64"),
                        coords={"lat": lats, "lon": lons}, dims=["lat", "lon"])


def test_weighted_mean_uses_cropfrac_weights():
    # 1x2 cells with values 10, 20 and crop weights 0.1, 0.3 → (1+6)/0.4 = 17.5
    lats = [-33.90]
    lons = [117.00, 117.05]
    rain = _grid([[10.0, 20.0]], lats, lons)
    cf = _grid([[0.1, 0.3]], lats, lons)
    poly = box(116.97, -33.93, 117.08, -33.87)  # covers both cell centres
    w = build_cell_weights(poly, rain["lat"].values, rain["lon"].values, cf,
                           crop_floor=0.0)
    assert crop_weighted_mean(rain.values, w) == 17.5


def test_nodata_cells_excluded():
    lats = [-33.90]
    lons = [117.00, 117.05]
    rain = _grid([[np.nan, 20.0]], lats, lons)
    cf = _grid([[0.5, 0.5]], lats, lons)
    poly = box(116.97, -33.93, 117.08, -33.87)
    w = build_cell_weights(poly, rain["lat"].values, rain["lon"].values, cf,
                           crop_floor=0.0)
    # NaN cell dropped → only the 20.0 cell remains
    assert crop_weighted_mean(rain.values, w) == 20.0


def test_no_cropland_falls_back_to_centroid_cell():
    lats = [-33.90]
    lons = [117.00, 117.05]
    rain = _grid([[10.0, 20.0]], lats, lons)
    cf = _grid([[0.0, 0.0]], lats, lons)        # no cropland anywhere
    poly = box(116.97, -33.93, 117.08, -33.87)
    w = build_cell_weights(poly, rain["lat"].values, rain["lon"].values, cf,
                           crop_floor=0.05)
    assert w.fallback is True
    # fallback returns the value of the cell nearest the polygon centroid
    val = crop_weighted_mean(rain.values, w)
    assert val in (10.0, 20.0)
