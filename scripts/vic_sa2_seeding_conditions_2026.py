#!/usr/bin/env python3
"""Victoria SA2-level seeding conditions report — 2026 autumn season.

Combines April 2026 monthly rainfall + May 2026 MTD (days 1 to the latest
available day, read from partial_month_through_day at runtime) to rank
each grain-belt SA2 in Victoria on:
  - April rainfall vs Apr climatology
  - May MTD vs May climatology (scaled to partial month)
  - Apr+May combined vs Apr+May climatology
  - Seeding adequacy classification using CropForecaster thresholds

Seeding thresholds (from config/crop_calendars.yaml):
  Adequate break  : ≥ 25 mm / 7-day window
  Marginal        : 15–24 mm / 7 day
  Marginal low    : 10–14 mm / 7 day
  Insufficient    : < 10 mm / 7 day

For monthly-level analysis we treat:
  Adequate    : May MTD ≥ 25 mm  (first clean trigger)
  Marginal    : 15–24 mm May MTD
  Marginal low: 10–14 mm
  Insufficient: < 10 mm

Apr+May combined classification:
  Strong season   : ≥ 70 mm combined (equivalent to ~half the typical winter)
  Adequate season : 40–69 mm
  Below average   : 20–39 mm
  Poor            : < 20 mm

Outputs:
  reports/weekly/vic_sa2_seeding_conditions_2026_W21.md   Markdown report
  data/features/vic_sa2_seeding_2026.csv                  Machine-readable

Usage:
  python scripts/vic_sa2_seeding_conditions_2026.py
  python scripts/vic_sa2_seeding_conditions_2026.py --no-report
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.file_utils import atomic_csv_write
from src.rainfall.analytics import decile_rank, percentile_rank

REPO_ROOT = Path(__file__).resolve().parents[1]
HIST_PATH = REPO_ROOT / "data/features/sa2_monthly_rainfall_history_national.csv"
MTD_PATH = REPO_ROOT / "data/features/sa2_2026_05_mtd.csv"
SA3_LOOKUP = REPO_ROOT / "data/meta/sa2_sa3_lookup.csv"
OUT_CSV = REPO_ROOT / "data/features/vic_sa2_seeding_2026.csv"
OUT_REPORT = REPO_ROOT / "reports/weekly/vic_sa2_seeding_conditions_2026_W21.md"

HIST_YEARS = range(2005, 2026)  # 21-year baseline


def classify_may_seeding(may_mm: float) -> str:
    if may_mm >= 25:
        return "Adequate"
    elif may_mm >= 15:
        return "Marginal"
    elif may_mm >= 10:
        return "Marginal-low"
    else:
        return "Insufficient"


def classify_apr_may_season(total_mm: float) -> str:
    if total_mm >= 70:
        return "Strong"
    elif total_mm >= 40:
        return "Adequate"
    elif total_mm >= 20:
        return "Below average"
    else:
        return "Poor"


def load_region_lookup() -> pd.DataFrame:
    """Return DataFrame with sa2_code, sa3_name, sa4_name columns."""
    if not SA3_LOOKUP.exists():
        return pd.DataFrame(columns=["sa2_code", "sa3_name", "sa4_name"])
    df = pd.read_csv(SA3_LOOKUP, low_memory=False)
    df["sa2_code"] = df["sa2_code"].astype(int)
    keep = ["sa2_code"]
    for col in ["sa3_name", "sa4_name"]:
        if col in df.columns:
            keep.append(col)
    return df[keep]


def main(write_report: bool = True) -> pd.DataFrame:
    hist = pd.read_csv(HIST_PATH, low_memory=False)
    mtd = pd.read_csv(MTD_PATH, low_memory=False)

    vic_hist = hist[hist["state_name"] == "Victoria"].copy()
    vic_mtd = mtd[mtd["state_name"] == "Victoria"].copy()

    through_day = int(vic_mtd["partial_month_through_day"].dropna().max()) if len(vic_mtd) > 0 else 25
    may_scale = through_day / 31.0

    # --- April 2026 actuals (already in history file)
    apr26 = vic_hist[(vic_hist["year"] == 2026) & (vic_hist["month"] == 4)][
        ["sa2_code", "sa2_name", "rainfall_mm"]
    ].rename(columns={"rainfall_mm": "apr_2026_mm"})

    # --- May 2026 MTD (days 1..through_day)
    may26_mtd = vic_mtd[["sa2_code", "rainfall_mm"]].rename(
        columns={"rainfall_mm": "may_mtd_mm"}
    )

    # Inner-join on SA2 code — do NOT outer-merge and zero-fill a missing month.
    # A missing April or May value is missing data, not 0 mm of rain, and a 0
    # fill would misreport the SA2 as an insufficient / dry seeding break.
    apr_codes = set(apr26["sa2_code"])
    may_codes = set(may26_mtd["sa2_code"])
    only_apr = sorted(apr_codes - may_codes)
    only_may = sorted(may_codes - apr_codes)
    if only_apr or only_may:
        print(
            f"WARNING: {len(only_apr)} SA2(s) have April but no May MTD, "
            f"{len(only_may)} have May MTD but no April — dropped (kept missing, "
            f"not zero-filled)."
        )
    df = apr26.merge(may26_mtd, on="sa2_code", how="inner")
    if df.empty:
        raise SystemExit(
            "No Victorian SA2 has both April 2026 and May MTD rainfall — "
            "cannot build the seeding report."
        )
    df["apr_may_total_mm"] = df["apr_2026_mm"] + df["may_mtd_mm"]

    # --- Historical Apr climatology (2005-2025)
    apr_hist = vic_hist[(vic_hist["month"] == 4) & (vic_hist["year"].isin(HIST_YEARS))]
    apr_stats = apr_hist.groupby("sa2_code")["rainfall_mm"].agg(
        apr_hist_median="median",
        apr_hist_p25=lambda x: np.percentile(x, 25),
        apr_hist_p75=lambda x: np.percentile(x, 75),
    ).reset_index()

    # --- Historical May climatology — scale to partial month
    may_hist = vic_hist[(vic_hist["month"] == 5) & (vic_hist["year"].isin(HIST_YEARS))]
    may_full_stats = may_hist.groupby("sa2_code")["rainfall_mm"].agg(
        may_full_median="median",
    ).reset_index()
    # Scale historical median to the same day count we have (day 1..through_day / 31 days)
    may_full_stats["may_scaled_median"] = may_full_stats["may_full_median"] * may_scale

    # --- Historical Apr+May climatology
    apr_may_parts = vic_hist[
        (vic_hist["month"].isin([4, 5])) & (vic_hist["year"].isin(HIST_YEARS))
    ].copy()
    apr_may_parts.loc[apr_may_parts["month"] == 5, "rainfall_mm"] *= may_scale
    apr_may_hist = apr_may_parts.groupby(["sa2_code", "year"])["rainfall_mm"].sum().reset_index()
    apr_may_stats = apr_may_hist.groupby("sa2_code")["rainfall_mm"].agg(
        apr_may_hist_median="median",
        apr_may_hist_p10=lambda x: np.percentile(x, 10),
        apr_may_hist_p90=lambda x: np.percentile(x, 90),
    ).reset_index()

    # --- Percentile ranks
    def pct_rank_col(df_in: pd.DataFrame, hist_df: pd.DataFrame, val_col: str, hist_val_col: str) -> pd.Series:
        result = []
        for _, row in df_in.iterrows():
            code = row["sa2_code"]
            hist_vals = hist_df[hist_df["sa2_code"] == code][hist_val_col].values
            result.append(percentile_rank(hist_vals, row[val_col]))
        return pd.Series(result, index=df_in.index)

    df = df.merge(apr_stats, on="sa2_code", how="left")
    df = df.merge(may_full_stats, on="sa2_code", how="left")
    df = df.merge(apr_may_stats, on="sa2_code", how="left")

    df["apr_pct_rank"] = pct_rank_col(df, apr_hist, "apr_2026_mm", "rainfall_mm")
    may_hist_scaled = may_hist.copy()
    may_hist_scaled["rainfall_mm"] = may_hist_scaled["rainfall_mm"] * may_scale
    df["may_pct_rank"] = pct_rank_col(df, may_hist_scaled, "may_mtd_mm", "rainfall_mm")
    df["apr_may_pct_rank"] = pct_rank_col(df, apr_may_hist, "apr_may_total_mm", "rainfall_mm")

    df["apr_pct_of_median"] = (df["apr_2026_mm"] / df["apr_hist_median"].clip(lower=0.1) * 100).round(0)
    df["may_pct_of_scaled_median"] = (df["may_mtd_mm"] / df["may_scaled_median"].clip(lower=0.1) * 100).round(0)

    # --- Classifications
    df["may_seeding_class"] = df["may_mtd_mm"].apply(classify_may_seeding)
    df["apr_may_season_class"] = df["apr_may_total_mm"].apply(classify_apr_may_season)

    # Decile buckets for apr+may — canonical rank-based decile (decile_rank) vs
    # the SA2's own scaled Apr+May climatology, NOT a percentile-floor cut, so
    # reported deciles match the house deciles contract.
    apr_may_decile = []
    for _, row in df.iterrows():
        hist_vals = apr_may_hist[apr_may_hist["sa2_code"] == row["sa2_code"]]["rainfall_mm"].values
        d = decile_rank(hist_vals, row["apr_may_total_mm"])
        apr_may_decile.append(f"D{int(d)}" if d is not None else None)
    df["decile"] = pd.Categorical(
        apr_may_decile, categories=[f"D{i}" for i in range(1, 11)], ordered=True
    )

    # --- SA3 / SA4 grouping
    region_lkp = load_region_lookup()
    df = df.merge(region_lkp, on="sa2_code", how="left")
    if "sa3_name" not in df.columns:
        df["sa3_name"] = "Unknown"
    if "sa4_name" not in df.columns:
        df["sa4_name"] = "Unknown"
    df["sa3_name"] = df["sa3_name"].fillna("Unknown")
    df["sa4_name"] = df["sa4_name"].fillna("Unknown")

    df = df.sort_values("apr_may_pct_rank")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not atomic_csv_write(df, OUT_CSV):
        raise SystemExit(f"Failed to write {OUT_CSV}")
    print(f"Written → {OUT_CSV.relative_to(REPO_ROOT)}")

    # ---- Console summary
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)

    print(f"\n=== Victoria SA2 Seeding Conditions — May 1–{through_day}, 2026 ===")
    print(f"({len(df)} grain-belt SA2s)\n")

    print("May seeding classification breakdown:")
    print(df["may_seeding_class"].value_counts().to_string())

    print("\nApr+May combined season classification:")
    print(df["apr_may_season_class"].value_counts().to_string())

    print("\nApr+May decile distribution:")
    print(df["decile"].value_counts().sort_index().to_string())

    print("\n--- Driest 10 SA2s (Apr+May combined, percentile rank) ---")
    cols_show = ["sa2_name", "apr_2026_mm", "may_mtd_mm", "apr_may_total_mm",
                 "apr_may_hist_median", "apr_may_pct_rank", "may_seeding_class", "apr_may_season_class"]
    print(df.head(10)[cols_show].round(1).to_string(index=False))

    print("\n--- Wettest 10 SA2s ---")
    print(df.tail(10)[cols_show].round(1).to_string(index=False))

    print("\n--- Insufficient May seeding break (<10mm) ---")
    insuf = df[df["may_seeding_class"] == "Insufficient"]
    print(insuf[cols_show].round(1).to_string(index=False) if len(insuf) else "  (none)")

    print("\n--- Adequate May seeding break (≥25mm) ---")
    adeq = df[df["may_seeding_class"] == "Adequate"]
    print(adeq[["sa2_name", "may_mtd_mm", "apr_may_total_mm", "apr_may_pct_rank"]].round(1).to_string(index=False) if len(adeq) else "  (none)")

    # --- SD (SA4) rollup
    print("\n=== SD-level (SA4) rollup ===")
    sd_grp = df.groupby("sa4_name").agg(
        n_sa2=("sa2_name", "count"),
        apr_mm_median=("apr_2026_mm", "median"),
        may_mtd_mm_median=("may_mtd_mm", "median"),
        apr_may_mm_median=("apr_may_total_mm", "median"),
        hist_median_median=("apr_may_hist_median", "median"),
        pct_rank_median=("apr_may_pct_rank", "median"),
        n_adequate=("may_seeding_class", lambda x: (x == "Adequate").sum()),
        n_marginal=("may_seeding_class", lambda x: (x == "Marginal").sum()),
        n_insufficient=("may_seeding_class", lambda x: (x == "Insufficient").sum()),
        n_strong_season=("apr_may_season_class", lambda x: (x == "Strong").sum()),
        n_below_avg=("apr_may_season_class", lambda x: (x == "Below average").sum()),
        n_poor=("apr_may_season_class", lambda x: (x == "Poor").sum()),
    ).reset_index().sort_values("pct_rank_median")
    print(sd_grp.round(1).to_string(index=False))

    if write_report:
        _write_markdown(df, through_day, OUT_REPORT)

    return df


def _write_markdown(df: pd.DataFrame, through_day: int, out_path: Path) -> None:
    adequate = df[df["may_seeding_class"] == "Adequate"].sort_values("may_mtd_mm", ascending=False)
    marginal = df[df["may_seeding_class"] == "Marginal"].sort_values("may_mtd_mm", ascending=False)
    marginal_low = df[df["may_seeding_class"] == "Marginal-low"].sort_values("may_mtd_mm", ascending=False)
    insufficient = df[df["may_seeding_class"] == "Insufficient"].sort_values("may_mtd_mm", ascending=False)

    poor_season = df[df["apr_may_season_class"] == "Poor"]
    strong_season = df[df["apr_may_season_class"].isin(["Strong", "Adequate"])]

    median_may = df["may_mtd_mm"].median()
    median_apr_may = df["apr_may_total_mm"].median()
    median_hist_apr_may = df["apr_may_hist_median"].median()

    def sa2_table(subset: pd.DataFrame, cols: list[str], headers: list[str]) -> str:
        if len(subset) == 0:
            return "_None_\n"
        lines = ["| " + " | ".join(headers) + " |"]
        lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        for _, row in subset.iterrows():
            lines.append("| " + " | ".join(str(round(row[c], 1)) if isinstance(row[c], float) else str(row[c]) for c in cols) + " |")
        return "\n".join(lines) + "\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(f"# Victoria SA2 Seeding Conditions — May 2026 (days 1–{through_day})\n\n")
        f.write(f"_Generated: 2026-05-26 | {len(df)} grain-belt SA2s | Baseline: 2005–2025_\n\n")
        f.write("---\n\n")

        f.write("## Summary\n\n")
        f.write(f"- **VIC median May MTD (days 1–{through_day}):** {median_may:.0f} mm\n")
        f.write(f"- **VIC median Apr+May combined:** {median_apr_may:.0f} mm\n")
        f.write(f"- **Historical median Apr+May (2005–2025):** {median_hist_apr_may:.0f} mm\n\n")

        f.write("### May seeding break classification\n\n")
        f.write("| Class | SA2 count | Threshold |\n")
        f.write("|---|---|---|\n")
        f.write(f"| ✅ Adequate | {len(adequate)} | ≥ 25 mm |\n")
        f.write(f"| ⚠️ Marginal | {len(marginal)} | 15–24 mm |\n")
        f.write(f"| 🔶 Marginal-low | {len(marginal_low)} | 10–14 mm |\n")
        f.write(f"| ❌ Insufficient | {len(insufficient)} | < 10 mm |\n\n")

        f.write("### Apr+May combined season classification\n\n")
        f.write("| Class | SA2 count |\n")
        f.write("|---|---|\n")
        for cls in ["Strong", "Adequate", "Below average", "Poor"]:
            n = len(df[df["apr_may_season_class"] == cls])
            emoji = {"Strong": "✅", "Adequate": "✅", "Below average": "⚠️", "Poor": "❌"}.get(cls, "")
            f.write(f"| {emoji} {cls} | {n} |\n")
        f.write("\n")

        f.write("### Apr+May decile distribution\n\n")
        f.write("| Decile | SA2 count |\n|---|---|\n")
        for d, cnt in df["decile"].value_counts().sort_index().items():
            f.write(f"| {d} | {cnt} |\n")
        f.write("\n---\n\n")

        # --- SD (SA4) rollup table
        sd_grp = df.groupby("sa4_name").agg(
            n_sa2=("sa2_name", "count"),
            apr_mm_median=("apr_2026_mm", "median"),
            may_mtd_mm_median=("may_mtd_mm", "median"),
            apr_may_mm_median=("apr_may_total_mm", "median"),
            hist_median_median=("apr_may_hist_median", "median"),
            pct_rank_median=("apr_may_pct_rank", "median"),
            n_adequate=("may_seeding_class", lambda x: (x == "Adequate").sum()),
            n_marginal=("may_seeding_class", lambda x: (x == "Marginal").sum()),
            n_insufficient=("may_seeding_class", lambda x: (x == "Insufficient").sum()),
        ).reset_index().sort_values("pct_rank_median")

        f.write("## Statistical Division (SA4) Rollup\n\n")
        f.write("_Medians across all grain SA2s within each SD. May seeding break counts use SA2-level classification._\n\n")
        f.write("| SD (SA4) | SA2s | Apr mm | May 1–{d} mm | Apr+May mm | Hist med | Pct rank | ✅ Adeq | ⚠️ Marg | ❌ Insuf |\n".format(d=through_day))
        f.write("|---|---|---|---|---|---|---|---|---|---|\n")
        for _, row in sd_grp.iterrows():
            pct = row["pct_rank_median"]
            flag = "🔴" if pct < 20 else ("🟡" if pct < 40 else "🟢")
            f.write(
                f"| {flag} {row['sa4_name']} | {int(row['n_sa2'])} "
                f"| {row['apr_mm_median']:.0f} | {row['may_mtd_mm_median']:.0f} "
                f"| {row['apr_may_mm_median']:.0f} | {row['hist_median_median']:.0f} "
                f"| {pct:.0f}th | {int(row['n_adequate'])} | {int(row['n_marginal'])} | {int(row['n_insufficient'])} |\n"
            )
        f.write("\n---\n\n")

        f.write("## Regional Detail\n\n")

        f.write(f"### ✅ Adequate May seeding break (≥25 mm) — {len(adequate)} SA2s\n\n")
        f.write(sa2_table(
            adequate,
            ["sa2_name", "apr_2026_mm", "may_mtd_mm", "apr_may_total_mm", "apr_may_hist_median", "apr_may_pct_rank"],
            ["SA2", "Apr mm", f"May 1–{through_day} mm", "Apr+May mm", "Hist median mm", "Pct rank"],
        ))

        f.write(f"\n### ⚠️ Marginal May break (15–24 mm) — {len(marginal)} SA2s\n\n")
        f.write(sa2_table(
            marginal,
            ["sa2_name", "apr_2026_mm", "may_mtd_mm", "apr_may_total_mm", "apr_may_hist_median", "apr_may_pct_rank"],
            ["SA2", "Apr mm", f"May 1–{through_day} mm", "Apr+May mm", "Hist median mm", "Pct rank"],
        ))

        f.write(f"\n### 🔶 Marginal-low May break (10–14 mm) — {len(marginal_low)} SA2s\n\n")
        f.write(sa2_table(
            marginal_low,
            ["sa2_name", "apr_2026_mm", "may_mtd_mm", "apr_may_total_mm", "apr_may_hist_median", "apr_may_pct_rank"],
            ["SA2", "Apr mm", f"May 1–{through_day} mm", "Apr+May mm", "Hist median mm", "Pct rank"],
        ))

        f.write(f"\n### ❌ Insufficient May break (<10 mm) — {len(insufficient)} SA2s\n\n")
        f.write(sa2_table(
            insufficient,
            ["sa2_name", "apr_2026_mm", "may_mtd_mm", "apr_may_total_mm", "apr_may_hist_median", "apr_may_pct_rank"],
            ["SA2", "Apr mm", f"May 1–{through_day} mm", "Apr+May mm", "Hist median mm", "Pct rank"],
        ))

        f.write("\n---\n\n")
        f.write("## Driest 10 SA2s (Apr+May combined)\n\n")
        f.write(sa2_table(
            df.head(10),
            ["sa2_name", "apr_2026_mm", "may_mtd_mm", "apr_may_total_mm", "apr_may_hist_median", "apr_may_pct_rank", "apr_may_season_class"],
            ["SA2", "Apr mm", f"May 1–{through_day} mm", "Apr+May mm", "Hist median", "Pct rank", "Season class"],
        ))

        f.write("\n## Wettest 10 SA2s (Apr+May combined)\n\n")
        f.write(sa2_table(
            df.tail(10).iloc[::-1],
            ["sa2_name", "apr_2026_mm", "may_mtd_mm", "apr_may_total_mm", "apr_may_hist_median", "apr_may_pct_rank", "apr_may_season_class"],
            ["SA2", "Apr mm", f"May 1–{through_day} mm", "Apr+May mm", "Hist median", "Pct rank", "Season class"],
        ))

        f.write("\n---\n\n")
        f.write("## Full SA2 Table (sorted driest → wettest Apr+May)\n\n")
        f.write(sa2_table(
            df,
            ["sa4_name", "sa2_name", "apr_2026_mm", "may_mtd_mm", "apr_may_total_mm", "apr_may_hist_median",
             "apr_may_pct_rank", "decile", "may_seeding_class", "apr_may_season_class"],
            ["SD (SA4)", "SA2", "Apr mm", f"May 1–{through_day} mm", "Apr+May mm", "Hist median", "Pct rank", "Decile", "May seeding", "Season"],
        ))

        f.write(f"\n---\n_Source: SILO daily_rain NetCDF (days 1–{through_day}); monthly_rain for Apr. Baseline 2005–2025._\n")

    print(f"Written → {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-report", action="store_true", help="Skip writing markdown report")
    args = parser.parse_args()
    main(write_report=not args.no_report)
