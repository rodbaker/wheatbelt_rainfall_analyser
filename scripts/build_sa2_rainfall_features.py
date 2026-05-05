"""
SA2 Rainfall Feature Builder

Reads weather observations from DuckDB, aggregates seasonal rainfall features
to ABS SA2 region level, and writes data/features/rainfall_features_sa2_season.csv.

Usage:
    python scripts/build_sa2_rainfall_features.py
    python scripts/build_sa2_rainfall_features.py --season-year 2025
    python scripts/build_sa2_rainfall_features.py --dry-run
"""

import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

import click
import pandas as pd
import numpy as np

# Allow running as a script from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.constants import SILO_QUALITY_CODES, SILO_QUALITY_DEFAULT
from src.common.file_utils import atomic_csv_write

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "0.1.0"
DEFAULT_OUTPUT = "data/features/rainfall_features_sa2_season.csv"
DEFAULT_DB = "data/weather.duckdb"
DEFAULT_STATIONS_META = "data/meta/wheatbelt_stations.csv"
DEFAULT_STATION_REGIONS = "data/meta/station_regions.csv"
DEFAULT_MIN_COVERAGE = 0.8

# Fixed days in sowing (Apr–Jun) and in-crop (May–Oct) windows — none contain Feb
SOWING_WINDOW_DAYS = 91    # Apr(30)+May(31)+Jun(30)
IN_CROP_WINDOW_DAYS = 184  # May(31)+Jun(30)+Jul(31)+Aug(31)+Sep(30)+Oct(31)

# Autumn break status boundaries (WA wheatbelt defaults)
AUTUMN_BREAK_EARLY_CUTOFF = (5, 15)   # before May 15 → early
AUTUMN_BREAK_LATE_CUTOFF = (6, 15)    # after Jun 15 → late


# ---------------------------------------------------------------------------
# Season-year helpers
# ---------------------------------------------------------------------------

def assign_season_year(dates: pd.Series) -> pd.Series:
    """
    Return the wheat season year for each date.

    Season year is the calendar year in which sowing occurs:
    Apr–Dec → same year; Jan–Mar → previous year.
    """
    dates = pd.to_datetime(dates)
    return dates.apply(lambda d: d.year if d.month >= 4 else d.year - 1)


def season_date_range(season_year: int):
    """Return (start_date, end_date) covering a full wheat season."""
    start = pd.Timestamp(season_year, 4, 1)
    end = pd.Timestamp(season_year + 1, 3, 31)
    return start, end


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_observations(db_path: str, season_year: int | None = None) -> pd.DataFrame:
    """Load weather_observations from DuckDB, optionally filtered by season."""
    try:
        import duckdb
    except ImportError:
        raise ImportError("duckdb is required: pip install duckdb")

    con = duckdb.connect(db_path, read_only=True)
    try:
        if season_year is not None:
            start, end = season_date_range(season_year)
            # Extend back to Jan of the season_year to catch Jan–Mar tail of
            # the preceding season if needed; here we want the current season
            # Apr sowing_year → Mar sowing_year+1 plus the Jan–Mar preceding tail.
            # For simplicity we load Apr sowing_year – Mar (sowing_year+1).
            query = """
                SELECT station_id, date, rainfall,
                       rainfall_quality
                FROM weather_observations
                WHERE date >= ? AND date <= ?
                ORDER BY station_id, date
            """
            df = con.execute(query, [start.strftime('%Y-%m-%d'),
                                     end.strftime('%Y-%m-%d')]).df()
        else:
            query = """
                SELECT station_id, date, rainfall,
                       rainfall_quality
                FROM weather_observations
                ORDER BY station_id, date
            """
            df = con.execute(query).df()
    finally:
        con.close()

    df['date'] = pd.to_datetime(df['date'])
    df['station_id'] = df['station_id'].astype(str)
    return df


