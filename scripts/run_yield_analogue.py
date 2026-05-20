"""
Wheat Yield Analogue Analysis
==============================
Selects historical analogue years by matching SA2-area-weighted seasonal
rainfall windows and produces implied production estimates using ABARES
state-level area data.

Usage:
    python scripts/run_yield_analogue.py --target-year 2026
    python scripts/run_yield_analogue.py --target-year 2026 --windows jan-mar,apr-may,jun-oct
    python scripts/run_yield_analogue.py --target-year 2024 --windows jan-mar,apr-may,jun-oct
"""

import sys
import logging
from pathlib import Path
from functools import reduce
from typing import Optional

import click
import numpy as np
import pandas as pd

# Allow imports from src/ when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.common.file_utils import atomic_csv_write

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent

RAINFALL_CSV = REPO_ROOT / "data/features/sa2_monthly_rainfall_history_national.csv"
CROP_CONTEXT_CSV = REPO_ROOT / "data/meta/crop_context_sa2.csv"
ABARES_CSV = REPO_ROOT / "data/meta/abares/abares_crop_production_normalized.csv"

# Map state_name (rainfall CSV) -> ABARES state code
STATE_NAME_TO_ABARES = {
    "New South Wales": "NSW",
    "Victoria": "VIC",
    "Queensland": "QLD",
    "South Australia": "SA",
    "Western Australia": "WA",
    "Tasmania": "TAS",
    "Australian Capital Territory": "ACT",
}

# Seasonal window definitions: name -> list of months
WINDOW_MONTHS = {
    "jan-mar": [1, 2, 3],
    "apr-may": [4, 5],
    "jun-oct": [6, 7, 8, 9, 10],
}

# ---------------------------------------------------------------------------
# Helper: SA2 code conversion
# ---------------------------------------------------------------------------


def convert_sa2_9to5(sa2_9: str) -> str:
    """state-first-digit + last-4-digits of 9-digit SA2 code.

    Example: '103011060' -> '11060'
             '501021007' -> '51007'
    """
    s = str(sa2_9)
    return s[0] + s[-4:] if len(s) >= 5 else s


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def compute_state_weighted_rainfall(
    rainfall_df: pd.DataFrame,
    crop_context_df: pd.DataFrame,
    target_year: int,
) -> pd.DataFrame:
    """Compute area-weighted state-level seasonal rainfall.

    Parameters
    ----------
    rainfall_df:
        Canonical monthly CSV (9-digit sa2_code). Must contain columns:
        year, month, sa2_code, state_name, rainfall_mm, is_partial_month.
    crop_context_df:
        Wheat rows only, columns: sa2_5dig (5-digit), state, area_ha_for_weighting.
    target_year:
        The analysis year. Partial months are excluded from historical
        baselines but are included as-is for the target year.

    Returns
    -------
    DataFrame with columns: [year, state_name, jan_mar, apr_may, jun_oct]
    """
    # Convert rainfall 9-digit -> 5-digit
    rain = rainfall_df.copy()
    rain["sa2_5dig"] = rain["sa2_code"].astype(str).apply(convert_sa2_9to5)

    # Prepare crop context: aggregate area by 5-digit SA2 (handles dual-state)
    ctx = (
        crop_context_df.groupby("sa2_5dig")["area_ha_for_weighting"]
        .sum()
        .reset_index()
    )

    # Join rainfall with crop context
    merged = rain.merge(ctx, on="sa2_5dig", how="inner")

    # Exclude partial months from HISTORICAL baseline; include target year as-is
    hist = merged[
        (merged["is_partial_month"] == False) | (merged["year"] == target_year)
    ].copy()

    def _weighted_window(df: pd.DataFrame, months: list, col_name: str) -> pd.DataFrame:
        wdf = df[df["month"].isin(months)].copy()
        # Sum rainfall across months per SA2 first, then apply area weighting
        sa2_sum = (
            wdf.groupby(["year", "state_name", "sa2_5dig", "area_ha_for_weighting"])
            ["rainfall_mm"]
            .sum()
            .reset_index()
        )
        sa2_sum["weighted"] = sa2_sum["rainfall_mm"] * sa2_sum["area_ha_for_weighting"]
        agg = (
            sa2_sum.groupby(["year", "state_name"])
            .agg(
                total_weighted=("weighted", "sum"),
                total_area=("area_ha_for_weighting", "sum"),
            )
            .reset_index()
        )
        agg[col_name] = agg["total_weighted"] / agg["total_area"]
        return agg[["year", "state_name", col_name]]

    window_dfs = [
        _weighted_window(hist, WINDOW_MONTHS["jan-mar"], "jan_mar"),
        _weighted_window(hist, WINDOW_MONTHS["apr-may"], "apr_may"),
        _weighted_window(hist, WINDOW_MONTHS["jun-oct"], "jun_oct"),
    ]

    result = reduce(
        lambda a, b: a.merge(b, on=["year", "state_name"], how="outer"), window_dfs
    )
    return result.sort_values(["state_name", "year"]).reset_index(drop=True)


