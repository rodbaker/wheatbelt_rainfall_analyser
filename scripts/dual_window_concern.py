#!/usr/bin/env python3
"""Dual-window concern analysis.

Two cumulative windows, both ending at the June month-to-date tail (through
day N, read dynamically from the MTD file; historical June scaled N/30):
  A) March 1 -> Jun N   (full-season accumulation incl. summer/autumn profile)
  B) May 1   -> Jun N   (recent rain only — establishment-window conditions)

Cross-classifying the two isolates *why* a region is dry:
  - dry A + dry B   = PERSISTENT DRY  (real concern: no profile, no recent rain)
  - dry A + wet B   = RECOVERED       (profile-light past, wet now -> spring risk)
  - wet A + dry B   = FADING          (stored moisture, recent dry -> watch)
  - wet A + wet B   = SOLID

Wheat-area weighted (2020-21 full universe). Deciles vs 2005-2025 same window.
"""
import csv
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
MAY_REVIEW = ROOT / "data/features/sa2_2026_05_rainfall_review.csv"
JUN_MTD = ROOT / "data/features/sa2_2026_06_mtd.csv"

# Scale historical June to the SAME partial window as 2026's actual MTD.
# Read the through-day dynamically from the MTD file — never hardcode it; the
# file advances each time SILO is refreshed (was day 8, now day 23, ...).
_JUN_THROUGH_DAY = int(
    pd.read_csv(JUN_MTD)["partial_month_through_day"].dropna().iloc[0]
)
JS = _JUN_THROUGH_DAY / 30  # June has 30 days
HY = list(range(2005, 2026))
FLOOR = 10_000.0
STATES = {"Western Australia", "South Australia", "Victoria",
          "New South Wales", "Queensland"}
ABBR = {"Western Australia": "WA", "South Australia": "SA", "Victoria": "Vic",
        "New South Wales": "NSW", "Queensland": "Qld"}
ORDER = ["WA", "SA", "Vic", "NSW", "Qld"]


def wmean(vw):
    tw = sum(w for _, w in vw if w > 0)
    return sum(v * w for v, w in vw if w > 0) / tw if tw > 0 else None


def cls(d):
    return "dry" if d < 4 else ("avg" if d < 7 else "wet")


