"""Crop-weighted spatial aggregation of a rainfall grid over SA2 polygons.

A single SA2 figure is the mean of every 0.05° grid cell whose centre falls
inside the SA2 polygon, weighted by the ABARES CLUM cropland fraction of each
cell (rainfall *where the wheat is*). Cells below `crop_floor` contribute zero
weight. If an SA2 has no cropland cells, we fall back to the single grid cell
nearest the polygon centroid and flag it.

No scipy: grid alignment uses xarray.sel(method="nearest"), never interp.
"""
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import xarray as xr
from shapely import contains_xy

REPO_ROOT = Path(__file__).resolve().parents[1]
CROPFRAC_NC = REPO_ROOT / "data" / "meta" / "clum_cropfrac_005.nc"
SA2_SHP = ("zip:///mnt/d/grains-data-store/wheatbelt_rainfall_analyser/"
           "data/meta/shapefiles/SA2_2021_AUST_SHP_GDA2020.zip")
CROP_FLOOR = 0.05  # CLUM cropland fraction threshold (matches the map's --crop-mask)


@dataclass
class CellWeights:
    """Precomputed cell selection + weights for one SA2 on one grid."""
    ji: np.ndarray        # lat indices of selected cells
    ii: np.ndarray        # lon indices of selected cells
    weights: np.ndarray   # cropland-fraction weight per selected cell
    fallback: bool        # True when no cropland → single centroid cell


def load_cropfrac() -> xr.DataArray:
    """Return the CLUM cropland-fraction grid (Band1)."""
    return xr.open_dataset(CROPFRAC_NC)["Band1"]


def load_sa2_polygons(codes: set[str] | None = None) -> dict[str, object]:
    """Return {sa2_code(2021): shapely geometry in EPSG:4326}."""
    g = gpd.read_file(SA2_SHP)[["SA2_CODE21", "geometry"]].to_crs(4326)
    g["SA2_CODE21"] = g["SA2_CODE21"].astype(str)
    if codes is not None:
        g = g[g["SA2_CODE21"].isin(codes)]
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    return dict(zip(g["SA2_CODE21"], g.geometry))


def build_cell_weights(geom, lat: np.ndarray, lon: np.ndarray,
                       cropfrac: xr.DataArray,
                       crop_floor: float = CROP_FLOOR) -> CellWeights:
    """Precompute the inside-polygon cells and their cropland weights.

    Cells are selected by centre-in-polygon test within the polygon bbox.
    Cropland fraction is sampled at each cell via nearest-index lookup.
    Weights below `crop_floor` are zeroed. If the total weight is zero,
    fall back to the single cell nearest the polygon centroid (fallback=True,
    weight 1.0) so the SA2 still gets a value.
    """
    minx, miny, maxx, maxy = geom.bounds
    ji = np.where((lat >= miny) & (lat <= maxy))[0]
    ii = np.where((lon >= minx) & (lon <= maxx))[0]
    if ji.size == 0 or ii.size == 0:
        return _centroid_fallback(geom, lat, lon)
    LON, LAT = np.meshgrid(lon[ii], lat[ji])
    inside = contains_xy(geom, LON, LAT)
    if not inside.any():
        return _centroid_fallback(geom, lat, lon)
    sub_ji = np.repeat(ji, ii.size).reshape(ji.size, ii.size)[inside]
    sub_ii = np.tile(ii, ji.size).reshape(ji.size, ii.size)[inside]
    cf = cropfrac.sel(lat=lat[sub_ji], lon=lon[sub_ii], method="nearest").values
    cf = np.nan_to_num(np.asarray(cf, dtype="float64"), nan=0.0)
    cf[cf < crop_floor] = 0.0
    if cf.sum() <= 0:
        return _centroid_fallback(geom, lat, lon)
    return CellWeights(ji=sub_ji, ii=sub_ii, weights=cf, fallback=False)


def _centroid_fallback(geom, lat: np.ndarray, lon: np.ndarray) -> CellWeights:
    c = geom.representative_point()
    cj = int(np.abs(lat - c.y).argmin())
    ci = int(np.abs(lon - c.x).argmin())
    return CellWeights(ji=np.array([cj]), ii=np.array([ci]),
                       weights=np.array([1.0]), fallback=True)


def crop_weighted_mean(grid2d: np.ndarray, w: CellWeights) -> float:
    """Weighted mean of grid2d over the precomputed cells, dropping NaN cells."""
    vals = grid2d[w.ji, w.ii]
    wt = w.weights.copy()
    good = np.isfinite(vals)
    vals, wt = vals[good], wt[good]
    if wt.sum() <= 0:
        return float("nan")
    return float((vals * wt).sum() / wt.sum())
