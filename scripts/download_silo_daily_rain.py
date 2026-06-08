#!/usr/bin/env python3
"""Download SILO daily_rain NetCDF files from the public S3 bucket.

Source:
    https://s3-ap-southeast-2.amazonaws.com/silo-open-data/Official/annual/daily_rain/
    Bucket: s3://silo-open-data  (public, no AWS credentials required)
    Key pattern: Official/annual/daily_rain/{year}.daily_rain.nc

Files are saved to data/meta/daily_rain/{year}.daily_rain.nc — which now lives
on the HDD (/mnt/d) via a symlink. Each file is downloaded to a .tmp path
*inside the destination directory*, validated (variable + lat/lon + time
coords), and only then atomically replaced via os.replace(). Temp and final
share a filesystem, so the rename is a safe intra-filesystem atomic swap and a
bad download can never clobber a good existing file.

By default an existing file is skipped. Pass --replace to refresh it: the new
file is validated before it overwrites the prior version, so the old manual
"move the .bak aside first" dance is no longer needed.

Note: For partial-year files (current year), pass --skip-validate; the
validator otherwise expects 365 (or 366) time steps for completed years.

Usage:
    python scripts/download_silo_daily_rain.py --years 2026 --skip-validate
    python scripts/download_silo_daily_rain.py --years 2026 --replace --skip-validate
    python scripts/download_silo_daily_rain.py --years 2024 2025
"""

import argparse
import calendar
import os
import sys
import urllib.request
from pathlib import Path
from typing import Callable

import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "data" / "meta" / "daily_rain"
BASE_URL = (
    "https://s3-ap-southeast-2.amazonaws.com"
    "/silo-open-data/Official/annual/daily_rain"
)
MIN_FILE_BYTES = 1_000_000  # 1 MB — sanity guard; full years are ~400 MB, partial 2026 is ~150 MB


def validate_daily_rain(path: Path, year: int, require_complete: bool = True) -> None:
    """Raise ValueError if `path` is not a structurally-valid daily_rain grid for `year`.

    Checks the variable, lat/lon dims, and time coordinates. When
    require_complete is True the file must hold a full year (365/366 days);
    when False (current-year partials) any non-empty time axis is accepted as
    long as every timestamp falls in `year`.
    """
    with xr.open_dataset(path) as ds:
        if "daily_rain" not in ds:
            raise ValueError("variable 'daily_rain' missing")
        if "lat" not in ds.dims or "lon" not in ds.dims:
            raise ValueError("dimension 'lat'/'lon' missing")
        n_time = len(ds.time)
        if n_time == 0:
            raise ValueError("time axis is empty")
        if require_complete:
            expected = 366 if calendar.isleap(year) else 365
            if n_time != expected:
                raise ValueError(f"expected {expected} time steps, got {n_time}")
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
    """Safely place one daily_rain grid: fetch → temp → validate → atomic replace.

    `fetch(tmp_path)` is responsible only for writing the downloaded bytes to the
    given temp path. The temp file is created INSIDE `dest_dir` so the final
    os.replace() is an intra-filesystem atomic rename (required for /mnt/d).

    The existing destination file is never modified unless the new download
    passes every check. Returns one of: "installed", "skipped",
    "invalid: <reason>", or "error: <reason>".
    """
    dest_dir = Path(dest_dir)
    dest = dest_dir / f"{year}.daily_rain.nc"

    if dest.exists() and not allow_replace:
        return "skipped"

    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / f"{year}.daily_rain.nc.tmp"

    try:
        fetch(tmp)
    except Exception as exc:  # download failed — leave dest untouched
        tmp.unlink(missing_ok=True)
        return f"error: {exc}"

    try:
        size = tmp.stat().st_size
        if size < min_bytes:
            raise ValueError(
                f"downloaded file too small ({size} bytes < {min_bytes} minimum)"
            )
        validate_daily_rain(tmp, year, require_complete=require_complete)
    except Exception as exc:  # bad file — preserve existing dest, drop temp
        tmp.unlink(missing_ok=True)
        return f"invalid: {exc}"

    os.replace(tmp, dest)  # atomic, intra-filesystem
    return "installed"


def _urlretrieve_fetch(year: int):
    """Build a fetch(tmp) callable that downloads the year's grid to tmp."""
    url = f"{BASE_URL}/{year}.daily_rain.nc"

    def fetch(tmp: Path) -> None:
        print(f"  GET  {url}")
        urllib.request.urlretrieve(url, tmp)

    return fetch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, required=True, help="Years to download")
    parser.add_argument("--dry-run", action="store_true", help="Skip actual download and write")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Re-download and atomically replace an existing file "
        "(validated before it overwrites the prior version)",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Accept partial current-year files (no full-year completeness check)",
    )
    args = parser.parse_args()

    require_complete = not args.skip_validate
    installed: list[int] = []
    skipped: list[int] = []
    failed: list[int] = []

    print(f"\n=== Installing {len(args.years)} year(s) → {OUTPUT_DIR} ===\n")
    for year in sorted(args.years):
        dest = OUTPUT_DIR / f"{year}.daily_rain.nc"
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
            print(f"  OK   {year}.daily_rain.nc ({dest.stat().st_size / 1e6:.1f} MB)")
        elif status == "skipped":
            skipped.append(year)
            print(f"  SKIP {year} — already exists (use --replace to refresh)")
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