def select_analogues(
    state_rainfall_df: pd.DataFrame,
    target_year: int,
    windows: list,
    n: int = 3,
) -> dict:
    """Select top-n analogue years per state using standardised Euclidean distance.

    Parameters
    ----------
    state_rainfall_df:
        Output of compute_state_weighted_rainfall().
    target_year:
        The year to find analogues for.
    windows:
        List of column names to use as distance dimensions
        (e.g. ['jan_mar', 'apr_may']).
    n:
        Number of analogues to return per state.

    Returns
    -------
    dict: {state_name -> {'analogue_years': [...], 'distances': [...]}}
    """
    result = {}
    for state, sdf in state_rainfall_df.groupby("state_name"):
        target_row = sdf[sdf["year"] == target_year][windows]
        if target_row.empty or target_row.isnull().all(axis=None).item():
            logger.warning("No complete target data for %s in windows %s", state, windows)
            continue

        hist = sdf[sdf["year"] < target_year].dropna(subset=windows)
        if len(hist) < n:
            logger.warning("Insufficient history for %s (%d rows)", state, len(hist))
            continue

        means = hist[windows].mean()
        stds = hist[windows].std().replace(0, 1.0)  # avoid divide-by-zero

        hist_std = (hist[windows] - means) / stds
        target_val = target_row[windows].values
        target_std = (target_val - means.values) / stds.values

        dists = np.sqrt(((hist_std.values - target_std) ** 2).sum(axis=1))
        idx = np.argsort(dists)[:n]
        result[state] = {
            "analogue_years": hist.iloc[idx]["year"].tolist(),
            "distances": dists[idx].tolist(),
        }
    return result


