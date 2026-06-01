#!/usr/bin/env python3
"""Download SILO monthly_rain NetCDF files from the public S3 bucket.

Source:
    https://s3-ap-southeast-2.amazonaws.com/silo-open-data/Official/annual/monthly_rain/
    Bucket: s3://silo-open-data  (public, no AWS credentials required)
    Key pattern: Official/annual/monthly_rain/{year}.monthly_rain.nc

Files are saved to data/meta/monthly_rain/{year}.monthly_rain.nc (on the HDD via
symlink). Each file is downloaded to a .tmp inside the destination dir, validated
(variable + lat/lon + 12 months in-year), and only then atomically replaced via
os.replace(). A bad download can never clobber a good grid. An existing file is
skipped only if it is itself valid; pass --replace to refresh.

Usage:
    python scripts/download_silo_monthly_rain.py --years 1990 1991 1992
    python scripts/download_silo_monthly_rain.py --years 1990 --replace
    python scripts/download_silo_monthly_rain.py --years 2026 --skip-validate
"""

import argparse
import os
import sys
import urllib.request
from pathlib import Path
from typing import Callable

import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "data" / "meta" / "monthly_rain"
BASE_URL = (
    "https://s3-ap-southeast-2.amazonaws.com"
    "/silo-open-data/Official/annual/monthly_rain"
)
MIN_FILE_BYTES = 1_000_000  # 1 MB — sanity guard; real files are ~14 MB


def validate_monthly_rain(path: Path, year: int, require_complete: bool = True) -> None:
    """Raise ValueError if `path` is not a valid monthly_rain grid for `year`."""
    with xr.open_dataset(path) as ds:
        if "monthly_rain" not in ds:
            raise ValueError("variable 'monthly_rain' missing")
        if "lat" not in ds.dims or "lon" not in ds.dims:
            raise ValueError("dimension 'lat'/'lon' missing")
        n_time = len(ds.time)
        if n_time == 0:
            raise ValueError("time axis is empty")
        if require_complete and n_time != 12:
            raise ValueError(f"expected 12 time steps, got {n_time}")
        bad_years = [
            str(t.values) for t in ds.time if int(str(t.dt.year.values)) != year
        ]
        if bad_years:
            raise ValueError(f"time coordinates with wrong year: {bad_years[:3]}")


def install_year(
    year: int,
    fetch: Callable[[Path], None],
    dest_dir: Path = OUTPUT_DIR,
    allow_replace: bool = False,
    require_complete: bool = True,
    min_bytes: int = MIN_FILE_BYTES,
) -> str:
    """Fetch one monthly grid: fetch -> temp (inside dest_dir) -> validate -> replace.

    Returns "installed", "skipped", "invalid: <reason>", or "error: <reason>".
    Validate-before-skip: an existing file is "skipped" only if it is valid; an
    existing invalid file returns "invalid: ..." unless allow_replace re-fetches.
    """
    dest_dir = Path(dest_dir)
    dest = dest_dir / f"{year}.monthly_rain.nc"

    if dest.exists() and not allow_replace:
        try:
            validate_monthly_rain(dest, year, require_complete=require_complete)
            return "skipped"
        except Exception as exc:
            return f"invalid: existing file {exc}"

    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / f"{year}.monthly_rain.nc.tmp"

    try:
        fetch(tmp)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        return f"error: {exc}"

    try:
        size = tmp.stat().st_size
        if size < min_bytes:
            raise ValueError(
                f"downloaded file too small ({size} bytes < {min_bytes} minimum)"
            )
        validate_monthly_rain(tmp, year, require_complete=require_complete)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        return f"invalid: {exc}"

    os.replace(tmp, dest)
    return "installed"


def _urlretrieve_fetch(year: int):
    url = f"{BASE_URL}/{year}.monthly_rain.nc"

    def fetch(tmp: Path) -> None:
        print(f"  GET  {url}")
        urllib.request.urlretrieve(url, tmp)

    return fetch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, required=True,
                        help="Years to download")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip actual download and write")
    parser.add_argument("--replace", action="store_true",
                        help="Re-download and atomically replace an existing file "
                             "(validated before it overwrites the prior version)")
    parser.add_argument("--skip-validate", action="store_true",
                        help="Accept partial files (no 12-month completeness check)")
    args = parser.parse_args()

    require_complete = not args.skip_validate
    installed: list[int] = []
    skipped: list[int] = []
    failed: list[int] = []

    print(f"\n=== Installing {len(args.years)} year(s) -> {OUTPUT_DIR} ===\n")
    for year in sorted(args.years):
        dest = OUTPUT_DIR / f"{year}.monthly_rain.nc"
        if args.dry_run:
            action = "replace" if (dest.exists() and args.replace) else (
                "skip (exists)" if dest.exists() else "download"
            )
            print(f"  [dry-run] {year}: would {action}")
            continue

        status = install_year(
            year,
            _urlretrieve_fetch(year),
            allow_replace=args.replace,
            require_complete=require_complete,
        )
        if status == "installed":
            installed.append(year)
            print(f"  OK   {year}.monthly_rain.nc ({dest.stat().st_size / 1e6:.1f} MB)")
        elif status == "skipped":
            skipped.append(year)
            print(f"  SKIP {year} — already exists and valid (use --replace to refresh)")
        else:
            failed.append(year)
            print(f"  FAIL {year}: {status}", file=sys.stderr)

    print("\n=== Summary ===")
    print(f"  Installed : {installed if installed else '(none)'}")
    print(f"  Skipped   : {skipped if skipped else '(none)'}")
    if failed:
        print(f"  Failed    : {failed}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
