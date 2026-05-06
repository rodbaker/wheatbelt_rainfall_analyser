#!/usr/bin/env python3
"""Build WA wheat area-weighted monthly rainfall decile summary.

For each year × month, computes a weighted rainfall total across all WA wheat
SA2s using crop area weights, then assigns a decile by comparing that weighted
total against the historical distribution of weighted totals for the same
calendar month (excluding the target year from its own baseline).

Deciles are NOT computed per SA2 and averaged. The weighted total is computed
first; the decile is then derived from the distribution of those weighted totals
across years.

Inputs:
    data/features/sa2_monthly_rainfall_history.csv   (historical NetCDF-derived)
    data/meta/crop_context_sa2.csv
    [optional] --current-year-csv                    (station-derived current year)

Output:
    data/features/wa_wheat_weighted_monthly_rainfall_deciles.csv

Source labelling:
    current_rainfall_source   — extraction method for the reported year's rainfall
    historical_baseline_source — always monthly_rain_netCDF (NetCDF 2005–2025)

Usage:
    python scripts/build_wa_wheat_weighted_monthly_rainfall_deciles.py
    python scripts/build_wa_wheat_weighted_monthly_rainfall_deciles.py --dry-run
    python scripts/build_wa_wheat_weighted_monthly_rainfall_deciles.py \\
        --current-year-csv data/features/sa2_2026_monthly_from_daily.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY_CSV = REPO_ROOT / "data" / "features" / "sa2_monthly_rainfall_history.csv"
CROP_CONTEXT_CSV = REPO_ROOT / "data" / "meta" / "crop_context_sa2.csv"
OUTPUT_CSV = REPO_ROOT / "data" / "features" / "wa_wheat_weighted_monthly_rainfall_deciles.csv"

MIN_HISTORY_COUNT = 10
MIN_COVERAGE_SHARE = 0.8  # suppress decile when contributing area < 80% of universe

DECILE_LABELS = {
    1: "very low",
    2: "below normal",
    3: "below normal",
    4: "near normal",
    5: "near normal",
    6: "near normal",
    7: "near normal",
    8: "above normal",
    9: "above normal",
    10: "very high",
}

OUTPUT_COLS = [
    "year",
    "month",
    "rainfall_mm_wt",
    "historical_year_count",
    "historical_median_mm_wt",
    "historical_mean_mm_wt",
    "anomaly_mm_wt",
    "anomaly_pct_wt",
    "rainfall_decile",
    "rainfall_decile_label",
    "climatology_quality_flag",
    "is_partial_month",
    "n_sa2s_universe",
    "n_sa2s_weighted",
    "n_sa2s_missing_rainfall",
    "weighting_area_ha",
    "weighting_area_share",
    "fallback_area_sa2s",
    "area_fallback_caveat",
    "current_rainfall_source",
    "historical_baseline_source",
]

HISTORICAL_BASELINE_SOURCE = "monthly_rain_netCDF"


def load_wa_wheat_weights(crop_context_path: Path) -> pd.DataFrame:
    """Return WA wheat SA2 weighting table filtered to non-null area rows."""
    df = pd.read_csv(crop_context_path, dtype={"sa2_code": str})
    wa_wheat = df[(df["state"] == "Western Australia") & (df["crop"] == "wheat")].copy()
    keep = [
        "sa2_code",
        "sa2_name",
        "area_ha_for_weighting",
        "area_source_year",
        "area_is_fallback",
        "area_fallback_reason",
    ]
    return wa_wheat[keep].reset_index(drop=True)


def _compute_decile(value: float, historical: pd.Series) -> int:
    """Return 1-10 decile rank of value within historical distribution."""
    n = len(historical)
    rank = (historical < value).sum() + 1
    decile = int(np.ceil(rank / n * 10))
    return max(1, min(10, decile))


def _build_fallback_caveat(eligible_weights: pd.DataFrame) -> tuple[int, str]:
    """Return (count, caveat_text) for fallback-area SA2s that participate in weighting."""
    fallback_rows = eligible_weights[
        eligible_weights["area_is_fallback"].astype(str).isin(["True", "true", "1"])
    ]
    if fallback_rows.empty:
        return 0, ""
    names = "; ".join(sorted(fallback_rows["sa2_name"].tolist()))
    caveat = (
        f"Monthly gridded rainfall weighting uses 2015-16 ABS fallback area for {names} "
        f"because 2020-21 wheat area was not published."
    )
    return len(fallback_rows), caveat


def compute_weighted_monthly_deciles(
    history: pd.DataFrame,
    weights: pd.DataFrame,
    current_year_source: dict = None,
) -> pd.DataFrame:
    """Compute area-weighted monthly rainfall and deciles for WA wheat.

    history: sa2_monthly_rainfall_history rows (year, month, sa2_code, rainfall_mm).
             May include a current-year block appended from build_2026_sa2_monthly_from_daily.
    weights: WA wheat SA2s with area_ha_for_weighting (may be null for some)
    current_year_source: {year: int, source: str} describing the extraction method
             used for the current-year rows (e.g. {"year": 2026, "source": "station_daily_sa2"}).
             When None, all rows are treated as monthly_rain_netCDF.

    Returns one row per year × month present in history.

    Decile integrity: for each target (year, month) the historical distribution is
    recomputed using only the SA2s that have rainfall data in that target month.
    This ensures the historical weighted totals use the same SA2 mask as the target,
    making the decile comparison like-for-like. When the contributing area falls
    below MIN_COVERAGE_SHARE (80%) of the universe total, the decile is suppressed.
    """
    eligible_weights = weights[weights["area_ha_for_weighting"].notna()].copy()

    fallback_count, fallback_caveat = _build_fallback_caveat(eligible_weights)

    # Universe totals — constant across all months
    universe_area = float(eligible_weights["area_ha_for_weighting"].sum())
    n_sa2s_universe = len(eligible_weights)

    # Merge history → keep only WA wheat SA2s (inner join on eligible codes)
    merged = history.merge(
        eligible_weights[["sa2_code", "area_ha_for_weighting"]],
        on="sa2_code",
        how="inner",
    )

    # Pre-group by (year, month) for efficient SA2-mask-restricted historical lookups
    groups: dict[tuple, pd.DataFrame] = {
        k: v for k, v in merged.groupby(["year", "month"], sort=True)
    }

    out_rows = []
    for (year, month), group in sorted(groups.items()):
        has_rain = group[group["rainfall_mm"].notna()]
        n_missing = len(group) - len(has_rain)

        is_partial = bool(
            "is_partial_month" in group.columns
            and group["is_partial_month"].any()
        )

        # Derive source label
        if current_year_source and int(year) == current_year_source["year"]:
            curr_src = current_year_source["source"]
        else:
            curr_src = HISTORICAL_BASELINE_SOURCE

        # Weighted total and contributing SA2 set for this target month
        if has_rain.empty:
            weighted_total = None
            contributing_codes: set[str] = set()
            weighting_area_ha = None
        else:
            w = has_rain["area_ha_for_weighting"]
            r = has_rain["rainfall_mm"]
            total_w = float(w.sum())
            contributing_codes = set(has_rain["sa2_code"].tolist())
            weighted_total = float((r * w).sum() / total_w) if total_w > 0 else None
            weighting_area_ha = round(total_w, 2) if total_w > 0 else None

        weighting_area_share = (
            round(weighting_area_ha / universe_area, 4)
            if (weighting_area_ha is not None and universe_area > 0)
            else None
        )

        out: dict = {
            "year": int(year),
            "month": int(month),
            "rainfall_mm_wt": round(weighted_total, 2) if weighted_total is not None else None,
            "historical_year_count": 0,
            "historical_median_mm_wt": None,
            "historical_mean_mm_wt": None,
            "anomaly_mm_wt": None,
            "anomaly_pct_wt": None,
            "rainfall_decile": None,
            "rainfall_decile_label": None,
            "climatology_quality_flag": None,
            "is_partial_month": is_partial,
            "n_sa2s_universe": n_sa2s_universe,
            "n_sa2s_weighted": len(has_rain),
            "n_sa2s_missing_rainfall": n_missing,
            "weighting_area_ha": weighting_area_ha,
            "weighting_area_share": weighting_area_share,
            "fallback_area_sa2s": fallback_count,
            "area_fallback_caveat": fallback_caveat,
            "current_rainfall_source": curr_src,
            "historical_baseline_source": HISTORICAL_BASELINE_SOURCE,
        }

        if weighted_total is None or pd.isna(weighted_total):
            out["climatology_quality_flag"] = "null_weighted_rainfall"
            out_rows.append(out)
            continue

        if is_partial:
            out["climatology_quality_flag"] = "partial_month"
            out_rows.append(out)
            continue

        if weighting_area_share is not None and weighting_area_share < MIN_COVERAGE_SHARE:
            out["climatology_quality_flag"] = f"low_coverage({weighting_area_share:.2f})"
            out_rows.append(out)
            continue

        # Historical distribution: same month, other years, same SA2 mask as target month.
        # Each historical year's weighted total is recomputed restricted to contributing_codes
        # so the comparison is like-for-like (same SA2 mix, same area weights).
        hist_totals: list[float] = []
        for (hist_year, hist_month), hist_group in groups.items():
            if hist_month != month or hist_year == year:
                continue
            hist_eligible = hist_group[
                hist_group["sa2_code"].isin(contributing_codes)
                & hist_group["rainfall_mm"].notna()
            ]
            if hist_eligible.empty:
                continue
            hw = hist_eligible["area_ha_for_weighting"]
            hr = hist_eligible["rainfall_mm"]
            ht = float(hw.sum())
            if ht > 0:
                hist_totals.append(float((hr * hw).sum() / ht))

        historical = pd.Series(hist_totals, dtype=float)
        hist_count = len(historical)
        out["historical_year_count"] = hist_count

        if hist_count < MIN_HISTORY_COUNT:
            out["climatology_quality_flag"] = f"insufficient_history({hist_count})"
            out_rows.append(out)
            continue

        median_mm = float(historical.median())
        mean_mm = float(historical.mean())
        anomaly_mm = weighted_total - median_mm
        anomaly_pct = (anomaly_mm / median_mm * 100) if median_mm != 0 else None
        decile = _compute_decile(weighted_total, historical)

        out.update({
            "historical_median_mm_wt": round(median_mm, 2),
            "historical_mean_mm_wt": round(mean_mm, 2),
            "anomaly_mm_wt": round(anomaly_mm, 2),
            "anomaly_pct_wt": round(anomaly_pct, 1) if anomaly_pct is not None else None,
            "rainfall_decile": decile,
            "rainfall_decile_label": DECILE_LABELS[decile],
            "climatology_quality_flag": "ok",
        })
        out_rows.append(out)

    return pd.DataFrame(out_rows, columns=OUTPUT_COLS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", default=str(HISTORY_CSV))
    parser.add_argument("--crop-context", default=str(CROP_CONTEXT_CSV))
    parser.add_argument("--output", default=str(OUTPUT_CSV))
    parser.add_argument(
        "--current-year-csv",
        default=None,
        help=(
            "Path to a station-derived monthly SA2 rainfall CSV (e.g. "
            "data/features/sa2_2026_monthly_from_daily.csv). Rows are appended "
            "to history before decile computation. The year and extraction_method "
            "from this file populate current_rainfall_source in the output."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    history_path = Path(args.history)
    context_path = Path(args.crop_context)
    output_path = Path(args.output)

    for path, label in [(history_path, "history"), (context_path, "crop-context")]:
        if not path.exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr)
            sys.exit(1)

    history = pd.read_csv(history_path, dtype={"sa2_code": str})

    current_year_source = None
    if args.current_year_csv:
        cy_path = Path(args.current_year_csv)
        if not cy_path.exists():
            print(f"ERROR: current-year-csv not found: {cy_path}", file=sys.stderr)
            sys.exit(1)
        cy_df = pd.read_csv(cy_path, dtype={"sa2_code": str})
        if cy_df.empty:
            print("WARNING: current-year-csv is empty — skipping", file=sys.stderr)
        else:
            cy_year = int(cy_df["year"].iloc[0])
            cy_source = str(cy_df["current_rainfall_source"].iloc[0])
            current_year_source = {"year": cy_year, "source": cy_source}
            history = pd.concat([history, cy_df], ignore_index=True)
            print(
                f"Appended {len(cy_df)} rows for year {cy_year} "
                f"from {cy_path.name} (source: {cy_source})"
            )

    weights = load_wa_wheat_weights(context_path)

    n_eligible = weights["area_ha_for_weighting"].notna().sum()
    print(
        f"History: {len(history)} rows, {history['sa2_code'].nunique()} SA2s, "
        f"years {sorted(history['year'].unique())}"
    )
    print(f"WA wheat universe: {len(weights)} SA2s, {n_eligible} with area for weighting")

    result = compute_weighted_monthly_deciles(history, weights, current_year_source)

    ok = result["climatology_quality_flag"].eq("ok").sum()
    insuff = result["climatology_quality_flag"].str.startswith("insufficient").sum()
    null_wt = result["climatology_quality_flag"].eq("null_weighted_rainfall").sum()
    partial = result["climatology_quality_flag"].eq("partial_month").sum()
    print(
        f"Results: {ok} ok, {insuff} insufficient history, "
        f"{null_wt} null weighted rainfall, {partial} partial month"
    )

    if args.dry_run:
        print("Dry run — not writing output.")
        with pd.option_context("display.max_columns", None, "display.width", 200):
            print(result.to_string(index=False))
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    print(f"Written {len(result)} rows to {output_path}")


if __name__ == "__main__":
    main()