def load_station_sa2_map(stations_meta_path: str, station_regions_path: str) -> pd.DataFrame:
    """
    Return a DataFrame mapping station_id → (sa2_code, sa2_name, state_name).

    Uses wheatbelt_stations.csv for state, SA2_5DIG16 code, and SA2 name fallback;
    station_regions.csv for SA2 name (preferred where present). Station IDs are kept
    as strings with leading zeros.
    """
    meta = pd.read_csv(stations_meta_path, dtype=str)
    # Normalise: the stations CSV uses 'Station number' with no leading zeros in some rows
    meta = meta.rename(columns={
        'Station number': 'station_id',
        'SA2_5DIG16': 'sa2_code',
        'SA2_NAME16': 'sa2_name_meta',
        'STE_NAME16': 'state_name',
    })
    meta['station_id'] = meta['station_id'].str.strip().str.zfill(6)
    meta['sa2_code'] = meta['sa2_code'].str.strip()

    regions = pd.read_csv(station_regions_path, dtype=str)
    regions['station_id'] = regions['station_id'].str.strip().str.zfill(6)
    regions = regions.rename(columns={'sa2_name': 'sa2_name'})

    merged = meta[['station_id', 'sa2_code', 'sa2_name_meta', 'state_name']].merge(
        regions[['station_id', 'sa2_name']],
        on='station_id',
        how='left',
    )
    # Fall back to wheatbelt_stations SA2 name when station_regions has no entry
    merged['sa2_name'] = merged['sa2_name'].fillna(merged['sa2_name_meta'])
    return merged[['station_id', 'sa2_code', 'sa2_name', 'state_name']].drop_duplicates('station_id')


# ---------------------------------------------------------------------------
# Feature computation — station level
# ---------------------------------------------------------------------------

def compute_station_season_features(obs: pd.DataFrame, min_coverage: float) -> pd.DataFrame:
    """
    Compute all seasonal rainfall features for each (station_id, season_year) pair.

    Returns one row per station × season.
    """
    obs = obs.copy()
    obs['season_year'] = assign_season_year(obs['date'])
    obs['month'] = obs['date'].dt.month
    obs['year'] = obs['date'].dt.year

    # Exclude Data Drill synthetic points from station-level aggregation
    obs = obs[~obs['station_id'].str.startswith('DD_')].copy()

    # Replace quality code 999 (missing) with NaN in rainfall
    obs.loc[obs['rainfall_quality'] == 999, 'rainfall'] = np.nan
    obs['rainfall'] = pd.to_numeric(obs['rainfall'], errors='coerce')

    records = []
    for (station_id, season_year), grp in obs.groupby(['station_id', 'season_year']):
        rec = _station_season_record(station_id, season_year, grp, min_coverage)
        if rec is not None:
            records.append(rec)

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _station_season_record(station_id: str, season_year: int,
                           grp: pd.DataFrame, min_coverage: float) -> dict | None:
    """Compute features for a single station × season group."""
    start, end = season_date_range(season_year)
    season_days = (end - start).days + 1
    coverage = len(grp) / season_days
    if coverage < min_coverage * 0.5:
        # Less than half the minimum coverage → skip entirely
        return None

    def window_total(month_start: int, month_end: int, year_offset: int = 0) -> float | None:
        """Sum rainfall for calendar months within the season window."""
        rows = _window_rows(grp, season_year, month_start, month_end, year_offset)
        if rows.empty or rows['rainfall'].isna().all():
            return None
        total_days = len(rows)
        valid_days = rows['rainfall'].notna().sum()
        if total_days > 0 and valid_days / total_days < min_coverage:
            return None
        return float(rows['rainfall'].sum(min_count=1))

    def monthly_total(month: int) -> float | None:
        year_offset = 1 if month < 4 else 0
        return window_total(month, month, year_offset)

    # Monthly totals
    monthly = {f'monthly_rainfall_{m}_mm': monthly_total(m)
               for m in range(1, 13)}
    month_names = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                   'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    monthly = {f'monthly_rainfall_{month_names[m-1]}_mm': monthly_total(m)
               for m in range(1, 13)}

    # Seasonal totals
    apr_rows = _window_rows(grp, season_year, 4, 10, 0)
    may_rows = _window_rows(grp, season_year, 5, 10, 0)
    total_apr_oct = _safe_sum(apr_rows, min_coverage)
    total_may_oct = _safe_sum(may_rows, min_coverage)

    # Crop windows
    sowing = window_total(4, 6)
    in_crop = window_total(5, 10)
    flowering = window_total(9, 10)
    grain_fill_rows = pd.concat([
        _window_rows(grp, season_year, 10, 10, 0),
        _window_rows(grp, season_year, 11, 11, 0),
    ])
    grain_fill = _safe_sum(grain_fill_rows, min_coverage)
    harvest_rows = pd.concat([
        _window_rows(grp, season_year, 11, 12, 0),
        _window_rows(grp, season_year, 1, 1, 1),
    ])
    harvest = _safe_sum(harvest_rows, min_coverage)

    # Autumn break
    break_date, break_7d, break_status = _detect_autumn_break(grp, season_year)

    # Dry spell metrics (in-season: Apr–Oct)
    in_season = _window_rows(grp, season_year, 4, 10, 0).copy()
    dry_7d = _dry_spell_days(in_season, window=7, threshold=5.0)
    dry_14d = _dry_spell_days(in_season, window=14, threshold=10.0)

    # Data quality
    quality_score = _quality_score(grp)

    # Coverage ratios
    sowing_obs = len(_window_rows(grp, season_year, 4, 6, 0))
    in_crop_obs = len(_window_rows(grp, season_year, 5, 10, 0))
    sowing_coverage = sowing_obs / SOWING_WINDOW_DAYS
    in_crop_coverage = in_crop_obs / IN_CROP_WINDOW_DAYS
    quality_flag = _feature_quality_flag(coverage, sowing_coverage, in_crop_coverage, min_coverage)

    return {
        'station_id': station_id,
        'season_year': season_year,
        'rainfall_total_apr_oct_mm': total_apr_oct,
        'rainfall_total_may_oct_mm': total_may_oct,
        **monthly,
        'sowing_window_rain_mm': sowing,
        'in_crop_rain_mm': in_crop,
        'flowering_rain_mm': flowering,
        'grain_fill_rain_mm': grain_fill,
        'harvest_rain_mm': harvest,
        'autumn_break_date': break_date,
        'autumn_break_7d_mm': break_7d,
        'autumn_break_status': break_status,
        'dry_spell_days_7d_lt_5mm': dry_7d,
        'dry_spell_days_14d_lt_10mm': dry_14d,
        'data_quality_score': quality_score,
        'season_coverage_ratio': round(coverage, 4),
        'sowing_window_coverage_ratio': round(sowing_coverage, 4),
        'in_crop_coverage_ratio': round(in_crop_coverage, 4),
        'feature_quality_flag': quality_flag,
    }


