#!/usr/bin/env python3
"""Download SILO monthly_rain NetCDF files from the public S3 bucket.

Source:
    https://s3-ap-southeast-2.amazonaws.com/silo-open-data/Official/annual/monthly_rain/
    Bucket: s3://silo-open-data  (public, no AWS credentials required)
    Key pattern: Official/annual/monthly_rain/{year}.monthly_rain.nc

Files are saved to data/meta/monthly_rain/{year}.monthly_rain.nc.
Existing files are never overwritten.
Each file is downloaded to a .tmp path and atomically renamed on success.

Usage:
    python scripts/download_silo_monthly_rain.py --years 2006 2007 2008 2009 2010
    python scripts/download_silo_monthly_rain.py --years 2006 --dry-run
    python scripts/download_silo_monthly_rain.py --years 2006 --skip-validate
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


def download_year(year: int, dry_run: bool = False) -> bool:
    filename = f"{year}.monthly_rain.nc"
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
    dest = OUTPUT_DIR / f"{year}.monthly_rain.nc"
    try:
        with xr.open_dataset(dest) as ds:
            if "monthly_rain" not in ds:
                raise ValueError("variable 'monthly_rain' missing")
            if "lat" not in ds.dims:
                raise ValueError("dimension 'lat' missing")
            if "lon" not in ds.dims:
                raise ValueError("dimension 'lon' missing")
            n_time = len(ds.time)
            if n_time != 12:
                raise ValueError(f"expected 12 time steps, got {n_time}")
            bad_years = [
                str(t.values)
                for t in ds.time
                if int(str(t.dt.year.values)) != year
            ]
            if bad_years:
                raise ValueError(
                    f"time coordinates with wrong year: {bad_years[:3]}"
                )
        print(f"  VALID {year}: monthly_rain ok, 12 time steps, lat/lon present, year correct")
        return True
    except Exception as exc:
        print(f"  INVALID {year}: {exc}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, required=True, help="Years to download")
    parser.add_argument("--dry-run", action="store_true", help="Skip actual download and write")
    parser.add_argument("--skip-validate", action="store_true", help="Skip post-download validation")
    args = parser.parse_args()

    failed_download: list[int] = []
    failed_validate: list[int] = []
    skipped: list[int] = []
    downloaded: list[int] = []

    print(f"\n=== Downloading {len(args.years)} year(s) → {OUTPUT_DIR} ===\n")
    for year in sorted(args.years):
        dest = OUTPUT_DIR / f"{year}.monthly_rain.nc"
        already_existed = dest.exists()
        ok = download_year(year, dry_run=args.dry_run)
        if not ok:
            failed_download.append(year)
        elif already_existed:
            skipped.append(year)
        else:
            downloaded.append(year)

    if not args.dry_run and not args.skip_validate:
        print(f"\n=== Validating ===\n")
        for year in sorted(args.years):
            if year in failed_download:
                continue
            if not validate_year(year):
                failed_validate.append(year)

    print(f"\n=== Summary ===")
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
