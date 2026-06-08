#!/usr/bin/env python3
"""Extract partial-month (month-to-date) rainfall for grain SA2s from a
SILO daily_rain NetCDF.

For the current-year scenario where SILO's annual monthly_rain NetCDF does
not yet contain the in-progress month, this script reads the corresponding
daily_rain NetCDF, sums days 1..N (N = latest day with data in that month),
and emits one partial-month row per SA2 in the same schema as the canonical
sa2_monthly_rainfall_history file plus two new columns:

    is_partial_month          (bool)   True for these rows
    partial_month_through_day (int)    Last day included in the sum

Method: centroid_nearest_grid_cell_daily_sum — uses the same SA2 centroid
and nearest-grid-cell selection as scripts/extract_sa2_monthly_rainfall.py,
just summed over a daily time dimension instead of read from a monthly NC.

Decile/anomaly fields are deliberately left null (climatology_quality_flag
= 'partial_month_no_decile') because we do not currently have historical
daily NetCDFs in the repo for a like-for-like 1..N baseline. The decile
builder is updated to pass these rows through unchanged.

Inputs:
    data/meta/daily_rain/{year}.daily_rain.nc
    SA2 universe via load_sa2_rows() from extract_sa2_monthly_rainfall.py

Output:
    data/features/sa2_{year}_{month:02d}_mtd.csv (sidecar, all matching SA2s)

Usage:
    python scripts/extract_sa2_partial_month_rainfall.py --year 2026 --month 5
    python scripts/extract_sa2_partial_month_rainfall.py --year 2026 --month 5 --dry-run
"""

import argparse
import calendar
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.extract_sa2_monthly_rainfall import (  # noqa: E402
    NODATA_THRESHOLD,
    DEFAULT_UNIVERSE_SOURCE,
    load_sa2_rows,
    nearest_grid_value,
)

DAILY_RAIN_DIR = REPO_ROOT / "data" / "meta" / "daily_rain"
OUTPUT_DIR = REPO_ROOT / "data" / "features"

EXTRACTION_METHOD = "centroid_nearest_grid_cell_daily_sum"
SOURCE_VARIABLE = "daily_rain"
PARTIAL_QUALITY_FLAG = "partial_month_no_decile"

# Output schema mirrors the canonical history + deciles file with the two
# new partial-month columns appended. Decile/anomaly fields are emitted as
# None so the downstream decile builder can pass partial-month rows through.
OUTPUT_COLS = [
    "year",
    "month",
    "sa2_code",
    "sa2_name",
    "state_name",
    "rainfall_mm",
    "extraction_method",
    "universe_source",
    "source_file",
    "source_variable",
    "quality_flag",
    "is_partial_month",
    "partial_month_through_day",
]


def _select_month_slice(ds: xr.Dataset, year: int, month: int) -> xr.DataArray:
    da = ds[SOURCE_VARIABLE]
    start = f"{year}-{month:02d}-01"
    # End of month inclusive — xarray slice is inclusive on both ends for
    # cftime/datetime64 indexes. Use the real last day-of-month rather than a
    # hardcoded 31 (which is an invalid date for 30-day months and February and
    # raises on slice); the month-equality check below remains as a guard.
    last_dom = calendar.monthrange(year, month)[1]
    end = f"{year}-{month:02d}-{last_dom:02d}"
    sliced = da.sel(time=slice(start, end))
    if len(sliced.time) == 0:
        raise ValueError(
            f"No daily time steps found for {year}-{month:02d} in NetCDF"
        )
    actual_months = {int(pd.Timestamp(t.values).month) for t in sliced.time}
    if actual_months != {month}:
        raise ValueError(
            f"Slice returned mixed months {actual_months}; expected {{{month}}}"
        )
    return sliced


def _last_complete_day(month_slice: xr.DataArray) -> int:
    """Return the last day-of-month with non-NaN data over the whole grid."""
    days = []
    for t in month_slice.time:
        sl = month_slice.sel(time=t)
        valid = sl.where(sl > NODATA_THRESHOLD)
        if not bool(np.isnan(valid).all()):
            days.append(int(pd.Timestamp(t.values).day))
    if not days:
        raise ValueError("No day in the month slice has any non-NaN values")
    return max(days)


