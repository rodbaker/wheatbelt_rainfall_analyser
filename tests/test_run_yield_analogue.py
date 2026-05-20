"""
Tests for scripts/run_yield_analogue.py

Run with:
    python -m pytest tests/test_run_yield_analogue.py -v
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Allow imports from scripts/ and src/
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_yield_analogue import (
    compute_implied_production,
    compute_implied_production_with_dispersion,
    compute_state_weighted_rainfall,
    select_analogues,
)


# ---------------------------------------------------------------------------
# Test 1: Area-weighted monthly aggregation
# ---------------------------------------------------------------------------


def test_area_weighted_monthly_aggregation():
    """
    Create a minimal synthetic dataset (2 SA2s, 1 state, months 1-3) with
    known areas and rainfall. Assert the area-weighted result matches hand
    calculation.

    SA2 A: area=100 ha, Jan=10mm, Feb=20mm, Mar=30mm  -> total=60mm, weighted=6000
    SA2 B: area=400 ha, Jan=40mm, Feb=50mm, Mar=60mm  -> total=150mm, weighted=60000
    Total area = 500 ha
    Expected jan_mar = (6000 + 60000) / 500 = 132.0 mm
    """
    # Build synthetic rainfall data with 9-digit sa2_codes
    rain_rows = []
    # SA2 A: 9-digit code 101001001 -> 5-digit 11001  (s[0]+'1001'='11001')
    for month, mm in zip([1, 2, 3], [10, 20, 30]):
        rain_rows.append(
            {
                "year": 2020,
                "month": month,
                "sa2_code": 101001001,
                "sa2_name": "Test A",
                "state_name": "TestState",
                "rainfall_mm": mm,
                "is_partial_month": False,
                "partial_month_through_day": None,
            }
        )
    # SA2 B: 9-digit code 101001002 -> 5-digit 11002  (s[0]+'1002'='11002')
    for month, mm in zip([1, 2, 3], [40, 50, 60]):
        rain_rows.append(
            {
                "year": 2020,
                "month": month,
                "sa2_code": 101001002,
                "sa2_name": "Test B",
                "state_name": "TestState",
                "rainfall_mm": mm,
                "is_partial_month": False,
                "partial_month_through_day": None,
            }
        )
    rain_df = pd.DataFrame(rain_rows)

    # Build crop context
    ctx_rows = [
        {"sa2_5dig": "11001", "area_ha_for_weighting": 100},
        {"sa2_5dig": "11002", "area_ha_for_weighting": 400},
    ]
    ctx_df = pd.DataFrame(ctx_rows)

    result = compute_state_weighted_rainfall(rain_df, ctx_df, target_year=2020)

    target_row = result[result["year"] == 2020]
    assert len(target_row) == 1, "Should have exactly one row for year 2020"

    expected_jan_mar = (10 * 100 + 20 * 100 + 30 * 100 + 40 * 400 + 50 * 400 + 60 * 400) / 500
    # = (6000 + 8000 + 12000 + 16000 + 20000 + 24000) / 500 wait, let me recalculate
    # SA2 A total (jan+feb+mar) weighted = (10+20+30)*100 = 6000
    # SA2 B total (jan+feb+mar) weighted = (40+50+60)*400 = 60000
    # But the function sums rainfall per SA2 per window THEN weights
    # so for SA2 A: sum=60, weighted=6000; SA2 B: sum=150, weighted=60000
    expected_jan_mar = (60 * 100 + 150 * 400) / (100 + 400)
    assert abs(target_row["jan_mar"].iloc[0] - expected_jan_mar) < 0.001, (
        f"Expected jan_mar={expected_jan_mar}, got {target_row['jan_mar'].iloc[0]}"
    )


# ---------------------------------------------------------------------------
# Test 2: Standardised joint distance
# ---------------------------------------------------------------------------


def test_standardised_joint_distance():
    """
    Create a minimal 3-year, 2-window history. Assert the target year's
    nearest neighbour is the one we expect by hand.

    History:
      Year 2010: jan_mar=100, apr_may=50
      Year 2011: jan_mar=200, apr_may=100
      Year 2012: jan_mar=150, apr_may=75

    Target 2013: jan_mar=110, apr_may=55

    Mean = (100+200+150)/3=150, (50+100+75)/3=75
    Std  = std([100,200,150]) ≈ 50.0, std([50,100,75]) ≈ 25.0

    Standardised target: ((110-150)/50, (55-75)/25) = (-0.8, -0.8)
    Standardised 2010: ((100-150)/50, (50-75)/25) = (-1.0, -1.0)  dist=sqrt(0.04+0.04)=0.283
    Standardised 2011: ((200-150)/50, (100-75)/25) = (1.0, 1.0)   dist=sqrt(3.24+3.24)=3.6
    Standardised 2012: ((150-150)/50, (75-75)/25) = (0.0, 0.0)    dist=sqrt(0.64+0.64)=1.131

    Nearest = 2010
    """
    data = pd.DataFrame(
        {
            "year": [2010, 2011, 2012, 2013],
            "state_name": ["TestState"] * 4,
            "jan_mar": [100, 200, 150, 110],
            "apr_may": [50, 100, 75, 55],
            "jun_oct": [None, None, None, None],
        }
    )

    result = select_analogues(data, target_year=2013, windows=["jan_mar", "apr_may"], n=1)
    assert "TestState" in result, "TestState not found in result"
    nearest = result["TestState"]["analogue_years"][0]
    assert nearest == 2010, f"Expected nearest analogue 2010, got {nearest}"


# ---------------------------------------------------------------------------
# Test 3: 2026 NSW analogues
# ---------------------------------------------------------------------------


def test_2026_nsw_analogues():
    """
    Load actual data files and assert that for 2026:
    - NSW analogues are [2017, 2019, 2023] (sorted)
    - Implied production is between 5.5 and 5.7 Mt
    """
    rain_df = pd.read_csv(REPO_ROOT / "data/features/sa2_monthly_rainfall_history_national.csv")
    ctx_df = pd.read_csv(REPO_ROOT / "data/meta/crop_context_sa2.csv")
    abares_df = pd.read_csv(REPO_ROOT / "data/meta/abares/abares_crop_production_normalized.csv")

    ctx_wheat = ctx_df[ctx_df["crop"] == "wheat"].copy()
    ctx_wheat["sa2_5dig"] = ctx_wheat["station_sa2_5dig16"].astype(str)

    target_year = 2026
    state_rain = compute_state_weighted_rainfall(rain_df, ctx_wheat, target_year)
    analogues = select_analogues(state_rain, target_year, windows=["jan_mar", "apr_may"], n=3)

    assert "New South Wales" in analogues, "NSW not in analogues result"
    nsw_years = sorted(analogues["New South Wales"]["analogue_years"])
    assert nsw_years == [2017, 2019, 2023], (
        f"Expected NSW analogues [2017, 2019, 2023], got {nsw_years}"
    )

    prod_df = compute_implied_production(analogues, abares_df, target_year)
    nsw_row = prod_df[prod_df["state"] == "New South Wales"]
    assert len(nsw_row) == 1, "Expected exactly one NSW row"
    nsw_prod = nsw_row["implied_production_mt"].iloc[0]
    assert 5.5 <= nsw_prod <= 5.7, (
        f"Expected NSW implied production between 5.5 and 5.7 Mt, got {nsw_prod}"
    )


# ---------------------------------------------------------------------------
# Test 4: Jun-Oct dispersion for 2026 (T-20260520-004)
# ---------------------------------------------------------------------------


def test_jun_oct_dispersion_2026():
    """
    Run with windows jan-mar,apr-may,jun-oct for target year 2026.
    Since 2026 has no Jun-Oct data, dispersion mode should be triggered.

    Assert:
    - Output includes columns implied_production_low_mt and implied_production_high_mt
    - low < high for at least one state
    """
    rain_df = pd.read_csv(REPO_ROOT / "data/features/sa2_monthly_rainfall_history_national.csv")
    ctx_df = pd.read_csv(REPO_ROOT / "data/meta/crop_context_sa2.csv")
    abares_df = pd.read_csv(REPO_ROOT / "data/meta/abares/abares_crop_production_normalized.csv")

    ctx_wheat = ctx_df[ctx_df["crop"] == "wheat"].copy()
    ctx_wheat["sa2_5dig"] = ctx_wheat["station_sa2_5dig16"].astype(str)

    target_year = 2026
    state_rain = compute_state_weighted_rainfall(rain_df, ctx_wheat, target_year)

    # Confirm dispersion mode is triggered (no jun_oct for 2026)
    target_rows = state_rain[state_rain["year"] == target_year]
    assert target_rows["jun_oct"].isna().all(), "Expected no jun_oct data for 2026"

    analogues = select_analogues(state_rain, target_year, windows=["jan_mar", "apr_may"], n=3)
    disp_df = compute_implied_production_with_dispersion(
        analogues, state_rain, abares_df, target_year
    )

    # Check required columns exist
    assert "implied_production_low_mt" in disp_df.columns
    assert "implied_production_high_mt" in disp_df.columns

    # At least one state should have low < high
    has_range = (disp_df["implied_production_low_mt"] < disp_df["implied_production_high_mt"]).any()
    assert has_range, "Expected at least one state with dispersion (low < high)"


# ---------------------------------------------------------------------------
# Test 5: Full 3-window retrospective for 2024 (T-20260520-004)
# ---------------------------------------------------------------------------


def test_full_3window_retrospective():
    """
    Run with windows jan-mar,apr-may,jun-oct for target year 2024.
    Since 2024 is a complete year, 3-window joint distance should be used.

    Assert:
    - Output has standard implied_production_mt column (no dispersion)
    - Analogues are selected using 3-window distance
    """
    rain_df = pd.read_csv(REPO_ROOT / "data/features/sa2_monthly_rainfall_history_national.csv")
    ctx_df = pd.read_csv(REPO_ROOT / "data/meta/crop_context_sa2.csv")
    abares_df = pd.read_csv(REPO_ROOT / "data/meta/abares/abares_crop_production_normalized.csv")

    ctx_wheat = ctx_df[ctx_df["crop"] == "wheat"].copy()
    ctx_wheat["sa2_5dig"] = ctx_wheat["station_sa2_5dig16"].astype(str)

    target_year = 2024
    state_rain = compute_state_weighted_rainfall(rain_df, ctx_wheat, target_year)

    # Confirm 2024 has jun_oct data
    target_rows = state_rain[state_rain["year"] == target_year]
    assert target_rows["jun_oct"].notna().any(), "Expected jun_oct data for 2024"

    # Use 3-window selection
    analogues = select_analogues(
        state_rain, target_year, windows=["jan_mar", "apr_may", "jun_oct"], n=3
    )

    # With 3-window analogues, produce standard (non-dispersion) output
    prod_df = compute_implied_production(analogues, abares_df, target_year)

    # Standard output: implied_production_mt column present and valid
    assert "implied_production_mt" in prod_df.columns
    assert prod_df["implied_production_mt"].notna().all(), "All states should have production"
    assert (prod_df["implied_production_mt"] > 0).all(), "All production values should be positive"

    # Verify 2-window vs 3-window give different analogues for at least one state
    analogues_2w = select_analogues(
        state_rain, target_year, windows=["jan_mar", "apr_may"], n=3
    )
    different = False
    for state in analogues:
        if state in analogues_2w:
            if sorted(analogues[state]["analogue_years"]) != sorted(
                analogues_2w[state]["analogue_years"]
            ):
                different = True
                break
    assert different, (
        "3-window and 2-window analogues should differ for at least one state in 2024"
    )
