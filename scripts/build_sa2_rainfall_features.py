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
import calendar
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

PIPELINE_VERSION = "0.2.0"
DEFAULT_OUTPUT = "data/features/rainfall_features_sa2_season.csv"
DEFAULT_DB = "data/weather.duckdb"
DEFAULT_STATIONS_META = "data/meta/wheatbelt_stations.csv"
DEFAULT_STATION_REGIONS = "data/meta/station_regions.csv"
DEFAULT_CANONICAL_HISTORY = "data/features/sa2_monthly_rainfall_history_national.csv"
DEFAULT_MIN_COVERAGE = 0.8
DEFAULT_SOURCE = "hybrid"

# Months used in seasonal-window totals (see DPIRD phenology).
MONTH_NAMES = ('jan', 'feb', 'mar', 'apr', 'may', 'jun',
               'jul', 'aug', 'sep', 'oct', 'nov', 'dec')
SEASONAL_WINDOWS = {
    'pre_seeding_rain_mm':       (1, 3),
    'sowing_window_rain_mm':     (4, 6),
    'in_crop_rain_mm':           (5, 10),
    'flowering_rain_mm':         (9, 10),
    'grain_fill_rain_mm':        (10, 11),
    'harvest_rain_mm':           (11, 12),
    'rainfall_total_apr_oct_mm': (4, 10),
    'rainfall_total_may_oct_mm': (5, 10),
}