def _window_rows(grp: pd.DataFrame, season_year: int,
                 month_start: int, month_end: int,
                 year_offset: int = 0) -> pd.DataFrame:
    """Filter grp to calendar months within the season window."""
    cal_year = season_year + year_offset
    rows = grp[(grp['year'] == cal_year) &
               (grp['month'] >= month_start) &
               (grp['month'] <= month_end)]
    return rows


def _safe_sum(rows: pd.DataFrame, min_coverage: float) -> float | None:
    if rows.empty or rows['rainfall'].isna().all():
        return None
    valid = rows['rainfall'].notna().sum()
    if valid / max(len(rows), 1) < min_coverage:
        return None
    return float(rows['rainfall'].sum(min_count=1))


def _detect_autumn_break(grp: pd.DataFrame, season_year: int):
    """
    Find the first qualifying autumn break event in Apr–Jun of season_year.

    Qualifying: single day ≥ 10 mm, or trailing 7-day total ≥ 25 mm.
    Returns (break_date, break_7d_mm, status) or (None, None, 'absent').
    """
    window = _window_rows(grp, season_year, 4, 6, 0).sort_values('date')
    if window.empty or window['rainfall'].isna().all():
        return None, None, 'absent'

    rain = window.set_index('date')['rainfall']
    rolling7 = rain.rolling('7D', min_periods=1).sum()

    # Single-day trigger
    single_day = rain[rain >= 10.0]
    # 7-day trigger
    rolling_trigger = rolling7[rolling7 >= 25.0]

    candidates = []
    if not single_day.empty:
        candidates.append(single_day.index[0])
    if not rolling_trigger.empty:
        candidates.append(rolling_trigger.index[0])

    if not candidates:
        return None, None, 'absent'

    break_dt = min(candidates)
    break_7d = float(rolling7.get(break_dt, np.nan))

    early_cutoff = pd.Timestamp(season_year, *AUTUMN_BREAK_EARLY_CUTOFF)
    late_cutoff = pd.Timestamp(season_year, *AUTUMN_BREAK_LATE_CUTOFF)

    if break_dt < early_cutoff:
        status = 'early'
    elif break_dt <= late_cutoff:
        status = 'on_time'
    else:
        status = 'late'

    return break_dt.date().isoformat(), break_7d, status


