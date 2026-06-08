"""Build SD- and SA2-level wheat-area-weighted rainfall breakdown for the
2026-W21 outlook v2 § 'SA2 / SD regional breakdown'.

Windows:
  - STD       = Jan-Apr 2026
  - Past month = Apr 2026
Both vs 2005-2025 historical median (per SA2, then weighted to SD).
SA2 weights = 2020-21 ABS wheat area x SA2->SD allocation ratio.
"""
from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path

import pandas as pd

from src.common.file_utils import atomic_csv_write
from src.rainfall.analytics import decile_rank

ROOT = Path("/home/roddyb/projects/wheatbelt_rainfall_analyser")
ABS = Path("/home/roddyb/projects/ABS Census Data/Modernised_Census_2022_2025/comparison_2020_21_to_2022_23/acf_historical")

CONCORD = ABS / "concordances" / "sa2_2021_to_sd_2011_area_overlay.csv"
SD_AGG = ABS / "census_to_sd_2020_21" / "census_2020_21_to_sd_aggregate.csv"
SA2_HIST = ROOT / "data/features/sa2_monthly_rainfall_history_national.csv"
SA2_CROP = ROOT / "data/features/sa2_rainfall_crop_context.csv"
SA2_DECILES = ROOT / "data/features/sa2_monthly_rainfall_deciles_national.csv"

OUT = ROOT / "data/features/sd_sa2_breakdown_2026W21.csv"
OUT_SA2 = ROOT / "data/features/sa2_breakdown_2026W21.csv"

JAN_APR = (1, 2, 3, 4)
APR = (4,)
HIST_YEARS = range(2005, 2026)  # 2005..2025 inclusive
TARGET_YEAR = 2026

WHEAT_AREA_FLOOR_HA = 10_000  # SD grain-belt filter


def load_sa2_wheat_area() -> dict[int, float]:
    """SA2 (9-digit code) -> 2020-21 wheat area_ha_for_weighting."""
    out: dict[int, float] = {}
    with SA2_CROP.open() as f:
        r = csv.DictReader(f)
        for row in r:
            if row["crop"] != "wheat" or row["crop_context_year"] != "2020-21":
                continue
            try:
                code = int(row["abs_sa2_code"])
                area = float(row["area_ha_for_weighting"] or 0)
            except ValueError:
                continue
            if area > 0:
                out[code] = area
    return out


def load_concordance() -> list[dict]:
    """List of {sa2_code, sd_code, sd_name, state, alloc_ratio}."""
    out = []
    with CONCORD.open() as f:
        r = csv.DictReader(f)
        for row in r:
            out.append({
                "sa2_code": int(row["SA2_CODE21"]),
                "sa2_name": row["SA2_NAME21"],
                "sd_code": int(row["SD_CODE11"]),
                "sd_name": row["SD_NAME11"],
                "state": row["STE_NAME21"],
                "alloc": float(row["allocation_ratio"]),
            })
    return out


def load_sd_wheat_area() -> dict[int, tuple[str, float]]:
    """SD_CODE11 -> (sd_name, wheat area_ha)."""
    out: dict[int, tuple[str, float]] = {}
    with SD_AGG.open() as f:
        r = csv.DictReader(f)
        for row in r:
            if row["commodity_code"] != "AGCEREAL_AHAWHT_F":
                continue
            try:
                code = int(row["SD_CODE11"])
                v = float(row["allocated_value"] or 0)
            except ValueError:
                continue
            out[code] = (row["SD_NAME11"], v)
    return out


def load_sa2_monthly() -> dict[tuple[int, int], dict[int, float]]:
    """(year, month) -> {sa2_code: rainfall_mm}. Skips partial months."""
    out: dict[tuple[int, int], dict[int, float]] = defaultdict(dict)
    with SA2_HIST.open() as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("is_partial_month") == "True":
                continue
            try:
                y, m, c = int(row["year"]), int(row["month"]), int(row["sa2_code"])
                v = float(row["rainfall_mm"])
            except (ValueError, KeyError):
                continue
            out[(y, m)][c] = v
    return out


