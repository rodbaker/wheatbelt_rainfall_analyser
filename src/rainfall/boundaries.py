"""WA wheatbelt SA2 boundaries for the rainfall percentile map (SA2-only)."""

from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON = REPO_ROOT / "data" / "meta" / "SA2_ABS_Regions.geojson"


def load_wheatbelt_regions(geojson_path: Path = GEOJSON) -> gpd.GeoDataFrame:
    """The 26 WA wheatbelt SA2 polygons in EPSG:4326, with SA2_NAME16 labels."""
    gdf = gpd.read_file(geojson_path)
    wa = gdf[gdf["STE_NAME16"] == "Western Australia"].copy()
    # A boolean-mask filter preserves CRS, so test wa (the object we act on).
    if wa.crs is None:
        wa = wa.set_crs(epsg=4326)
    else:
        wa = wa.to_crs(epsg=4326)
    return wa.reset_index(drop=True)


def clip_mask(regions: gpd.GeoDataFrame) -> BaseGeometry:
    """Union of the wheatbelt polygons — used to blank raster cells outside it."""
    return unary_union(regions.geometry.values)
