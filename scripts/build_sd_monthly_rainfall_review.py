#!/usr/bin/env python3
"""Build a COMPLETED-month area-weighted rainfall review per ABS Statistical
Division (SD_CODE11) across the five wheatbelt states.

Generalises the one-off scripts/_vic_sd_may_deciles.py (VIC-only, hardcoded
May 2026) to any --year --month and ALL SD codes present in the SA2->SD
concordance. Each SD's dominant state is derived by summing member-SA2 wheat
weights per STE_NAME21.

Month totals for the target year come from the SILO DAILY grid summed over
the whole month (data/features/sa2_{year}_{month:02d}_mtd.csv, produced by
scripts/extract_sa2_partial_month_rainfall.py). THROUGH_DAY is read
dynamically from that file; SCALE = THROUGH_DAY / days_in_month (== 1.0 for a
completed month, < 1.0 for a partial month, with the historical baseline
scaled to match the same window).

Historical baseline: full-month per-year SA2 values from
sa2_monthly_rainfall_history_national.csv (is_partial_month != True) for the
same month, years BASELINE_START..(year-1), scaled by SCALE.

Weight per SA2 = wheat area_ha_for_weighting * allocation_ratio. SDs are kept
only if total wheat weight >= WHEAT_FLOOR_HA (grain-belt filter).

Outputs (paths parameterised by year/month):
    data/features/sd_{year}_{month:02d}_rainfall_review.csv
    data/features/state_{year}_{month:02d}_rainfall_review.csv
and prints clean markdown tables (per-state SD tables + state summary +
driest/wettest callouts) to stdout for pasting into the monthly report.

NOTE on nodata: SILO daily cells that are all-negative over the month are
nodata sentinels (e.g. -594.5 sums). Any SA2 with a negative month total is
treated as nodata and dropped from its SD's weighting (never fabricated).

Usage:
    poetry run python scripts/build_sd_monthly_rainfall_review.py --year 2026 --month 5
    poetry run python scripts/build_sd_monthly_rainfall_review.py --year 2026 --month 5 \
        --mtd data/features/sa2_2026_05_mtd.csv
"""
import argparse
import calendar
import csv
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ABS = Path(
    "/home/roddyb/projects/ABS Census Data/Modernised_Census_2022_2025/"
    "comparison_2020_21_to_2022_23/acf_historical"
)

CONCORD = ABS / "concordances" / "sa2_2021_to_sd_2011_area_overlay.csv"
SA2_CROP = ROOT / "data/features/sa2_rainfall_crop_context.csv"
SA2_HIST = ROOT / "data/features/sa2_monthly_rainfall_history_national.csv"

BASELINE_START = 2005  # historical baseline first year (inclusive)
WHEAT_FLOOR_HA = 10_000.0  # grain-belt floor, as in build_sd_sa2_breakdown.py

# Five wheatbelt states only.
WHEATBELT_STATES = {
    "Western Australia",
    "South Australia",
    "Victoria",
    "New South Wales",
    "Queensland",
}
STATE_ABBR = {
    "Western Australia": "WA",
    "South Australia": "SA",
    "Victoria": "Vic",
    "New South Wales": "NSW",
    "Queensland": "Qld",
}
STATE_ORDER = ["WA", "SA", "Vic", "NSW", "Qld"]


def weighted_mean(vals_weights):
    total_w = sum(w for _, w in vals_weights if w > 0)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in vals_weights if w > 0) / total_w


def pct_rank(arr, val):
    a = np.array([x for x in arr if not np.isnan(x)])
    return float((a < val).sum() / len(a) * 100) if len(a) else float("nan")


def decile_from_pct(p):
    if np.isnan(p):
        return None
    return max(1, min(10, int(p / 10) + 1))


