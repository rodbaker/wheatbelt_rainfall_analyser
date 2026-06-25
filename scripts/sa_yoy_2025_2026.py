#!/usr/bin/env python3
"""South Australia year-over-year: 2026 vs 2025 wheat-weighted rainfall.

Refreshes the June-17 SA dual-window comparison against current data. Two
like-for-like windows, each decile-ranked against the 2005-2025 climatology:

  A) Apr 1 -> May 31    (complete-month window — canonical like-for-like)
  B) Apr 1 -> Jun N     (partial window; the older/historical June is scaled
                         N/30 so every year is measured over the same calendar
                         span as 2026's actual N-day month-to-date grid)

2026 June is the actual N-day SILO grid (data/features/sa2_2026_06_mtd.csv);
every other year's June is the monthly total scaled N/30. Apr/May come from the
national monthly history for both years. Wheat-area weighted (2020-21 universe),
SA grain SDs only.
"""
import statistics
from collections import defaultdict
from pathlib import Path

import pandas as pd

from src.rainfall.analytics import decile_score

ROOT = Path(__file__).resolve().parents[1]
ABS = Path("/home/roddyb/projects/ABS Census Data/Modernised_Census_2022_2025/"
           "comparison_2020_21_to_2022_23/acf_historical")
CONCORD = ABS / "concordances" / "sa2_2021_to_sd_2011_area_overlay.csv"
SA2_CROP = ROOT / "data/features/sa2_rainfall_crop_context.csv"
HIST = ROOT / "data/features/sa2_monthly_rainfall_history_national.csv"
JUN_MTD = ROOT / "data/features/sa2_2026_06_mtd.csv"

THROUGH = int(pd.read_csv(JUN_MTD)["partial_month_through_day"].dropna().iloc[0])
JS = THROUGH / 30
HY = list(range(2005, 2026))
FLOOR = 10_000.0


def wmean(vw):
    tw = sum(w for _, w in vw if w > 0)
    return sum(v * w for v, w in vw if w > 0) / tw if tw > 0 else None


def main():
    import csv

    ctx = pd.read_csv(SA2_CROP, low_memory=False)
    cw = ctx[(ctx["crop"] == "wheat") & (ctx["crop_context_year"] == "2020-21")]
    wheat = dict(zip(cw["abs_sa2_code"].astype(int),
                     cw["area_ha_for_weighting"].astype(float)))

    conc, sd_name = [], {}
    with open(CONCORD) as f:
        for r in csv.DictReader(f):
            if r["STE_NAME21"] != "South Australia":
                continue
            sd = int(r["SD_CODE11"])
            conc.append({"sa2": int(r["SA2_CODE21"]), "sd": sd,
                         "alloc": float(r["allocation_ratio"])})
            sd_name[sd] = r["SD_NAME11"]

    h = pd.read_csv(HIST, low_memory=False)
    h = h[h["month"].isin([4, 5, 6])]
    hist_m = defaultdict(dict)
    for _, r in h.iterrows():
        v = r["rainfall_mm"]
        if pd.notna(v) and v >= 0:
            hist_m[int(r["sa2_code"])][(int(r["year"]), int(r["month"]))] = float(v)

    jun = pd.read_csv(JUN_MTD)
    jun26 = dict(zip(jun["sa2_code"].astype(int), jun["rainfall_mm"].astype(float)))

    def aprmay(sa2, y):
        a = hist_m.get(sa2, {}).get((y, 4))
        m = hist_m.get(sa2, {}).get((y, 5))
        return None if a is None or m is None else a + m

    def june(sa2, y):
        """Scaled June for any year; 2026 uses the actual N-day grid."""
        if y == 2026:
            return jun26.get(sa2)
        j = hist_m.get(sa2, {}).get((y, 6))
        return None if j is None else j * JS

    def win(sa2, y, partial):
        am = aprmay(sa2, y)
        if am is None:
            return None
        if not partial:
            return am
        j = june(sa2, y)
        return None if j is None else am + j

    def decile_for(members, year, partial):
        cvw = [(win(m["sa2"], year, partial), m["w"]) for m in members]
        cwm = wmean([(v, w) for v, w in cvw if v is not None])
        ser = []
        for y in HY:
            vw = [(win(m["sa2"], y, partial), m["w"]) for m in members]
            wm = wmean([(v, w) for v, w in vw if v is not None])
            if wm is not None:
                ser.append(wm)
        if cwm is None or len(ser) < 10:
            return None
        med = statistics.median(ser)
        return (decile_score(ser, cwm), cwm,
                cwm / med * 100 if med > 0 else float("nan"))

    # SD membership (SA only)
    sd_members = defaultdict(list)
    for c in conc:
        w = wheat.get(c["sa2"], 0.0) * c["alloc"]
        if w > 0:
            sd_members[c["sd"]].append({"sa2": c["sa2"], "w": w})

    def block(members):
        out = {}
        for partial in (False, True):
            for yr in (2025, 2026):
                out[(partial, yr)] = decile_for(members, yr, partial)
        return out

    # State total
    all_members = [m for ms in sd_members.values() for m in ms]
    state = block(all_members)
    state_kha = sum(m["w"] for m in all_members) / 1000

    def fmt(d):
        return "   -" if d is None else f"{d[0]:4.1f} ({d[1]:4.0f}mm {d[2]:3.0f}%)"

    print(f"\n========== SOUTH AUSTRALIA — 2026 vs 2025 (wheat-weighted, "
          f"{state_kha:.0f} kha) ==========")
    print(f"Windows: A = Apr1-May31 complete | B = Apr1-Jun{THROUGH} "
          f"(hist/2025 June scaled {THROUGH}/30)\n")
    print("| Zone | Wheat kha | A 2025 | A 2026 | B 2025 | B 2026 |")
    print("|---|---:|---|---|---|---|")
    print(f"| **SOUTH AUSTRALIA** | **{state_kha:.0f}** "
          f"| {fmt(state[(False, 2025)])} | {fmt(state[(False, 2026)])} "
          f"| {fmt(state[(True, 2025)])} | {fmt(state[(True, 2026)])} |")

    rows = []
    for sd, members in sd_members.items():
        tw = sum(m["w"] for m in members)
        if tw < FLOOR:
            continue
        b = block(members)
        rows.append((tw, sd_name[sd], b))
    for tw, name, b in sorted(rows, reverse=True):
        print(f"| {name} | {tw/1000:.0f} "
              f"| {fmt(b[(False, 2025)])} | {fmt(b[(False, 2026)])} "
              f"| {fmt(b[(True, 2025)])} | {fmt(b[(True, 2026)])} |")

    print("\n_Decile vs 2005-2025 same window. Cell = decile (mm, % of median)._")


if __name__ == "__main__":
    main()
