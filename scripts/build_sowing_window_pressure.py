#!/usr/bin/env python
"""Build the sowing_window_area_pressure.csv contract (swp-1).

Orchestrates the Phase 2 v1 evidence pipeline:
  load windows + region_reference gate
  -> load SA2 breaks (all years) and roll up to BEN Agri SD
  -> build per-SD historical break series + current-season SD breaks
  -> derive directional pressure rows (at_risk only in v1; no hectares; no neutral)
  -> write a stable latest CSV + a dated archive snapshot (rainfall-handoff pattern).

WA-only. All semantic choices (R2/R3 aggregation, coverage/history confidence
downgrades, full-envelope wheat windows) live in the imported modules.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.sowing.crosswalk import load_sa2_breaks, rollup_breaks_to_sd  # noqa: E402
from src.sowing.evidence import generate_pressure_rows, write_pressure_csv  # noqa: E402
from src.sowing.region_ref import sd_region_codes  # noqa: E402
from src.sowing.windows import load_sowing_windows  # noqa: E402

DEFAULTS = {
    "features": "data/features/rainfall_features_sa2_season.csv",
    "concordance": "data/meta/sa2_2021_to_sd_2011_concordance_wa.csv",
    "broadacre": "data/meta/sa2_coverage_report.csv",
    "windows": "config/sowing_windows_wa.csv",
    "region_reference": "data/meta/region_reference.csv",
    "out_dir": "data/sowing_pressure",
}


def build_pressure_rows(
    *,
    features: str,
    concordance: str,
    broadacre: str,
    windows: str,
    region_reference: str,
    generated_at: str,
    rainfall_run_id: str,
    season_year: Optional[int] = None,
):
    """Load inputs, roll up to SD, and derive pressure rows for one season."""
    valid_sds = sd_region_codes(region_reference, state="WA")
    win = load_sowing_windows(windows, valid_sd_regions=valid_sds)

    recs = load_sa2_breaks(features, concordance, broadacre)
    all_sd = rollup_breaks_to_sd(recs)
    if not all_sd:
        return []

    years = sorted({s.season_year for s in all_sd})
    if season_year is None:
        season_year = years[-1]

    current = [s for s in all_sd if s.season_year == season_year]
    history_by_sd: Dict[str, List[float]] = {}
    for s in all_sd:
        if s.season_year < season_year:
            history_by_sd.setdefault(s.sd_region, []).append(s.break_doy)

    return generate_pressure_rows(
        current, win, history_by_sd,
        generated_at=generated_at, rainfall_run_id=rainfall_run_id,
    )


def write_outputs(rows, out_dir: str, generated_at: str):
    """Write the stable latest CSV + a dated archive snapshot; return both paths."""
    out = Path(out_dir)
    latest = out / "sowing_window_area_pressure.csv"
    archive = out / f"sowing_window_area_pressure_{generated_at}.csv"
    write_pressure_csv(rows, latest)
    write_pressure_csv(rows, archive)
    return latest, archive


def run(
    *,
    generated_at: Optional[str] = None,
    rainfall_run_id: Optional[str] = None,
    season_year: Optional[int] = None,
    out_dir: str = DEFAULTS["out_dir"],
    **path_overrides,
):
    """Full build: returns (rows, latest_path, archive_path)."""
    generated_at = generated_at or date.today().isoformat()
    rainfall_run_id = rainfall_run_id or "rainfall_features_sa2_season"
    paths = {k: DEFAULTS[k] for k in
             ("features", "concordance", "broadacre", "windows", "region_reference")}
    paths.update({k: v for k, v in path_overrides.items() if v is not None})

    rows = build_pressure_rows(
        generated_at=generated_at, rainfall_run_id=rainfall_run_id,
        season_year=season_year, **paths,
    )
    latest, archive = write_outputs(rows, out_dir, generated_at)
    return rows, latest, archive


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("features", "concordance", "broadacre", "windows", "region_reference"):
        ap.add_argument(f"--{key.replace('_', '-')}", default=DEFAULTS[key])
    ap.add_argument("--out-dir", default=DEFAULTS["out_dir"])
    ap.add_argument("--generated-at", default=None, help="ISO date; default today")
    ap.add_argument("--rainfall-run-id", default=None)
    ap.add_argument("--season-year", type=int, default=None)
    args = ap.parse_args(argv)

    rows, latest, archive = run(
        features=args.features, concordance=args.concordance, broadacre=args.broadacre,
        windows=args.windows, region_reference=args.region_reference,
        out_dir=args.out_dir, generated_at=args.generated_at,
        rainfall_run_id=args.rainfall_run_id, season_year=args.season_year,
    )
    print(f"wrote {len(rows)} pressure rows -> {latest} and {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
