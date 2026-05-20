"""
SA2 Rainfall × Crop Context Join

Preserves the full ABS SA2 wheat-region frame by starting from crop_context_sa2.csv
and left-joining rainfall features onto it. SA2s with no rainfall data are retained
with rainfall_feature_quality_flag = 'no_data'.

Join key: crop_context.station_sa2_5dig16 == rainfall_features.sa2_code

Usage:
    python scripts/join_sa2_rainfall_crop_context.py
    python scripts/join_sa2_rainfall_crop_context.py --season-year 2025
    python scripts/join_sa2_rainfall_crop_context.py --dry-run
    python scripts/join_sa2_rainfall_crop_context.py --state "Western Australia" --financial-year 2020-21
"""

import sys
import logging
from pathlib import Path

import click
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.file_utils import atomic_csv_write

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "0.2.0"

DEFAULT_FEATURES = "data/features/rainfall_features_sa2_season.csv"
DEFAULT_CROP_CONTEXT = "data/meta/crop_context_sa2.csv"
DEFAULT_OUTPUT = "data/features/sa2_rainfall_crop_context.csv"
DEFAULT_STATE = "Western Australia"
DEFAULT_FINANCIAL_YEAR = "2020-21"

# Rainfall columns to carry into output (nullable for no-match rows)
RAINFALL_FEATURE_COLS = [
    "sa2_code",           # becomes rainfall_sa2_code
    "season_year",
    "station_count",
    "aggregation_method",
    "rainfall_total_apr_oct_mm",
    "rainfall_total_may_oct_mm",
    "pre_seeding_rain_mm",
    "sowing_window_rain_mm",
    "in_crop_rain_mm",
    "flowering_rain_mm",
    "grain_fill_rain_mm",
    "harvest_rain_mm",
    "autumn_break_date",
    "autumn_break_status",
    "dry_spell_days_7d_lt_5mm",
    "dry_spell_days_14d_lt_10mm",
    "data_quality_score",
    "season_coverage_ratio",
    "feature_quality_flag",
    "monthly_features_source",
    "daily_features_status",
    "partial_through_day",
]

CROP_CONTEXT_COLS = [
    "sa2_code",           # becomes abs_sa2_code
    "station_sa2_5dig16",
    "sa2_name",
    "state",
    "financial_year",     # becomes crop_context_year
    "crop",
    "area_ha",
    "area_ha_official",
    "area_ha_for_weighting",
    "area_source_year",
    "area_is_fallback",
    "area_fallback_reason",
    "production_t",
    "yield_t_ha",
    "area_share",
    "area_rse",
    "production_rse",
    "yield_rse",
    "boundary_status",
    "source_dataset",
]


def load_features(path: str, season_year: int | None) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"sa2_code": str})
    if season_year is not None:
        df = df[df["season_year"] == season_year]
    available = [c for c in RAINFALL_FEATURE_COLS if c in df.columns]
    return df[available].copy()


def load_crop_context(
    path: str, state: str | None, financial_year: str
) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"sa2_code": str, "station_sa2_5dig16": str})
    if state and state.lower() != "all":
        states = {s.strip() for s in state.split(",") if s.strip()}
        df = df[df["state"].isin(states)]
    df = df[df["financial_year"] == financial_year]
    available = [c for c in CROP_CONTEXT_COLS if c in df.columns]
    return df[available].copy()


def build_join(features: pd.DataFrame, crop_ctx: pd.DataFrame) -> pd.DataFrame:
    features = features.copy()
    crop_ctx = crop_ctx.copy()

    # Normalise join keys to str (never cast to int)
    features["_join_key"] = features["sa2_code"].astype(str).str.strip()
    crop_ctx["_join_key"] = crop_ctx["station_sa2_5dig16"].astype(str).str.strip()

    # ABS-frame-led: crop_ctx is the left table
    merged = crop_ctx.merge(
        features.rename(columns={"sa2_code": "rainfall_sa2_code"}),
        on="_join_key",
        how="left",
    ).drop(columns=["_join_key"])

    # Expose SA2 key forms explicitly
    merged = merged.rename(columns={
        "sa2_code": "abs_sa2_code",
        "financial_year": "crop_context_year",
    })

    merged["crop_context_is_historical"] = True

    # rainfall_feature_quality_flag: carry through on match, 'no_data' when absent
    merged["rainfall_feature_quality_flag"] = merged["feature_quality_flag"].where(
        merged["feature_quality_flag"].notna(), other="no_data"
    )
    if "feature_quality_flag" in merged.columns:
        merged = merged.drop(columns=["feature_quality_flag"])

    # Canonical column order
    front_cols = [
        "abs_sa2_code", "station_sa2_5dig16", "rainfall_sa2_code",
        "sa2_name", "state", "crop",
        "crop_context_year", "crop_context_is_historical",
        "rainfall_feature_quality_flag",
    ]
    remaining = [c for c in merged.columns if c not in front_cols]
    return merged[front_cols + remaining]


