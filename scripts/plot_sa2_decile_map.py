#!/usr/bin/env python3
"""Choropleth map of wheat-belt SA2s coloured by rainfall decile.

Joins the SA2 rainfall review (decile_decimal) to 2021 ABS SA2 boundaries and
renders a BOM-style decile map (dry = red, wet = blue), state outlines overlaid,
notable wet/dry SA2s labelled.

Usage: python scripts/plot_sa2_decile_map.py --year 2026 --month 6
"""
import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SHP = ("zip:///mnt/d/grains-data-store/wheatbelt_rainfall_analyser/data/meta/"
       "shapefiles/SA2_2021_AUST_SHP_GDA2020.zip")
MONTHS = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May",
          6: "June", 7: "July", 8: "August", 9: "September", 10: "October",
          11: "November", 12: "December"}

# SA2s to label (by name substring) so the map tells its story; the label-box
# colour follows each region's ACTUAL decile that month, not a fixed wet/dry list
LABEL_SA2 = ["Gnowangerup", "Wagin", "Morawa", "Esperance Surrounds",
             "Mukinbudin", "Kimba"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--month", type=int, default=6)
    ap.add_argument("--region", default=None,
                    help="state name to zoom to (e.g. 'Western Australia'); "
                         "default shows all of Australia")
    args = ap.parse_args()

    review = ROOT / f"data/features/sa2_{args.year}_{args.month:02d}_rainfall_review.csv"
    df = pd.read_csv(review)
    through = ""
    mtd = ROOT / f"data/features/sa2_{args.year}_{args.month:02d}_mtd.csv"
    if mtd.exists():
        d = pd.read_csv(mtd)["partial_month_through_day"].dropna()
        if len(d):
            through = f" 1–{int(d.iloc[0])}"

    g = gpd.read_file(SHP)[["SA2_CODE21", "SA2_NAME21", "STE_NAME21", "geometry"]]
    g["SA2_CODE21"] = g["SA2_CODE21"].astype(str)
    df["sa2_code"] = df["sa2_code"].astype(str)
    gdf = g.merge(df, left_on="SA2_CODE21", right_on="sa2_code", how="inner")
    gdf = gdf.to_crs(3577)  # GDA2020 Australian Albers — equal-area for mapping

    # BOM-style decile classes: dry (1-3) reds, average (4-7) white, wet (8-10) blues
    bounds = [0, 1, 2, 3, 4, 6, 8, 9, 10, 10.001]
    colors = ["#67000d", "#cb181d", "#fb6a4a", "#fcae91", "#f7f7f7",
              "#c6dbef", "#6baed6", "#2171b5", "#08306b"]
    cmap = mcolors.ListedColormap(colors)
    norm = mcolors.BoundaryNorm(bounds, cmap.N)

    fig, ax = plt.subplots(figsize=(13, 11))
    gdf.plot(column="decile_decimal", cmap=cmap, norm=norm, linewidth=0.2,
             edgecolor="#555555", ax=ax, legend=False)

    # full-Australia state/territory outlines (drop non-spatial SA2s — "No usual
    # address", "Migratory/Offshore", "Outside Australia" carry null geometry)
    full = g[g.geometry.notna() & ~g.geometry.is_empty].to_crs(3577)
    full.dissolve("STE_NAME21").boundary.plot(ax=ax, color="black", linewidth=0.7)

    # labels — box colour follows the region's actual decile this month
    def label(names):
        for nm in names:
            sel = gdf[gdf["SA2_NAME21"].str.contains(nm, case=False, na=False)]
            for _, r in sel.iterrows():
                d = r.decile_decimal
                box = "#67000d" if d < 4 else ("#08306b" if d > 7 else "#444444")
                c = r.geometry.representative_point()
                ax.annotate(f"{r.SA2_NAME21.split(' - ')[0].split(' (')[0]}\n"
                            f"d{d:.0f}",
                            (c.x, c.y), fontsize=7.5, ha="center", va="center",
                            color="white", weight="bold",
                            bbox=dict(boxstyle="round,pad=0.15", fc=box,
                                      ec="none", alpha=0.9))

    label(LABEL_SA2)

    # optional zoom to one state's grain SA2 extent
    suffix = ""
    if args.region:
        reg = gdf[gdf["STE_NAME21"] == args.region]
        if reg.empty:
            raise SystemExit(f"no grain SA2s for region {args.region!r}")
        b = reg.total_bounds
        mx, my = (b[2] - b[0]) * 0.08, (b[3] - b[1]) * 0.08
        ax.set_xlim(b[0] - mx, b[2] + mx)
        ax.set_ylim(b[1] - my, b[3] + my)
        suffix = "_" + "".join(w[0] for w in args.region.split())

    # discrete legend
    labels = ["1 (very dry)", "2", "3", "4–5", "6–7", "8", "9", "10 (very wet)"]
    legcolors = colors[:3] + [colors[3], colors[4], colors[6], colors[7], colors[8]]
    handles = [plt.Rectangle((0, 0), 1, 1, fc=c, ec="#555") for c in legcolors]
    ax.legend(handles, labels, title="Rainfall decile\n(vs 2005–2025)",
              loc="lower left", fontsize=9, title_fontsize=9, frameon=True)

    ax.set_title(f"{MONTHS[args.month]} {args.year}{through} rainfall decile — "
                 f"wheat-belt SA2s\n(SILO gridded, decile vs 2005–2025 climatology)",
                 fontsize=14, weight="bold")
    ax.set_axis_off()
    fig.tight_layout()

    out = (ROOT / f"reports/figures/"
           f"sa2_decile_map_{args.year}_{args.month:02d}{suffix}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"wrote {out}  ({len(gdf)} SA2s)")


if __name__ == "__main__":
    main()
