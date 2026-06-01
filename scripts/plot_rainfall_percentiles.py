#!/usr/bin/env python3
"""Plot WA wheatbelt monthly rainfall percentiles (SA2 overlay) to a PNG.

Per-cell percentile of the target month vs the same calendar month across the
1911-latest-complete-year baseline, rendered as a discrete-binned raster clipped
to the 26 WA wheatbelt SA2s.

Usage:
    python scripts/plot_rainfall_percentiles.py --month 7 --year 2024
    python scripts/plot_rainfall_percentiles.py --month 7 --year 2024 \
        --baseline-start 1911 --baseline-end 2023 --out reports/figures/jul24.png
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rainfall import boundaries as bd
from src.rainfall import percentiles as pc
from src.rainfall import render as rd


def _lon_lat(grids_dir: Path, year: int):
    with xr.open_dataset(grids_dir / f"{year}.monthly_rain.nc") as ds:
        return ds.lon.values, ds.lat.values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", type=int, required=True, choices=range(1, 13))
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--baseline-start", type=int, default=1911)
    parser.add_argument("--baseline-end", type=int, default=None)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    baseline_end = args.baseline_end or pc.latest_complete_year()
    try:
        target, stack, years = pc.load_month_stack(
            args.month, args.year, args.baseline_start, baseline_end
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    pct = pc.cell_percentile(target, stack)
    regions = bd.load_wheatbelt_regions()
    lon, lat = _lon_lat(pc.GRIDS_DIR, args.year)

    out = rd.render_percentile_map(
        pct, regions, lon=lon, lat=lat, month=args.month, year=args.year,
        baseline_start=args.baseline_start, baseline_end=baseline_end,
        out_path=args.out, mask_geom=bd.clip_mask(regions),
    )
    print(f"Wrote {out} (baseline {args.baseline_start}-{baseline_end}, {len(years)} yrs)")


if __name__ == "__main__":
    main()