def report_coverage(merged: pd.DataFrame) -> None:
    total = len(merged)
    distinct_sa2 = merged["abs_sa2_code"].nunique()

    flag_col = "rainfall_feature_quality_flag"

    def _flag_summary(flag: str) -> str:
        rows = (merged[flag_col] == flag).sum()
        sa2s = merged.loc[merged[flag_col] == flag, "abs_sa2_code"].nunique()
        return f"{rows} rows / {sa2s} SA2s"

    logger.info("Total output rows: %d | distinct SA2s: %d", total, distinct_sa2)
    logger.info("  complete:           %s", _flag_summary("complete"))
    logger.info("  insufficient_season:%s", _flag_summary("insufficient_season"))
    logger.info("  no_data:            %s", _flag_summary("no_data"))

    no_data_rows = merged[merged[flag_col] == "no_data"]
    if not no_data_rows.empty:
        no_data_sa2s = (
            no_data_rows[["abs_sa2_code", "sa2_name"]]
            .drop_duplicates()
            .sort_values("abs_sa2_code")
        )
        logger.warning("SA2s with no rainfall data:")
        for _, row in no_data_sa2s.iterrows():
            logger.warning("  %s  %s", row["abs_sa2_code"], row["sa2_name"])

    matched_sa2 = merged[merged[flag_col] != "no_data"]["abs_sa2_code"].nunique()
    unmatched_sa2 = distinct_sa2 - matched_sa2
    logger.info("Join coverage: %d/%d SA2s matched (%.0f%%)",
                matched_sa2, distinct_sa2,
                100 * matched_sa2 / distinct_sa2 if distinct_sa2 else 0)

    # Per-state coverage breakdown — useful for national runs
    if "state" in merged.columns:
        for state_name, group in merged.groupby("state"):
            matched = group[group[flag_col] != "no_data"]["abs_sa2_code"].nunique()
            total = group["abs_sa2_code"].nunique()
            logger.info(
                "  %s: %d/%d SA2s matched (%.0f%%)",
                state_name, matched, total,
                100 * matched / total if total else 0,
            )


@click.command()
@click.option("--features", default=DEFAULT_FEATURES, show_default=True,
              help="Rainfall features CSV")
@click.option("--crop-context", "crop_context", default=DEFAULT_CROP_CONTEXT,
              show_default=True, help="ABS crop context CSV")
@click.option("--output", default=DEFAULT_OUTPUT, show_default=True,
              help="Output path")
@click.option("--season-year", type=int, default=None,
              help="Filter features to a single season year (e.g. 2025)")
@click.option("--state", default="all", show_default=True,
              help="Filter crop context by state (comma-separated list, or 'all' for national)")
@click.option("--financial-year", "financial_year", default=DEFAULT_FINANCIAL_YEAR,
              show_default=True, help="Crop context financial year (e.g. 2020-21)")
@click.option("--dry-run", is_flag=True,
              help="Print coverage report but do not write output")
def main(
    features: str,
    crop_context: str,
    output: str,
    season_year: int | None,
    state: str,
    financial_year: str,
    dry_run: bool,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    feat_df = load_features(features, season_year)
    ctx_df = load_crop_context(crop_context, state, financial_year)

    logger.info(
        "Loaded %d rainfall feature rows, %d crop context rows (%s / %s)",
        len(feat_df), len(ctx_df), state, financial_year,
    )

    merged = build_join(feat_df, ctx_df)
    report_coverage(merged)

    if dry_run:
        print(merged[["abs_sa2_code", "station_sa2_5dig16", "rainfall_sa2_code",
                       "sa2_name", "crop", "rainfall_feature_quality_flag",
                       "station_count", "season_year"]].to_string())
        return

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_csv_write(merged, out_path)
    logger.info("Wrote %d rows → %s", len(merged), out_path)


if __name__ == "__main__":
    main()
