"""SA2-level drill within each state — surface anomalies and NSW north/south split.

For each state and for each 2026 window (Jan-Apr cumulative, Jan-May MTD cumulative):
  - Rank each grain-belt SA2 by 2026 rainfall vs its own 2005-2025 climatology
  - Compute SA2-level percentile rank and decile-bucket counts
  - List driest 8 and wettest 8 SA2s per state
  - For NSW: split into Northern (north of ~ -33.0 lat) and Southern bands

Outputs:
  - data/features/sa2_state_drill_2026.csv  (per-SA2 ranks + buckets)
  - Stdout: per-state driest/wettest tables and NSW split summary
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
import json

from src.common.file_utils import atomic_csv_write
from src.rainfall.analytics import decile_rank, percentile_rank

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS_PATH = ROOT / "data/meta/crop_context_sa2.csv"
HISTORY_PATH = ROOT / "data/features/sa2_monthly_rainfall_history_national.csv"
MTD_PATH = ROOT / "data/features/sa2_2026_05_mtd.csv"
GEOJSON_PATH = ROOT / "data/meta/SA2_ABS_Regions.geojson"
OUT_PATH = ROOT / "data/features/sa2_state_drill_2026.csv"


def load_universe() -> pd.DataFrame:
    df = pd.read_csv(WEIGHTS_PATH, low_memory=False)
    return df[df["crop"] == "wheat"][["sa2_code", "state", "sa2_name"]].rename(columns={"state": "state_name"})


def sa2_centroid_lat(geojson_path: Path, codes: set[int]) -> dict[int, float]:
    """Approximate centroid latitude per SA2 from GeoJSON (bbox mean as proxy)."""
    with open(geojson_path) as f:
        gj = json.load(f)
    out = {}
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        code = None
        for key in ("SA2_CODE16", "SA2_CODE21", "SA2_MAIN16", "sa2_code"):
            if key in props:
                try:
                    code = int(props[key])
                except Exception:
                    pass
                break
        if code is None or code not in codes:
            continue
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [])
        lats = []
        def walk(c):
            if isinstance(c, (int, float)):
                return
            if len(c) == 2 and all(isinstance(x, (int, float)) for x in c):
                lats.append(c[1])
                return
            for sub in c:
                walk(sub)
        walk(coords)
        if lats:
            out[code] = (min(lats) + max(lats)) / 2.0
    return out


def compute_window_ranks(history: pd.DataFrame, universe: pd.DataFrame, months: list[int], mtd_add: pd.DataFrame | None, label: str, mtd_day: int | None = None) -> pd.DataFrame:
    """For each SA2 in universe, compute 2026 rainfall and percentile rank.

    When May (month 5) is not yet in the history file for 2026, the partial
    month-to-date May is added to the 2026 cumulative AND the historical May
    portion of the baseline is scaled by ``mtd_day / 31`` — so a partial 2026
    May is never ranked against full historical Mays. When May 2026 is already
    present in history, the full-vs-full comparison is preserved unchanged.
    """
    rows = []
    h = history[history["month"].isin(months)]
    target_has_may = bool(
        5 in months
        and not h[(h["year"] == 2026) & (h["month"] == 5)].empty
    )
    add_partial_may = mtd_add is not None and 5 in months and not target_has_may

    if add_partial_may:
        if mtd_day is None:
            raise ValueError(
                f"[{label}] mtd_day is required to scale the historical May "
                "baseline when adding partial-May MTD to the 2026 cumulative."
            )
        scale = mtd_day / 31.0
        # Historical baseline (excluding 2026): a year is eligible only if EVERY
        # month in the window is present — both the full Jan-Apr component and
        # the May component — so an incomplete year never enters the baseline as
        # a partial total. May is scaled to the same through-day fraction the
        # 2026 partial May carries (never partial-vs-full May).
        hist_h = h[h["year"] != 2026].copy()
        hist_h.loc[hist_h["month"] == 5, "rainfall_mm"] *= scale
        hist_grp = hist_h.groupby(["sa2_code", "year"])
        hist_totals = hist_grp["rainfall_mm"].sum()
        month_counts = hist_grp["month"].nunique()
        hist_totals = hist_totals[month_counts == len(months)].reset_index()

        # 2026 target only: Jan-Apr from history + partial May from the MTD
        # frame. Do NOT zero-fill a missing MTD SA2 — a missing MTD row is
        # missing data, not 0 mm; skip it.
        target = h[h["year"] == 2026].groupby(["sa2_code", "year"])["rainfall_mm"].sum().reset_index()
        mtd_2026 = mtd_add[mtd_add["year"] == 2026][["sa2_code", "rainfall_mm"]].rename(columns={"rainfall_mm": "mtd_add"})
        addable = target.merge(mtd_2026, on="sa2_code", how="left")
        missing = addable[addable["mtd_add"].isna()]
        if not missing.empty:
            print(
                f"[{label}] WARNING: skipping {len(missing)} SA2(s) with no May "
                f"MTD row (kept missing, not zero-filled): "
                f"{sorted(int(c) for c in missing['sa2_code'])[:10]}"
            )
        addable = addable.dropna(subset=["mtd_add"]).copy()
        addable["rainfall_mm"] = addable["rainfall_mm"] + addable["mtd_add"]
        addable = addable.drop(columns=["mtd_add"])

        by_sa2_year = pd.concat([hist_totals, addable], ignore_index=True)
    else:
        by_sa2_year = h.groupby(["sa2_code", "year"])["rainfall_mm"].sum().reset_index()

    for code in universe["sa2_code"].unique():
        sub = by_sa2_year[by_sa2_year["sa2_code"] == code]
        hist = sub[(sub["year"] >= 2005) & (sub["year"] <= 2025)]["rainfall_mm"].values
        cur_row = sub[sub["year"] == 2026]
        if cur_row.empty or len(hist) < 10:
            continue
        cur = float(cur_row["rainfall_mm"].iloc[0])
        rows.append({
            "sa2_code": int(code),
            "window": label,
            "rainfall_2026_mm": round(cur, 1),
            "hist_median_mm": round(float(np.median(hist)), 1),
            "hist_p10_mm": round(float(np.percentile(hist, 10)), 1),
            "hist_p90_mm": round(float(np.percentile(hist, 90)), 1),
            "pct_of_median": round(cur / max(float(np.median(hist)), 0.1) * 100.0, 0),
            "percentile_rank": round(percentile_rank(hist, cur), 0),
            "decile": decile_rank(hist, cur),
            "n_hist_years": int(len(hist)),
        })
    return pd.DataFrame(rows)


def main() -> None:
    universe = load_universe()
    history = pd.read_csv(HISTORY_PATH, low_memory=False)[["year", "month", "sa2_code", "rainfall_mm"]]
    mtd_full = pd.read_csv(MTD_PATH, low_memory=False)
    mtd_day = int(mtd_full["partial_month_through_day"].dropna().max())
    mtd = mtd_full[["year", "month", "sa2_code", "rainfall_mm"]]

    jan_apr = compute_window_ranks(history, universe, [1, 2, 3, 4], None, "Jan-Apr_cum")
    jan_may = compute_window_ranks(history, universe, [1, 2, 3, 4, 5], mtd, f"Jan-May_d{mtd_day}_cum", mtd_day=mtd_day)

    drill = pd.concat([jan_apr, jan_may], ignore_index=True)
    drill = drill.merge(universe, on="sa2_code", how="left")
    # Canonical rank-based decile (decile_rank), NOT a percentile-floor cut, so
    # reported deciles never disagree with the house deciles contract.
    drill["decile_bucket"] = pd.Categorical(
        drill["decile"].map(lambda d: f"D{int(d)}" if pd.notna(d) else None),
        categories=[f"D{i}" for i in range(1, 11)],
        ordered=True,
    )

    # NSW lat split
    codes = set(int(c) for c in universe["sa2_code"].unique())
    print(f"Loading SA2 centroids from GeoJSON for {len(codes)} grain SA2s...")
    centroids = sa2_centroid_lat(GEOJSON_PATH, codes)
    print(f"  Resolved centroids for {len(centroids)} / {len(codes)} SA2s")

    drill["centroid_lat"] = drill["sa2_code"].map(centroids)
    drill["nsw_zone"] = np.where(
        (drill["state_name"] == "New South Wales") & (drill["centroid_lat"] > -33.0),
        "NSW_North",
        np.where(
            (drill["state_name"] == "New South Wales") & (drill["centroid_lat"] <= -33.0),
            "NSW_South",
            "",
        ),
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not atomic_csv_write(drill, OUT_PATH):
        raise SystemExit(f"Failed to write {OUT_PATH}")

    pd.set_option("display.width", 180)
    pd.set_option("display.max_columns", 30)

    current_window = f"Jan-May_d{mtd_day}_cum"
    print(f"\n=== Per-state SA2 anomalies ({current_window}) ===")
    for state in sorted(drill["state_name"].unique()):
        sub = drill[(drill["state_name"] == state) & (drill["window"] == current_window)].copy()
        sub = sub.sort_values("percentile_rank")
        print(f"\n--- {state} (n={len(sub)} grain SA2s) ---")
        print("Decile bucket counts:")
        print(sub["decile_bucket"].value_counts().sort_index().to_string())
        print("\nDriest 8:")
        print(sub.head(8)[["sa2_name", "rainfall_2026_mm", "hist_median_mm", "pct_of_median", "percentile_rank"]].to_string(index=False))
        print("\nWettest 8:")
        print(sub.tail(8)[["sa2_name", "rainfall_2026_mm", "hist_median_mm", "pct_of_median", "percentile_rank"]].to_string(index=False))

    print(f"\n\n=== NSW North vs South split ({current_window}) ===")
    nsw = drill[(drill["state_name"] == "New South Wales") & (drill["window"] == current_window)]
    for zone in ("NSW_North", "NSW_South"):
        sub = nsw[nsw["nsw_zone"] == zone]
        if sub.empty:
            continue
        median_pct_rank = sub["percentile_rank"].median()
        mean_pct_of_med = sub["pct_of_median"].mean()
        print(f"\n{zone}: {len(sub)} SA2s")
        print(f"  Median percentile rank: {median_pct_rank:.0f}")
        print(f"  Mean % of historical median: {mean_pct_of_med:.0f}%")
        print(f"  Decile bucket counts:")
        print(sub["decile_bucket"].value_counts().sort_index().to_string())

    print(f"\nWrote {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
