#!/usr/bin/env python3
"""BOM-format monthly rainfall decile map for one state's wheat-belt SA2s.

Mimics the Bureau's "Monthly rainfall deciles" layout (portrait state map, the
7-tier red->white->blue decile palette, right-side "Rainfall decile ranges"
legend, base-period footnote) so our SA2-level product can be eyeballed against
the official BOM map.

IMPORTANT — not identical to BOM:
  * baseline is 2005-2025 (21 yrs); BOM uses 1900-present. "On record" here means
    "in the 2005-2025 record". A longer baseline generally reads wet months lower.
  * values are SILO gridded, wheat-area aggregated to SA2 polygons; BOM is raw
    gridded with its own contouring. Only the grain-belt SA2s are filled.

Usage: python scripts/plot_decile_map_bom.py --year 2026 --month 5 --state "Western Australia"
"""
import argparse
import calendar
from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SHP = ("zip:///mnt/d/grains-data-store/wheatbelt_rainfall_analyser/data/meta/"
       "shapefiles/SA2_2021_AUST_SHP_GDA2020.zip")
MONTHS = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May",
          6: "June", 7: "July", 8: "August", 9: "September", 10: "October",
          11: "November", 12: "December"}

# BOM AGCD decile palette (dry -> wet), top-to-bottom legend order
TIERS = [
    ("highest", "#1c1cae", "Highest on record"),
    ("d10", "#6f6fcf", "10   Very much above average"),
    ("d89", "#c9cdeb", "8-9  Above average"),
    ("d47", "#ffffff", "4-7  Average"),
    ("d23", "#f7c5c5", "2-3  Below average"),
    ("d1", "#ed5f5f", "1    Very much below average"),
    ("lowest", "#e60000", "Lowest on record"),
]
COLOR = {k: c for k, c, _ in TIERS}


def bom_class(pr):
    """Map percentile_rank (0=driest, 100=wettest of the sample) to a BOM tier."""
    if pr >= 100:
        return "highest"
    if pr <= 0:
        return "lowest"
    if pr >= 90:
        return "d10"
    if pr >= 70:
        return "d89"
    if pr >= 30:
        return "d47"
    if pr >= 10:
        return "d23"
    return "d1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--month", type=int, default=5)
    ap.add_argument("--state", default="Western Australia")
    args = ap.parse_args()

    df = pd.read_csv(ROOT / f"data/features/"
                     f"sa2_{args.year}_{args.month:02d}_rainfall_review.csv")
    df["sa2_code"] = df["sa2_code"].astype(str)

    # end-of-window day: partial month if an MTD file pins a through-day
    last = calendar.monthrange(args.year, args.month)[1]
    mtd = ROOT / f"data/features/sa2_{args.year}_{args.month:02d}_mtd.csv"
    if mtd.exists():
        d = pd.read_csv(mtd)["partial_month_through_day"].dropna()
        if len(d):
            last = int(d.iloc[0])

    g = gpd.read_file(SHP)[["SA2_CODE21", "STE_NAME21", "geometry"]]
    g["SA2_CODE21"] = g["SA2_CODE21"].astype(str)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    state_poly = g[g["STE_NAME21"] == args.state].to_crs(3577)
    gdf = state_poly.merge(df, left_on="SA2_CODE21", right_on="sa2_code")
    gdf["tier"] = gdf["percentile_rank"].map(bom_class)
    gdf["fc"] = gdf["tier"].map(COLOR)

    fig, ax = plt.subplots(figsize=(9.5, 11))
    # full state outline (so non-cropping areas read as blank, like BOM's coast)
    state_poly.dissolve("STE_NAME21").plot(ax=ax, facecolor="white",
                                           edgecolor="#999999", linewidth=0.6)
    # filled grain-belt SA2s — no internal borders, to mimic a smooth field
    gdf.plot(ax=ax, color=gdf["fc"], edgecolor="none")
    state_poly.dissolve("STE_NAME21").boundary.plot(ax=ax, color="#555555",
                                                    linewidth=0.7)

    ax.set_title(f"Monthly rainfall deciles for {args.state}\n"
                 f"01/{args.month:02d}/{args.year} – "
                 f"{last:02d}/{args.month:02d}/{args.year}",
                 fontsize=14, weight="bold")
    ax.set_axis_off()

    # right-side legend block
    handles = [mpatches.Patch(facecolor=c, edgecolor="#888", label=lbl)
               for _, c, lbl in TIERS]
    leg = ax.legend(handles=handles, title="Rainfall decile ranges",
                    loc="center left", bbox_to_anchor=(1.0, 0.5),
                    fontsize=9, title_fontsize=10, frameon=False,
                    handlelength=1.6, handleheight=1.4, labelspacing=0.8)
    leg.get_title().set_fontweight("bold")

    fig.text(0.02, 0.045, f"Base period: 2005–2025 (21 years) — NOT BOM's "
             f"1900–present; “on record” = within this sample.",
             fontsize=7.5, color="#333333")
    fig.text(0.02, 0.022, "Dataset: SILO gridded (Data Drill), wheat-area "
             "aggregated to ABS 2021 SA2 polygons. Grain-belt SA2s only.",
             fontsize=7.5, color="#333333")

    out = (ROOT / f"reports/figures/decile_map_bom_"
           f"{''.join(w[0] for w in args.state.split())}_"
           f"{args.year}_{args.month:02d}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"wrote {out}  ({len(gdf)} SA2s, window end day {last})")


if __name__ == "__main__":
    main()
