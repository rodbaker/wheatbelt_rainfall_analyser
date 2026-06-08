"""Extract state-level commodity area totals from CLUM 2023 shapefile.

Reads directly from the zip — no extraction. Produces:
  data/processed/clum_commodities_2023_area_by_state.csv
  data/processed/clum_commodities_2023_area_summary.md

CLUM is context-only; do not use for validation against ABS/ABARES.
"""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
ZIP_PATH = REPO_ROOT / "data/meta/shapefiles/clum_commodities_2023.zip"
SHP_INNER = "CLUM_Commodities_2023/CLUM_Commodities_2023.shp"
OUT_DIR = REPO_ROOT / "data/processed"
CSV_OUT = OUT_DIR / "clum_commodities_2023_area_by_state.csv"
MD_OUT = OUT_DIR / "clum_commodities_2023_area_summary.md"

REQUIRED_FIELDS = ["Commod_dsc", "Broad_type", "Source_yr", "State", "Area_ha"]


def load_shapefile(zip_path: Path) -> gpd.GeoDataFrame:
    return gpd.read_file(f"zip://{zip_path}!{SHP_INNER}")


def aggregate(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    grouped = (
        gdf.groupby(["State", "Broad_type", "Commod_dsc", "Source_yr"], dropna=False)
        .agg(feature_count=("Area_ha", "count"), area_ha=("Area_ha", "sum"))
        .reset_index()
        .rename(
            columns={
                "State": "state",
                "Broad_type": "broad_type",
                "Commod_dsc": "commodity",
                "Source_yr": "source_year",
            }
        )
        .sort_values(["state", "broad_type", "commodity", "source_year"])
    )
    return grouped


def write_summary(gdf: gpd.GeoDataFrame, df: pd.DataFrame, zip_path: Path) -> str:
    total_area = gdf["Area_ha"].sum()
    grouped_area = df["area_ha"].sum()
    diff = abs(total_area - grouped_area)

    broad_totals = (
        gdf.groupby("Broad_type")["Area_ha"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    broad_lines = "\n".join(
        f"| {row.Broad_type} | {row.Area_ha:,.1f} |"
        for row in broad_totals.itertuples()
    )

    source_yr_counts = gdf["Source_yr"].value_counts().sort_index()
    yr_lines = "\n".join(
        f"| {yr} | {cnt:,} |" for yr, cnt in source_yr_counts.items()
    )

    md = f"""# CLUM Commodities 2023 — Area Summary

**Source zip**: `{zip_path}`
**Inner shapefile**: `{SHP_INNER}`
**CRS**: {gdf.crs}
**Total features**: {len(gdf):,}
**Fields**: {', '.join(gdf.columns.tolist())}

## Interpretation

CLUM is land-use/commodity context only. Do not use to validate or replace:
ABS Agricultural Census, ABS modernised satellite area, ACF, or ABARES estimates.
Source_yr values are mixed across polygons — not all represent 2023 data.

**Area method**: `Area_ha` was used as supplied in the shapefile attribute table.
Geometry area was NOT recalculated from GDA94 geographic coordinates (EPSG:4283).
Recalculating from degrees would be incorrect without first reprojecting to a
equal-area CRS — use the supplied field only.

## Area by Broad Type (ha)

| Broad_type | Area_ha |
|---|---|
{broad_lines}

**Total Area_ha (source)**: {total_area:,.1f}
**Total Area_ha (grouped)**: {grouped_area:,.1f}
**Difference**: {diff:.4f} ha (rounding only — within tolerance if < 1 ha)

## Feature Counts by Source Year

| Source_yr | Features |
|---|---|
{yr_lines}

## Output CSV

Columns: state, broad_type, commodity, source_year, feature_count, area_ha
Rows: {len(df):,}
"""
    return md


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading {ZIP_PATH.name} ...")
    gdf = load_shapefile(ZIP_PATH)

    missing = [f for f in REQUIRED_FIELDS if f not in gdf.columns]
    if missing:
        print(f"ERROR: missing required fields: {missing}", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(gdf):,} features loaded, CRS={gdf.crs}")

    df = aggregate(gdf)
    df.to_csv(CSV_OUT, index=False)
    print(f"Written: {CSV_OUT}")

    md = write_summary(gdf, df, ZIP_PATH)
    MD_OUT.write_text(md)
    print(f"Written: {MD_OUT}")


if __name__ == "__main__":
    main()
