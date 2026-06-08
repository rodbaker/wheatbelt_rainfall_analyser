#!/usr/bin/env python3
"""Extract monthly rainfall for wheatbelt SA2s from SILO NetCDF files.

Method: centroid_nearest_grid_cell — each SA2 is represented by its polygon
centroid (average of exterior ring vertices), and we snap to the nearest
NetCDF grid cell. This is NOT polygon-area-averaged.

Inputs:
    data/meta/monthly_rain/*.monthly_rain.nc
    data/meta/wa_wheatbelt_sa2_universe_2021.csv  (optional WA 2021 override)
    data/meta/SA2_ABS_Regions.geojson  (2016 boundaries; used for centroid calc)

Output:
    data/features/sa2_monthly_rainfall_history.csv

Usage:
    python scripts/extract_sa2_monthly_rainfall.py
    python scripts/extract_sa2_monthly_rainfall.py --universe-source geojson
    python scripts/extract_sa2_monthly_rainfall.py --states "Western Australia,South Australia"
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
DEFAULT_UNIVERSE_SOURCE = "combined"

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


def _normalise_states(states: str | None) -> set[str] | None:
    if not states:
        return None
    return {s.strip() for s in states.split(",") if s.strip()}


def _load_geojson_features() -> list[dict]:
    with open(GEOJSON_PATH) as fh:
        geojson = json.load(fh)
    return geojson["features"]


def _geojson_centroids() -> dict[str, tuple[float, float]]:
    return {
        feat["properties"]["SA2_MAIN16"]: _poly_centroid(feat["geometry"])
        for feat in _load_geojson_features()
    }


def load_wa_universe_rows() -> list[dict]:
    """Return WA override rows from the 2021 QGIS universe CSV."""
    universe = pd.read_csv(SA2_UNIVERSE_CSV, dtype=str)
    centroids = _geojson_centroids()

    rows = []
    for _, row in universe.iterrows():
        code = row["SA2_CODE21"]
        if code in centroids:
            lat, lon = centroids[code]
        elif code in FALLBACK_CENTROIDS:
            lat, lon = FALLBACK_CENTROIDS[code]
        else:
            raise ValueError(
                f"No centroid available for SA2 {code} ({row['SA2_NAME21']}). "
                "Add an entry to FALLBACK_CENTROIDS."
            )
        rows.append({
            "sa2_code": code,
            "sa2_name": row["SA2_NAME21"],
            "state_name": "Western Australia",
            "lat": lat,
            "lon": lon,
            "universe_source": "wa_2021_csv",
        })
    return rows


def load_geojson_universe_rows(
    states: set[str] | None = None,
    exclude_states: set[str] | None = None,
) -> list[dict]:
    """Return SA2 rows from the wheatbelt GeoJSON boundary file."""
    rows = []
    for feat in _load_geojson_features():
        props = feat["properties"]
        state_name = props.get("STE_NAME16", "")
        if states is not None and state_name not in states:
            continue
        if exclude_states is not None and state_name in exclude_states:
            continue
        lat, lon = _poly_centroid(feat["geometry"])
        rows.append({
            "sa2_code": props["SA2_MAIN16"],
            "sa2_name": props["SA2_NAME16"],
            "state_name": state_name,
            "lat": lat,
            "lon": lon,
            "universe_source": "geojson_2016",
        })
    return rows


def load_sa2_rows(
    universe_source: str = DEFAULT_UNIVERSE_SOURCE,
    states: str | None = None,
) -> list[dict]:
    """
    Return SA2 rows for rainfall extraction.

    universe_source:
      - combined: WA 2021 CSV plus non-WA GeoJSON rows.
      - geojson: all rows directly from the GeoJSON boundary file.
      - wa_csv: legacy 28-region WA 2021 CSV only.
    """
    state_filter = _normalise_states(states)
    if universe_source == "wa_csv":
        rows = load_wa_universe_rows()
    elif universe_source == "geojson":
        rows = load_geojson_universe_rows(states=state_filter)
    elif universe_source == "combined":
        rows = load_geojson_universe_rows(states=state_filter, exclude_states={"Western Australia"})
        if state_filter is None or "Western Australia" in state_filter:
            rows.extend(load_wa_universe_rows())
    else:
        raise ValueError(f"Unsupported universe_source: {universe_source}")

    if state_filter is not None:
        rows = [row for row in rows if row["state_name"] in state_filter]

    return sorted(rows, key=lambda r: (r["state_name"], r["sa2_code"]))


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
                        "state_name": row.get("state_name"),
                        "rainfall_mm": rainfall_mm,
                        "extraction_method": EXTRACTION_METHOD,
                        "universe_source": row.get("universe_source"),
                        "source_file": nc_path.name,
                        "source_variable": SOURCE_VARIABLE,
                        "quality_flag": quality_flag,
                        "is_partial_month": False,
                        "partial_month_through_day": None,
                    }
                )
    return records


def run(
    dry_run: bool = False,
    universe_source: str = DEFAULT_UNIVERSE_SOURCE,
    states: str | None = None,
    output: Path | None = None,
) -> pd.DataFrame:
    nc_files = sorted(MONTHLY_RAIN_DIR.glob("*.monthly_rain.nc"))
    if not nc_files:
        print(f"ERROR: no *.monthly_rain.nc files found in {MONTHLY_RAIN_DIR}", file=sys.stderr)
        sys.exit(1)

    sa2_rows = load_sa2_rows(universe_source=universe_source, states=states)
    if not sa2_rows:
        print("ERROR: SA2 universe is empty after filtering", file=sys.stderr)
        sys.exit(1)

    state_counts = pd.Series([row["state_name"] for row in sa2_rows]).value_counts().sort_index()
    print(
        f"Processing {len(nc_files)} NetCDF file(s) for {len(sa2_rows)} SA2s "
        f"({universe_source})"
    )
    for state_name, count in state_counts.items():
        print(f"  {state_name}: {count} SA2s")

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

    out_path = output if output is not None else OUTPUT_CSV
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    try:
        display = out_path.relative_to(REPO_ROOT)
    except ValueError:
        display = out_path
    print(f"Written → {display}")
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--universe-source",
        choices=["combined", "geojson", "wa_csv"],
        default=DEFAULT_UNIVERSE_SOURCE,
        help=(
            "SA2 universe to extract. combined uses WA 2021 CSV plus non-WA "
            "GeoJSON rows; geojson uses all GeoJSON rows; wa_csv preserves the "
            "legacy WA-only 28-region universe."
        ),
    )
    parser.add_argument(
        "--states",
        default=None,
        help='Optional comma-separated state filter, e.g. "Western Australia,South Australia".',
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output CSV path. Defaults to data/features/sa2_monthly_rainfall_history.csv. "
            "Use a different path (e.g. sa2_monthly_rainfall_history_national.csv) to avoid "
            "overwriting existing WA outputs."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip writing output CSV")
    args = parser.parse_args()
    output = Path(args.output) if args.output else None
    run(
        dry_run=args.dry_run,
        universe_source=args.universe_source,
        states=args.states,
        output=output,
    )


if __name__ == "__main__":
    main()
