#!/usr/bin/env python
"""Per-SA2 daily-observation freshness report — decision-grade gate input.

Why this exists: the swp-1 sowing-pressure snapshot emits at_risk rows only,
so its content cannot distinguish "no pressure" from "no data". This report
is the companion coverage artifact named by the June 2026 house-round spec:
for every WA cropping SA2 it states the latest daily observation date and a
freshness status against a required cutoff. The decision-grade gate reads
THIS file, never the snapshot content.

Run:
  .venv/bin/python scripts/build_sa2_obs_freshness_report.py --cutoff 2026-06-08

Exit code: 0 if every SA2 is current to the cutoff, 1 otherwise.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULTS = {
    "db": "data/weather.duckdb",
    "coverage": "data/meta/sa2_coverage_report.csv",
    "out": "data/meta/sa2_obs_freshness_report.csv",
}

FIELDS = ["sa2_code", "sa2_name", "state", "n_stations", "max_obs_date",
          "days_behind_cutoff", "status"]

# sa2_coverage_report.csv uses full state name "Western Australia"
WA_STATE_VALUES = {"WA", "Western Australia"}


def station_max_dates(db_path: str) -> dict:
    """{station_id: max observation date} from weather_observations."""
    con = duckdb.connect(db_path, read_only=True)
    try:
        rows = con.execute(
            "select station_id, max(date) from weather_observations group by station_id"
        ).fetchall()
    finally:
        con.close()
    out = {}
    for sid, d in rows:
        if d is None:
            continue
        out[str(sid)] = d.date() if isinstance(d, datetime) else d
    return out


def load_cropping_sa2s(coverage_path: str) -> list:
    """sa2_coverage_report.csv rows restricted to WA cropping SA2s."""
    with open(coverage_path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    return [r for r in rows if r.get("state") in WA_STATE_VALUES]


def freshness_rows(sa2s, max_dates, cutoff: date) -> list:
    """One report row per SA2: newest obs across its stations vs cutoff."""
    out = []
    for r in sa2s:
        stations = [s for s in (r.get("station_ids") or "").split(";") if s]
        dates = [max_dates[s] for s in stations if s in max_dates]
        latest = max(dates) if dates else None
        if latest is None:
            status, behind = "no_data", None
        elif latest >= cutoff:
            status, behind = "current", 0
        else:
            status, behind = "stale", (cutoff - latest).days
        out.append({
            "sa2_code": r["sa2_code"],
            "sa2_name": r["sa2_name"],
            "state": r["state"],
            "n_stations": len(stations),
            "max_obs_date": latest.isoformat() if latest else "",
            "days_behind_cutoff": "" if behind is None else behind,
            "status": status,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cutoff", required=True, help="required coverage date, YYYY-MM-DD")
    ap.add_argument("--db", default=str(REPO_ROOT / DEFAULTS["db"]))
    ap.add_argument("--coverage", default=str(REPO_ROOT / DEFAULTS["coverage"]))
    ap.add_argument("--out", default=str(REPO_ROOT / DEFAULTS["out"]))
    args = ap.parse_args()

    cutoff = date.fromisoformat(args.cutoff)
    sa2s = load_cropping_sa2s(args.coverage)
    rows = freshness_rows(sa2s, station_max_dates(args.db), cutoff)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    n_current = sum(1 for r in rows if r["status"] == "current")
    verdict = "PASS" if n and n_current == n else "FAIL"
    print(f"wrote {args.out}")
    print(f"freshness: {n_current}/{n} WA cropping SA2s current to {cutoff}")
    print(f"decision_grade_coverage={verdict}")
    for r in rows:
        if r["status"] != "current":
            print(f"  {r['status']:8s} {r['sa2_code']} {r['sa2_name']} "
                  f"max_obs={r['max_obs_date'] or '-'}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
