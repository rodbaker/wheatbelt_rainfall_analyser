"""SA2 broadacre coverage derivation.

Turns ABS crop-area data (crop_context_sa2.csv) into a daily station coverage
plan: which SA2s have meaningful broadacre cropping, which BOM stations sit
inside them, which zero-station SA2s need a Data Drill point, and a reviewable
coverage report.

Join key: crop_context_sa2.csv.station_sa2_5dig16 (5-digit 2016 SA2 code)
          <-> wheatbelt_stations.csv.SA2_5DIG16 (loaded as 'sa2_code').
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import pandas as pd

logger = logging.getLogger(__name__)

CROP_SA2_KEY = "station_sa2_5dig16"   # 5-digit 2016 SA2 code in crop_context_sa2.csv
# 9-digit SA2 code in crop_context_sa2.csv (== SA2_MAIN16 in the ABS GeoJSON).
# NOTE: the column is literally named "sa2_code" in the crop CSV, but the STATION
# DataFrame from stations_loader ALSO has a "sa2_code" column holding the 5-DIGIT
# code — different semantics, same label. Keep the two straight when joining.
CROP_SA2_9DIG_KEY = "sa2_code"


def _norm_sa2(series: pd.Series) -> pd.Series:
    """Normalise an SA2 code column to a clean integer-like string.

    Handles ints, floats (``11060.0``), and strings uniformly so the crop side
    and station side join. Non-numeric / missing -> empty string.
    """
    num = pd.to_numeric(series, errors="coerce")
    out = num.astype("Int64").astype(str)
    return out.replace("<NA>", "")


def load_broadacre_sa2_areas(crop_path: Union[str, Path], area_col: str = "area_ha") -> pd.DataFrame:
    """Aggregate broadacre area per SA2 (NaN-skipping sum).

    Returns columns: sa2_5, sa2_name, state, total_area_ha. An SA2 whose every
    crop row has a missing area gets total_area_ha == 0.0 and is RETAINED
    (row-presence inclusion at threshold 0).

    Uses ``area_ha`` by default; cells suppressed in the source fall to 0 via
    the NaN-skip. ``area_ha_for_weighting`` is an alternative the caller may
    pass via ``area_col``.
    """
    df = pd.read_csv(crop_path, dtype=str)
    df[area_col] = pd.to_numeric(df[area_col], errors="coerce")
    df["sa2_5"] = _norm_sa2(df[CROP_SA2_KEY])
    df = df[df["sa2_5"] != ""]

    grouped = (
        df.groupby("sa2_5")
        .agg(
            total_area_ha=(area_col, lambda s: float(s.dropna().sum())),
            sa2_name=("sa2_name", "first"),
            state=("state", "first"),
        )
        .reset_index()
    )
    logger.info("Loaded broadacre areas for %d SA2s from %s", len(grouped), crop_path)
    return grouped


def select_target_sa2s(areas_df: pd.DataFrame, threshold_ha: float = 5000) -> Set[str]:
    """SA2 codes with total_area_ha >= threshold_ha.

    threshold_ha=0 returns every SA2 present (incl. 0.0-area ones); any value
    >= 1 drops the 0.0-area SA2s.
    """
    return set(areas_df.loc[areas_df["total_area_ha"] >= threshold_ha, "sa2_5"])


def derive_station_universe(target_sa2s: Set[str], stations_df: pd.DataFrame) -> pd.DataFrame:
    """Select stations whose SA2 (column 'sa2_code', the 5-digit code as loaded
    by WheatbeltStationsLoader) is in target_sa2s. Adds a normalised 'sa2_5'.
    """
    df = stations_df.copy()
    df["sa2_5"] = _norm_sa2(df["sa2_code"])
    selected = df[df["sa2_5"].isin(target_sa2s)].copy()
    # WheatbeltStationsLoader left-joins station_regions.csv, which has duplicate
    # station_id rows; that fan-out would otherwise inflate n_stations and repeat
    # IDs downstream. Collapse to one row per station.
    selected = selected.drop_duplicates(subset="station_id").reset_index(drop=True)
    logger.info("Derived station universe: %d stations across %d target SA2s",
                len(selected), selected["sa2_5"].nunique())
    return selected


COVERAGE_COLUMNS = [
    "sa2_code", "sa2_name", "state", "broadacre_area_ha",
    "n_stations", "station_ids", "gap_status",
]


def build_coverage_report(
    target_sa2s: Set[str],
    areas_df: pd.DataFrame,
    station_universe: pd.DataFrame,
    dd_covered_sa2s: Optional[Set[str]] = None,
) -> pd.DataFrame:
    """One row per included SA2 with a controlled gap_status:
    internal_bom | data_drill_gapfill | unresolved_gap.

    areas_df is expected to be unique per sa2_5 (as produced by
    load_broadacre_sa2_areas); it is deduped defensively.
    """
    dd_covered_sa2s = dd_covered_sa2s or set()
    # Dedupe defensively: callers should pass the aggregated frame from
    # load_broadacre_sa2_areas (already unique per sa2_5), but guard against a
    # raw frame so area_lookup.loc[sa2] always yields a Series, never a slice.
    area_lookup = areas_df.drop_duplicates("sa2_5").set_index("sa2_5")
    ids_by_sa2: Dict[str, List[str]] = {}
    if not station_universe.empty:
        for sa2, grp in station_universe.groupby("sa2_5"):
            ids_by_sa2[sa2] = sorted(set(grp["station_id"].astype(str)))

    rows = []
    for sa2 in sorted(target_sa2s):
        ids = ids_by_sa2.get(sa2, [])
        n = len(ids)
        if n > 0:
            status = "internal_bom"
        elif sa2 in dd_covered_sa2s:
            status = "data_drill_gapfill"
        else:
            status = "unresolved_gap"
        meta = area_lookup.loc[sa2] if sa2 in area_lookup.index else None
        rows.append({
            "sa2_code": sa2,
            "sa2_name": "" if meta is None else meta["sa2_name"],
            "state": "" if meta is None else meta["state"],
            "broadacre_area_ha": 0.0 if meta is None else round(float(meta["total_area_ha"]), 2),
            "n_stations": n,
            "station_ids": ";".join(ids),
            "gap_status": status,
        })
    return pd.DataFrame(rows, columns=COVERAGE_COLUMNS)


def _name_match(crop_name: str, geo_name: str) -> bool:
    """Conservative name match: equal (case-insensitive) or the GeoJSON name is the
    crop name followed by a space (e.g. 'Esperance' -> 'Esperance Region'). No
    substring/fuzzy matching."""
    c = (crop_name or "").strip().casefold()
    g = (geo_name or "").strip().casefold()
    return bool(c) and (g == c or g.startswith(c + " "))


def build_sa2_polygon_index(crop_df: pd.DataFrame, geojson_path) -> Dict[str, "object"]:  # values are shapely BaseGeometry
    """Map 5-digit SA2 code -> shapely polygon.

    Primary match is by code: the crop 5-digit code is mapped to its 9-digit
    SA2_MAIN16 via the crop table, and the GeoJSON is indexed by SA2_MAIN16.

    Conservative name fallback: for crop SA2s the code match missed (the crop
    file uses 2021 codes; the GeoJSON uses 2016 codes, so some SA2s never match
    by code), a crop SA2 is resolved by name ONLY if its sa2_name matches exactly
    ONE not-yet-claimed GeoJSON feature (equal, or GeoJSON name starts with the
    crop name + a space, e.g. 'Esperance' -> 'Esperance Region'). Ambiguous (>=2)
    matches are logged and left unresolved; 0 matches stay unresolved.
    """
    import json

    from shapely.geometry import shape

    codes = crop_df[[CROP_SA2_9DIG_KEY, CROP_SA2_KEY, "sa2_name"]].copy()
    codes["nine"] = _norm_sa2(codes[CROP_SA2_9DIG_KEY])
    codes["five"] = _norm_sa2(codes[CROP_SA2_KEY])
    nine_to_five = dict(zip(codes["nine"], codes["five"]))
    five_to_name = {f: n for f, n in zip(codes["five"], codes["sa2_name"]) if f}

    with open(geojson_path) as f:
        gj = json.load(f)

    index: Dict[str, object] = {}
    unclaimed = []   # GeoJSON features with no code match: (name, polygon)
    for feat in gj.get("features", []):
        if not feat.get("geometry"):
            continue
        props = feat.get("properties", {})
        nine = _norm_sa2(pd.Series([props.get("SA2_MAIN16")])).iloc[0]
        five = nine_to_five.get(nine)
        poly = shape(feat["geometry"])
        if five:
            existing = index.get(five)
            # Some SA2s appear twice in the ABS GeoJSON (a degenerate ~0-area
            # artefact + the real polygon). Keep the larger so the result does
            # not depend on feature ordering.
            if existing is None or poly.area > existing.area:
                index[five] = poly
        else:
            unclaimed.append((str(props.get("SA2_NAME16") or ""), poly))

    # --- conservative, uniqueness-checked name fallback ---
    for five in sorted(five_to_name):
        if five in index:
            continue
        crop_name = str(five_to_name[five])
        matches = [(nm, poly) for nm, poly in unclaimed if _name_match(crop_name, nm)]
        if len(matches) == 1:
            nm, poly = matches[0]
            index[five] = poly
            # Claim this feature so it can't also resolve another crop name.
            # poly is shape()-constructed per feature, so object identity uniquely
            # identifies the just-claimed (name, polygon) entry to remove.
            unclaimed = [(n, p) for n, p in unclaimed if not (n == nm and p is poly)]
            logger.info("SA2 %s resolved by name fallback: crop '%s' -> GeoJSON '%s'",
                        five, crop_name.strip(), nm)
        elif len(matches) > 1:
            logger.warning(
                "SA2 %s name '%s' is ambiguous across %d GeoJSON features; left unresolved",
                five, crop_name.strip(), len(matches))
        # 0 matches: silently leave unresolved (caller marks unresolved_gap)

    logger.info("Built SA2 polygon index for %d SA2s", len(index))
    return index


def resolve_gap_points(
    zero_station_sa2s: Set[str],
    polygon_index: Dict[str, "object"],  # values are shapely BaseGeometry
    existing_points: Optional[List[Tuple[float, float]]] = None,
) -> Dict[str, Tuple[float, float]]:
    """For each zero-station SA2 with a known polygon, return a (lat, lon) point
    inside it. Reuses an existing grid point if one already falls inside;
    otherwise injects the polygon's representative point. SA2s with no polygon
    are omitted (caller marks them unresolved_gap).
    """
    from shapely.geometry import Point

    existing_points = existing_points or []
    result: Dict[str, Tuple[float, float]] = {}
    for sa2 in sorted(zero_station_sa2s):
        poly = polygon_index.get(sa2)
        if poly is None:
            continue
        reused = None
        for lat, lon in existing_points:           # Point(x=lon, y=lat)
            if poly.contains(Point(lon, lat)):
                reused = (round(float(lat), 4), round(float(lon), 4))
                break
        if reused is not None:
            result[sa2] = reused
        else:
            rp = poly.representative_point()
            result[sa2] = (round(float(rp.y), 4), round(float(rp.x), 4))
    return result
