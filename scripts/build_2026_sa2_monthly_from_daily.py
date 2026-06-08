#!/usr/bin/env python3
"""Derive SA2 monthly rainfall from daily SILO station data in DuckDB.

Used when SILO NetCDF monthly files are not yet available for the current year.
For each WA wheat SA2, aggregates daily station rainfall to monthly totals
using simple mean across contributing stations.

Method: station_daily_sa2 — each SA2 gets the simple mean of monthly
station totals from all stations mapped to that SA2 in station_regions.csv.
This differs from the NetCDF centroid_nearest_grid_cell method used for
historical monthly rainfall. Rows are labelled with current_rainfall_source
so the distinction is preserved downstream.

Inputs:
    data/weather.duckdb                                  (daily station obs)
    data/meta/station_regions.csv                        (station_id → sa2_name)
    data/meta/wa_wheatbelt_sa2_universe_2021.csv         (sa2_name → sa2_code)

Output:
    data/features/sa2_<year>_monthly_from_daily.csv

Usage:
    python scripts/build_2026_sa2_monthly_from_daily.py
    python scripts/build_2026_sa2_monthly_from_daily.py --year 2026 --dry-run
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DUCKDB_PATH = REPO_ROOT / "data" / "weather.duckdb"
STATION_REGIONS_CSV = REPO_ROOT / "data" / "meta" / "station_regions.csv"
SA2_UNIVERSE_CSV = REPO_ROOT / "data" / "meta" / "wa_wheatbelt_sa2_universe_2021.csv"

EXTRACTION_METHOD = "station_daily_sa2"
SOURCE_FILE = "weather.duckdb"
SOURCE_VARIABLE = "rainfall"


def output_path(year: int) -> Path:
    return REPO_ROOT / "data" / "features" / f"sa2_{year}_monthly_from_daily.csv"


def load_sa2_station_mapping() -> pd.DataFrame:
    """Return DataFrame with station_id, sa2_code, sa2_name for WA wheat SA2s."""
    regions = pd.read_csv(STATION_REGIONS_CSV, dtype={"station_id": str})
    universe = pd.read_csv(SA2_UNIVERSE_CSV, dtype=str).rename(
        columns={"SA2_CODE21": "sa2_code", "SA2_NAME21": "sa2_name"}
    )
    merged = regions.merge(universe, on="sa2_name", how="inner")
    return merged[["station_id", "sa2_code", "sa2_name"]].drop_duplicates()


def fetch_station_monthly(year: int) -> pd.DataFrame:
    """Query DuckDB: monthly rainfall total per station for the given year."""
    conn = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    df = conn.execute(
        """
        SELECT
            station_id,
            year(date)::INTEGER  AS year,
            month(date)::INTEGER AS month,
            SUM(rainfall)        AS monthly_total_mm,
            COUNT(*)             AS day_count
        FROM weather_observations
        WHERE year(date) = ?
          AND rainfall IS NOT NULL
        GROUP BY station_id, year(date), month(date)
        ORDER BY station_id, month(date)
        """,
        [year],
    ).fetchdf()
    conn.close()
    return df


def compute_sa2_monthly(
    station_monthly: pd.DataFrame,
    sa2_mapping: pd.DataFrame,
    year: int,
    today: date,
) -> pd.DataFrame:
    """Aggregate station monthly totals to SA2 level via simple mean.

    A month is flagged is_partial_month when it matches the current calendar
    month of the target year, indicating an in-progress accumulation.
    """
    joined = station_monthly.merge(sa2_mapping, on="station_id", how="inner")
    if joined.empty:
        return pd.DataFrame()

    current_month = today.month if today.year == year else 0
    records = []
    for (sa2_code, sa2_name, month), group in joined.groupby(
        ["sa2_code", "sa2_name", "month"], sort=True
    ):
        is_partial = int(month) == current_month
        records.append(
            {
                "year": year,
                "month": int(month),
                "sa2_code": sa2_code,
                "sa2_name": sa2_name,
                "rainfall_mm": round(float(group["monthly_total_mm"].mean()), 3),
                "extraction_method": EXTRACTION_METHOD,
                "source_file": SOURCE_FILE,
                "source_variable": SOURCE_VARIABLE,
                "quality_flag": "partial_month" if is_partial else "ok",
                "station_count": len(group),
                "is_partial_month": is_partial,
                "current_rainfall_source": EXTRACTION_METHOD,
            }
        )
    return pd.DataFrame(records)


def run(year: int = 2026, dry_run: bool = False, today: date = None) -> pd.DataFrame:
    if today is None:
        today = date.today()

    sa2_mapping = load_sa2_station_mapping()
    matched_sa2s = sa2_mapping["sa2_code"].nunique()
    print(
        f"Station mapping: {len(sa2_mapping)} station-SA2 pairs, {matched_sa2s} SA2s matched"
    )

    station_monthly = fetch_station_monthly(year)
    print(f"Station monthly totals: {len(station_monthly)} rows for {year}")

    result = compute_sa2_monthly(station_monthly, sa2_mapping, year, today)
    if result.empty:
        print("WARNING: no SA2 monthly rows produced", file=sys.stderr)
        return result

    by_month = result.groupby("month").agg(
        n_sa2s=("sa2_code", "count"),
        partial=("is_partial_month", "any"),
    )
    for m, row in by_month.iterrows():
        tag = " (MTD)" if row["partial"] else ""
        print(f"  Month {m:02d}{tag}: {int(row['n_sa2s'])} SA2s")

    if dry_run:
        print("[dry-run] skipping write")
        with pd.option_context("display.max_columns", None, "display.width", 200):
            print(result.to_string(index=False))
        return result

    out = output_path(year)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    print(f"Written {len(result)} rows → {out.relative_to(REPO_ROOT)}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026, help="Target year (default: 2026)")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing")
    args = parser.parse_args()
    run(year=args.year, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
