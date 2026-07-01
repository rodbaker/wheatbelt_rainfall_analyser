#!/usr/bin/env python3
"""East-west drill of the three dry WA SDs (Midlands, Upper Great Southern,
Lower Great Southern) at SA2 level.

For each member wheat SA2: centroid longitude (west->east order), wheat area,
and both cumulative-window deciles — Mar 1->June MTD (profile) and May 1->June
MTD (recent / establishment). Lets us see whether the dry is worse on the
eastern (low-rainfall) margin or through the central belt.
"""
import calendar
import csv
import statistics
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.rainfall.analytics import decile_score

ROOT = Path(__file__).resolve().parents[1]
ABS = Path("/home/roddyb/projects/ABS Census Data/Modernised_Census_2022_2025/"
           "comparison_2020_21_to_2022_23/acf_historical")
CONCORD = ABS / "concordances" / "sa2_2021_to_sd_2011_area_overlay.csv"
SA2_CROP = ROOT / "data/features/sa2_rainfall_crop_context.csv"
HIST = ROOT / "data/features/sa2_monthly_rainfall_history_national.csv"
MAY_REVIEW = ROOT / "data/features/sa2_2026_05_rainfall_review.csv"
JUN_MTD = ROOT / "data/features/sa2_2026_06_mtd.csv"
GEOJSON = ROOT / "data/meta/SA2_ABS_Regions.geojson"

HY = list(range(2005, 2026))
TARGET_SDS = {"Midlands", "Upper Great Southern", "Lower Great Southern"}


def main():
    # centroids (lon) per SA2 — geojson is 2016 ASGS (SA2_MAIN16); for WA
    # wheatbelt the 2016/2021 codes match. Key by code and by name (fallback).
    gdf = gpd.read_file(GEOJSON)
    cent = gdf.geometry.centroid  # already EPSG:4326; fine for relative lon
    lon = dict(zip(gdf["SA2_MAIN16"].astype(int), cent.x))
    lon_by_name = dict(zip(gdf["SA2_NAME16"].astype(str), cent.x))

    # wheat weights
    ctx = pd.read_csv(SA2_CROP, low_memory=False)
    cw = ctx[(ctx["crop"] == "wheat") & (ctx["crop_context_year"] == "2020-21")]
    wheat = dict(zip(cw["abs_sa2_code"].astype(int),
                     cw["area_ha_for_weighting"].astype(float)))

    # dominant SD per SA2 (WA target SDs only)
    dom = {}
    with open(CONCORD) as f:
        for r in csv.DictReader(f):
            sa2 = int(r["SA2_CODE21"])
            al = float(r["allocation_ratio"])
            if sa2 not in dom or al > dom[sa2][1]:
                dom[sa2] = (r["SD_NAME11"], al)

    h = pd.read_csv(HIST, low_memory=False)
    h = h[h["month"].isin([3, 4, 5, 6])]
    hist_m = defaultdict(dict)
    name = {}
    for _, r in h.iterrows():
        v = r["rainfall_mm"]
        name[int(r["sa2_code"])] = r["sa2_name"]
        if pd.notna(v) and v >= 0:
            hist_m[int(r["sa2_code"])][(int(r["year"]), int(r["month"]))] = float(v)
    may = pd.read_csv(MAY_REVIEW)
    may26 = dict(zip(may["sa2_code"].astype(int), may["rain_mm"].astype(float)))
    jun = pd.read_csv(JUN_MTD)
    jun26 = dict(zip(jun["sa2_code"].astype(int), jun["rainfall_mm"].astype(float)))

    # June is a month-to-date (MTD) partial: scale historical full-June by the
    # same through-day fraction so current partial June is compared like-for-
    # like. Read the through-day at runtime rather than hardcoding it.
    jun_through_day = int(jun["partial_month_through_day"].dropna().max())
    days_in_june = calendar.monthrange(2026, 6)[1]
    js = jun_through_day / days_in_june
    print(f"# June MTD through day {jun_through_day}/{days_in_june} "
          f"(historical June scaled ×{js:.3f})")

    def cur(sa2, start):
        tot = 0.0
        for m in range(start, 6):
            v = may26.get(sa2) if m == 5 else hist_m.get(sa2, {}).get((2026, m))
            if v is None:
                return None
            tot += v
        j = jun26.get(sa2)
        return tot + j if j is not None else None

    def histw(sa2, y, start):
        tot = 0.0
        for m in range(start, 6):
            v = hist_m.get(sa2, {}).get((y, m))
            if v is None:
                return None
            tot += v
        j = hist_m.get(sa2, {}).get((y, 6))
        return tot + j * js if j is not None else None

    def dec(sa2, start):
        c = cur(sa2, start)
        s = [v for v in (histw(sa2, y, start) for y in HY) if v is not None]
        if c is None or len(s) < 10:
            return None, None, None
        med = statistics.median(s)
        return decile_score(s, c), (c / med * 100 if med > 0 else float("nan")), c
    rows = []
    for sa2, area in wheat.items():
        d = dom.get(sa2)
        if not d or d[0] not in TARGET_SDS:
            continue
        if area / 1000 < 10:  # keep ≥10 kha
            continue
        dA, pA, rawA = dec(sa2, 3)
        dB, pB, rawB = dec(sa2, 5)
        if dA is None or dB is None:
            continue
        nm = name.get(sa2, str(sa2))
        lo = lon.get(sa2, lon_by_name.get(nm, float("nan")))
        rows.append({"sd": d[0], "sa2": nm,
                     "lon": lo, "kha": area / 1000,
                     "marDec": dA, "marPct": pA, "mayDec": dB, "mayPct": pB,
                     "mayRain": rawB})
    df = pd.DataFrame(rows)

    for sd in ["Midlands", "Upper Great Southern", "Lower Great Southern"]:
        sub = df[df.sd == sd].sort_values("lon")  # west -> east
        if not len(sub):
            continue
        wk = sub.kha.sum()
        print(f"\n## {sd} (WA) — {len(sub)} wheat SA2s, {wk:.0f} kha — west→east")
        print("| SA2 | Lon°E | Wheat kha | May→MTD mm | Mar→MTD dec (%med) | "
              "May→MTD dec (%med) |")
        print("|---|---:|---:|---:|---:|---:|")
        for _, r in sub.iterrows():
            print(f"| {r.sa2} | {r.lon:.2f} | {r.kha:.0f} | {r.mayRain:.0f} "
                  f"| {r.marDec:.1f} ({r.marPct:.0f}%) "
                  f"| {r.mayDec:.1f} ({r.mayPct:.0f}%) |")
        # west vs east half by longitude (area-weighted mean May decile)
        med_lon = sub.lon.median()
        west = sub[sub.lon <= med_lon]
        east = sub[sub.lon > med_lon]
        for lbl, part in [("WEST half", west), ("EAST half", east)]:
            if len(part):
                awm = (part.mayDec * part.kha).sum() / part.kha.sum()
                print(f"  _{lbl}: area-wtd May→MTD decile = {awm:.1f} "
                      f"(lon {part.lon.min():.2f}-{part.lon.max():.2f})_")


if __name__ == "__main__":
    main()