# Columns produced from daily data (DuckDB stations or future daily-grid extract).
# Hybrid mode preserves these from the DuckDB path; canonical-monthly leaves them null.
DAILY_DERIVED_COLS = (
    'autumn_break_date',
    'autumn_break_7d_mm',
    'autumn_break_status',
    'dry_spell_days_7d_lt_5mm',
    'dry_spell_days_14d_lt_10mm',
)

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

    Season year = calendar year (Jan–Dec).
    """
    return pd.to_datetime(dates).dt.year


def season_date_range(season_year: int):
    """Return (start_date, end_date) covering a full wheat season (Jan–Dec)."""
    start = pd.Timestamp(season_year, 1, 1)
    end = pd.Timestamp(season_year, 12, 31)
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
    # For in-progress seasons, assess coverage against observed data horizon
    # (last obs date in this group), not future dates that haven't arrived yet.
    last_obs = grp['date'].max() if not grp.empty else start
    effective_end = min(end, last_obs)
    season_days = max((effective_end - start).days + 1, 1)
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
        return window_total(month, month, 0)

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

    # Seasonal sub-windows
    pre_seeding = window_total(1, 3)        # Jan–Mar: pre-seeding/subsoil recharge
    sowing = window_total(4, 6)             # Apr–Jun: sowing window
    in_crop = window_total(5, 10)           # May–Oct: in-crop
    flowering = window_total(9, 10)         # Sep–Oct: flowering
    grain_fill = window_total(10, 11)       # Oct–Nov: grain fill
    harvest = window_total(11, 12)          # Nov–Dec: harvest (deleterious)

    # Autumn break
    break_date, break_7d, break_status = _detect_autumn_break(grp, season_year)

    # Dry spell metrics (in-season: Apr–Oct)
    in_season = _window_rows(grp, season_year, 4, 10, 0).copy()
    dry_7d = _dry_spell_days(in_season, window=7, threshold=5.0)
    dry_14d = _dry_spell_days(in_season, window=14, threshold=10.0)

    # Data quality
    quality_score = _quality_score(grp)

    # Coverage ratios — use last-obs-date denominators for in-progress seasons
    sowing_start_ts = pd.Timestamp(season_year, 4, 1)
    sowing_end_ts = pd.Timestamp(season_year, 6, 30)
    in_crop_start_ts = pd.Timestamp(season_year, 5, 1)
    in_crop_end_ts = pd.Timestamp(season_year, 10, 31)

    effective_sowing_end = min(sowing_end_ts, effective_end)
    effective_in_crop_end = min(in_crop_end_ts, effective_end)

    effective_sowing_days = (
        max((effective_sowing_end - sowing_start_ts).days + 1, 0)
        if effective_end >= sowing_start_ts else 1
    )
    effective_in_crop_days = (
        max((effective_in_crop_end - in_crop_start_ts).days + 1, 0)
        if effective_end >= in_crop_start_ts else 1
    )

    sowing_obs = len(_window_rows(grp, season_year, 4, 6, 0))
    in_crop_obs = len(_window_rows(grp, season_year, 5, 10, 0))
    sowing_coverage = sowing_obs / max(effective_sowing_days, 1)
    in_crop_coverage = in_crop_obs / max(effective_in_crop_days, 1)
    # Season is in-progress when observations don't yet cover Dec 31
    is_in_progress = effective_end < end
    quality_flag = _feature_quality_flag(coverage, sowing_coverage, in_crop_coverage,
                                          min_coverage, has_partial_month=is_in_progress)

    return {
        'station_id': station_id,
        'season_year': season_year,
        'rainfall_total_apr_oct_mm': total_apr_oct,
        'rainfall_total_may_oct_mm': total_may_oct,
        **monthly,
        'pre_seeding_rain_mm': pre_seeding,
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
        '_is_in_progress': is_in_progress,
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
                           in_crop_cov: float, min_coverage: float,
                           has_partial_month: bool = False) -> str:
    """
    Classify feature completeness from three coverage ratios.

    Priority (worst first): insufficient_season > insufficient_sowing_window
    > partial > complete_to_date > complete. 'no_data' is reserved for callers
    that need to signal total absence before this function is reached.

    has_partial_month: True when the season is in-progress and the latest
    month's data is only available through a mid-month cutoff date. Causes
    'complete_to_date' to be returned instead of 'complete' when coverage
    thresholds are otherwise met.
    """
    if season_cov < min_coverage:
        return 'insufficient_season'
    if sowing_cov < min_coverage:
        return 'insufficient_sowing_window'
    if in_crop_cov < min_coverage:
        return 'partial'
    if has_partial_month:
        return 'complete_to_date'
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
                   'feature_quality_flag', '_is_in_progress')
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
        # Propagate in-progress status from any contributing station
        is_in_progress = bool(grp['_is_in_progress'].any()) if '_is_in_progress' in grp.columns else False
        row['feature_quality_flag'] = _feature_quality_flag(s_cov, sw_cov, ic_cov, min_coverage,
                                                             has_partial_month=is_in_progress)

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
        'season_year', 'state_name', 'sa2_code', 'sa2_code_9dig', 'sa2_name',
        'station_count', 'contributing_station_ids', 'aggregation_method',
        'rainfall_total_apr_oct_mm', 'rainfall_total_may_oct_mm',
        'monthly_rainfall_jan_mm', 'monthly_rainfall_feb_mm', 'monthly_rainfall_mar_mm',
        'monthly_rainfall_apr_mm', 'monthly_rainfall_may_mm', 'monthly_rainfall_jun_mm',
        'monthly_rainfall_jul_mm', 'monthly_rainfall_aug_mm', 'monthly_rainfall_sep_mm',
        'monthly_rainfall_oct_mm', 'monthly_rainfall_nov_mm', 'monthly_rainfall_dec_mm',
        'pre_seeding_rain_mm', 'sowing_window_rain_mm', 'in_crop_rain_mm',
        'flowering_rain_mm', 'grain_fill_rain_mm', 'harvest_rain_mm',
        'autumn_break_date', 'autumn_break_7d_mm', 'autumn_break_status',
        'dry_spell_days_7d_lt_5mm', 'dry_spell_days_14d_lt_10mm',
        'data_quality_score',
        'season_coverage_ratio', 'sowing_window_coverage_ratio', 'in_crop_coverage_ratio',
        'feature_quality_flag',
        'monthly_features_source', 'daily_features_status', 'partial_through_day',
        'source_dataset', 'pipeline_version', 'created_at',
    ]
    present = [c for c in ordered_cols if c in sa2_df.columns]
    extra = [c for c in sa2_df.columns if c not in ordered_cols]
    return sa2_df[present + extra]


# ---------------------------------------------------------------------------
# Canonical-monthly source (national, all 192 SA2s)
# ---------------------------------------------------------------------------

def load_canonical_history(canonical_path: str,
                           season_year: int | None = None) -> pd.DataFrame:
    """Load the national SA2 monthly rainfall history CSV."""
    df = pd.read_csv(canonical_path, dtype={'sa2_code': str})
    if season_year is not None:
        df = df[df['year'] == season_year]
    df['rainfall_mm'] = pd.to_numeric(df['rainfall_mm'], errors='coerce')
    if 'is_partial_month' in df.columns:
        df['is_partial_month'] = df['is_partial_month'].fillna(False).astype(bool)
    else:
        df['is_partial_month'] = False
    if 'partial_month_through_day' not in df.columns:
        df['partial_month_through_day'] = None
    return df


def compute_features_from_canonical(history_df: pd.DataFrame,
                                    today: pd.Timestamp | None = None,
                                    min_coverage: float = DEFAULT_MIN_COVERAGE
                                    ) -> pd.DataFrame:
    """Build one feature row per (state_name, sa2_code, year) from canonical monthly rainfall."""
    if today is None:
        today = pd.Timestamp(datetime.now().date())

    # Pivot months wide. One row per (state_name, sa2_code, year).
    keys = ['state_name', 'sa2_code', 'sa2_name', 'year']
    pivot = (
        history_df.pivot_table(
            index=keys, columns='month', values='rainfall_mm', aggfunc='first'
        )
        .reset_index()
    )
    # Track partial-month rows separately (1 partial row per SA2-year at most).
    partial = (
        history_df[history_df['is_partial_month']]
        .groupby(['state_name', 'sa2_code', 'year'])
        ['partial_month_through_day'].max()
        .reset_index()
        .rename(columns={'partial_month_through_day': 'partial_through_day'})
    )

    # Pre-build per-month day-count lookup for day-level coverage ratios.
    # For partial months uses partial_month_through_day; for full months uses
    # calendar days. Key: (state_name, sa2_code_str, year, month).
    month_day_counts: dict[tuple, int] = {}
    for _, mr in history_df.iterrows():
        key = (mr['state_name'], str(mr['sa2_code']), int(mr['year']), int(mr['month']))
        if mr['is_partial_month'] and pd.notna(mr.get('partial_month_through_day')):
            month_day_counts[key] = int(mr['partial_month_through_day'])
        else:
            month_day_counts[key] = calendar.monthrange(int(mr['year']), int(mr['month']))[1]

    records = []
    for _, row in pivot.iterrows():
        season_year = int(row['year'])
        months_present = {int(m): row[m] for m in range(1, 13)
                          if m in pivot.columns and pd.notna(row.get(m))}

        # Window totals
        window_vals = {}
        for col, (m_start, m_end) in SEASONAL_WINDOWS.items():
            window_months = list(range(m_start, m_end + 1))
            vals = [months_present[m] for m in window_months if m in months_present]
            window_vals[col] = float(sum(vals)) if vals else None

        # Monthly rainfall_*_mm
        monthly_out = {
            f'monthly_rainfall_{MONTH_NAMES[m - 1]}_mm':
                float(row[m]) if m in pivot.columns and pd.notna(row.get(m)) else None
            for m in range(1, 13)
        }

        # ---------- Quality-gate coverage (month-based) ----------
        # Used only for feature_quality_flag classification; the output CSV
        # columns carry day-level coverage ratios computed below.
        if season_year < today.year:
            months_elapsed = 12
        elif season_year > today.year:
            months_elapsed = 0
        else:
            months_elapsed = today.month
        denom = max(months_elapsed, 1)
        season_cov_gate = round(len(months_present) / denom, 4) if months_elapsed > 0 else 0.0

        sowing_months_present = sum(1 for m in range(4, 7) if m in months_present)
        sowing_elapsed = (
            3 if season_year < today.year
            else max(0, min(3, today.month - 3)) if season_year == today.year
            else 0
        )
        sowing_cov_gate = (
            round(sowing_months_present / sowing_elapsed, 4)
            if sowing_elapsed > 0 else 0.0
        )

        in_crop_months_present = sum(1 for m in range(5, 11) if m in months_present)
        in_crop_elapsed = (
            6 if season_year < today.year
            else max(0, min(6, today.month - 4)) if season_year == today.year
            else 0
        )
        in_crop_cov_gate = (
            round(in_crop_months_present / in_crop_elapsed, 4)
            if in_crop_elapsed > 0 else 0.0
        )

        # ---------- Day-level coverage ratios (output columns) ----------
        # Numerator: actual days present per month (partial months use
        # partial_month_through_day; full months use calendar days).
        # Denominators are fixed: full year = 365/366; sowing = 91; in-crop = 184.
        raw_sa2 = str(row['sa2_code'])

        def days_for_month(m: int) -> int:
            if m not in months_present:
                return 0
            return month_day_counts.get(
                (row['state_name'], raw_sa2, season_year, m),
                calendar.monthrange(season_year, m)[1],
            )

        full_year_days = 366 if calendar.isleap(season_year) else 365
        season_days_num = sum(days_for_month(m) for m in range(1, 13))
        season_cov = round(season_days_num / full_year_days, 4)

        sowing_days_num = sum(days_for_month(m) for m in range(4, 7))
        sowing_cov = round(sowing_days_num / SOWING_WINDOW_DAYS, 4)

        in_crop_days_num = sum(days_for_month(m) for m in range(5, 11))
        in_crop_cov = round(in_crop_days_num / IN_CROP_WINDOW_DAYS, 4)

        # Partial-month flag for this season
        match = partial[
            (partial['state_name'] == row['state_name']) &
            (partial['sa2_code'] == row['sa2_code']) &
            (partial['year'] == season_year)
        ]
        partial_through_day = (
            int(match['partial_through_day'].iloc[0])
            if not match.empty and pd.notna(match['partial_through_day'].iloc[0])
            else None
        )

        # feature_quality_flag uses month-gate ratios (did every elapsed month
        # have data?) plus has_partial_month (is the current month still MTD?).
        # 'complete_to_date' fires when all elapsed months are present but the
        # latest is partial — the MTD in-progress case.
        quality_flag = _feature_quality_flag(
            season_cov_gate, sowing_cov_gate, in_crop_cov_gate, min_coverage,
            has_partial_month=(partial_through_day is not None),
        )

        # The canonical CSV uses 9-digit SA2_MAIN codes; the downstream join
        # (and the legacy DuckDB-stations features file) expect the 5-digit
        # SA2_5DIG form that matches crop_context.station_sa2_5dig16. ABS's
        # 5-digit form is state-first-digit + last-4-digits of the 9-digit
        # code (e.g. 501021007 → 51007, 103011060 → 11060).
        canonical_sa2 = str(row['sa2_code'])
        sa2_5dig = (
            canonical_sa2[0] + canonical_sa2[-4:] if len(canonical_sa2) >= 5
            else canonical_sa2
        )

        records.append({
            'season_year': season_year,
            'state_name': row['state_name'],
            'sa2_code': sa2_5dig,
            'sa2_code_9dig': canonical_sa2,
            'sa2_name': row['sa2_name'],
            'station_count': 0,
            'contributing_station_ids': '',
            'aggregation_method': 'canonical_monthly_nearest_grid',
            **window_vals,
            **monthly_out,
            # Daily-derived columns are null in canonical-monthly mode.
            # autumn_break_status uses 'not_assessed' (not None) so downstream
            # consumers can distinguish "no daily data, can't assess" from
            # "had daily data, no break detected" (which is 'absent').
            **{c: ('not_assessed' if c == 'autumn_break_status' else None)
               for c in DAILY_DERIVED_COLS},
            'data_quality_score': None,
            'season_coverage_ratio': season_cov,
            'sowing_window_coverage_ratio': sowing_cov,
            'in_crop_coverage_ratio': in_crop_cov,
            'feature_quality_flag': quality_flag,
            'monthly_features_source': 'canonical_national',
            'daily_features_status': 'monthly_only',
            'partial_through_day': partial_through_day,
        })

    return pd.DataFrame(records)


def overlay_daily_features(base: pd.DataFrame, overlay: pd.DataFrame) -> pd.DataFrame:
    """
    Overlay daily-derived columns from the DuckDB-stations path onto canonical
    base rows. Match on (season_year, sa2_code). Only daily columns + the
    quality_score are copied; monthly metrics remain from the canonical row.
    """
    if overlay.empty:
        return base
    overlay = overlay[['season_year', 'sa2_code', 'data_quality_score',
                       *DAILY_DERIVED_COLS]].copy()
    merged = base.merge(
        overlay,
        on=['season_year', 'sa2_code'],
        how='left',
        suffixes=('', '_dly'),
    )
    # Determine which rows actually received DuckDB overlay data before
    # applying combine_first — autumn_break_status is now 'not_assessed'
    # (non-null) in the base, so we can't rely on notna() post-merge.
    has_overlay = pd.Series(False, index=merged.index)
    for col in (*DAILY_DERIVED_COLS, 'data_quality_score'):
        dly = f'{col}_dly'
        if dly in merged.columns:
            has_overlay |= merged[dly].notna()

    for col in (*DAILY_DERIVED_COLS, 'data_quality_score'):
        dly = f'{col}_dly'
        if dly in merged.columns:
            merged[col] = merged[dly].combine_first(merged[col])
            merged = merged.drop(columns=[dly])

    merged.loc[has_overlay, 'daily_features_status'] = 'duckdb_stations'
    return merged


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_duckdb_stations(season_year, db_path, stations_meta_path,
                           station_regions_path, min_coverage):
    """Run the legacy DuckDB-stations build path and return the SA2 frame."""
    logger.info("Loading weather observations from DuckDB: %s", db_path)
    obs = load_observations(db_path, season_year)
    logger.info("Loaded %d observation rows", len(obs))

    logger.info("Loading station SA2 map")
    station_map = load_station_sa2_map(stations_meta_path, station_regions_path)
    logger.info("Loaded %d station records", len(station_map))

    logger.info("Computing station-level seasonal features (min_coverage=%.2f)", min_coverage)
    station_features = compute_station_season_features(obs, min_coverage)
    logger.info("Station features: %d rows", len(station_features))

    if station_features.empty:
        return pd.DataFrame()

    logger.info("Aggregating to SA2")
    sa2_df = aggregate_to_sa2(station_features, station_map, min_coverage)
    sa2_df['monthly_features_source'] = 'duckdb_stations'
    sa2_df['daily_features_status'] = 'duckdb_stations'
    sa2_df['partial_through_day'] = None
    logger.info("DuckDB-stations SA2 features: %d rows", len(sa2_df))
    return sa2_df


def _build_canonical_monthly(season_year, canonical_path, min_coverage):
    """Build SA2 features from the national canonical monthly history."""
    logger.info("Loading canonical monthly history: %s", canonical_path)
    history = load_canonical_history(canonical_path, season_year)
    logger.info("Loaded %d canonical rows", len(history))

    sa2_df = compute_features_from_canonical(history, min_coverage=min_coverage)
    logger.info("Canonical-monthly SA2 features: %d rows", len(sa2_df))
    return sa2_df


@click.command()
@click.option('--source',
              type=click.Choice(['hybrid', 'canonical-monthly', 'duckdb-stations']),
              default=DEFAULT_SOURCE, show_default=True,
              help='Feature build source. hybrid = canonical monthly base + DuckDB '
                   'daily overlay for WA; canonical-monthly = national monthly only; '
                   'duckdb-stations = legacy station-derived behaviour.')
@click.option('--canonical-history', default=DEFAULT_CANONICAL_HISTORY, show_default=True,
              help='Path to the national canonical monthly rainfall history CSV.')
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
def main(source, canonical_history, season_year, output, db_path,
         stations_meta, station_regions, min_coverage, pipeline_version,
         dry_run, verbose):
    """Build SA2-level seasonal rainfall features."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )

    if source == 'duckdb-stations':
        sa2_df = _build_duckdb_stations(
            season_year, db_path, stations_meta, station_regions, min_coverage,
        )
        if sa2_df.empty:
            logger.warning("No DuckDB-stations features produced.")
            return
    elif source == 'canonical-monthly':
        sa2_df = _build_canonical_monthly(season_year, canonical_history, min_coverage)
        if sa2_df.empty:
            logger.warning("No canonical-monthly features produced.")
            return
    else:  # hybrid
        sa2_df = _build_canonical_monthly(season_year, canonical_history, min_coverage)
        if sa2_df.empty:
            logger.warning("Canonical-monthly base is empty; aborting hybrid build.")
            return
        try:
            overlay = _build_duckdb_stations(
                season_year, db_path, stations_meta, station_regions, min_coverage,
            )
        except Exception as exc:
            logger.warning("DuckDB overlay failed (%s); proceeding with monthly-only.", exc)
            overlay = pd.DataFrame()
        if not overlay.empty:
            logger.info("Overlaying daily features from %d DuckDB-stations rows", len(overlay))
            sa2_df = overlay_daily_features(sa2_df, overlay)

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
