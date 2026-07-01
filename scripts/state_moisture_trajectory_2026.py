"""Compute state-level area-weighted rainfall trajectory for 2026.

For each state, output Jan/Feb/Mar/Apr/May-MTD 2026 area-weighted rainfall
alongside historical 2005-2025 percentile ranks. Also produce Sep-Oct
historical distribution (P10/P50/P90) per state for scenario framing.

Inputs:
- data/meta/crop_context_sa2.csv          (wheat area weights)
- data/features/sa2_monthly_rainfall_history_national.csv  (Jan-May 2026 monthly)
- data/features/sa2_2026_05_mtd.csv       (May 2026 MTD; through-day read from
                                           partial_month_through_day at runtime)

Outputs:
- data/features/state_moisture_trajectory_2026.csv
- data/features/state_sep_oct_climatology.csv
- Stdout: human-readable tables
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path

from src.common.file_utils import atomic_csv_write
from src.rainfall.analytics import area_weighted, percentile_rank

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS_PATH = ROOT / "data/meta/crop_context_sa2.csv"
HISTORY_PATH = ROOT / "data/features/sa2_monthly_rainfall_history_national.csv"
MTD_PATH = ROOT / "data/features/sa2_2026_05_mtd.csv"
OUT_TRAJ = ROOT / "data/features/state_moisture_trajectory_2026.csv"
OUT_SEPOCT = ROOT / "data/features/state_sep_oct_climatology.csv"


def load_weights() -> pd.DataFrame:
    df = pd.read_csv(WEIGHTS_PATH, low_memory=False)
    df = df[df["crop"] == "wheat"][["sa2_code", "state", "area_ha_for_weighting"]].copy()
    df = df.rename(columns={"state": "state_name", "area_ha_for_weighting": "weight"})
    return df


def main() -> None:
    weights = load_weights()
    history = pd.read_csv(HISTORY_PATH, low_memory=False)
    mtd = pd.read_csv(MTD_PATH, low_memory=False)
    mtd_day = int(mtd["partial_month_through_day"].dropna().max())
    may_label = f"May_d1_d{mtd_day}"
    jam_label = f"Jan-May_d{mtd_day}_cum"

    history = history[["year", "month", "sa2_code", "state_name", "rainfall_mm"]]
    aw_monthly = area_weighted(history, weights, "rainfall_mm", ["year", "month", "state_name"])

    aw_mtd = area_weighted(
        mtd[["year", "month", "sa2_code", "state_name", "rainfall_mm"]],
        weights,
        "rainfall_mm",
        ["year", "month", "state_name"],
    )
    aw_mtd["month_label"] = f"May_MTD_d{mtd_day}"

    states = sorted(weights["state_name"].unique())

    rows = []

    for state in states:
        s_hist = aw_monthly[aw_monthly["state_name"] == state]

        for m, label in [(1, "Jan"), (2, "Feb"), (3, "Mar"), (4, "Apr")]:
            cur = s_hist[(s_hist["year"] == 2026) & (s_hist["month"] == m)]
            if cur.empty:
                continue
            v_2026 = cur["rainfall_mm"].iloc[0]
            base = s_hist[(s_hist["month"] == m) & (s_hist["year"] >= 2005) & (s_hist["year"] <= 2025)]["rainfall_mm"].values
            rows.append({
                "state": state,
                "window": label,
                "rainfall_2026_mm": round(v_2026, 1),
                "hist_median_mm": round(float(np.median(base)), 1),
                "hist_p10_mm": round(float(np.percentile(base, 10)), 1),
                "hist_p90_mm": round(float(np.percentile(base, 90)), 1),
                "percentile_rank_2026": round(percentile_rank(base, v_2026), 1),
                "n_hist_years": int(len(base)),
            })

        # Jan-Apr cumulative — require all four 2026 months present before
        # summing, so an absent month is never silently treated as 0 mm.
        jan_apr_2026 = s_hist[(s_hist["year"] == 2026) & (s_hist["month"].between(1, 4))]
        present = {int(m) for m in jan_apr_2026["month"]}
        if present != {1, 2, 3, 4}:
            missing = sorted({1, 2, 3, 4} - present)
            raise SystemExit(
                f"Missing Jan-Apr 2026 month(s) {missing} for state {state!r}: "
                f"cannot compute the Jan-Apr cumulative. Refusing to silently "
                f"understate it with a 0 mm fill."
            )
        ytd_2026 = jan_apr_2026["rainfall_mm"].sum()
        hist_ytd = (
            s_hist[(s_hist["year"] >= 2005) & (s_hist["year"] <= 2025) & (s_hist["month"].between(1, 4))]
            .groupby("year")["rainfall_mm"].sum().values
        )
        rows.append({
            "state": state,
            "window": "Jan-Apr_cum",
            "rainfall_2026_mm": round(float(ytd_2026), 1),
            "hist_median_mm": round(float(np.median(hist_ytd)), 1),
            "hist_p10_mm": round(float(np.percentile(hist_ytd, 10)), 1),
            "hist_p90_mm": round(float(np.percentile(hist_ytd, 90)), 1),
            "percentile_rank_2026": round(percentile_rank(hist_ytd, ytd_2026), 1),
            "n_hist_years": int(len(hist_ytd)),
        })

        # May MTD
        mtd_v = aw_mtd[(aw_mtd["state_name"] == state) & (aw_mtd["year"] == 2026) & (aw_mtd["month"] == 5)]
        if mtd_v.empty:
            raise SystemExit(
                f"Missing May 2026 MTD for state {state!r}: cannot compute "
                f"like-for-like {may_label} / {jam_label} windows. Refusing to "
                f"silently understate the Jan-May cumulative with a 0 mm fill."
            )
        v_mtd = mtd_v["rainfall_mm"].iloc[0]
        base_may = (
            s_hist[(s_hist["month"] == 5) & (s_hist["year"] >= 2005) & (s_hist["year"] <= 2025)]["rainfall_mm"].values
            * (mtd_day / 31.0)
        )
        rows.append({
            "state": state,
            "window": may_label,
            "rainfall_2026_mm": round(v_mtd, 1),
            "hist_median_mm": round(float(np.median(base_may)), 1),
            "hist_p10_mm": round(float(np.percentile(base_may, 10)), 1),
            "hist_p90_mm": round(float(np.percentile(base_may, 90)), 1),
            "percentile_rank_2026": round(percentile_rank(base_may, v_mtd), 1),
            "n_hist_years": int(len(base_may)),
        })

        # Jan-May cumulative through the available May MTD day.
        cum_full = ytd_2026 + v_mtd
        hist_jan_apr = (
            s_hist[(s_hist["year"] >= 2005) & (s_hist["year"] <= 2025) & (s_hist["month"].between(1, 4))]
            .groupby("year")["rainfall_mm"].sum()
        )
        hist_may_scaled = (
            s_hist[(s_hist["year"] >= 2005) & (s_hist["year"] <= 2025) & (s_hist["month"] == 5)]
            .set_index("year")["rainfall_mm"]
            * (mtd_day / 31.0)
        )
        hist_jam = (hist_jan_apr + hist_may_scaled).dropna().values
        rows.append({
            "state": state,
            "window": jam_label,
            "rainfall_2026_mm": round(float(cum_full), 1),
            "hist_median_mm": round(float(np.median(hist_jam)), 1),
            "hist_p10_mm": round(float(np.percentile(hist_jam, 10)), 1),
            "hist_p90_mm": round(float(np.percentile(hist_jam, 90)), 1),
            "percentile_rank_2026": round(percentile_rank(hist_jam, cum_full), 1),
            "n_hist_years": int(len(hist_jam)),
        })

    traj = pd.DataFrame(rows)
    OUT_TRAJ.parent.mkdir(parents=True, exist_ok=True)
    if not atomic_csv_write(traj, OUT_TRAJ):
        raise SystemExit(f"Failed to write {OUT_TRAJ}")

    # Sep-Oct climatology per state for scenario buckets
    sepoct_rows = []
    for state in states:
        s_hist = aw_monthly[aw_monthly["state_name"] == state]
        cum = (
            s_hist[(s_hist["year"] >= 2005) & (s_hist["year"] <= 2025) & (s_hist["month"].isin([9, 10]))]
            .groupby("year")["rainfall_mm"].sum()
        )
        sepoct_rows.append({
            "state": state,
            "n_years": int(len(cum)),
            "sep_oct_p10_mm": round(float(np.percentile(cum.values, 10)), 1),
            "sep_oct_p25_mm": round(float(np.percentile(cum.values, 25)), 1),
            "sep_oct_median_mm": round(float(np.median(cum.values)), 1),
            "sep_oct_p75_mm": round(float(np.percentile(cum.values, 75)), 1),
            "sep_oct_p90_mm": round(float(np.percentile(cum.values, 90)), 1),
            "sep_oct_min_mm": round(float(cum.min()), 1),
            "sep_oct_max_mm": round(float(cum.max()), 1),
        })
    sepoct = pd.DataFrame(sepoct_rows)
    if not atomic_csv_write(sepoct, OUT_SEPOCT):
        raise SystemExit(f"Failed to write {OUT_SEPOCT}")

    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 20)
    print("=== State moisture trajectory 2026 (area-weighted by wheat area) ===")
    for state in states:
        print(f"\n--- {state} ---")
        print(traj[traj["state"] == state].drop(columns=["state"]).to_string(index=False))

    print("\n\n=== Sep-Oct historical climatology (2005-2025) ===")
    print(sepoct.to_string(index=False))

    print(f"\nWrote {OUT_TRAJ.relative_to(ROOT)}")
    print(f"Wrote {OUT_SEPOCT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
