#!/usr/bin/env python3
"""BOM-format gridded rainfall decile map — true per-cell deciles.

Unlike plot_decile_map_bom.py (which averages to SA2 polygons), this computes the
decile at every 0.05° SILO grid cell against the full monthly record, so it shows
within-region variation the way BOM's published maps do.

Per cell: rank the target month's 2026 total against the same month in every
baseline year. percentile = (#baseline years below) / N * 100, binned to BOM
tiers; "lowest/highest on record" = below/above every baseline year.

Baseline defaults to 1911-2025 (the full local archive ≈ BOM's 1900-present).

Usage: python scripts/plot_decile_grid_bom.py --year 2026 --month 5 --state "Western Australia"
"""
import argparse
import calendar
import glob
import os
from pathlib import Path as FsPath

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath

ROOT = FsPath(__file__).resolve().parents[1]
GRID_DIR = ROOT / "data/meta/monthly_rain"
DAILY_DIR = ROOT / "data/meta/daily_rain"
CROPFRAC = ROOT / "data/meta/clum_cropfrac_005.nc"  # ABARES CLUM dryland-crop frac
SHP = ("zip:///mnt/d/grains-data-store/wheatbelt_rainfall_analyser/data/meta/"
       "shapefiles/SA2_2021_AUST_SHP_GDA2020.zip")
CONCORD = FsPath("/home/roddyb/projects/ABS Census Data/"
                 "Modernised_Census_2022_2025/comparison_2020_21_to_2022_23/"
                 "acf_historical/concordances/"
                 "sa2_2021_to_sd_2011_area_overlay.csv")
ABBR = {"Western Australia": "WA", "South Australia": "SA", "Victoria": "Vic",
        "New South Wales": "NSW", "Queensland": "Qld"}
MONTHS = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May",
          6: "June", 7: "July", 8: "August", 9: "September", 10: "October",
          11: "November", 12: "December"}

# state plotting boxes (lon_min, lon_max, lat_min, lat_max)
BOX = {"Western Australia": (112.5, 129.5, -35.6, -13.5),
       "South Australia": (128.5, 141.5, -38.5, -25.5),
       "Victoria": (140.5, 150.3, -39.4, -33.8),
       "New South Wales": (140.5, 154.2, -37.7, -28.0),
       "Queensland": (137.8, 154.2, -29.5, -9.5)}

TIERS = [
    ("highest", "#1c1cae", "Highest on record"),
    ("d10", "#6f6fcf", "10   Very much above average"),
    ("d89", "#c9cdeb", "8-9  Above average"),
    ("d47", "#ffffff", "4-7  Average"),
    ("d23", "#f7c5c5", "2-3  Below average"),
    ("d1", "#ed5f5f", "1    Very much below average"),
    ("lowest", "#e60000", "Lowest on record"),
]
# class index 0..6 = lowest..highest (low to high), for the colormap
ORDER = ["lowest", "d1", "d23", "d47", "d89", "d10", "highest"]
CMAP_COLORS = ["#e60000", "#ed5f5f", "#f7c5c5", "#ffffff",
               "#c9cdeb", "#6f6fcf", "#1c1cae"]


def geom_to_path(geom):
    verts, codes = [], []
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for poly in polys:
        for ring in [poly.exterior, *poly.interiors]:
            xy = np.asarray(ring.coords)
            if len(xy) < 3:
                continue
            verts.append(xy)
            c = np.full(len(xy), MplPath.LINETO)
            c[0], c[-1] = MplPath.MOVETO, MplPath.CLOSEPOLY
            codes.append(c)
    return MplPath(np.concatenate(verts), np.concatenate(codes))


def month_slice(ds, month, lon0, lon1, lat0, lat1):
    da = ds["monthly_rain"]
    da = da.sel(time=da["time"].dt.month == month)
    if da["time"].size == 0:
        return None
    da = da.isel(time=0).sel(lat=slice(lat0, lat1), lon=slice(lon0, lon1))
    if da["lat"].size == 0:  # lat may be descending
        da = ds["monthly_rain"].sel(time=ds["monthly_rain"]["time"].dt.month == month)
        da = da.isel(time=0).sel(lat=slice(lat1, lat0), lon=slice(lon0, lon1))
    return da


