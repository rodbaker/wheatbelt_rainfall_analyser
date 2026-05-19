#!/usr/bin/env python3
"""Build monthly rainfall climatology and deciles for wheatbelt SA2s.

For each SA2 × month × year, compares rainfall_mm against all prior years
for the same SA2 and calendar month, excluding the current row's year from
its own historical baseline.

Inputs:
    data/features/sa2_monthly_rainfall_history.csv

Output:
    data/features/sa2_monthly_rainfall_deciles.csv

Usage:
    python scripts/build_sa2_rainfall_deciles.py
    python scripts/build_sa2_rainfall_deciles.py --dry-run
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = REPO_ROOT / "data" / "features" / "sa2_monthly_rainfall_history.csv"
OUTPUT_CSV = REPO_ROOT / "data" / "features" / "sa2_monthly_rainfall_deciles.csv"

MIN_HISTORY_COUNT = 10

OUTPUT_COLS = [
    "year",
    "month",
    "sa2_code",
    "sa2_name",
    "state_name",
    "rainfall_mm",
    "historical_year_count",
    "historical_median_mm",
    "historical_mean_mm",
    "anomaly_mm",
    "anomaly_pct",
    "rainfall_decile",
    "rainfall_decile_label",
    "climatology_quality_flag",
    "extraction_method",
    "universe_source",
    "source_variable",
]

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


def _decile_label(decile: int) -> str:
    return DECILE_LABELS[decile]


def _compute_decile(value: float, historical: pd.Series) -> int:
    """Return 1-10 decile rank of value within historical distribution."""
    n = len(historical)
    rank = (historical < value).sum() + 1
    # Convert rank to decile (1-10), clamped
    decile = int(np.ceil(rank / n * 10))
    return max(1, min(10, decile))


def compute_deciles(df: pd.DataFrame) -> pd.DataFrame:
    """Compute climatology and decile fields for each row in df."""
    has_state_col = "state_name" in df.columns
    rows = []
    for _, row in df.iterrows():
        sa2 = row["sa2_code"]
        month = row["month"]
        year = row["year"]
        rainfall = row["rainfall_mm"]
        state = row.get("state_name") if has_state_col else None

        # Historical baseline key: state+SA2+month when state_name is present,
        # SA2+month only for legacy inputs without state_name.  This prevents
        # the four SA2 codes that appear in two states from sharing baselines.
        mask = (df["sa2_code"] == sa2) & (df["month"] == month) & (df["year"] != year)
        if has_state_col and pd.notna(state):
            mask = mask & (df["state_name"] == state)
        historical = df.loc[mask, "rainfall_mm"].dropna()
        hist_count = len(historical)

        out = {
            "year": year,
            "month": month,
            "sa2_code": sa2,
            "sa2_name": row["sa2_name"],
            "state_name": row.get("state_name"),
            "rainfall_mm": rainfall,
            "historical_year_count": hist_count,
            "historical_median_mm": None,
            "historical_mean_mm": None,
            "anomaly_mm": None,
            "anomaly_pct": None,
            "rainfall_decile": None,
            "rainfall_decile_label": None,
            "climatology_quality_flag": None,
            "extraction_method": row.get("extraction_method"),
            "universe_source": row.get("universe_source"),
            "source_variable": row.get("source_variable"),
        }

        if pd.isna(rainfall):
            out["climatology_quality_flag"] = "null_rainfall"
            rows.append(out)
            continue

        if hist_count < MIN_HISTORY_COUNT:
            out["climatology_quality_flag"] = f"insufficient_history({hist_count})"
            rows.append(out)
            continue

        median_mm = historical.median()
        mean_mm = historical.mean()
        anomaly_mm = rainfall - median_mm
        anomaly_pct = (anomaly_mm / median_mm * 100) if median_mm != 0 else None
        decile = _compute_decile(rainfall, historical)

        out.update({
            "historical_median_mm": round(median_mm, 2),
            "historical_mean_mm": round(mean_mm, 2),
            "anomaly_mm": round(anomaly_mm, 2),
            "anomaly_pct": round(anomaly_pct, 1) if anomaly_pct is not None else None,
            "rainfall_decile": decile,
            "rainfall_decile_label": _decile_label(decile),
            "climatology_quality_flag": "ok",
        })
        rows.append(out)

    return pd.DataFrame(rows, columns=OUTPUT_COLS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(INPUT_CSV))
    parser.add_argument("--output", default=str(OUTPUT_CSV))
    parser.add_argument(
        "--states",
        default=None,
        help='Optional comma-separated state filter on state_name, e.g. "Western Australia,South Australia".',
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(input_path, dtype={"sa2_code": str})
    print(f"Loaded {len(df)} rows from {input_path}")

    if args.states:
        if "state_name" not in df.columns:
            print(
                "ERROR: --states provided but input has no state_name column",
                file=sys.stderr,
            )
            sys.exit(1)
        state_filter = {s.strip() for s in args.states.split(",") if s.strip()}
        df = df[df["state_name"].isin(state_filter)]
        if df.empty:
            print(
                f"ERROR: no rows remain after filtering to states: {sorted(state_filter)}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Filtered to {len(df)} rows for states: {sorted(state_filter)}")

    result = compute_deciles(df)

    null_rain = result["climatology_quality_flag"].eq("null_rainfall").sum()
    insuff = result["climatology_quality_flag"].str.startswith("insufficient").sum()
    ok = result["climatology_quality_flag"].eq("ok").sum()
    print(f"Results: {ok} ok, {insuff} insufficient history, {null_rain} null rainfall")

    if args.dry_run:
        print("Dry run — not writing output.")
        print(result.head(10).to_string(index=False))
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    print(f"Written {len(result)} rows to {output_path}")


if __name__ == "__main__":
    main()