def load_may_2026_partial() -> tuple[dict[int, float], dict[int, float], int]:
    """Return (sa2 -> May 1-day_through 2026 mm, sa2 -> historical full-May median, through_day)."""
    may_mtd: dict[int, float] = {}
    through_day = 0
    with SA2_HIST.open() as f:
        r = csv.DictReader(f)
        for row in r:
            if int(row["year"]) != TARGET_YEAR or int(row["month"]) != 5:
                continue
            try:
                c = int(row["sa2_code"])
                may_mtd[c] = float(row["rainfall_mm"])
                if row.get("partial_month_through_day"):
                    through_day = max(through_day, int(float(row["partial_month_through_day"])))
            except (ValueError, KeyError):
                continue

    # historical_median_mm is null on the partial 2026 row; pick it up from any
    # prior-year May row (same median is repeated per SA2 across all years).
    may_median: dict[int, float] = {}
    with SA2_DECILES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            if int(row["month"]) != 5 or int(row["year"]) == TARGET_YEAR:
                continue
            if not row.get("historical_median_mm"):
                continue
            try:
                c = int(row["sa2_code"])
                may_median.setdefault(c, float(row["historical_median_mm"]))
            except (ValueError, KeyError):
                continue
    return may_mtd, may_median, through_day


def sa2_period_total(monthly: dict, sa2: int, year: int, months: tuple[int, ...]) -> float | None:
    """Sum SA2 rainfall over months; None if any month missing."""
    tot = 0.0
    for m in months:
        v = monthly.get((year, m), {}).get(sa2)
        if v is None:
            return None
        tot += v
    return tot


def weighted_mean(values_weights: list[tuple[float, float]]) -> float | None:
    w_sum = sum(w for _, w in values_weights if w > 0)
    if w_sum <= 0:
        return None
    return sum(v * w for v, w in values_weights if w > 0) / w_sum


def decile(value: float, history: list[float]) -> float:
    """Return 1..10 decile rank of value against history (canonical convention)."""
    d = decile_rank(history, value)
    return float(d) if d is not None else float("nan")


