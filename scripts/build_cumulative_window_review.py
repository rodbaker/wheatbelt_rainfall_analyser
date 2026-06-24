#!/usr/bin/env python3
"""Cumulative in-season rainfall window (March -> current MTD), wheat-area
weighted by state and SD, with deciles vs the same window 2005-2025.

Mirrors build_sd_monthly_rainfall_review.py weighting + decile conventions.

2026 actuals per SA2:
  - Mar, Apr: full months from sa2_monthly_rainfall_history_national.csv
  - May:      COMPLETED month from sa2_2026_05_rainfall_review.csv
              (history May 2026 is the stale day-27 snapshot; the review is the
              re-pulled completed month)
  - Jun 1-8:  daily-grid sum from sa2_2026_06_mtd.csv (through_day = 8)

Historical window per year y (2005-2025):
  Mar(y) + Apr(y) + May(y) [full months from history]
  + Jun(y) * (8/30)  [full-June history scaled to the same 8-day tail]

Two windows reported:
  A) Mar-May  (clean: all full months, no scaling)
  B) Mar->Jun8 (adds the scaled-June tail)

State decile = state wheat-weighted window total ranked vs the 21 historical
year windows (same method as the monthly builder's state decile).
"""
import calendar
import csv
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.rainfall.analytics import decile_rank, decile_score, percentile_rank

ROOT = Path(__file__).resolve().parents[1]
ABS = Path(
    "/home/roddyb/projects/ABS Census Data/Modernised_Census_2022_2025/"
    "comparison_2020_21_to_2022_23/acf_historical"
)
CONCORD = ABS / "concordances" / "sa2_2021_to_sd_2011_area_overlay.csv"
SA2_CROP = ROOT / "data/features/sa2_rainfall_crop_context.csv"
SA2_HIST = ROOT / "data/features/sa2_monthly_rainfall_history_national.csv"
MAY_REVIEW = ROOT / "data/features/sa2_2026_05_rainfall_review.csv"
JUN_MTD = ROOT / "data/features/sa2_2026_06_mtd.csv"

YEAR = 2026
HIST_YEARS = list(range(2005, YEAR))
WHEAT_FLOOR_HA = 10_000.0
WHEATBELT_STATES = {
    "Western Australia", "South Australia", "Victoria",
    "New South Wales", "Queensland",
}
STATE_ABBR = {
    "Western Australia": "WA", "South Australia": "SA", "Victoria": "Vic",
    "New South Wales": "NSW", "Queensland": "Qld",
}
STATE_ORDER = ["WA", "SA", "Vic", "NSW", "Qld"]


def weighted_mean(vals_weights):
    total_w = sum(w for _, w in vals_weights if w > 0)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in vals_weights if w > 0) / total_w


def load_wheat_areas():
    wheat = {}
    with open(SA2_CROP) as f:
        for row in csv.DictReader(f):
            if row["crop"] != "wheat" or row["crop_context_year"] != "2020-21":
                continue
            try:
                wheat[int(row["abs_sa2_code"])] = float(
                    row["area_ha_for_weighting"] or 0
                )
            except ValueError:
                pass
    return wheat


def load_concordance():
    conc, sd_name = [], {}
    with open(CONCORD) as f:
        for row in csv.DictReader(f):
            sd = int(row["SD_CODE11"])
            conc.append({
                "sa2_code": int(row["SA2_CODE21"]),
                "sd_code": sd,
                "sd_name": row["SD_NAME11"],
                "ste": row["STE_NAME21"],
                "alloc": float(row["allocation_ratio"]),
            })
            sd_name[sd] = row["SD_NAME11"]
    return conc, sd_name


def load_sa2_col(path, code_col, val_col, filt=None):
    out = {}
    df = pd.read_csv(path, low_memory=False)
    for _, r in df.iterrows():
        if filt and not filt(r):
            continue
        v = float(r[val_col])
        if np.isnan(v) or v < 0:
            continue
        out[int(r[code_col])] = v
    return out


