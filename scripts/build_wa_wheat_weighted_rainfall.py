#!/usr/bin/env python3
"""Build crop-area-weighted rainfall summary for WA wheat.

Reads data/features/sa2_rainfall_crop_context.csv and produces a single-row-per-
season summary suitable for feeding into the weekly market brief reporter.

Quality gate (strict):
  - crop = wheat
  - rainfall_feature_quality_flag = complete
  - area_ha not null

Rows that pass the gate are used for weighted metrics.
All exclusions are tracked by reason so the reporter can attach a coverage
caveat (e.g. "complete data represents X% of mapped WA wheat area").

Usage:
    python scripts/build_wa_wheat_weighted_rainfall.py
    python scripts/build_wa_wheat_weighted_rainfall.py --season-year 2025
    python scripts/build_wa_wheat_weighted_rainfall.py --dry-run
"""

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "data" / "features" / "sa2_rainfall_crop_context.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "features" / "wa_wheat_area_weighted_rainfall_summary.csv"

# Rainfall metrics to area-weight (all in mm or days)
WEIGHTED_METRICS = [
    "pre_seeding_rain_mm",
    "sowing_window_rain_mm",
    "in_crop_rain_mm",
    "rainfall_total_apr_oct_mm",
    "rainfall_total_may_oct_mm",
    "flowering_rain_mm",
    "grain_fill_rain_mm",
    "harvest_rain_mm",
    "dry_spell_days_7d_lt_5mm",
    "dry_spell_days_14d_lt_10mm",
]

# BACKLOG: Add latest_obs_date to OUTPUT_COLS (max observation date across eligible SA2s).
# Once present in the summary CSV, surface it in WeeklyReportGenerator._generate_wa_wheat_section
# alongside the coverage line so readers know the exact date rainfall data runs to.

# BACKLOG: Rename qgis_wheat_area_mapped_ha before reporter-facing consumers
# harden against this column name. Suggested names: mapped_area_for_weighting_ha
# or total_weight_area_ha. Update OUTPUT_COLS, build_summary_row, print_report,
# WeeklyReportGenerator, and any downstream assembler that reads this column.

OUTPUT_COLS = [
    "season_year",
    "state",
    "crop",
    # Coverage accounting
    "n_sa2s_qgis_universe",
    "n_sa2s_complete",
    "n_sa2s_eligible",
    "n_sa2s_insufficient_season",
    "n_sa2s_no_data",
    "n_sa2s_complete_no_area",
    # Area accounting
    "total_wheat_area_ha",
    "qgis_wheat_area_mapped_ha",
    "coverage_share",
    # Area-weighted rainfall metrics
    "pre_seeding_rain_mm_wt",
    "sowing_window_rain_mm_wt",
    "in_crop_rain_mm_wt",
    "rainfall_total_apr_oct_mm_wt",
    "rainfall_total_may_oct_mm_wt",
    "flowering_rain_mm_wt",
    "grain_fill_rain_mm_wt",
    "harvest_rain_mm_wt",
    "dry_spell_days_7d_lt_5mm_wt",
    "dry_spell_days_14d_lt_10mm_wt",
    # SA2 membership lists (semicolon-separated names)
    "eligible_sa2s",
    "excluded_insufficient_season_sa2s",
    "excluded_no_data_sa2s",
    "excluded_complete_no_area_sa2s",
    "area_fallback_caveat",
    "generated_at",
]


