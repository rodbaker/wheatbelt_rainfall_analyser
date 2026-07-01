"""Per-state SA2 production-area-weighted rainfall drill for 2026.

For each state:
  - Top-10 SA2s by 2020-21 ABS wheat area (with cumulative share)
  - 2026 Jan-May MTD rainfall + % of median + percentile rank per top-10 SA2
  - Area share by decile band (Dry D1-D3 / Mid D4-D7 / Wet D8-D10)
  - Area-weighted vs unweighted percentile rank and % of median

Outputs:
  - data/features/state_sa2_area_weighted_2026.csv
  - Stdout: per-state tables
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path

from src.common.file_utils import atomic_csv_write

ROOT = Path(__file__).resolve().parents[1]
DRILL_PATH = ROOT / "data/features/sa2_state_drill_2026.csv"
WEIGHTS_PATH = ROOT / "data/meta/crop_context_sa2.csv"
SA3_LOOKUP = ROOT / "data/meta/sa2_sa3_lookup.csv"
OUT_PATH = ROOT / "data/features/state_sa2_area_weighted_2026.csv"
OUT_SA3 = ROOT / "data/features/state_sa3_area_weighted_2026.csv"


def main() -> None:
    drill = pd.read_csv(DRILL_PATH)
    jan_may_windows = sorted(
        w for w in drill["window"].dropna().unique()
        if str(w).startswith("Jan-May_d") and str(w).endswith("_cum")
    )
    if not jan_may_windows:
        raise SystemExit("No Jan-May MTD window found in SA2 drill output")
    current_window = jan_may_windows[-1]
    drill = drill[drill["window"] == current_window].copy()

    if "decile" not in drill.columns:
        raise SystemExit(
            f"{DRILL_PATH.name} has no 'decile' column — regenerate it with "
            "scripts/sa2_state_drill_2026.py (canonical decile_rank) before "
            "running this drill."
        )

    weights = pd.read_csv(WEIGHTS_PATH, low_memory=False)
    weights = weights[weights["crop"] == "wheat"][
        ["sa2_code", "state", "area_ha_for_weighting"]
    ].rename(columns={"area_ha_for_weighting": "wheat_area_ha", "state": "state_name"})

    m = drill.merge(weights, on=["sa2_code", "state_name"], how="left", indicator=True)

    # A drill row with NO wheat record at all is a universe/coverage gap — keep
    # failing loudly.
    no_record = m[m["_merge"] == "left_only"][["state_name", "sa2_code", "sa2_name"]]
    if not no_record.empty:
        sample = no_record.head(10).to_dict("records")
        raise SystemExit(
            f"Missing wheat weight records for {len(no_record)} SA2 row(s) "
            f"(no wheat row in {WEIGHTS_PATH.name}): {sample}"
        )

    # A wheat record exists but its area is missing / zero / non-positive — the
    # weight is suppressed or unusable. Exclude it from the area-weighted outputs
    # (do NOT impute a weight), and say so.
    unusable = m[(m["_merge"] == "both") & ~(m["wheat_area_ha"] > 0)]
    if not unusable.empty:
        excl = unusable[["state_name", "sa2_code", "sa2_name"]].to_dict("records")
        print(
            f"WARNING: excluded {len(unusable)} SA2 with missing/non-positive "
            f"wheat weight (suppressed area, not imputed): {excl}"
        )
    m = m[m["wheat_area_ha"] > 0].drop(columns=["_merge"]).copy()

    sa3 = pd.read_csv(SA3_LOOKUP)[["sa2_code", "sa3_name"]]
    m = m.merge(sa3, on="sa2_code", how="left")

    # Dry/Mid/Wet bands from the canonical rank-based decile, NOT a raw
    # percentile cut, so band membership matches the house deciles contract.
    def _band(d):
        if pd.isna(d):
            return None
        d = int(d)
        if d <= 3:
            return "Dry (D1-D3)"
        if d <= 7:
            return "Mid (D4-D7)"
        return "Wet (D8-D10)"

    m["band"] = pd.Categorical(
        m["decile"].map(_band),
        categories=["Dry (D1-D3)", "Mid (D4-D7)", "Wet (D8-D10)"],
        ordered=True,
    )

    rows_out = []
    pd.set_option("display.width", 180)
    pd.set_option("display.max_columns", 20)

    for state in sorted(m["state_name"].unique()):
        s = m[m["state_name"] == state].copy()
        total_area = s["wheat_area_ha"].sum()
        if total_area == 0:
            continue
        s["area_share_pct"] = (s["wheat_area_ha"] / total_area * 100).round(1)
        s_sorted = s.sort_values("wheat_area_ha", ascending=False)

        unw_pr = s["percentile_rank"].mean()
        aw_pr = (s["percentile_rank"] * s["wheat_area_ha"]).sum() / total_area
        unw_pm = s["pct_of_median"].mean()
        aw_pm = (s["pct_of_median"] * s["wheat_area_ha"]).sum() / total_area

        band_agg = s.groupby("band", observed=True).agg(
            n_sa2=("sa2_code", "count"),
            wheat_area_ha=("wheat_area_ha", "sum"),
        ).reset_index()
        band_agg["area_share_pct"] = (band_agg["wheat_area_ha"] / total_area * 100).round(1)

        print(f"\n\n=== {state} ({current_window}; total wheat area: {total_area:,.0f} ha) ===")
        print(f"Unweighted mean pct rank: {unw_pr:.1f} | Area-weighted: {aw_pr:.1f}")
        print(f"Unweighted mean % of median: {unw_pm:.0f}% | Area-weighted: {aw_pm:.0f}%")
        print("\nArea by band:")
        print(band_agg.to_string(index=False))

        top10 = s_sorted.head(10)
        top10_share = top10["area_share_pct"].sum()
        print(f"\nTop 10 SA2s by area (cum {top10_share:.1f}% of state):")
        name_col = "sa2_name_x" if "sa2_name_x" in top10.columns else "sa2_name"
        print(top10[[name_col, "sa3_name", "wheat_area_ha", "area_share_pct",
                     "rainfall_2026_mm", "hist_median_mm", "pct_of_median",
                     "percentile_rank"]].rename(columns={name_col: "sa2_name"}).to_string(index=False))

        rows_out.append({
            "state": state,
            "total_wheat_area_ha": int(total_area),
            "unweighted_pct_rank": round(unw_pr, 1),
            "area_weighted_pct_rank": round(aw_pr, 1),
            "unweighted_pct_of_median": round(unw_pm, 0),
            "area_weighted_pct_of_median": round(aw_pm, 0),
            "area_share_dry_pct": round(band_agg.loc[band_agg["band"] == "Dry (D1-D3)", "area_share_pct"].sum(), 1),
            "area_share_mid_pct": round(band_agg.loc[band_agg["band"] == "Mid (D4-D7)", "area_share_pct"].sum(), 1),
            "area_share_wet_pct": round(band_agg.loc[band_agg["band"] == "Wet (D8-D10)", "area_share_pct"].sum(), 1),
            "top10_area_share_pct": round(top10_share, 1),
        })

    if not atomic_csv_write(pd.DataFrame(rows_out), OUT_PATH):
        raise SystemExit(f"Failed to write {OUT_PATH}")
    print(f"\n\nWrote {OUT_PATH.relative_to(ROOT)}")

    # SA3-level aggregation: area-weighted pct rank and % of median per SA3
    sa3_rows = []
    for state in sorted(m["state_name"].unique()):
        s = m[m["state_name"] == state].copy()
        total_state = s["wheat_area_ha"].sum()
        if total_state == 0:
            continue
        for sa3_name, sub in s.groupby("sa3_name", dropna=False):
            area = sub["wheat_area_ha"].sum()
            if area == 0:
                continue
            aw_pr = (sub["percentile_rank"] * sub["wheat_area_ha"]).sum() / area
            aw_pm = (sub["pct_of_median"] * sub["wheat_area_ha"]).sum() / area
            sa3_rows.append({
                "state": state,
                "sa3_name": sa3_name,
                "n_sa2": len(sub),
                "wheat_area_ha": int(area),
                "state_area_share_pct": round(area / total_state * 100, 1),
                "area_weighted_pct_rank": round(aw_pr, 1),
                "area_weighted_pct_of_median": round(aw_pm, 0),
            })
    sa3_df = pd.DataFrame(sa3_rows)
    if not atomic_csv_write(sa3_df, OUT_SA3):
        raise SystemExit(f"Failed to write {OUT_SA3}")
    print(f"\nWrote {OUT_SA3.relative_to(ROOT)}")

    print("\n=== SA3-level area-weighted percentile rank per state ===")
    for state in sorted(sa3_df["state"].unique()):
        print(f"\n--- {state} ---")
        sub = sa3_df[sa3_df["state"] == state].sort_values("wheat_area_ha", ascending=False)
        print(sub.drop(columns=["state"]).to_string(index=False))


if __name__ == "__main__":
    main()
