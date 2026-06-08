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
    logger.info("Derived station universe: %d stations across %d target SA2s",
                len(selected), selected["sa2_5"].nunique())
    return selected