def parse_args():
    p = argparse.ArgumentParser(
        description="Build wheat area-weighted rainfall summary per state"
    )
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--season-year", type=int, default=None,
                   help="Filter to a single season year (default: all years in input)")
    p.add_argument(
        "--states",
        default="all",
        help=(
            "Comma-separated state names to include, or 'all' for every state "
            "present in the input (default: all)"
        ),
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Print summary without writing output file")
    return p.parse_args()


def weighted_mean(values: pd.Series, weights: pd.Series) -> float | None:
    """Area-weighted mean; returns None when total weight is zero."""
    mask = values.notna() & weights.notna() & (weights > 0)
    v, w = values[mask], weights[mask]
    if w.sum() == 0:
        return None
    return float((v * w).sum() / w.sum())


def build_summary_row(
    season_df: pd.DataFrame, state_name: str | None = None
) -> dict:
    """Build one summary row from all wheat rows for a single (state, season).

    If state_name is not provided, infer it from the input rows (falling back
    to 'Western Australia' to preserve historical default behaviour).
    """
    wheat = season_df[season_df["crop"] == "wheat"].copy()
    season_year = int(wheat["season_year"].iloc[0]) if wheat["season_year"].notna().any() else None
    if state_name is None:
        states_present = wheat["state"].dropna().unique() if "state" in wheat.columns else []
        state_name = states_present[0] if len(states_present) else "Western Australia"

    # Partition by quality gate
    complete = wheat[wheat["rainfall_feature_quality_flag"] == "complete"]
    insufficient = wheat[wheat["rainfall_feature_quality_flag"] == "insufficient_season"]
    no_data = wheat[wheat["rainfall_feature_quality_flag"] == "no_data"]

    # area_ha_for_weighting uses 2015-16 fallback for SA2s where 2020-21 is suppressed (np)
    weight_col = "area_ha_for_weighting" if "area_ha_for_weighting" in complete.columns else "area_ha"
    eligible = complete[complete[weight_col].notna()]
    complete_no_area = complete[complete[weight_col].isna()]

    # Area totals
    qgis_mapped_ha = wheat[weight_col].sum()  # sum over all 28; nulls ignored by pandas
    eligible_ha = eligible[weight_col].sum()
    coverage_share = (eligible_ha / qgis_mapped_ha) if qgis_mapped_ha > 0 else None

    # Area-weighted metrics
    weights = eligible[weight_col]
    weighted = {}
    for metric in WEIGHTED_METRICS:
        col = f"{metric}_wt"
        if metric in eligible.columns:
            weighted[col] = weighted_mean(eligible[metric], weights)
        else:
            weighted[col] = None

    def _names(df: pd.DataFrame) -> str:
        return "; ".join(sorted(df["sa2_name"].tolist()))

    # Build caveat string for SA2s using historical fallback area
    fallback_col = "area_is_fallback" if "area_is_fallback" in eligible.columns else None
    if fallback_col:
        fallback_rows = eligible[eligible[fallback_col].astype(str).isin(["True", "true", "1"])]
        if not fallback_rows.empty:
            fb_names = "; ".join(sorted(fallback_rows["sa2_name"].tolist()))
            area_fallback_caveat = (
                f"Uses 2015-16 ABS fallback area for {fb_names} "
                f"because 2020-21 wheat area was not published."
            )
        else:
            area_fallback_caveat = ""
    else:
        area_fallback_caveat = ""

    return {
        "season_year": season_year,
        "state": state_name,
        "crop": "wheat",
        "n_sa2s_qgis_universe": len(wheat),
        "n_sa2s_complete": len(complete),
        "n_sa2s_eligible": len(eligible),
        "n_sa2s_insufficient_season": len(insufficient),
        "n_sa2s_no_data": len(no_data),
        "n_sa2s_complete_no_area": len(complete_no_area),
        "total_wheat_area_ha": round(eligible_ha, 2) if eligible_ha > 0 else None,
        "qgis_wheat_area_mapped_ha": round(qgis_mapped_ha, 2) if qgis_mapped_ha > 0 else None,
        "coverage_share": round(coverage_share, 4) if coverage_share is not None else None,
        **{k: (round(v, 2) if v is not None else None) for k, v in weighted.items()},
        "eligible_sa2s": _names(eligible),
        "excluded_insufficient_season_sa2s": _names(insufficient),
        "excluded_no_data_sa2s": _names(no_data),
        "excluded_complete_no_area_sa2s": _names(complete_no_area),
        "area_fallback_caveat": area_fallback_caveat,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def print_report(row: dict) -> None:
    sy = row["season_year"]
    state = row.get("state", "—")
    print(f"\n=== {state} Wheat Area-Weighted Rainfall Summary — {sy} ===")
    print(f"\nCoverage:")
    print(f"  QGIS universe SA2s:          {row['n_sa2s_qgis_universe']}")
    print(f"  Complete + eligible:          {row['n_sa2s_eligible']}  (complete={row['n_sa2s_complete']}, area_null={row['n_sa2s_complete_no_area']})")
    print(f"  Insufficient season:          {row['n_sa2s_insufficient_season']}")
    print(f"  No data:                      {row['n_sa2s_no_data']}")
    print(f"\nArea:")
    print(f"  Eligible wheat area:          {row['total_wheat_area_ha']:,.0f} ha" if row['total_wheat_area_ha'] else "  Eligible wheat area:          —")
    print(f"  QGIS mapped wheat area:       {row['qgis_wheat_area_mapped_ha']:,.0f} ha" if row['qgis_wheat_area_mapped_ha'] else "  QGIS mapped wheat area:       —")
    cov = f"{row['coverage_share']:.1%}" if row['coverage_share'] is not None else "—"
    print(f"  Coverage share:               {cov}")
    print(f"\nArea-weighted rainfall metrics:")
    metrics = [
        ("Pre-seeding rain (Jan–Mar)", "pre_seeding_rain_mm_wt",          "mm"),
        ("Sowing window rain",         "sowing_window_rain_mm_wt",        "mm"),
        ("In-crop rain",               "in_crop_rain_mm_wt",              "mm"),
        ("Growing season (Apr–Oct)",   "rainfall_total_apr_oct_mm_wt",    "mm"),
        ("Growing season (May–Oct)",   "rainfall_total_may_oct_mm_wt",    "mm"),
        ("Flowering rain",             "flowering_rain_mm_wt",            "mm"),
        ("Grain fill rain",            "grain_fill_rain_mm_wt",           "mm"),
        ("Harvest rain (Nov–Dec)",     "harvest_rain_mm_wt",              "mm"),
        ("Dry spells (7d <5mm)",       "dry_spell_days_7d_lt_5mm_wt",     "days"),
        ("Dry spells (14d <10mm)",     "dry_spell_days_14d_lt_10mm_wt",   "days"),
    ]
    for label, key, unit in metrics:
        val = row.get(key)
        print(f"  {label:<28} {val:.1f} {unit}" if val is not None else f"  {label:<28} —")
    print(f"\nEligible SA2s:  {row['eligible_sa2s']}")
    if row["excluded_complete_no_area_sa2s"]:
        print(f"Complete, no ABS area:  {row['excluded_complete_no_area_sa2s']}")
    if row["excluded_insufficient_season_sa2s"]:
        print(f"Insufficient season:    {row['excluded_insufficient_season_sa2s']}")
    if row.get("area_fallback_caveat"):
        print(f"Area caveat:  {row['area_fallback_caveat']}")
    print()


def main() -> int:
    args = parse_args()

    if not args.input.exists():
        print(f"ERROR: Input not found: {args.input}", file=sys.stderr)
        return 1

    df = pd.read_csv(
        args.input,
        dtype={"abs_sa2_code": str, "station_sa2_5dig16": str},
    )

    # Resolve requested states (default: every state in the input).
    if args.states and args.states.lower() != "all":
        requested = {s.strip() for s in args.states.split(",") if s.strip()}
    else:
        requested = set(df["state"].dropna().unique())

    available_states = [s for s in df["state"].dropna().unique() if s in requested]
    missing = requested - set(available_states)
    if missing:
        print(
            f"WARNING: requested states absent from input: {sorted(missing)}",
            file=sys.stderr,
        )
    if not available_states:
        print("ERROR: No matching state rows in input.", file=sys.stderr)
        return 1

    rows = []
    for state_name in sorted(available_states):
        state_df = df[df["state"] == state_name].copy()

        # Determine available seasons from rows that carry rainfall data.
        # no_data rows have NaN season_year — never pre-filter them.
        available_seasons = sorted(state_df["season_year"].dropna().unique().astype(int))
        if not available_seasons:
            print(
                f"WARNING: No season_year values in input for {state_name}; skipped.",
                file=sys.stderr,
            )
            continue

        if args.season_year is not None:
            if args.season_year not in available_seasons:
                print(
                    f"WARNING: season_year={args.season_year} not in {state_name} "
                    f"(available: {available_seasons}); skipped.",
                    file=sys.stderr,
                )
                continue
            season_years = [args.season_year]
        else:
            season_years = available_seasons

        no_data_rows = state_df[state_df["rainfall_feature_quality_flag"] == "no_data"]

        for sy in season_years:
            has_data = state_df["season_year"] == sy
            season_df = pd.concat([state_df[has_data], no_data_rows], ignore_index=True)
            season_df["season_year"] = season_df["season_year"].fillna(sy)
            rows.append(build_summary_row(season_df, state_name))

    for row in rows:
        print_report(row)

    if args.dry_run:
        print("Dry run — output file not written.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Written: {args.output} ({len(rows)} row{'s' if len(rows) != 1 else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
