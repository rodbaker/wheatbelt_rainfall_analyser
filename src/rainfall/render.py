"""Render the discrete-binned rainfall percentile raster + SA2 overlay to PNG."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from shapely.geometry import Point
from shapely.prepared import prep

REPO_ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = REPO_ROOT / "reports" / "figures"

_BIN_EDGES = [10, 20, 30, 40, 50, 60, 70, 80, 90]  # right-closed
_BIN_LABELS = ["<=10", "10-20", "20-30", "30-40", "40-50",
               "50-60", "60-70", "70-80", "80-90", ">90"]
_MONTHS = ["", "January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


def bin_index(pct: np.ndarray) -> np.ndarray:
    """Map a percentile array to 10 right-closed bin indices 0-9 (NaN-safe)."""
    return np.digitize(pct, _BIN_EDGES, right=True)


def _palette() -> ListedColormap:
    base = plt.get_cmap("RdBu")
    return ListedColormap([base(i / 9) for i in range(10)])


def clip_to_regions(pct, lon, lat, mask_geom, margin=0.5):
    """Set cells whose centre falls outside `mask_geom` to NaN (hard wheatbelt clip).

    Cells outside the mask's bounding box (plus `margin` degrees) are blanked
    without a per-cell point-in-polygon test, so the expensive containment check
    only runs near the wheatbelt rather than across the whole national grid.
    """
    lon = np.asarray(lon, dtype="float64")
    lat = np.asarray(lat, dtype="float64")
    minx, miny, maxx, maxy = mask_geom.bounds
    minx -= margin; miny -= margin; maxx += margin; maxy += margin

    prepared = prep(mask_geom)
    out = np.full(np.asarray(pct, dtype="float64").shape, np.nan)
    for j, la in enumerate(lat):
        if la < miny or la > maxy:
            continue
        for i, lo in enumerate(lon):
            if lo < minx or lo > maxx:
                continue
            if prepared.contains(Point(float(lo), float(la))):
                out[j, i] = pct[j, i]
    return out


def render_percentile_map(pct, regions, *, lon, lat, month, year,
                          baseline_start, baseline_end, out_path=None,
                          mask_geom=None):
    """Draw the percentile raster with SA2 overlay; write PNG; return the path.

    If `mask_geom` is given, cells outside it are blanked (reproduce the
    reference map's hard clip to the wheatbelt).
    """
    out_path = Path(out_path) if out_path else (
        FIG_DIR / f"wa_{month:02d}_{year}_percentiles.png"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if mask_geom is not None:
        pct = clip_to_regions(pct, lon, lat, mask_geom)

    cmap = _palette()
    idx = bin_index(pct).astype("float64")
    idx[np.isnan(pct)] = np.nan
    masked = np.ma.masked_invalid(idx)

    fig, ax = plt.subplots(figsize=(11, 9))
    ax.pcolormesh(lon, lat, masked, cmap=cmap, vmin=0, vmax=9, shading="auto")
    regions.boundary.plot(ax=ax, color="black", linewidth=0.6)
    for _, row in regions.iterrows():
        pt = row.geometry.representative_point()
        ax.annotate(row["SA2_NAME16"], (pt.x, pt.y), fontsize=7,
                    ha="center", va="center")

    minx, miny, maxx, maxy = regions.total_bounds
    ax.set_xlim(minx - 0.3, maxx + 0.3)
    ax.set_ylim(miny - 0.3, maxy + 0.3)
    ax.set_aspect("equal")

    ax.set_title(f"WA Wheatbelt {_MONTHS[month]} Rainfall Percentiles", fontsize=16)
    ax.set_axis_off()
    handles = [Patch(facecolor=cmap(i), edgecolor="black", label=_BIN_LABELS[i])
               for i in range(10)]
    ax.legend(handles=handles, title="Percentiles", loc="center left",
              bbox_to_anchor=(1.01, 0.5), frameon=True)
    fig.text(0.5, 0.02,
             f"Baseline: {baseline_start}-{baseline_end}  |  "
             f"Source: SILO (LongPaddock) monthly_rain",
             ha="center", fontsize=8)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
