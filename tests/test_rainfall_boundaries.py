"""Tests for the SA2 wheatbelt boundary loader."""

from shapely.geometry import MultiPolygon, Polygon

from src.rainfall import boundaries as bd


def test_load_wheatbelt_regions_returns_26_wa_sa2():
    regions = bd.load_wheatbelt_regions()
    assert len(regions) == 26
    assert (regions["STE_NAME16"] == "Western Australia").all()
    assert "SA2_NAME16" in regions.columns
    # Reference-map landmarks present
    names = set(regions["SA2_NAME16"])
    assert {"Moora", "Dowerin", "Merredin", "Esperance Region"} <= names


def test_regions_crs_is_wgs84():
    regions = bd.load_wheatbelt_regions()
    assert regions.crs is not None
    assert regions.crs.to_epsg() == 4326


def test_clip_mask_is_single_geometry():
    regions = bd.load_wheatbelt_regions()
    mask = bd.clip_mask(regions)
    assert isinstance(mask, (Polygon, MultiPolygon))
    assert mask.is_valid