def compute_implied_production(
    analogues: dict,
    abares_df: pd.DataFrame,
    target_year: int,
) -> pd.DataFrame:
    """Compute implied state-level wheat production from analogue yields.

    For each state, implied production = 2025 ABARES area × mean analogue yield.
    Analogue yield = production_t / area_ha for each analogue year.

    Parameters
    ----------
    analogues:
        Output of select_analogues().
    abares_df:
        ABARES data filtered to Wheat rows.
    target_year:
        Used for labelling; does not affect calculation.

    Returns
    -------
    DataFrame with columns: state, analogue_years, mean_yield, implied_production_mt,
        area_2025_ha
    """
    wheat = abares_df[abares_df["crop"] == "Wheat"].copy()

    rows = []
    for state_name, ana_data in analogues.items():
        state_code = STATE_NAME_TO_ABARES.get(state_name)
        if state_code is None:
            continue

        state_data = wheat[wheat["state"] == state_code]
        area_data = state_data[state_data["metric"] == "Area"].set_index("crop_season")[
            "value_normalized"
        ]
        prod_data = state_data[state_data["metric"] == "Production"].set_index(
            "crop_season"
        )["value_normalized"]

        # Area base: 2025 ABARES (forecast)
        area_2025 = area_data.get(2025)
        if area_2025 is None or pd.isna(area_2025):
            logger.warning("No 2025 area for %s", state_name)
            continue

        # Compute yield per analogue year
        yields = []
        for yr in ana_data["analogue_years"]:
            a = area_data.get(yr)
            p = prod_data.get(yr)
            if a is not None and p is not None and not pd.isna(a) and not pd.isna(p) and a > 0:
                yields.append(p / a)

        if not yields:
            logger.warning("No valid yields for %s analogues %s", state_name, ana_data["analogue_years"])
            continue

        mean_yield = float(np.mean(yields))
        implied_mt = mean_yield * area_2025 / 1e6

        rows.append(
            {
                "state": state_name,
                "target_year": target_year,
                "analogue_years": ana_data["analogue_years"],
                "analogue_distances": ana_data["distances"],
                "mean_analogue_yield_t_ha": round(mean_yield, 4),
                "implied_production_mt": round(implied_mt, 3),
                "area_2025_ha": int(area_2025),
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Jun-Oct dispersion (T-20260520-004)
# ---------------------------------------------------------------------------


def _target_has_jun_oct(state_rainfall_df: pd.DataFrame, target_year: int) -> bool:
    """Return True if target year has non-null jun_oct data for at least one state."""
    target_rows = state_rainfall_df[state_rainfall_df["year"] == target_year]
    return bool(target_rows["jun_oct"].notna().any())


def compute_implied_production_with_dispersion(
    analogues: dict,
    state_rainfall_df: pd.DataFrame,
    abares_df: pd.DataFrame,
    target_year: int,
) -> pd.DataFrame:
    """Conditional analogue mode for 3-window when jun-oct is not yet available.

    Analogues are selected on (jan-mar, apr-may). For each analogue year,
    we look up that year's jun-oct rainfall. We then report low/mid/high
    implied production corresponding to low/mid/high jun-oct analogue.

    Returns DataFrame with additional columns:
        jun_oct_low_mm, jun_oct_high_mm,
        implied_production_low_mt, implied_production_mid_mt, implied_production_high_mt
    """
    base_df = compute_implied_production(analogues, abares_df, target_year)

    wheat = abares_df[abares_df["crop"] == "Wheat"].copy()

    dispersion_rows = []
    for _, row in base_df.iterrows():
        state_name = row["state"]
        state_code = STATE_NAME_TO_ABARES.get(state_name)
        if state_code is None:
            continue

        # Get jun_oct values for each analogue year in this state
        sdf = state_rainfall_df[state_rainfall_df["state_name"] == state_name]
        ana_years = row["analogue_years"]

        jun_oct_vals = []
        for yr in ana_years:
            jval = sdf[sdf["year"] == yr]["jun_oct"]
            if not jval.empty and not jval.isnull().all():
                jun_oct_vals.append(float(jval.iloc[0]))

        if len(jun_oct_vals) < len(ana_years):
            logger.warning(
                "Missing jun_oct for some analogue years in %s: %s", state_name, ana_years
            )

        if not jun_oct_vals:
            dispersion_rows.append(
                {**row.to_dict(), "jun_oct_low_mm": None, "jun_oct_high_mm": None,
                 "implied_production_low_mt": row["implied_production_mt"],
                 "implied_production_mid_mt": row["implied_production_mt"],
                 "implied_production_high_mt": row["implied_production_mt"]}
            )
            continue

        jun_oct_low = min(jun_oct_vals)
        jun_oct_high = max(jun_oct_vals)

        # Compute per-year yield for dispersion (same area base)
        state_data = wheat[wheat["state"] == state_code]
        area_data = state_data[state_data["metric"] == "Area"].set_index("crop_season")[
            "value_normalized"
        ]
        prod_data = state_data[state_data["metric"] == "Production"].set_index(
            "crop_season"
        )["value_normalized"]

        area_2025 = area_data.get(2025, row["area_2025_ha"])

        per_year_yields = []
        for yr in ana_years:
            a = area_data.get(yr)
            p = prod_data.get(yr)
            if a is not None and p is not None and not pd.isna(a) and not pd.isna(p) and a > 0:
                per_year_yields.append((yr, p / a))

        if not per_year_yields:
            dispersion_rows.append(
                {**row.to_dict(), "jun_oct_low_mm": jun_oct_low, "jun_oct_high_mm": jun_oct_high,
                 "implied_production_low_mt": row["implied_production_mt"],
                 "implied_production_mid_mt": row["implied_production_mt"],
                 "implied_production_high_mt": row["implied_production_mt"]}
            )
            continue

        # Map year -> jun_oct value
        sdf_dict = {yr: v for yr, v in zip(ana_years, jun_oct_vals)}

        # Sort per_year_yields by their jun_oct value
        per_year_yields_with_jval = [
            (yr, yld, sdf_dict.get(yr, np.nan)) for yr, yld in per_year_yields
        ]
        per_year_yields_with_jval.sort(key=lambda x: x[2] if not np.isnan(x[2]) else 0)

        low_yield = per_year_yields_with_jval[0][1]
        high_yield = per_year_yields_with_jval[-1][1]
        mid_yield = float(np.mean([y for _, y, _ in per_year_yields_with_jval]))

        dispersion_rows.append(
            {
                **row.to_dict(),
                "jun_oct_low_mm": round(jun_oct_low, 1),
                "jun_oct_high_mm": round(jun_oct_high, 1),
                "implied_production_low_mt": round(low_yield * area_2025 / 1e6, 3),
                "implied_production_mid_mt": round(mid_yield * area_2025 / 1e6, 3),
                "implied_production_high_mt": round(high_yield * area_2025 / 1e6, 3),
            }
        )

    return pd.DataFrame(dispersion_rows)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _build_output_df(
    prod_df: pd.DataFrame,
    windows_used: list,
    n_analogues: int = 3,
    dispersion_mode: bool = False,
) -> pd.DataFrame:
    """Flatten analogue list columns into individual columns for CSV output."""
    rows = []
    for _, row in prod_df.iterrows():
        ana_years = row.get("analogue_years", [])
        ana_dists = row.get("analogue_distances", [])

        out = {
            "state": row["state"],
            "target_year": row["target_year"],
            "windows_used": ",".join(windows_used),
        }
        for i in range(n_analogues):
            out[f"analogue_year_{i+1}"] = ana_years[i] if i < len(ana_years) else None
            out[f"dist_{i+1}"] = round(ana_dists[i], 4) if i < len(ana_dists) else None

        out["mean_analogue_yield_t_ha"] = row["mean_analogue_yield_t_ha"]
        out["area_2025_ha"] = row["area_2025_ha"]

        if dispersion_mode:
            out["implied_production_mt"] = row.get("implied_production_mid_mt", row.get("implied_production_mt"))
            out["jun_oct_low_mm"] = row.get("jun_oct_low_mm")
            out["jun_oct_high_mm"] = row.get("jun_oct_high_mm")
            out["implied_production_low_mt"] = row.get("implied_production_low_mt")
            out["implied_production_mid_mt"] = row.get("implied_production_mid_mt")
            out["implied_production_high_mt"] = row.get("implied_production_high_mt")
        else:
            out["implied_production_mt"] = row["implied_production_mt"]

        rows.append(out)

    return pd.DataFrame(rows)


def print_markdown_table(
    prod_df: pd.DataFrame,
    target_year: int,
    windows_used: list,
    dispersion_mode: bool = False,
) -> None:
    """Print analysis results as a markdown table to stdout."""
    print(f"\n## Wheat Yield Analogue Analysis — {target_year}\n")
    print(f"Windows used: {', '.join(windows_used)}\n")

    if dispersion_mode:
        print(
            "Note: %d Jun-Oct data not yet available. "
            "Showing Jun-Oct dispersion across (jan-mar, apr-may) analogues.\n"
            % target_year
        )
        print("| State | Analogues | Implied Prod Low (Mt) | Implied Prod Mid (Mt) | Implied Prod High (Mt) | Mean Yield (t/ha) | 2025 Area (Mha) |")
        print("|-------|-----------|----------------------|----------------------|----------------------|-------------------|-----------------|")
    else:
        print("| State | Analogues | Implied Prod (Mt) | Mean Yield (t/ha) | 2025 Area (Mha) |")
        print("|-------|-----------|-------------------|-------------------|-----------------|")

    national_low = 0.0
    national_mid = 0.0
    national_high = 0.0
    national_single = 0.0

    for _, row in prod_df.iterrows():
        ana_years = row.get("analogue_years", [])
        ana_str = ", ".join(str(y) for y in sorted(ana_years))
        area_mha = row["area_2025_ha"] / 1e6

        if dispersion_mode:
            low_mt = row.get("implied_production_low_mt", row.get("implied_production_mt", 0))
            mid_mt = row.get("implied_production_mid_mt", row.get("implied_production_mt", 0))
            high_mt = row.get("implied_production_high_mt", row.get("implied_production_mt", 0))
            national_low += low_mt or 0
            national_mid += mid_mt or 0
            national_high += high_mt or 0
            print(
                f"| {row['state']} | {ana_str} | {low_mt:.1f} | {mid_mt:.1f} | {high_mt:.1f} | "
                f"{row['mean_analogue_yield_t_ha']:.2f} | {area_mha:.2f} |"
            )
        else:
            prod_mt = row.get("implied_production_mt", 0)
            national_single += prod_mt or 0
            print(
                f"| {row['state']} | {ana_str} | {prod_mt:.1f} | "
                f"{row['mean_analogue_yield_t_ha']:.2f} | {area_mha:.2f} |"
            )

    if dispersion_mode:
        print(
            f"| **Australia** | — | **{national_low:.1f}** | **{national_mid:.1f}** | "
            f"**{national_high:.1f}** | — | — |"
        )
    else:
        print(f"| **Australia** | — | **{national_single:.1f}** | — | — |")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--target-year",
    default=None,
    type=int,
    help="Target year (default: current year inferred from data)",
)
@click.option(
    "--windows",
    default="jan-mar,apr-may",
    help="Comma-separated windows to use: jan-mar, apr-may, jun-oct",
)
@click.option(
    "--output",
    default=str(REPO_ROOT / "data/features/wheat_yield_analogue_summary.csv"),
    help="Output CSV path",
)
@click.option("--n-analogues", default=3, type=int, help="Number of analogue years to select")
def main(
    target_year: Optional[int],
    windows: str,
    output: str,
    n_analogues: int,
) -> None:
    """Run wheat yield analogue analysis."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Parse windows
    windows_list = [w.strip() for w in windows.split(",")]
    for w in windows_list:
        if w not in WINDOW_MONTHS:
            raise click.BadParameter(
                f"Unknown window '{w}'. Choose from: {list(WINDOW_MONTHS.keys())}"
            )

    # Load data
    logger.info("Loading rainfall data from %s", RAINFALL_CSV)
    rain_df = pd.read_csv(RAINFALL_CSV)

    logger.info("Loading crop context from %s", CROP_CONTEXT_CSV)
    ctx_df = pd.read_csv(CROP_CONTEXT_CSV)
    ctx_wheat = ctx_df[ctx_df["crop"] == "wheat"].copy()
    ctx_wheat["sa2_5dig"] = ctx_wheat["station_sa2_5dig16"].astype(str)

    logger.info("Loading ABARES data from %s", ABARES_CSV)
    abares_df = pd.read_csv(ABARES_CSV)

    # Determine target year
    if target_year is None:
        target_year = int(rain_df["year"].max())
        logger.info("Target year inferred from data: %d", target_year)

    # Compute area-weighted rainfall
    logger.info("Computing state-weighted rainfall for all windows...")
    state_rain = compute_state_weighted_rainfall(rain_df, ctx_wheat, target_year)

    # Determine whether to use 3-window full or conditional mode
    use_jun_oct = "jun-oct" in windows_list
    dispersion_mode = False

    if use_jun_oct:
        if not _target_has_jun_oct(state_rain, target_year):
            dispersion_mode = True
            logger.info(
                "Jun-Oct data not available for %d. Using conditional analogue mode "
                "(analogues from jan-mar + apr-may, jun-oct dispersion reported).",
                target_year,
            )
            windows_for_selection = ["jan_mar", "apr_may"]
        else:
            windows_for_selection = [w.replace("-", "_") for w in windows_list]
    else:
        windows_for_selection = [w.replace("-", "_") for w in windows_list]

    # Select analogues
    logger.info("Selecting analogues on windows: %s", windows_for_selection)
    analogues = select_analogues(
        state_rain, target_year, windows=windows_for_selection, n=n_analogues
    )

    # Compute implied production
    if dispersion_mode:
        prod_df = compute_implied_production_with_dispersion(
            analogues, state_rain, abares_df, target_year
        )
    else:
        prod_df = compute_implied_production(analogues, abares_df, target_year)

    # Build output DataFrame
    out_df = _build_output_df(prod_df, windows_list, n_analogues=n_analogues,
                              dispersion_mode=dispersion_mode)

    # Write CSV
    logger.info("Writing output to %s", output)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    atomic_csv_write(out_df, output)

    # Print markdown table
    print_markdown_table(prod_df, target_year, windows_list, dispersion_mode=dispersion_mode)


if __name__ == "__main__":
    main()
