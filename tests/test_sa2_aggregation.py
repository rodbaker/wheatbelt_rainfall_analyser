"""Unit tests for crop-weighted SA2 aggregation (synthetic grids — no I/O)."""
import numpy as np
import pytest
import xarray as xr
from shapely.geometry import box
from shapely.ops import unary_union

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
    # fallback returns the value of the cell nearest the polygon centroid.
    # Box centroid ~(117.025, -33.90); nearest lon is 117.05 → the 20.0 cell.
    val = crop_weighted_mean(rain.values, w)
    assert val == 20.0


def test_multi_lat_nonrectangular_mask_pointwise_weights():
    """Regression: cells spanning >1 lat row with a non-rectangular inside
    mask must use POINTWISE cropfrac, not orthogonal (outer-product) indexing.

    3x3 grid; only the diagonal-ish cells (lat0,lon0), (lat1,lon2), (lat2,lon1)
    are selected via a MultiPolygon of three tight per-cell boxes. The selected
    set spans all 3 lat rows and is not a full lat x lon rectangle, so the
    buggy outer-product sel and the correct pointwise sel diverge.

        values    10 / 60 / 80
        cropfrac 0.1 / 0.6 / 0.8
        expected (10*0.1 + 60*0.6 + 80*0.8) / (0.1 + 0.6 + 0.8) = 67.333...
    """
    lats = [-33.80, -33.85, -33.90]
    lons = [117.00, 117.05, 117.10]
    # Target cells carry the load; the other six get distinct nonzero values so
    # the outer-product bug (which would pull them in) produces a wrong answer.
    rain = _grid([[10.0, 0.0, 0.0],
                  [0.0, 0.0, 60.0],
                  [0.0, 80.0, 0.0]], lats, lons)
    cf = _grid([[0.1, 0.9, 0.9],
                [0.9, 0.9, 0.6],
                [0.9, 0.8, 0.9]], lats, lons)
    # Three tight boxes (+/-0.01, well inside the 0.05 spacing) each enclose
    # exactly one target cell centre → a non-rectangular 3-cell selection.
    poly = unary_union([
        box(117.00 - 0.01, -33.80 - 0.01, 117.00 + 0.01, -33.80 + 0.01),
        box(117.10 - 0.01, -33.85 - 0.01, 117.10 + 0.01, -33.85 + 0.01),
        box(117.05 - 0.01, -33.90 - 0.01, 117.05 + 0.01, -33.90 + 0.01),
    ])
    w = build_cell_weights(poly, rain["lat"].values, rain["lon"].values, cf,
                           crop_floor=0.0)
    assert w.fallback is False
    # exactly three cells selected, across all three lat rows
    assert w.ji.size == 3
    assert set(w.ji.tolist()) == {0, 1, 2}
    assert crop_weighted_mean(rain.values, w) == pytest.approx(101.0 / 1.5)