def load_wheat_areas():
    """abs_sa2_code -> 2020-21 wheat area_ha_for_weighting."""
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
    """Return (conc rows, sd_code -> sd_name)."""
    conc = []
    sd_name = {}
    with open(CONCORD) as f:
        for row in csv.DictReader(f):
            sd = int(row["SD_CODE11"])
            conc.append(
                {
                    "sa2_code": int(row["SA2_CODE21"]),
                    "sd_code": sd,
                    "sd_name": row["SD_NAME11"],
                    "ste": row["STE_NAME21"],
                    "alloc": float(row["allocation_ratio"]),
                }
            )
            sd_name[sd] = row["SD_NAME11"]
    return conc, sd_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True, help="1-12")
    parser.add_argument(
        "--mtd",
        default=None,
        help="Override path to the daily-grid month-sum CSV "
        "(default: data/features/sa2_{year}_{month:02d}_mtd.csv).",
    )
    parser.add_argument(
        "--baseline-start",
        type=int,
        default=BASELINE_START,
        help=f"First historical baseline year (default {BASELINE_START}).",
    )
    args = parser.parse_args()

    year, month = args.year, args.month
    if not 1 <= month <= 12:
        parser.error("--month must be 1-12")
    days_in_month = calendar.monthrange(year, month)[1]
    hist_years = list(range(args.baseline_start, year))  # ..year-1 inclusive
    month_name = calendar.month_name[month]

    mtd_path = (
        Path(args.mtd)
        if args.mtd
        else ROOT / f"data/features/sa2_{year}_{month:02d}_mtd.csv"
    )
    if not mtd_path.exists():
        parser.error(
            f"month-sum CSV not found: {mtd_path}\n"
            f"Run: poetry run python scripts/extract_sa2_partial_month_rainfall.py "
            f"--year {year} --month {month} --universe-source combined"
        )
    out_sd = ROOT / f"data/features/sd_{year}_{month:02d}_rainfall_review.csv"
    out_state = ROOT / f"data/features/state_{year}_{month:02d}_rainfall_review.csv"

    wheat = load_wheat_areas()
    conc, sd_name = load_concordance()

    # ---- target-month SA2 totals (DAILY grid sum)
    mtd = pd.read_csv(mtd_path)
    through_days = sorted(mtd["partial_month_through_day"].dropna().unique())
    if len(through_days) != 1:
        print(f"WARNING: multiple through_day values found: {through_days}")
    through_day = int(through_days[-1]) if through_days else days_in_month
    scale = through_day / days_in_month
    # Map sa2_code -> month mm; drop nodata (negative-summed) cells.
    target_rain = {}
    nodata_sa2 = []
    for _, r in mtd.iterrows():
        code = int(r["sa2_code"])
        val = float(r["rainfall_mm"])
        if np.isnan(val) or val < 0:
            nodata_sa2.append((code, r["sa2_name"], r["state_name"], val))
            continue
        target_rain[code] = val

    # ---- historical full-month SA2 values (not partial)
    hist = pd.read_csv(SA2_HIST, low_memory=False)
    month_hist = hist[
        (hist["month"] == month)
        & (hist["year"].isin(hist_years))
        & (hist["is_partial_month"] != True)  # noqa: E712
    ]
    hist_lookup = defaultdict(dict)  # sa2_code -> {year: full_month_mm}
    for _, r in month_hist.iterrows():
        v = r["rainfall_mm"]
        if pd.isna(v) or v < 0:
            continue
        hist_lookup[int(r["sa2_code"])][int(r["year"])] = float(v)

    # ---- build SD membership with weights (all SDs; floor applied later)
    sd_members = defaultdict(list)
    sd_state_weight = defaultdict(lambda: defaultdict(float))
    for c in conc:
        w = wheat.get(c["sa2_code"], 0.0) * c["alloc"]
        if w <= 0:
            continue
        sd_members[c["sd_code"]].append({"sa2_code": c["sa2_code"], "weight": w})
        sd_state_weight[c["sd_code"]][c["ste"]] += w

    # ---- compute per-SD metrics
    sd_rows = []
    for sd_code, members in sd_members.items():
        total_w = sum(m["weight"] for m in members)
        if total_w < WHEAT_FLOOR_HA:
            continue
        ste = max(sd_state_weight[sd_code].items(), key=lambda kv: kv[1])[0]
        if ste not in WHEATBELT_STATES:
            continue
        state_abbr = STATE_ABBR[ste]

        target_vw = []
        for m in members:
            v = target_rain.get(m["sa2_code"])
            if v is None:
                continue
            target_vw.append((v, m["weight"]))
        target_wm = weighted_mean(target_vw)
        if target_wm is None:
            continue

        hist_yr_wm = []
        for y in hist_years:
            yr_vw = []
            for m in members:
                hv = hist_lookup.get(m["sa2_code"], {}).get(y)
                if hv is None:
                    continue
                yr_vw.append((hv * scale, m["weight"]))
            wm = weighted_mean(yr_vw)
            if wm is not None:
                hist_yr_wm.append(wm)
        if not hist_yr_wm:
            continue

        med = statistics.median(hist_yr_wm)
        pct = target_wm / med * 100 if med > 0 else float("nan")
        pr = pct_rank(hist_yr_wm, target_wm)
        dec = decile_from_pct(pr)
        anomaly = target_wm - med

        sd_rows.append(
            {
                "sd_code": sd_code,
                "sd_name": sd_name[sd_code],
                "state": state_abbr,
                "state_full": ste,
                "wheat_kha": total_w / 1000.0,
                "rain_mm": target_wm,
                "hist_scaled_median_mm": med,
                "pct_of_median": pct,
                "percentile_rank": pr,
                "decile": dec,
                "anomaly_mm": anomaly,
                "n_hist_years": len(hist_yr_wm),
            }
        )

    if not sd_rows:
        raise SystemExit(
            "No SDs passed the grain-belt floor — check inputs for "
            f"{year}-{month:02d}."
        )

    sd_df = pd.DataFrame(sd_rows)
    sd_df = sd_df.sort_values(
        ["state", "wheat_kha"], ascending=[True, False]
    ).reset_index(drop=True)

    # ---- per-STATE rollup, area-weighted across that state's SDs
    state_rows = []
    for ste in WHEATBELT_STATES:
        abbr = STATE_ABBR[ste]
        sub = sd_df[sd_df["state"] == abbr]
        if len(sub) == 0:
            continue
        w = sub["wheat_kha"].values * 1000.0
        tot_w = w.sum()
        rain_wm = float((sub["rain_mm"].values * w).sum() / tot_w)
        med_wm = float((sub["hist_scaled_median_mm"].values * w).sum() / tot_w)
        pct = rain_wm / med_wm * 100 if med_wm > 0 else float("nan")
        state_rows.append(
            {
                "state": abbr,
                "state_full": ste,
                "wheat_kha": tot_w / 1000.0,
                "rain_mm": rain_wm,
                "hist_scaled_median_mm": med_wm,
                "pct_of_median": pct,
                "n_sds": len(sub),
            }
        )

    # ---- proper state-level decile: state-weighted per-year history vs target
    sd_state_of = {r["sd_code"]: r["state"] for r in sd_rows}
    members_by_state = defaultdict(list)
    for sd_code, members in sd_members.items():
        if sd_code in sd_state_of:
            members_by_state[sd_state_of[sd_code]].extend(members)

    state_decile, state_pr = {}, {}
    for abbr, members in members_by_state.items():
        target_vw = [
            (target_rain[m["sa2_code"]], m["weight"])
            for m in members
            if m["sa2_code"] in target_rain
        ]
        rain_wm = weighted_mean(target_vw)
        yr_series = []
        for y in hist_years:
            yr_vw = []
            for m in members:
                hv = hist_lookup.get(m["sa2_code"], {}).get(y)
                if hv is not None:
                    yr_vw.append((hv * scale, m["weight"]))
            wm = weighted_mean(yr_vw)
            if wm is not None:
                yr_series.append(wm)
        if rain_wm is not None and yr_series:
            pr = pct_rank(yr_series, rain_wm)
            state_pr[abbr] = pr
            state_decile[abbr] = decile_from_pct(pr)

    for sr in state_rows:
        sr["percentile_rank"] = state_pr.get(sr["state"], float("nan"))
        sr["decile"] = state_decile.get(sr["state"])

    state_df = pd.DataFrame(state_rows)
    state_df["__ord"] = state_df["state"].map(
        {s: i for i, s in enumerate(STATE_ORDER)}
    )
    state_df = (
        state_df.sort_values("__ord").drop(columns="__ord").reset_index(drop=True)
    )

    # ---- write CSVs
    round_cols = [
        "wheat_kha",
        "rain_mm",
        "hist_scaled_median_mm",
        "pct_of_median",
        "percentile_rank",
        "anomaly_mm",
    ]
    sd_out = sd_df.copy()
    for col in round_cols:
        sd_out[col] = sd_out[col].round(1)
    sd_out.to_csv(out_sd, index=False)

    state_out = state_df.copy()
    for col in [c for c in round_cols if c in state_out.columns]:
        state_out[col] = state_out[col].round(1)
    state_out.to_csv(out_state, index=False)

    # ---- print markdown
    def flag(d):
        if d is None:
            return ""
        return "(dry)" if d <= 3 else ("(mid)" if d <= 6 else "(wet)")

    print()
    print(
        f"# {month_name} {year} Wheatbelt Rainfall Review by ABS Statistical Division"
    )
    print()
    note = (
        "completed month, true full-month comparison"
        if through_day == days_in_month
        else f"days 1-{through_day}, history scaled to {through_day}/{days_in_month}"
    )
    print(
        f"_{month_name} {year} from SILO daily grid through day {through_day} "
        f"({note}). Baseline: full-{month_name} "
        f"{hist_years[0]}-{hist_years[-1]}, SCALE={scale:.3f}._"
    )
    if nodata_sa2:
        print()
        print(
            "_Nodata SA2s dropped (negative SILO sentinel sums): "
            + ", ".join(f"{n} ({s})" for _, n, s, _ in nodata_sa2)
            + "._"
        )

    print()
    print("## State summary")
    print()
    print("| State | Wheat (kha) | Rain (mm) | % of median | Decile |")
    print("|---|---:|---:|---:|---:|")
    for _, r in state_df.iterrows():
        print(
            f"| {r['state']} | {r['wheat_kha']:.0f} | {r['rain_mm']:.1f} "
            f"| {r['pct_of_median']:.0f}% | D{r['decile']} {flag(r['decile'])} |"
        )

    for abbr in STATE_ORDER:
        sub = sd_df[sd_df["state"] == abbr]
        if len(sub) == 0:
            continue
        full = sub["state_full"].iloc[0]
        print()
        print(f"## {full} ({abbr}) — {len(sub)} grain SDs")
        print()
        print(
            "| SD | Wheat (kha) | Rain (mm) | Hist median mm "
            "| % of median | Decile | Anomaly mm |"
        )
        print("|---|---:|---:|---:|---:|---:|---:|")
        for _, r in sub.iterrows():
            print(
                f"| {r['sd_name']} | {r['wheat_kha']:.0f} | {r['rain_mm']:.1f} "
                f"| {r['hist_scaled_median_mm']:.1f} | {r['pct_of_median']:.0f}% "
                f"| D{r['decile']} {flag(r['decile'])} | {r['anomaly_mm']:+.1f} |"
            )

    print()
    print("## Per-state driest / wettest grain SD")
    print()
    print("| State | Driest SD | Decile | % med | Wettest SD | Decile | % med |")
    print("|---|---|---:|---:|---|---:|---:|")
    for abbr in STATE_ORDER:
        sub = sd_df[sd_df["state"] == abbr]
        if len(sub) == 0:
            continue
        driest = sub.sort_values(["decile", "pct_of_median"]).iloc[0]
        wettest = sub.sort_values(
            ["decile", "pct_of_median"], ascending=False
        ).iloc[0]
        print(
            f"| {abbr} | {driest['sd_name']} | D{driest['decile']} "
            f"| {driest['pct_of_median']:.0f}% | {wettest['sd_name']} "
            f"| D{wettest['decile']} | {wettest['pct_of_median']:.0f}% |"
        )

    print()
    print(f"_Written: {out_sd}_")
    print(f"_Written: {out_state}_")
    print(
        f"_SD count: {len(sd_df)}; through_day={through_day}/{days_in_month}; "
        f"scale={scale:.3f}_"
    )


if __name__ == "__main__":
    main()
