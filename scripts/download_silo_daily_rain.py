#!/usr/bin/env python3
"""Download SILO daily_rain NetCDF files from the public S3 bucket.

Source:
    https://s3-ap-southeast-2.amazonaws.com/silo-open-data/Official/annual/daily_rain/
    Bucket: s3://silo-open-data  (public, no AWS credentials required)
    Key pattern: Official/annual/daily_rain/{year}.daily_rain.nc

Files are saved to data/meta/daily_rain/{year}.daily_rain.nc.
Existing files are never overwritten.
Each file is downloaded to a .tmp path and atomically renamed on success.

Note: For partial-year files (current year), pass --skip-validate; the
validator otherwise expects 365 (or 366) time steps for completed years.

Usage:
    python scripts/download_silo_daily_rain.py --years 2026 --skip-validate
    python scripts/download_silo_daily_rain.py --years 2024 2025
"""

import argparse
import calendar
import sys
import urllib.request
from pathlib import Path

import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "data" / "meta" / "daily_rain"
BASE_URL = (
    "https://s3-ap-southeast-2.amazonaws.com"
    "/silo-open-data/Official/annual/daily_rain"
)
MIN_FILE_BYTES = 1_000_000  # 1 MB — sanity guard; full years are ~400 MB, partial 2026 is ~150 MB


def download_year(year: int, dry_run: bool = False) -> bool:
    filename = f"{year}.daily_rain.nc"
    dest = OUTPUT_DIR / filename
    url = f"{BASE_URL}/{filename}"

    if dest.exists():
        print(f"  SKIP {filename} — already exists ({dest.stat().st_size / 1e6:.1f} MB)")
        return True

    print(f"  GET  {url}")
    if dry_run:
        print(f"       [dry-run] would write → {dest}")
        return True

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".nc.tmp")
    try:
        urllib.request.urlretrieve(url, tmp)
        size = tmp.stat().st_size
        if size < MIN_FILE_BYTES:
            tmp.unlink(missing_ok=True)
            print(
                f"  ERR  {filename}: downloaded file too small "
                f"({size} bytes < {MIN_FILE_BYTES} minimum)",
                file=sys.stderr,
            )
            return False
        tmp.rename(dest)
        print(f"  OK   {filename} ({dest.stat().st_size / 1e6:.1f} MB)")
        return True
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        print(f"  ERR  {filename}: {exc}", file=sys.stderr)
        return False


def validate_year(year: int) -> bool:
    dest = OUTPUT_DIR / f"{year}.daily_rain.nc"
    expected = 366 if calendar.isleap(year) else 365
    try:
        with xr.open_dataset(dest) as ds:
            if "daily_rain" not in ds:
                raise ValueError("variable 'daily_rain' missing")
            if "lat" not in ds.dims or "lon" not in ds.dims:
                raise ValueError("dimension 'lat'/'lon' missing")
            n_time = len(ds.time)
            if n_time != expected:
                raise ValueError(f"expected {expected} time steps, got {n_time}")
            bad_years = [
                str(t.values)
                for t in ds.time
                if int(str(t.dt.year.values)) != year
            ]
            if bad_years:
                raise ValueError(f"time coordinates with wrong year: {bad_years[:3]}")
        print(f"  VALID {year}: daily_rain ok, {n_time} time steps")
        return True
    except Exception as exc:
        print(f"  INVALID {year}: {exc}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, required=True, help="Years to download")
    parser.add_argument("--dry-run", action="store_true", help="Skip actual download and write")
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip post-download validation (use for partial current-year files)",
    )
    args = parser.parse_args()

    failed_download: list[int] = []
    failed_validate: list[int] = []
    skipped: list[int] = []
    downloaded: list[int] = []

    print(f"\n=== Downloading {len(args.years)} year(s) → {OUTPUT_DIR} ===\n")
    for year in sorted(args.years):
        dest = OUTPUT_DIR / f"{year}.daily_rain.nc"
        already_existed = dest.exists()
        ok = download_year(year, dry_run=args.dry_run)
        if not ok:
            failed_download.append(year)
        elif already_existed:
            skipped.append(year)
        else:
            downloaded.append(year)

    if not args.dry_run and not args.skip_validate:
        print("\n=== Validating ===\n")
        for year in sorted(args.years):
            if year in failed_download:
                continue
            if not validate_year(year):
                failed_validate.append(year)

    print("\n=== Summary ===")
    print(f"  Downloaded : {downloaded if downloaded else '(none)'}")
    print(f"  Skipped    : {skipped if skipped else '(none)'}")
    if failed_download:
        print(f"  Failed DL  : {failed_download}", file=sys.stderr)
    if failed_validate:
        print(f"  Failed val : {failed_validate}", file=sys.stderr)

    if failed_download or failed_validate:
        sys.exit(1)


if __name__ == "__main__":
    main()