def _dry_spell_days(rows: pd.DataFrame, window: int, threshold: float) -> float | None:
    """Count days where the trailing `window`-day rainfall total is below threshold."""
    if rows.empty or rows['rainfall'].isna().all():
        return None
    rain = rows.set_index('date')['rainfall'].sort_index()
    rolling = rain.rolling(f'{window}D', min_periods=window).sum()
    return float((rolling < threshold).sum())


def _quality_score(grp: pd.DataFrame) -> float:
    """Weighted mean quality score from rainfall_quality codes."""
    if 'rainfall_quality' not in grp.columns or grp['rainfall_quality'].isna().all():
        return SILO_QUALITY_DEFAULT
    scores = grp['rainfall_quality'].map(
        lambda c: SILO_QUALITY_CODES.get(int(c) if pd.notna(c) else 999, SILO_QUALITY_DEFAULT)
    )
    return float(scores.mean())


def _feature_quality_flag(season_cov: float, sowing_cov: float,
                           in_crop_cov: float, min_coverage: float) -> str:
    """
    Classify feature completeness from three coverage ratios.

    Priority (worst first): insufficient_season > insufficient_sowing_window
    > partial > complete. 'no_data' is reserved for callers that need to signal
    total absence before this function is reached.
    """
    if season_cov < min_coverage:
        return 'insufficient_season'
    if sowing_cov < min_coverage:
        return 'insufficient_sowing_window'
    if in_crop_cov < min_coverage:
        return 'partial'
    return 'complete'


# ---------------------------------------------------------------------------
# SA2 aggregation
# ---------------------------------------------------------------------------

def aggregate_to_sa2(station_features: pd.DataFrame,
                     station_map: pd.DataFrame,
                     min_coverage: float = DEFAULT_MIN_COVERAGE) -> pd.DataFrame:
    """Aggregate station-level seasonal features to SA2 level via simple mean."""
    df = station_features.merge(
        station_map[['station_id', 'sa2_code', 'sa2_name', 'state_name']],
        on='station_id',
        how='inner',
    )
    df = df[df['sa2_code'].notna() & (df['sa2_code'] != '')].copy()

    non_numeric = ('station_id', 'season_year', 'sa2_code', 'sa2_name',
                   'state_name', 'autumn_break_date', 'autumn_break_status',
                   'feature_quality_flag')
    numeric_cols = [c for c in df.columns if c not in non_numeric]

    def agg_group(grp):
        row = {}
        row['station_count'] = len(grp)
        row['contributing_station_ids'] = '|'.join(sorted(grp['station_id'].unique()))
        row['aggregation_method'] = 'simple_mean'
        row['state_name'] = grp['state_name'].iloc[0]
        row['sa2_name'] = grp['sa2_name'].iloc[0]

        for col in numeric_cols:
            valid = grp[col].dropna()
            row[col] = float(valid.mean()) if not valid.empty else None

        # Autumn break: use modal status; earliest non-null break date
        statuses = grp['autumn_break_status'].dropna()
        row['autumn_break_status'] = statuses.mode().iloc[0] if not statuses.empty else 'absent'
        breaks = grp['autumn_break_date'].dropna()
        row['autumn_break_date'] = breaks.min() if not breaks.empty else None

        # Derive SA2-level quality flag from mean coverage ratios
        s_cov = row.get('season_coverage_ratio') or 0.0
        sw_cov = row.get('sowing_window_coverage_ratio') or 0.0
        ic_cov = row.get('in_crop_coverage_ratio') or 0.0
        row['feature_quality_flag'] = _feature_quality_flag(s_cov, sw_cov, ic_cov, min_coverage)

        return pd.Series(row)

    sa2_df = (
        df.groupby(['season_year', 'sa2_code'])
        .apply(agg_group, include_groups=False)
        .reset_index()
    )
    return sa2_df


# ---------------------------------------------------------------------------
# Output assembly
# ---------------------------------------------------------------------------