def extract_partial_month(
    nc_path: Path,
    year: int,
    month: int,
    sa2_rows: list[dict],
) -> tuple[pd.DataFrame, int]:
    """Sum daily rainfall at each SA2 centroid for days 1..N of the month.

    Returns (DataFrame, through_day).
    """
    with xr.open_dataset(nc_path) as ds:
        month_slice = _select_month_slice(ds, year, month)
        through_day = _last_complete_day(month_slice)
        # Restrict to days 1..through_day; xarray's selector is inclusive.
        upper = f"{year}-{month:02d}-{through_day:02d}"
        partial = month_slice.sel(time=slice(None, upper))

        records = []
        for row in sa2_rows:
            # Pick the SA2 centroid grid cell, then sum across the daily axis.
            cell = partial.sel(
                lat=row["lat"], lon=row["lon"], method="nearest"
            )
            cell_valid = cell.where(cell > NODATA_THRESHOLD)
            if bool(np.isnan(cell_valid).all()):
                rainfall_mm = float("nan")
                quality_flag = "nodata"
            else:
                rainfall_mm = float(cell_valid.fillna(0).sum().values)
                quality_flag = PARTIAL_QUALITY_FLAG
            records.append(
                {
                    "year": year,
                    "month": month,
                    "sa2_code": row["sa2_code"],
                    "sa2_name": row["sa2_name"],
                    "state_name": row.get("state_name"),
                    "rainfall_mm": rainfall_mm,
                    "extraction_method": EXTRACTION_METHOD,
                    "universe_source": row.get("universe_source"),
                    "source_file": nc_path.name,
                    "source_variable": SOURCE_VARIABLE,
                    "quality_flag": quality_flag,
                    "is_partial_month": True,
                    "partial_month_through_day": through_day,
                }
            )
        return pd.DataFrame(records, columns=OUTPUT_COLS), through_day


def run(
    year: int,
    month: int,
    universe_source: str = DEFAULT_UNIVERSE_SOURCE,
    states: str | None = None,
    output: Path | None = None,
    dry_run: bool = False,
) -> pd.DataFrame:
    nc_path = DAILY_RAIN_DIR / f"{year}.daily_rain.nc"
    if not nc_path.exists():
        print(
            f"ERROR: daily NetCDF not found: {nc_path}\n"
            f"Run: python scripts/download_silo_daily_rain.py "
            f"--years {year} --skip-validate",
            file=sys.stderr,
        )
        sys.exit(1)

    sa2_rows = load_sa2_rows(universe_source=universe_source, states=states)
    if not sa2_rows:
        print("ERROR: SA2 universe is empty after filtering", file=sys.stderr)
        sys.exit(1)

    state_counts = (
        pd.Series([r["state_name"] for r in sa2_rows])
        .value_counts()
        .sort_index()
    )
    print(
        f"Processing {nc_path.name} for {len(sa2_rows)} SA2s "
        f"({universe_source}), year={year} month={month}"
    )
    for state_name, count in state_counts.items():
        print(f"  {state_name}: {count} SA2s")

    df, through_day = extract_partial_month(nc_path, year, month, sa2_rows)
    print(
        f"Extracted {len(df)} rows for {year}-{month:02d} days 1..{through_day} "
        f"({df['quality_flag'].value_counts().to_dict()})"
    )

    if dry_run:
        print("[dry-run] skipping write")
        return df

    out_path = output if output is not None else (
        OUTPUT_DIR / f"sa2_{year}_{month:02d}_mtd.csv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Written → {out_path.relative_to(REPO_ROOT)}")
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument(
        "--universe-source",
        choices=["combined", "geojson", "wa_csv"],
        default=DEFAULT_UNIVERSE_SOURCE,
    )
    parser.add_argument("--states", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output = Path(args.output) if args.output else None
    run(
        year=args.year,
        month=args.month,
        universe_source=args.universe_source,
        states=args.states,
        output=output,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