def daily_partial(year, month, lon0, lon1, lat0, lat1):
    """Sum the daily grid over days 1..N of a month (N = latest day present).

    Returns (summed DataArray, through_day) or (None, None). Used when the
    monthly grid for the target month isn't published yet (mid-month)."""
    f = DAILY_DIR / f"{year}.daily_rain.nc"
    if not f.exists():
        return None, None
    with xr.open_dataset(f) as ds:
        da = ds["daily_rain"]
        da = da.sel(time=da["time"].dt.month == month)
        if da["time"].size == 0:
            return None, None
        through = int(da["time"].dt.day.values.max())
        sub = da.sel(lat=slice(lat0, lat1), lon=slice(lon0, lon1))
        return sub.sum("time", skipna=False).load(), through


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--month", type=int, default=5)
    ap.add_argument("--state", default="Western Australia")
    ap.add_argument("--base-start", type=int, default=1911)
    ap.add_argument("--overlay", choices=["sd", "sa2", "both", "none"],
                    default="sd", help="region boundaries to overlay (default: SD; "
                    "'both' draws SD + SA2)")
    ap.add_argument("--crop-mask", type=float, default=None, metavar="FRAC",
                    help="cropland threshold: ABARES CLUM cropland fraction >= FRAC "
                         "per cell (e.g. 0.25). Drives the cropland footprint used "
                         "to mask the field and/or cut the overlays")
    ap.add_argument("--field", choices=["cropland", "statewide"],
                    default="cropland", help="show deciles only on cropland "
                    "(default) or state-wide; overlays are still cut to cropland "
                    "when --crop-mask is set")
    ap.add_argument("--smooth", type=float, default=0.25, metavar="DEG",
                    help="close radius (degrees) for the cropping outline; bridges "
                         "gaps between scattered patches into a broad region "
                         "(default 0.25 ≈ 28 km)")
    ap.add_argument("--label-below", type=float, default=None, metavar="DECILE",
                    help="annotate each cropping SA2 whose decile is below this "
                         "threshold with its name (e.g. 4 labels below-average "
                         "SA2s). Requires --overlay sa2 or both")
    ap.add_argument("--review-tag", default="", metavar="SUFFIX",
                    help="suffix inserted before .csv in the SA2/SD rainfall "
                         "review filenames read for SA2 deciles, labels and SD "
                         "selection (e.g. '_cropwtd' drives the map from the "
                         "crop-weighted review). Also appended to the output PNG "
                         "name so it doesn't clobber the centroid figure")
    args = ap.parse_args()

    lon0, lon1, lat0, lat1 = BOX[args.state]

    files = {int(os.path.basename(f)[:4]): f
             for f in glob.glob(str(GRID_DIR / "*.monthly_rain.nc"))}
    cur_f = files.get(args.year)
    if not cur_f:
        raise SystemExit(f"no grid file for {args.year}")
    dim = calendar.monthrange(args.year, args.month)[1]  # days in month

    # current value: full month from the monthly grid if published, else a
    # partial month-to-date sum from the daily grid (days 1..through).
    with xr.open_dataset(cur_f) as ds:
        cur = month_slice(ds, args.month, lon0, lon1, lat0, lat1)
        cur = cur.load() if cur is not None else None
    if cur is not None:
        through, scale = dim, 1.0
        print(f"{MONTHS[args.month]} {args.year}: full month (monthly grid)")
    else:
        cur, through = daily_partial(args.year, args.month,
                                     lon0, lon1, lat0, lat1)
        if cur is None:
            raise SystemExit(f"{MONTHS[args.month]} {args.year} not in monthly "
                             "grid and no daily grid to build a partial month")
        scale = through / dim   # scale historical full months to the same window
        print(f"{MONTHS[args.month]} {args.year}: partial 1–{through} from daily "
              f"grid; historical scaled ×{scale:.3f}")
    lats, lons = cur["lat"].values, cur["lon"].values
    curv = cur.values

    # baseline: historical full months from the monthly grid, scaled to the
    # same partial window so the comparison is like-for-like.
    stack = []
    for y in range(args.base_start, args.year):
        f = files.get(y)
        if not f:
            continue
        with xr.open_dataset(f) as ds:
            sl = month_slice(ds, args.month, lon0, lon1, lat0, lat1)
            if sl is not None:
                stack.append(sl.load().values * scale)
    base = np.stack(stack)            # (nyears, lat, lon)
    n = base.shape[0]
    print(f"baseline years: {n} ({args.base_start}-{args.year-1})")

    land = np.isfinite(curv) & np.isfinite(base).all(axis=0)
    below = np.sum(base < curv[None, :, :], axis=0).astype(float)
    pr = np.where(land, below / n * 100.0, np.nan)
    above_all = land & (below == n)
    below_all = land & (below == 0)

    cls = np.full(curv.shape, np.nan)
    cls[land & (pr >= 90)] = 5      # d10
    cls[land & (pr >= 70) & (pr < 90)] = 4
    cls[land & (pr >= 30) & (pr < 70)] = 3
    cls[land & (pr >= 10) & (pr < 30)] = 2
    cls[land & (pr < 10)] = 1       # d1
    cls[below_all] = 0              # lowest on record
    cls[above_all] = 6              # highest on record

    # restrict the field to actual cropland (ABARES CLUM cropland fraction) and
    # build a cropland polygon (union of qualifying 0.05° cells) used to "cut"
    # the region overlays so their outlines follow the cropping footprint.
    cropland_union = None
    if args.crop_mask is not None:
        cf = xr.open_dataset(CROPFRAC)["Band1"]
        cf = cf.sel(lat=xr.DataArray(lats, dims="lat"),
                    lon=xr.DataArray(lons, dims="lon"), method="nearest")
        frac = np.where(cf.values < 0, np.nan, cf.values)
        keep = np.isfinite(frac) & (frac >= args.crop_mask)
        if args.field == "cropland":
            cls = np.where(keep, cls, np.nan)
        from shapely.geometry import box
        from shapely.ops import unary_union
        # half a 0.05° cell, plus a tiny overlap so neighbouring cell boxes share
        # interiors and unary_union fully dissolves internal grid edges (otherwise
        # float mismatch on shared edges leaves spurious horizontal/vertical lines)
        h = 0.025 + 1e-4
        ys, xs = np.where(keep)
        cropland_union = unary_union(
            [box(lons[x] - h, lats[y] - h, lons[x] + h, lats[y] + h)
             for y, x in zip(ys, xs)]).buffer(0)
        # Build a BROAD cropping outline for the visual: morphological close with
        # a wide radius bridges gaps between scattered patches so isolated cropping
        # is absorbed into one region (dense belts like WA barely change; sparse
        # ones like Qld read as a coherent zone instead of speckle). No erosion —
        # nothing real is dropped. --smooth sets the bridging radius in degrees.
        r = args.smooth
        cropland_union = cropland_union.buffer(r).buffer(-r).simplify(0.03)
        print(f"crop mask >= {args.crop_mask}: {len(xs)} cropland cells shown")

    # state SA2s — full set for the clip outline; cropping subset for the overlay
    g = gpd.read_file(SHP)[["SA2_CODE21", "STE_NAME21", "geometry"]]
    g["SA2_CODE21"] = g["SA2_CODE21"].astype(str)
    g = g[(g["STE_NAME21"] == args.state) & g.geometry.notna()
          & ~g.geometry.is_empty].to_crs(4326)
    state_geom = g.dissolve("STE_NAME21").geometry.iloc[0]
    review = (ROOT / f"data/features/"
              f"sa2_{args.year}_{args.month:02d}_rainfall_review"
              f"{args.review_tag}.csv")
    review_df = pd.read_csv(review)
    review_df["sa2_code"] = review_df["sa2_code"].astype(str)
    crop_codes = set(review_df["sa2_code"])
    sa2_crop = g[g["SA2_CODE21"].isin(crop_codes)]

    # SD polygons: assign each SA2 to its dominant SD, dissolve, keep the
    # cropping SDs the report covers (those in the SD rainfall review)
    sd_crop = None
    if args.overlay in ("sd", "both"):
        conc = pd.read_csv(CONCORD)
        conc = conc[conc["STE_NAME21"] == args.state].copy()
        conc["SA2_CODE21"] = conc["SA2_CODE21"].astype(str)
        dom = conc.loc[conc.groupby("SA2_CODE21")["allocation_ratio"].idxmax()]
        merged = g.merge(dom[["SA2_CODE21", "SD_CODE11", "SD_NAME11"]],
                         on="SA2_CODE21")
        sd_all = merged.dissolve("SD_CODE11", aggfunc={"SD_NAME11": "first"})
        sdr = pd.read_csv(ROOT / f"data/features/"
                          f"sd_{args.year}_{args.month:02d}_rainfall_review"
                          f"{args.review_tag}.csv")
        crop_sd = set(sdr[sdr["state"] == ABBR[args.state]]["sd_code"].astype(int))
        sd_crop = sd_all[sd_all.index.isin(crop_sd)]

    from matplotlib.colors import BoundaryNorm, ListedColormap
    cmap = ListedColormap(CMAP_COLORS)
    cmap.set_bad(alpha=0)
    norm = BoundaryNorm(np.arange(-0.5, 7.5, 1), cmap.N)

    fig, ax = plt.subplots(figsize=(9.5, 11))
    mlat = float(np.mean(lats))
    ax.set_aspect(1.0 / np.cos(np.radians(mlat)))
    qm = ax.pcolormesh(lons, lats, np.ma.masked_invalid(cls),
                       cmap=cmap, norm=norm, shading="nearest")
    # clip the gridded field: to the cropland polygon when the field is restricted
    # to cropland; to the cropping-SD footprint when overlaying SD without a crop
    # mask; otherwise the whole state (state-wide field).
    if cropland_union is not None and args.field == "cropland":
        clip_geom = cropland_union
    elif args.crop_mask is None and args.overlay == "sd" \
            and sd_crop is not None and len(sd_crop):
        clip_geom = sd_crop.geometry.unary_union
    else:
        clip_geom = state_geom
    patch = PathPatch(geom_to_path(clip_geom), transform=ax.transData,
                      facecolor="none", edgecolor="none")
    ax.add_patch(patch)
    qm.set_clip_path(patch)
    # region boundaries overlaid — cut to the cropland footprint when masking
    def cut(gs):
        return gs.intersection(cropland_union) if cropland_union is not None else gs

    if args.overlay in ("sa2", "both"):
        cut(sa2_crop.geometry).boundary.plot(ax=ax, color="#1a1a1a",
                                             linewidth=0.4, alpha=0.6)
        if args.label_below is not None:
            dec_by_code = dict(zip(review_df["sa2_code"],
                                   review_df["decile_decimal"]))
            name_by_code = dict(zip(review_df["sa2_code"],
                                    review_df["sa2_name"]))
            below = []
            for _, r in sa2_crop.iterrows():
                code = r["SA2_CODE21"]
                if dec_by_code.get(code, 99) < args.label_below:
                    p = r.geometry.representative_point()
                    below.append((name_by_code.get(code, code),
                                  dec_by_code.get(code), p.y, p.x))
            # Callout style: stack labels down the left margin (over ocean),
            # ordered north→south so leader arrows don't cross, each arrow
            # pointing to its SA2 centroid.
            below.sort(key=lambda t: t[2], reverse=True)
            y0, dy = 0.30, 0.06
            for i, (name, dec, plat, plon) in enumerate(below):
                ax.annotate(
                    f"{name} (d{dec:.1f})",
                    xy=(plon, plat), xycoords="data",
                    xytext=(0.02, y0 - i * dy), textcoords="axes fraction",
                    fontsize=7.5, ha="left", va="center", weight="bold",
                    color="#7a0000",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white",
                              ec="#c0392b", alpha=0.95),
                    arrowprops=dict(arrowstyle="->", color="#7a0000", lw=0.9,
                                    shrinkB=3,
                                    connectionstyle="arc3,rad=0.15"))
    if args.overlay in ("sd", "both") and sd_crop is not None:
        cut(sd_crop.geometry).boundary.plot(ax=ax, color="#000000", linewidth=1.1)
        for _, r in sd_crop.iterrows():
            c = r.geometry.representative_point()
            ax.annotate(r["SD_NAME11"], (c.x, c.y), fontsize=7.5, ha="center",
                        va="center", weight="bold", color="#111111",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white",
                                  ec="#888", alpha=0.7))
    gpd.GeoSeries([state_geom]).boundary.plot(ax=ax, color="#000000",
                                              linewidth=0.8)

    ax.set_xlim(lon0, lon1)
    ax.set_ylim(lat0, lat1)
    ax.set_title(f"Monthly rainfall deciles for {args.state}\n"
                 f"01/{args.month:02d}/{args.year} – "
                 f"{through:02d}/{args.month:02d}/{args.year}",
                 fontsize=14, weight="bold")
    ax.set_axis_off()

    handles = [mpatches.Patch(facecolor=c, edgecolor="#888", label=lbl)
               for _, c, lbl in TIERS]
    leg = ax.legend(handles=handles, title="Rainfall decile ranges",
                    loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=9,
                    title_fontsize=10, frameon=False, handlelength=1.6,
                    handleheight=1.4, labelspacing=0.8)
    leg.get_title().set_fontweight("bold")

    ov = {"sd": "Statistical Division (report geography)", "sa2": "ABS 2021 SA2",
          "both": "SD + SA2", "none": "no"}[args.overlay]
    if args.crop_mask is None:
        note = f"; cropping {ov} boundaries overlaid."
    elif args.field == "cropland":
        note = (f". Field masked to ABARES CLUM cropland (dryland + irrigated) "
                f"≥{args.crop_mask:.0%} per cell; {ov} boundaries cut to it.")
    else:
        note = (f". State-wide field; {ov} boundaries cut to ABARES CLUM cropland "
                f"≥{args.crop_mask:.0%} per cell.")
    partial = ("" if through == dim else
               f" Partial month-to-date (days 1–{through} from the daily grid); "
               f"historical full months scaled ×{scale:.2f} for like-for-like.")
    fig.text(0.02, 0.04, f"Base period: {args.base_start}–{args.year-1} "
             f"({n} years). SILO/AGCD gridded rainfall, 0.05° per-cell "
             f"decile (no aggregation)" + note + partial,
             fontsize=7.5, color="#333")

    tag = f"_{args.overlay}"
    if args.crop_mask is not None:
        tag += ("statewide" if args.field == "statewide" else "") \
            + f"_crop{int(args.crop_mask*100):02d}"
    tag += args.review_tag
    out = (ROOT / f"reports/figures/decile_grid_bom_"
           f"{''.join(w[0] for w in args.state.split())}_"
           f"{args.year}_{args.month:02d}{tag}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
