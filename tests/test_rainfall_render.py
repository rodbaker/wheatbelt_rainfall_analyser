"""Renderer tests: binning correctness + headless PNG smoke."""

import numpy as np

from src.rainfall import render as rd


def test_bin_index_right_closed():
    # pct == 10 must land in bin 0 (the <=10 class); 10.0001 -> bin 1.
    pct = np.array([[0.0, 10.0, 10.5, 95.0, 100.0]])
    idx = rd.bin_index(pct)
    assert idx.tolist() == [[0, 0, 1, 9, 9]]


def test_clip_to_regions_blanks_outside_cells():
    from shapely.geometry import box
    # Unit square mask at lon 0-1, lat 0-1. Grid centres: one inside, one outside.
    mask = box(0.0, 0.0, 1.0, 1.0)
    lon = np.array([0.5, 5.0])
    lat = np.array([0.5])
    pct = np.array([[40.0, 60.0]])
    out = rd.clip_to_regions(pct, lon, lat, mask)
    assert out[0, 0] == 40.0          # inside the mask -> kept
    assert np.isnan(out[0, 1])         # outside the mask -> blanked


def test_render_writes_png(tmp_path):
    from src.rainfall import boundaries as bd
    regions = bd.load_wheatbelt_regions()
    # Toy percentile grid over a small lon/lat window inside WA.
    lon = np.linspace(114.0, 124.0, 20)
    lat = np.linspace(-35.0, -27.0, 16)
    pct = np.random.default_rng(0).uniform(0, 100, size=(lat.size, lon.size))
    out = tmp_path / "test_map.png"
    rd.render_percentile_map(
        pct, regions, lon=lon, lat=lat, month=7, year=2024,
        baseline_start=1911, baseline_end=2023, out_path=out,
        mask_geom=bd.clip_mask(regions),
    )
    assert out.exists() and out.stat().st_size > 0