def main():
    ctx = pd.read_csv(SA2_CROP, low_memory=False)
    cw = ctx[(ctx["crop"] == "wheat") & (ctx["crop_context_year"] == "2020-21")]
    wheat = dict(zip(cw["abs_sa2_code"].astype(int),
                     cw["area_ha_for_weighting"].astype(float)))

    conc, sd_name = [], {}
    with open(CONCORD) as f:
        for r in csv.DictReader(f):
            sd = int(r["SD_CODE11"])
            conc.append({"sa2": int(r["SA2_CODE21"]), "sd": sd,
                         "ste": r["STE_NAME21"], "alloc": float(r["allocation_ratio"])})
            sd_name[sd] = r["SD_NAME11"]

    h = pd.read_csv(HIST, low_memory=False)
    h = h[h["month"].isin([3, 4, 5, 6])]
    hist_m = defaultdict(dict)
    for _, r in h.iterrows():
        v = r["rainfall_mm"]
        if pd.notna(v) and v >= 0:
            hist_m[int(r["sa2_code"])][(int(r["year"]), int(r["month"]))] = float(v)

    may = pd.read_csv(MAY_REVIEW)
    may26 = dict(zip(may["sa2_code"].astype(int), may["rain_mm"].astype(float)))
    jun = pd.read_csv(JUN_MTD)
    jun26 = dict(zip(jun["sa2_code"].astype(int), jun["rainfall_mm"].astype(float)))

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
        return tot + j * JS if j is not None else None

    def decile(members, start):
        cvw = [(cur(m["sa2"], start), m["w"]) for m in members]
        cvw = [(v, w) for v, w in cvw if v is not None]
        cwm = wmean(cvw)
        ser = []
        for y in HY:
            vw = [(histw(m["sa2"], y, start), m["w"]) for m in members]
            vw = [(v, w) for v, w in vw if v is not None]
            wm = wmean(vw)
            if wm is not None:
                ser.append(wm)
        if cwm is None or len(ser) < 10:
            return None
        med = statistics.median(ser)
        return decile_score(ser, cwm), cwm / med * 100 if med > 0 else float("nan")

    # ---- SD membership
    sd_members = defaultdict(list)
    sd_stw = defaultdict(lambda: defaultdict(float))
    for c in conc:
        w = wheat.get(c["sa2"], 0.0) * c["alloc"]
        if w <= 0:
            continue
        sd_members[c["sd"]].append({"sa2": c["sa2"], "w": w})
        sd_stw[c["sd"]][c["ste"]] += w

    sd_rows = []
    for sd, members in sd_members.items():
        tw = sum(m["w"] for m in members)
        if tw < FLOOR:
            continue
        ste = max(sd_stw[sd].items(), key=lambda kv: kv[1])[0]
        if ste not in STATES:
            continue
        A = decile(members, 3)
        B = decile(members, 5)
        if A is None or B is None:
            continue
        sd_rows.append({"sd": sd_name[sd], "state": ABBR[ste], "kha": tw / 1000,
                        "decA": A[0], "pctA": A[1], "decB": B[0], "pctB": B[1]})
    sd_df = pd.DataFrame(sd_rows)

    def quad(a, b):
        ca, cb = cls(a), cls(b)
        if ca == "dry" and cb == "dry":
            return "🔴 PERSISTENT DRY"
        if ca == "dry" and cb == "wet":
            return "🟢 recovered"
        if ca == "wet" and cb == "dry":
            return "🟠 fading"
        if ca == "wet" and cb == "wet":
            return "🟢 solid"
        return "🟡 mixed"

    sd_df["flag"] = [quad(a, b) for a, b in zip(sd_df.decA, sd_df.decB)]
    sd_df["__o"] = sd_df.state.map({s: i for i, s in enumerate(ORDER)})
    sd_df = sd_df.sort_values(["__o", "kha"], ascending=[True, False])

    print("\n========== SD-LEVEL: dual-window (Mar->MTD vs May->MTD) ==========\n")
    print("| SD | State | Wheat kha | Mar→MTD dec (%med) | May→MTD dec (%med) | Class |")
    print("|---|---|---:|---:|---:|---|")
    for _, r in sd_df.iterrows():
        print(f"| {r.sd} | {r.state} | {r.kha:.0f} | {r.decA:.1f} ({r.pctA:.0f}%) "
              f"| {r.decB:.1f} ({r.pctB:.0f}%) | {r.flag} |")

    # ---- SA2 level (material >=80 kha), own-history deciles
    meta = may[["sa2_code", "sa2_name", "state", "sd_name"]].copy()
    meta["wheat_kha"] = may["wheat_kha"]
    sa2_rows = []
    for _, m in meta.iterrows():
        sa2 = int(m["sa2_code"])
        wk = float(m["wheat_kha"])
        if wk < 80:
            continue
        cA, cB = cur(sa2, 3), cur(sa2, 5)
        if cA is None or cB is None:
            continue
        sA = [v for v in (histw(sa2, y, 3) for y in HY) if v is not None]
        sB = [v for v in (histw(sa2, y, 5) for y in HY) if v is not None]
        if len(sA) < 10 or len(sB) < 10:
            continue
        dA = decile_score(sA, cA)
        dB = decile_score(sB, cB)
        sa2_rows.append({"sa2": m["sa2_name"], "state": m["state"],
                         "sd": m["sd_name"], "kha": wk, "decA": dA, "decB": dB,
                         "flag": quad(dA, dB)})
    sa2_df = pd.DataFrame(sa2_rows)

    def show(title, sub):
        print(f"\n### {title}  ({len(sub)})")
        print("| SA2 | State · SD | Wheat kha | Mar→MTD dec | May→MTD dec |")
        print("|---|---|---:|---:|---:|")
        for _, r in sub.iterrows():
            print(f"| {r.sa2} | {r.state} · {r.sd} | {r.kha:.0f} "
                  f"| {r.decA:.1f} | {r.decB:.1f} |")

    print("\n\n========== SA2-LEVEL CROSS-CLASSIFICATION (wheat >= 80 kha) ==========")
    persist = sa2_df[sa2_df.flag == "🔴 PERSISTENT DRY"].sort_values(["decA", "decB"])
    recov = sa2_df[sa2_df.flag == "🟢 recovered"].sort_values("decB", ascending=False)
    fading = sa2_df[sa2_df.flag == "🟠 fading"].sort_values("decB")
    show("🔴 PERSISTENT DRY — dry on BOTH (real concern)", persist)
    show("🟢 RECOVERED — dry Mar→MTD, wet May→MTD (profile-light, est. ok)",
         recov.head(8))
    show("🟠 FADING — wet Mar→MTD, dry May→MTD (stored moisture, recent dry)",
         fading.head(8))
    print(f"\n_Material SA2s: {len(sa2_df)}. persistent={len(persist)} "
          f"recovered={len(recov)} fading={len(fading)}._")


if __name__ == "__main__":
    main()