def main() -> None:
    print("Loading inputs...")
    wheat = load_sa2_wheat_area()
    conc = load_concordance()
    sd_meta = load_sd_wheat_area()
    monthly = load_sa2_monthly()
    print(f"  SA2 wheat-area rows: {len(wheat)}")
    print(f"  Concordance rows:    {len(conc)}")
    print(f"  SD wheat rows:       {len(sd_meta)}")
    print(f"  Monthly rainfall keys (year,month): {len(monthly)}")

    # Restrict concordance rows to SA2s that have wheat area
    conc_w = [c for c in conc if c["sa2_code"] in wheat]
    print(f"  Concordance rows w/ SA2 wheat area: {len(conc_w)}")

    # Build SA2 weight per SD: weight = sa2_wheat_area * allocation_ratio
    # Index by SD
    sd_to_sa2 = defaultdict(list)
    for c in conc_w:
        w = wheat[c["sa2_code"]] * c["alloc"]
        if w > 0:
            sd_to_sa2[c["sd_code"]].append({
                "sa2_code": c["sa2_code"],
                "sa2_name": c["sa2_name"],
                "state": c["state"],
                "weight": w,
            })

    # ---- SA2-level metrics (one row per SA2; STD + past-month + medians) ----
    sa2_rows = []
    for sa2_code in wheat:
        std_2026 = sa2_period_total(monthly, sa2_code, TARGET_YEAR, JAN_APR)
        apr_2026 = sa2_period_total(monthly, sa2_code, TARGET_YEAR, APR)
        std_hist = [
            v for y in HIST_YEARS
            if (v := sa2_period_total(monthly, sa2_code, y, JAN_APR)) is not None
        ]
        apr_hist = [
            v for y in HIST_YEARS
            if (v := sa2_period_total(monthly, sa2_code, y, APR)) is not None
        ]
        if not std_hist or not apr_hist or std_2026 is None or apr_2026 is None:
            continue
        sa2_rows.append({
            "sa2_code": sa2_code,
            "wheat_area_ha": wheat[sa2_code],
            "std_2026": std_2026,
            "std_median": statistics.median(std_hist),
            "std_decile": decile(std_2026, std_hist),
            "apr_2026": apr_2026,
            "apr_median": statistics.median(apr_hist),
            "apr_decile": decile(apr_2026, apr_hist),
        })
    sa2_idx = {r["sa2_code"]: r for r in sa2_rows}
    print(f"  SA2 rows with complete history: {len(sa2_idx)}")

    # ---- SD-level rollups ----
    sd_out = []
    for sd_code, entries in sd_to_sa2.items():
        sd_name, sd_wheat = sd_meta.get(sd_code, (f"SD {sd_code}", 0))
        if sd_wheat < WHEAT_AREA_FLOOR_HA:
            continue
        # Determine dominant state from member SA2s by weight
        state_w = defaultdict(float)
        for e in entries:
            state_w[e["state"]] += e["weight"]
        dom_state = max(state_w, key=state_w.get)

        # Weighted means (2026 vals + historical medians) using SA2 weights
        def wm(field: str) -> float | None:
            return weighted_mean([
                (sa2_idx[e["sa2_code"]][field], e["weight"])
                for e in entries if e["sa2_code"] in sa2_idx
            ])

        std_2026 = wm("std_2026")
        std_med = wm("std_median")
        apr_2026 = wm("apr_2026")
        apr_med = wm("apr_median")
        if None in (std_2026, std_med, apr_2026, apr_med):
            continue

        # SD-level decile: build SD-weighted historical Jan-Apr / Apr per year
        std_hist_sd = []
        apr_hist_sd = []
        for y in HIST_YEARS:
            std_yr = weighted_mean([
                (v, e["weight"])
                for e in entries
                if (v := sa2_period_total(monthly, e["sa2_code"], y, JAN_APR)) is not None
            ])
            apr_yr = weighted_mean([
                (v, e["weight"])
                for e in entries
                if (v := sa2_period_total(monthly, e["sa2_code"], y, APR)) is not None
            ])
            if std_yr is not None:
                std_hist_sd.append(std_yr)
            if apr_yr is not None:
                apr_hist_sd.append(apr_yr)
        std_dec = decile(std_2026, std_hist_sd)
        apr_dec = decile(apr_2026, apr_hist_sd)

        sd_out.append({
            "sd_code": sd_code,
            "sd_name": sd_name,
            "state": dom_state,
            "sd_wheat_ha": sd_wheat,
            "std_2026": std_2026,
            "std_median": std_med,
            "std_decile": std_dec,
            "std_pct": 100.0 * std_2026 / std_med if std_med > 0 else None,
            "apr_2026": apr_2026,
            "apr_median": apr_med,
            "apr_decile": apr_dec,
            "apr_pct": 100.0 * apr_2026 / apr_med if apr_med > 0 else None,
        })

    # ---- May 2026 MTD per SD (weighted) ----
    may_mtd_sa2, may_med_sa2, may_through = load_may_2026_partial()
    print(f"  May 2026 partial through day: {may_through}; SA2 rows: {len(may_mtd_sa2)}")
    for sd_row in sd_out:
        members = sd_to_sa2[sd_row["sd_code"]]
        mtd = weighted_mean([
            (may_mtd_sa2[e["sa2_code"]], e["weight"])
            for e in members if e["sa2_code"] in may_mtd_sa2
        ])
        med = weighted_mean([
            (may_med_sa2[e["sa2_code"]], e["weight"])
            for e in members if e["sa2_code"] in may_med_sa2
        ])
        sd_row["may_mtd_2026"] = mtd
        sd_row["may_full_median"] = med
        sd_row["may_gap_to_median"] = (med - mtd) if (mtd is not None and med is not None) else None
        sd_row["may_pct_of_full_median"] = (100.0 * mtd / med) if (mtd is not None and med and med > 0) else None
    sd_row_extras_ok = True

    sd_out.sort(key=lambda r: (-r["sd_wheat_ha"],))

    # ---- For each SD, pick top SA2 movers ----
    sa2_callouts = defaultdict(list)
    for sd_row in sd_out:
        sd_code = sd_row["sd_code"]
        members = sd_to_sa2[sd_code]
        cand = []
        for e in members:
            r = sa2_idx.get(e["sa2_code"])
            if not r or r["apr_median"] <= 0:
                continue
            apr_pct = 100.0 * r["apr_2026"] / r["apr_median"]
            std_pct = 100.0 * r["std_2026"] / r["std_median"] if r["std_median"] > 0 else None
            cand.append({
                "sa2_code": e["sa2_code"],
                "sa2_name": e["sa2_name"],
                "weight": e["weight"],
                "wheat_ha": wheat[e["sa2_code"]],
                "apr_2026": r["apr_2026"],
                "apr_pct": apr_pct,
                "apr_decile": r["apr_decile"],
                "std_2026": r["std_2026"],
                "std_pct": std_pct,
                "std_decile": r["std_decile"],
            })
        # Rank by absolute Apr % deviation from 100, weighted by wheat area
        cand.sort(key=lambda x: -x["wheat_ha"])
        # Take top 5 by wheat area, then pick the wettest + driest by apr_pct
        top_wheat = cand[:8]
        if not top_wheat:
            continue
        top_wheat.sort(key=lambda x: x["apr_pct"])
        picks = []
        if len(top_wheat) >= 1:
            picks.append(top_wheat[0])  # driest
        if len(top_wheat) >= 2:
            picks.append(top_wheat[-1])  # wettest
        sa2_callouts[sd_code] = picks

    # ---- Write CSVs ----
    if not atomic_csv_write(pd.DataFrame(sd_out), OUT):
        raise SystemExit(f"Failed to write {OUT}")
    print(f"Wrote {OUT} ({len(sd_out)} SDs)")

    sa2_flat = []
    for sd_row in sd_out:
        for c in sa2_callouts.get(sd_row["sd_code"], []):
            sa2_flat.append({"sd_code": sd_row["sd_code"], "sd_name": sd_row["sd_name"], **c})
    if sa2_flat:
        if not atomic_csv_write(pd.DataFrame(sa2_flat), OUT_SA2):
            raise SystemExit(f"Failed to write {OUT_SA2}")
        print(f"Wrote {OUT_SA2} ({len(sa2_flat)} SA2 callouts)")

    # ---- Print markdown ----
    print("\n=== MARKDOWN (May MTD by SD) ===\n")
    print(f"_May 2026 partial through day {may_through} of 31._\n")
    print("| SD (state) | Wheat (kha) | May 1–{d} 2026 (mm) | Full-May median (mm) | mm to reach median |".replace("{d}", str(may_through)))
    print("|---|---:|---:|---:|---:|")
    for r in sd_out:
        mtd = r.get("may_mtd_2026")
        med = r.get("may_full_median")
        gap = r.get("may_gap_to_median")
        if mtd is None or med is None:
            continue
        gap_disp = f"{max(0, gap):.0f}" if gap is not None else "—"
        print(
            f"| {r['sd_name']} ({r['state'][:3].upper()}) "
            f"| {r['sd_wheat_ha']/1000:.0f} "
            f"| {mtd:.0f} | {med:.0f} | {gap_disp} |"
        )

    print("\n=== MARKDOWN ===\n")
    print("| SD (state) | Wheat area (kha) | STD Jan–Apr 2026 (mm) | % of median | Decile | Apr 2026 (mm) | % of median | Decile |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in sd_out:
        print(
            f"| {r['sd_name']} ({r['state'][:3].upper()}) "
            f"| {r['sd_wheat_ha']/1000:.0f} "
            f"| {r['std_2026']:.0f} | {r['std_pct']:.0f}% | {r['std_decile']:.0f} "
            f"| {r['apr_2026']:.0f} | {r['apr_pct']:.0f}% | {r['apr_decile']:.0f} |"
        )
    print()
    print("=== SA2 callouts (driest / wettest within top 8 wheat SA2s per SD) ===\n")
    for sd_row in sd_out:
        cs = sa2_callouts.get(sd_row["sd_code"], [])
        if not cs:
            continue
        bits = []
        for c in cs:
            bits.append(f"{c['sa2_name']} (Apr {c['apr_2026']:.0f} mm, {c['apr_pct']:.0f}% of median, decile {c['apr_decile']:.0f})")
        print(f"- **{sd_row['sd_name']}** — " + "; ".join(bits))


if __name__ == "__main__":
    main()