def main():
    jun_scale = 8.0 / calendar.monthrange(2026, 6)[1]  # 8/30

    wheat = load_wheat_areas()
    conc, sd_name = load_concordance()

    # ---- historical full-month per-SA2 values, months 3..6
    hist = pd.read_csv(SA2_HIST, low_memory=False)
    h = hist[(hist["month"].isin([3, 4, 5, 6]))
             & (hist["is_partial_month"] != True)]  # noqa: E712
    hist_m = defaultdict(dict)  # sa2 -> {(year, month): mm}
    for _, r in h.iterrows():
        v = r["rainfall_mm"]
        if pd.isna(v) or v < 0:
            continue
        hist_m[int(r["sa2_code"])][(int(r["year"]), int(r["month"]))] = float(v)

    # ---- 2026 actuals
    may26 = load_sa2_col(MAY_REVIEW, "sa2_code", "rain_mm")
    jun26 = load_sa2_col(JUN_MTD, "sa2_code", "rainfall_mm")

    def window_2026(sa2, include_june):
        mar = hist_m.get(sa2, {}).get((2026, 3))
        apr = hist_m.get(sa2, {}).get((2026, 4))
        may = may26.get(sa2)
        if mar is None or apr is None or may is None:
            return None
        tot = mar + apr + may
        if include_june:
            jun = jun26.get(sa2)
            if jun is None:
                return None
            tot += jun
        return tot

    def window_hist(sa2, y, include_june):
        mar = hist_m.get(sa2, {}).get((y, 3))
        apr = hist_m.get(sa2, {}).get((y, 4))
        may = hist_m.get(sa2, {}).get((y, 5))
        if mar is None or apr is None or may is None:
            return None
        tot = mar + apr + may
        if include_june:
            jun = hist_m.get(sa2, {}).get((y, 6))
            if jun is None:
                return None
            tot += jun * jun_scale
        return tot

    # ---- SD membership + weights
    sd_members = defaultdict(list)
    sd_state_weight = defaultdict(lambda: defaultdict(float))
    for c in conc:
        w = wheat.get(c["sa2_code"], 0.0) * c["alloc"]
        if w <= 0:
            continue
        sd_members[c["sd_code"]].append({"sa2_code": c["sa2_code"], "weight": w})
        sd_state_weight[c["sd_code"]][c["ste"]] += w

    def build(include_june):
        # per-SD
        sd_rows = []
        sd_state_of = {}
        for sd_code, members in sd_members.items():
            total_w = sum(m["weight"] for m in members)
            if total_w < WHEAT_FLOOR_HA:
                continue
            ste = max(sd_state_weight[sd_code].items(), key=lambda kv: kv[1])[0]
            if ste not in WHEATBELT_STATES:
                continue
            abbr = STATE_ABBR[ste]
            sd_state_of[sd_code] = abbr

            cur_vw = [(window_2026(m["sa2_code"], include_june), m["weight"])
                      for m in members]
            cur_vw = [(v, w) for v, w in cur_vw if v is not None]
            cur_wm = weighted_mean(cur_vw)
            if cur_wm is None:
                continue
            yr_series = []
            for y in HIST_YEARS:
                vw = [(window_hist(m["sa2_code"], y, include_june), m["weight"])
                      for m in members]
                vw = [(v, w) for v, w in vw if v is not None]
                wm = weighted_mean(vw)
                if wm is not None:
                    yr_series.append(wm)
            if not yr_series:
                continue
            med = statistics.median(yr_series)
            sd_rows.append({
                "sd_name": sd_name[sd_code], "state": abbr,
                "wheat_kha": total_w / 1000.0, "rain_mm": cur_wm,
                "median_mm": med,
                "pct_of_median": cur_wm / med * 100 if med > 0 else float("nan"),
                "decile": decile_rank(yr_series, cur_wm),
                "decile_decimal": decile_score(yr_series, cur_wm),
            })

        # per-state (state-weighted window ranked vs history)
        members_by_state = defaultdict(list)
        for sd_code, members in sd_members.items():
            if sd_code in sd_state_of:
                members_by_state[sd_state_of[sd_code]].extend(members)
        state_rows = []
        for abbr, members in members_by_state.items():
            cur_vw = [(window_2026(m["sa2_code"], include_june), m["weight"])
                      for m in members]
            cur_vw = [(v, w) for v, w in cur_vw if v is not None]
            cur_wm = weighted_mean(cur_vw)
            yr_series = []
            for y in HIST_YEARS:
                vw = [(window_hist(m["sa2_code"], y, include_june), m["weight"])
                      for m in members]
                vw = [(v, w) for v, w in vw if v is not None]
                wm = weighted_mean(vw)
                if wm is not None:
                    yr_series.append(wm)
            if cur_wm is None or not yr_series:
                continue
            med = statistics.median(yr_series)
            total_w = sum(m["weight"] for m in members)
            state_rows.append({
                "state": abbr, "wheat_kha": total_w / 1000.0,
                "rain_mm": cur_wm, "median_mm": med,
                "pct_of_median": cur_wm / med * 100 if med > 0 else float("nan"),
                "decile_decimal": decile_score(yr_series, cur_wm),
                "percentile_rank": percentile_rank(yr_series, cur_wm),
            })
        return pd.DataFrame(state_rows), pd.DataFrame(sd_rows)

    def flag(d):
        return "(dry)" if d <= 3 else ("(mid)" if d <= 6 else "(wet)")

    for include_june, label in [(False, "March-May (completed, clean)"),
                                (True, "March 1 -> June 8 (June tail scaled 8/30)")]:
        state_df, sd_df = build(include_june)
        state_df["__o"] = state_df["state"].map(
            {s: i for i, s in enumerate(STATE_ORDER)})
        state_df = state_df.sort_values("__o").drop(columns="__o")
        print(f"\n\n========== WINDOW: {label} ==========\n")
        print("| State | Wheat (kha) | Rain (mm) | Median (mm) | % median | Decile |")
        print("|---|---:|---:|---:|---:|---:|")
        for _, r in state_df.iterrows():
            print(f"| {r['state']} | {r['wheat_kha']:.0f} | {r['rain_mm']:.0f} "
                  f"| {r['median_mm']:.0f} | {r['pct_of_median']:.0f}% "
                  f"| {r['decile_decimal']:.1f} {flag(r['decile_decimal'])} |")
        # SD detail, key states
        for abbr in STATE_ORDER:
            sub = sd_df[sd_df["state"] == abbr].sort_values(
                "wheat_kha", ascending=False)
            if len(sub) == 0:
                continue
            print(f"\n### {abbr} grain SDs")
            print("| SD | Wheat (kha) | Rain (mm) | Median (mm) | % median | Decile |")
            print("|---|---:|---:|---:|---:|---:|")
            for _, r in sub.iterrows():
                print(f"| {r['sd_name']} | {r['wheat_kha']:.0f} | {r['rain_mm']:.0f} "
                      f"| {r['median_mm']:.0f} | {r['pct_of_median']:.0f}% "
                      f"| {r['decile_decimal']:.1f} {flag(r['decile_decimal'])} |")

    # ---- SA2-level highlights for the March 1 -> June 8 window ----
    meta = pd.read_csv(MAY_REVIEW)  # sa2_code, sa2_name, state, sd_name, wheat_kha
    sa2_rows = []
    for _, m in meta.iterrows():
        sa2 = int(m["sa2_code"])
        wk = float(m["wheat_kha"])
        cur = window_2026(sa2, True)
        if cur is None:
            continue
        series = [v for v in (window_hist(sa2, y, True) for y in HIST_YEARS)
                  if v is not None]
        if len(series) < 10:
            continue
        med = statistics.median(series)
        sa2_rows.append({
            "sa2": m["sa2_name"], "state": m["state"], "sd": m["sd_name"],
            "wheat_kha": wk, "rain": cur, "median": med,
            "pct": cur / med * 100 if med > 0 else float("nan"),
            "dec": decile_score(series, cur),
        })
    sdf = pd.DataFrame(sa2_rows)
    mat = sdf[sdf["wheat_kha"] >= 80].copy()  # material wheat-area SA2s only

    def show(title, rows):
        print(f"\n### {title}")
        print("| SA2 | State | SD | Wheat (kha) | Rain (mm) | % median | Decile |")
        print("|---|---|---|---:|---:|---:|---:|")
        for _, r in rows.iterrows():
            print(f"| {r['sa2']} | {r['state']} | {r['sd']} | {r['wheat_kha']:.0f} "
                  f"| {r['rain']:.0f} | {r['pct']:.0f}% | {r['dec']:.1f} |")

    print("\n\n========== SA2 HIGHLIGHTS (March 1 -> June 8, wheat >= 80 kha) ==========")
    good = mat[mat["dec"] >= 7].sort_values("dec", ascending=False)
    avg = mat[(mat["dec"] >= 4) & (mat["dec"] < 7)].copy()
    avg["d5"] = (avg["dec"] - 5).abs()
    avg = avg.sort_values("d5")
    bad = mat[mat["dec"] < 4].sort_values("dec")
    show("GOOD (decile >= 7) — top 8 by area-relevant wetness", good.head(8))
    show("AVERAGE (decile 4-7) — 8 nearest to median", avg.head(8))
    show("BAD (decile < 4) — driest 8", bad.head(8))
    print(f"\n_Material SA2s: {len(mat)} (>=80 kha). "
          f"good={len(good)} avg={len(avg)} bad={len(bad)}._")


if __name__ == "__main__":
    main()