def build_output(sa2_df: pd.DataFrame, pipeline_version: str) -> pd.DataFrame:
    """Add metadata columns and enforce column order."""
    sa2_df = sa2_df.copy()
    sa2_df['source_dataset'] = 'silo_patched_point'
    sa2_df['pipeline_version'] = pipeline_version
    sa2_df['created_at'] = datetime.now(timezone.utc).isoformat()

    ordered_cols = [
        'season_year', 'state_name', 'sa2_code', 'sa2_name',
        'station_count', 'contributing_station_ids', 'aggregation_method',
        'rainfall_total_apr_oct_mm', 'rainfall_total_may_oct_mm',
        'monthly_rainfall_jan_mm', 'monthly_rainfall_feb_mm', 'monthly_rainfall_mar_mm',
        'monthly_rainfall_apr_mm', 'monthly_rainfall_may_mm', 'monthly_rainfall_jun_mm',
        'monthly_rainfall_jul_mm', 'monthly_rainfall_aug_mm', 'monthly_rainfall_sep_mm',
        'monthly_rainfall_oct_mm', 'monthly_rainfall_nov_mm', 'monthly_rainfall_dec_mm',
        'sowing_window_rain_mm', 'in_crop_rain_mm', 'flowering_rain_mm',
        'grain_fill_rain_mm', 'harvest_rain_mm',
        'autumn_break_date', 'autumn_break_7d_mm', 'autumn_break_status',
        'dry_spell_days_7d_lt_5mm', 'dry_spell_days_14d_lt_10mm',
        'data_quality_score',
        'season_coverage_ratio', 'sowing_window_coverage_ratio', 'in_crop_coverage_ratio',
        'feature_quality_flag',
        'source_dataset', 'pipeline_version', 'created_at',
    ]
    present = [c for c in ordered_cols if c in sa2_df.columns]
    extra = [c for c in sa2_df.columns if c not in ordered_cols]
    return sa2_df[present + extra]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option('--season-year', type=int, default=None,
              help='Compute for a single season year (e.g. 2025). Default: all available.')
@click.option('--output', default=DEFAULT_OUTPUT, show_default=True,
              help='Output CSV path.')
@click.option('--db-path', default=DEFAULT_DB, show_default=True,
              help='Path to weather.duckdb.')
@click.option('--stations-meta', default=DEFAULT_STATIONS_META, show_default=True,
              help='Path to wheatbelt_stations.csv.')
@click.option('--station-regions', default=DEFAULT_STATION_REGIONS, show_default=True,
              help='Path to station_regions.csv.')
@click.option('--min-coverage', type=float, default=DEFAULT_MIN_COVERAGE, show_default=True,
              help='Minimum daily data coverage fraction to include a window total.')
@click.option('--pipeline-version', default=PIPELINE_VERSION, show_default=True,
              help='Pipeline version string written to output.')
@click.option('--dry-run', is_flag=True,
              help='Print summary without writing output file.')
@click.option('--verbose', '-v', is_flag=True)
def main(season_year, output, db_path, stations_meta, station_regions,
         min_coverage, pipeline_version, dry_run, verbose):
    """Build SA2-level seasonal rainfall features from DuckDB weather observations."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )

    logger.info("Loading weather observations from DuckDB: %s", db_path)
    obs = load_observations(db_path, season_year)
    logger.info("Loaded %d observation rows", len(obs))

    logger.info("Loading station SA2 map")
    station_map = load_station_sa2_map(stations_meta, station_regions)
    logger.info("Loaded %d station records", len(station_map))

    logger.info("Computing station-level seasonal features (min_coverage=%.2f)", min_coverage)
    station_features = compute_station_season_features(obs, min_coverage)
    logger.info("Station features: %d rows", len(station_features))

    if station_features.empty:
        logger.warning("No station features computed — check data availability and season filter.")
        return

    logger.info("Aggregating to SA2")
    sa2_df = aggregate_to_sa2(station_features, station_map, min_coverage)
    logger.info("SA2 features: %d rows", len(sa2_df))

    out_df = build_output(sa2_df, pipeline_version)

    if dry_run:
        logger.info("[DRY RUN] Would write %d rows to %s", len(out_df), output)
        print(out_df.head(5).to_string())
        return

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    success = atomic_csv_write(out_df, str(out_path))
    if success:
        logger.info("Wrote %d rows to %s", len(out_df), out_path)
    else:
        logger.error("Failed to write %s", out_path)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
