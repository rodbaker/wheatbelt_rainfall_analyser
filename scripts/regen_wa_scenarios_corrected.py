#!/usr/bin/env python3
"""Regenerate WA wheat production scenarios on the CORRECTED full-geography
wheat universe, with completed-May 2026, and reproduce the W21 BOM-weighted
central for comparison.

WA seasonal rainfall (jan_mar, apr_may, jun_oct) is area-weighted over the FULL
WA wheat SA2 universe (sa2_rainfall_crop_context.csv, 2020-21 wheat area). The
rainfall history join is on the 9-digit sa2_code directly (no 5-digit hop), so
nothing is dropped. For 2026, May is taken from the COMPLETED-month review
(sa2_2026_05_rainfall_review.csv) rather than the partial history snapshot.

Analogues: top-3 nearest years on standardised (jan_mar, apr_may) Euclidean
distance — identical algorithm to run_yield_analogue.py.

Production per analogue = analogue ABARES yield x 2025 ABARES area.
BOM-weighted central = P(above)*mean(Jun-Aug-above analogues)
                       + P(below)*mean(Jun-Aug-below analogues).
"""
import statistics
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "data/features/sa2_monthly_rainfall_history_national.csv"
FULLCTX = ROOT / "data/features/sa2_rainfall_crop_context.csv"
MAY_REVIEW = ROOT / "data/features/sa2_2026_05_rainfall_review.csv"
ABARES = ROOT / "data/meta/abares/abares_crop_production_normalized.csv"

TARGET = 2026
WINDOWS = {"jan_mar": [1, 2, 3], "apr_may": [4, 5], "jun_oct": [6, 7, 8, 9, 10]}
# WA Jun-Aug median for the above/below bucket (long-run, from W21 method).
# BOM Jun-Aug 2026: P(above-median) = 30%  ->  P(below) = 70%.
BOM_P_ABOVE = 0.30
JUN_AUG = [6, 7, 8]


def wa_wheat_weights():
    ctx = pd.read_csv(FULLCTX, low_memory=False)
    w = ctx[(ctx["crop"] == "wheat") & (ctx["crop_context_year"] == "2020-21")
            & (ctx["state"].astype(str).str.contains("Western", na=False))]
    return dict(zip(w["abs_sa2_code"].astype(int),
                    w["area_ha_for_weighting"].astype(float)))


def main():
    weights = wa_wheat_weights()
    wa_codes = set(weights)
    print(f"WA wheat SA2s in corrected universe: {len(wa_codes)}  "
          f"total {sum(weights.values())/1000:.0f} kha")

    hist = pd.read_csv(HIST, low_memory=False)
    hist = hist[hist["sa2_code"].astype(int).isin(wa_codes)].copy()
    hist["sa2_code"] = hist["sa2_code"].astype(int)

    # completed-May 2026 per SA2
    may = pd.read_csv(MAY_REVIEW)
    may26 = dict(zip(may["sa2_code"].astype(int), may["rain_mm"].astype(float)))

    import os
    USE_COMPLETED_MAY = os.environ.get("COMPLETED_MAY", "1") == "1"

    def month_val(sa2, year, month):
        if year == TARGET and month == 5 and USE_COMPLETED_MAY:
            return may26.get(sa2)
        r = hist[(hist["sa2_code"] == sa2) & (hist["year"] == year)
                 & (hist["month"] == month)]
        if r.empty:
            return None
        # exclude partial-month except not relevant here (we override May)
        v = float(r["rainfall_mm"].iloc[0])
        return v if v >= 0 else None

    def window_weighted(year, months):
        num = den = 0.0
        for sa2, wt in weights.items():
            tot = 0.0
            ok = True
            for m in months:
                v = month_val(sa2, year, m)
                if v is None:
                    ok = False
                    break
                tot += v
            if ok:
                num += tot * wt
                den += wt
        return num / den if den > 0 else None

    years = list(range(2005, TARGET + 1))
    rows = {}
    for y in years:
        rows[y] = {w: window_weighted(y, ms) for w, ms in WINDOWS.items()}

    # ---- analogue selection on (jan_mar, apr_may), corrected + completed May
    sel_w = ["jan_mar", "apr_may"]
    histyrs = [y for y in years if y < TARGET
               and all(rows[y][w] is not None for w in sel_w)]
    means = {w: statistics.mean(rows[y][w] for y in histyrs) for w in sel_w}
    stds = {w: statistics.pstdev([rows[y][w] for y in histyrs]) for w in sel_w}
    # sample std to match pandas .std() (ddof=1)
    stds = {w: statistics.stdev([rows[y][w] for y in histyrs]) for w in sel_w}

    tvec = {w: (rows[TARGET][w] - means[w]) / stds[w] for w in sel_w}
    dists = []
    for y in histyrs:
        d = np.sqrt(sum(((rows[y][w] - means[w]) / stds[w] - tvec[w]) ** 2
                        for w in sel_w))
        dists.append((y, d))
    dists.sort(key=lambda x: x[1])
    analogues = [y for y, _ in dists[:3]]

    print(f"\n2026 WA windows (corrected geom, completed May): "
          f"jan_mar={rows[TARGET]['jan_mar']:.1f}  apr_may={rows[TARGET]['apr_may']:.1f}")
    print(f"Nearest analogues: " +
          ", ".join(f"{y} (d={d:.3f})" for y, d in dists[:5]))

    # ---- ABARES yields/areas
    ab = pd.read_csv(ABARES)
    w = ab[(ab["crop"] == "Wheat") & (ab["state"] == "WA")]
    piv = w.pivot_table(index="crop_season", columns="metric",
                        values="value_normalized", aggfunc="first")
    area_2025 = piv.loc[2025, "Area"]

    def yield_of(y):
        return piv.loc[y, "Production"] / piv.loc[y, "Area"]

    def junaug_above(y):
        ja = window_weighted(y, JUN_AUG)
        return ja

    ja_hist_median = statistics.median(
        [window_weighted(y, JUN_AUG) for y in histyrs])

    print(f"\nJun-Aug long-run median (corrected geom): {ja_hist_median:.1f} mm")
    print("\n| Analogue | Jun-Aug mm | bucket | Sep-Oct mm | yield t/ha | prod=Y*2025area Mt |")
    print("|---|---:|---|---:|---:|---:|")
    above, below = [], []
    for y in analogues:
        ja = junaug_above(y)
        so = window_weighted(y, [9, 10])
        yld = yield_of(y)
        prod = yld * area_2025 / 1e6
        bucket = "above" if ja >= ja_hist_median else "below"
        (above if bucket == "above" else below).append(prod)
        print(f"| {y} | {ja:.0f} | {bucket} | {so:.0f} | {yld:.2f} | {prod:.2f} |")

    mean_above = statistics.mean(above) if above else None
    mean_below = statistics.mean(below) if below else None
    # BOM-weighted central (W21 method)
    if above and below:
        central = BOM_P_ABOVE * mean_above + (1 - BOM_P_ABOVE) * mean_below
    elif above:
        central = mean_above
    else:
        central = mean_below
    mean_simple = statistics.mean(above + below)

    print(f"\nMean analogue production (simple): {mean_simple:.2f} Mt")
    print(f"BOM-weighted central (P_above={BOM_P_ABOVE}): "
          f"{central:.2f} Mt   [above set mean={mean_above}, below set mean={mean_below}]")
    print(f"Range across analogues: {min(above+below):.2f} - {max(above+below):.2f} Mt")
    print(f"\nW21 published: analogues 2009/2018/2020, BOM-weighted central 8.85 Mt")


if __name__ == "__main__":
    main()
