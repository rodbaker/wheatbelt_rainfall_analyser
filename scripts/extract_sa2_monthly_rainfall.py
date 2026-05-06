#!/usr/bin/env python3
"""Extract monthly rainfall for WA wheatbelt SA2s from SILO NetCDF files.

Method: centroid_nearest_grid_cell — each SA2 is represented by its polygon
centroid (average of exterior ring vertices), and we snap to the nearest
NetCDF grid cell. This is NOT polygon-area-averaged.

Inputs:
    data/meta/monthly_rain/*.monthly_rain.nc
    data/meta/wa_wheatbelt_sa2_universe_2021.csv
    data/meta/SA2_ABS_Regions.geojson  (2016 boundaries; used for centroid calc)

Output:
    data/features/sa2_monthly_rainfall_history.csv

Usage:
    python scripts/extract_sa2_monthly_rainfall.py
    python scripts/extract_sa2_monthly_rainfall.py --dry-run
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[1]
MONTHLY_RAIN_DIR = REPO_ROOT / "data" / "meta" / "monthly_rain"
SA2_UNIVERSE_CSV = REPO_ROOT / "data" / "meta" / "wa_wheatbelt_sa2_universe_2021.csv"
GEOJSON_PATH = REPO_ROOT / "data" / "meta" / "SA2_ABS_Regions.geojson"
OUTPUT_CSV = REPO_ROOT / "data" / "features" / "sa2_monthly_rainfall_history.csv"

EXTRACTION_METHOD = "centroid_nearest_grid_cell"
SOURCE_VARIABLE = "monthly_rain"
NODATA_THRESHOLD = -32000.0

# Approximate centroids for 3 SA2s whose 2021 codes are absent from the 2016
# GeoJSON. Coordinates verified against ABS boundaries and OSM:
#   501021007 Capel: new SA2 carved from 501021008 Harvey in 2021
#   511011274 Esperance: code change from 511011275 in 2021
#   511041287 Geraldton - North: split from 511041285 Geraldton in 2021
FALLBACK_CENTROIDS = {
    "501021007": (-33.56, 115.57),   # Capel
    "511011274": (-33.86, 121.89),   # Esperance
    "511041287": (-28.71, 114.61),   # Geraldton - North
}


def _poly_centroid(geometry: dict) -> tuple[float, float]:
    """Return (lat, lon) centroid by averaging exterior ring vertices."""
    lons, lats = [], []
    polys = (
        geometry["coordinates"]
        if geometry["type"] == "MultiPolygon"
        else [geometry["coordinates"]]
    )
    for poly in polys:
        for lon, lat in poly[0]:
            lons.append(lon)
            lats.append(lat)
    return sum(lats) / len(lats), sum(lons) / len(lons)


def load_sa2_centroids() -> dict[str, tuple[float, float]]:
    """Return {sa2_code: (lat, lon)} for all 28 universe SA2s."""
    universe = pd.read_csv(SA2_UNIVERSE_CSV, dtype=str)
    with open(GEOJSON_PATH) as fh:
        geojson = json.load(fh)

    code_to_geom = {
        feat["properties"]["SA2_MAIN16"]: feat["geometry"]
        for feat in geojson["features"]
    }

    centroids: dict[str, tuple[float, float]] = {}
    for _, row in universe.iterrows():
        code = row["SA2_CODE21"]
        if code in code_to_geom:
            centroids[code] = _poly_centroid(code_to_geom[code])
        elif code in FALLBACK_CENTROIDS:
            centroids[code] = FALLBACK_CENTROIDS[code]
        else:
            raise ValueError(
                f"No centroid available for SA2 {code} ({row['SA2_NAME21']}). "
                "Add an entry to FALLBACK_CENTROIDS."
            )
    return centroids


def nearest_grid_value(
    da: xr.DataArray,
    lat: float,
    lon: float,
) -> float:
    """Snap to nearest grid cell and return the scalar value."""
    point = da.sel(lat=lat, lon=lon, method="nearest")
    return float(point.values)


def extract_one_file(
    nc_path: Path,
    sa2_rows: list[dict],
) -> list[dict]:
    """Extract monthly rainfall for all SA2s from a single NetCDF file."""
    records = []
    with xr.open_dataset(nc_path) as ds:
        da = ds[SOURCE_VARIABLE]
        for time_step in da.time:
            dt = pd.Timestamp(time_step.values)
            year, month = dt.year, dt.month
            da_slice = da.sel(time=time_step)
            for row in sa2_rows:
                raw = nearest_grid_value(da_slice, row["lat"], row["lon"])
                if raw < NODATA_THRESHOLD:
                    rainfall_mm = float("nan")
                    quality_flag = "nodata"
                else:
                    rainfall_mm = raw
                    quality_flag = "ok"
                records.append(
                    {
                        "year": year,
                        "month": month,
                        "sa2_code": row["sa2_code"],
                        "sa2_name": row["sa2_name"],
                        "rainfall_mm": rainfall_mm,
                        "extraction_method": EXTRACTION_METHOD,
                        "source_file": nc_path.name,
                        "source_variable": SOURCE_VARIABLE,
                        "quality_flag": quality_flag,
                    }
                )
    return records


def run(dry_run: bool = False) -> pd.DataFrame:
    nc_files = sorted(MONTHLY_RAIN_DIR.glob("*.monthly_rain.nc"))
    if not nc_files:
        print(f"ERROR: no *.monthly_rain.nc files found in {MONTHLY_RAIN_DIR}", file=sys.stderr)
        sys.exit(1)

    universe = pd.read_csv(SA2_UNIVERSE_CSV, dtype=str)
    centroids = load_sa2_centroids()

    sa2_rows = [
        {
            "sa2_code": row["SA2_CODE21"],
            "sa2_name": row["SA2_NAME21"],
            "lat": centroids[row["SA2_CODE21"]][0],
            "lon": centroids[row["SA2_CODE21"]][1],
        }
        for _, row in universe.iterrows()
    ]

    print(f"Processing {len(nc_files)} NetCDF file(s) for {len(sa2_rows)} SA2s …")
    all_records = []
    for nc_path in nc_files:
        print(f"  {nc_path.name}")
        all_records.extend(extract_one_file(nc_path, sa2_rows))

    df = pd.DataFrame(all_records)

    # Validate: no values below nodata threshold survive
    bad = df["rainfall_mm"].dropna() < NODATA_THRESHOLD
    if bad.any():
        raise RuntimeError(f"NODATA values leaked into output: {bad.sum()} rows")

    print(f"Extracted {len(df):,} rows ({df['quality_flag'].value_counts().to_dict()})")

    if dry_run:
        print("[dry-run] skipping write")
        return df

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Written → {OUTPUT_CSV.relative_to(REPO_ROOT)}")
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Skip writing output CSV")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
