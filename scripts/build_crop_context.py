#!/usr/bin/env python3
"""Build SA2-level crop context from ABS Agricultural Census data.

Reads baseline-year area/production/yield observations from ag_census.db and
produces data/meta/crop_context_sa2.csv with one row per SA2 per crop.
Only SA2s represented in the station metadata are included.
"""

import argparse
import csv
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ABS_DB = Path("/home/roddyb/projects/ABS Census Data/ag_census.db")
DEFAULT_CONFIG = REPO_ROOT / "config" / "crop_context.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "meta" / "crop_context_sa2.csv"
DEFAULT_WA_UNIVERSE = REPO_ROOT / "data" / "meta" / "wa_wheatbelt_sa2_universe_2021.csv"

OUTPUT_COLS = [
    "sa2_code",
    "station_sa2_5dig16",
    "sa2_name",
    "state",
    "financial_year",
    "crop",
    "area_ha",
    "production_t",
    "yield_t_ha",
    "area_share",
    "area_rse",
    "production_rse",
    "yield_rse",
    "source_dataset",
    "source_commodity_area",
    "source_commodity_production",
    "source_commodity_yield",
    "boundary_status",
    "notes",
]

STATE_NAME_TO_CODE = {
    "New South Wales": "1",
    "Victoria": "2",
    "Queensland": "3",
    "South Australia": "4",
    "Western Australia": "5",
    "Tasmania": "6",
    "Northern Territory": "7",
    "Australian Capital Territory": "8",
}


def parse_args():
    p = argparse.ArgumentParser(
        description="Build SA2 crop context CSV from ABS Agricultural Census"
    )
    p.add_argument("--abs-db", type=Path, default=DEFAULT_ABS_DB)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print summary without writing output file",
    )
    return p.parse_args()


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_station_sa2s(stations_path: Path) -> dict:
    """Return {sa2_5dig: {sa2_name, state}} for all unique SA2s in stations."""
    result = {}
    with open(stations_path) as f:
        for row in csv.DictReader(f):
            code = row.get("SA2_5DIG16", "").strip()
            if code:
                result[code] = {
                    "sa2_name": row.get("SA2_NAME16", "").strip(),
                    "state": row.get("STE_NAME16", "").strip(),
                }
    return result


def load_geojson_sa2s(geojson_path: Path) -> dict:
    """Return {SA2_5DIG16: {sa2_name, state}} for all SA2s in GeoJSON boundary file.

    This is the authoritative SA2 universe — not filtered by station metadata.
    """
    with open(geojson_path) as f:
        gj = json.load(f)
    result = {}
    for feat in gj["features"]:
        p = feat["properties"]
        code = p["SA2_5DIG16"]
        result[code] = {
            "sa2_name": p["SA2_NAME16"],
            "state": p["STE_NAME16"],
        }
    return result


def load_geojson_mapping(geojson_path: Path) -> dict:
    """Return {SA2_5DIG16: SA2_MAIN16} from GeoJSON boundary file."""
    with open(geojson_path) as f:
        gj = json.load(f)
    return {
        feat["properties"]["SA2_5DIG16"]: feat["properties"]["SA2_MAIN16"]
        for feat in gj["features"]
    }


def load_wa_wheatbelt_universe(path: Path) -> tuple[dict, dict]:
    """Load the QGIS 28-region WA wheatbelt SA2 universe.

    Returns:
        sa2s_dict: {sa2_5dig: {sa2_name, state}} — universe keyed by 5-digit compat code
        sa2_main_map: {sa2_5dig: SA2_CODE21} — 9-digit code for ABS lookup
    """
    sa2s: dict = {}
    sa2_map: dict = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            code21 = row["SA2_CODE21"].strip()
            name21 = row["SA2_NAME21"].strip()
            # Derive 5-digit compatibility code: state prefix + last 4 digits
            sa2_5dig = code21[0] + code21[-4:]
            sa2s[sa2_5dig] = {"sa2_name": name21, "state": "Western Australia"}
            sa2_map[sa2_5dig] = code21
    return sa2s, sa2_map


def fallback_main_code(conn: sqlite3.Connection, sa2_name: str, state_name: str) -> Optional[str]:
    """Look up SA2_MAIN16 by label+state prefix when GeoJSON mapping is missing."""
    state_code = STATE_NAME_TO_CODE.get(state_name)
    if not state_code:
        return None
    cur = conn.cursor()
    cur.execute(
        "SELECT region_code FROM regions "
        "WHERE region_label=? AND region_code LIKE ? AND LENGTH(region_code)=9",
        (sa2_name, f"{state_code}%"),
    )
    rows = cur.fetchall()
    if len(rows) == 1:
        return rows[0][0]
    return None


def get_year_id(conn: sqlite3.Connection, financial_year: str) -> int:
    cur = conn.cursor()
    cur.execute(
        "SELECT year_id FROM census_years WHERE financial_year=?", (financial_year,)
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Financial year {financial_year!r} not found in census_years")
    return row[0]


def batch_query_observations(
    conn: sqlite3.Connection,
    year_id: int,
    region_codes: list,
    commodity_codes: list,
) -> dict:
    """Return {(region_code, commodity_code): (estimate, rse)} for all matches."""
    if not region_codes or not commodity_codes:
        return {}
    ph_r = ",".join(["?"] * len(region_codes))
    ph_c = ",".join(["?"] * len(commodity_codes))
    cur = conn.cursor()
    cur.execute(
        f"SELECT region_code, commodity_code, estimate, rse "
        f"FROM observations "
        f"WHERE year_id=? AND region_code IN ({ph_r}) AND commodity_code IN ({ph_c})",
        [year_id] + list(region_codes) + list(commodity_codes),
    )
    return {(r[0], r[1]): (r[2], r[3]) for r in cur.fetchall()}


def build_rows(
    geojson_sa2s: dict,
    geojson_map: dict,
    abs_conn: sqlite3.Connection,
    cfg: dict,
) -> tuple[list[dict], dict]:
    """Build output rows and collect validation stats.

    geojson_sa2s drives the SA2 universe — {sa2_5dig: {sa2_name, state}}.
    Station metadata is not consulted here; the GeoJSON boundary is authoritative.
    """
    baseline_year = cfg["baseline_year"]
    crops = cfg["crops"]
    year_id = get_year_id(abs_conn, baseline_year)
    source_dataset = f"ABS Agricultural Census {baseline_year}"

    sa2_5digs = sorted(geojson_sa2s.keys())

    # Resolve each station SA2 to a 9-digit MAIN code
    sa2_to_main = {}
    boundary_status = {}
    unmatched_sa2s = []

    for code_5 in sa2_5digs:
        if code_5 in geojson_map:
            sa2_to_main[code_5] = geojson_map[code_5]
            boundary_status[code_5] = "matched"
        else:
            info = geojson_sa2s[code_5]
            main = fallback_main_code(abs_conn, info["sa2_name"], info["state"])
            if main:
                sa2_to_main[code_5] = main
                boundary_status[code_5] = "matched_via_label"
            else:
                boundary_status[code_5] = "unmatched"
                unmatched_sa2s.append(code_5)

    matched_5digs = [c for c in sa2_5digs if c in sa2_to_main]
    matched_mains = [sa2_to_main[c] for c in matched_5digs]

    # Collect all commodity codes
    all_codes = []
    for crop_def in crops.values():
        all_codes += [
            crop_def["area_code"],
            crop_def["production_code"],
            crop_def["yield_code"],
        ]

    obs = batch_query_observations(abs_conn, year_id, matched_mains, all_codes)

    # Compute area_share per SA2, keyed by 9-digit main code.
    sa2_total_area: dict[str, Optional[float]] = {}
    for code_5 in matched_5digs:
        main = sa2_to_main[code_5]
        total = None
        for crop_def in crops.values():
            est, _ = obs.get((main, crop_def["area_code"]), (None, None))
            if est is not None:
                total = (total or 0.0) + est
        sa2_total_area[main] = total

    rows = []
    null_counts: dict[str, int] = {"area_ha": 0, "production_t": 0, "yield_t_ha": 0}

    for code_5 in sa2_5digs:
        info = geojson_sa2s[code_5]
        bstatus = boundary_status[code_5]

        for crop_key, crop_def in crops.items():
            row_notes = []
            area_ha = production_t = yield_t_ha = None
            area_rse = production_rse = yield_rse = ""

            if code_5 in sa2_to_main:
                main = sa2_to_main[code_5]

                area_est, area_r = obs.get((main, crop_def["area_code"]), (None, ""))
                prod_est, prod_r = obs.get((main, crop_def["production_code"]), (None, ""))
                yield_est, yield_r = obs.get((main, crop_def["yield_code"]), (None, ""))

                area_ha = area_est
                production_t = prod_est
                yield_t_ha = yield_est
                area_rse = area_r if area_r is not None else ""
                production_rse = prod_r if prod_r is not None else ""
                yield_rse = yield_r if yield_r is not None else ""

                if area_ha is None:
                    null_counts["area_ha"] += 1
                    row_notes.append("area suppressed")
                if production_t is None:
                    null_counts["production_t"] += 1
                    row_notes.append("production suppressed")
                if yield_t_ha is None:
                    null_counts["yield_t_ha"] += 1
                    row_notes.append("yield suppressed")
            else:
                row_notes.append("SA2 not in GeoJSON boundary file; no ABS lookup")

            # area_share — keyed by resolved 9-digit code
            main_for_share = sa2_to_main.get(code_5)
            total_area = sa2_total_area.get(main_for_share) if main_for_share else None
            if area_ha is not None and total_area:
                area_share = area_ha / total_area
            else:
                area_share = None

            rows.append(
                {
                    "sa2_code": sa2_to_main.get(code_5, ""),
                    "station_sa2_5dig16": code_5,
                    "sa2_name": info["sa2_name"],
                    "state": info["state"],
                    "financial_year": baseline_year,
                    "crop": crop_key,
                    "area_ha": area_ha,
                    "production_t": production_t,
                    "yield_t_ha": yield_t_ha,
                    "area_share": area_share,
                    "area_rse": area_rse,
                    "production_rse": production_rse,
                    "yield_rse": yield_rse,
                    "source_dataset": source_dataset,
                    "source_commodity_area": crop_def["area_code"],
                    "source_commodity_production": crop_def["production_code"],
                    "source_commodity_yield": crop_def["yield_code"],
                    "boundary_status": bstatus,
                    "notes": "; ".join(row_notes),
                }
            )

    stats = {
        "n_geojson_sa2s": len(sa2_5digs),
        "n_mapped_to_abs": len(matched_5digs),
        "unmatched_sa2s": unmatched_sa2s,
        "n_rows": len(rows),
        "null_counts": null_counts,
    }
    return rows, stats


def top_crop_by_area_per_state(rows: list[dict]) -> dict:
    """Return {state: (crop_key, total_area_ha)} for the highest-area crop per state."""
    state_crop_area: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        if row["area_ha"] is not None:
            state_crop_area[row["state"]][row["crop"]] += row["area_ha"]
    result = {}
    for state, crop_areas in sorted(state_crop_area.items()):
        best_crop = max(crop_areas, key=crop_areas.__getitem__)
        result[state] = (best_crop, crop_areas[best_crop])
    return result


def query_wa_wheat_nonnull_count(conn: sqlite3.Connection, year_id: int) -> int:
    """Return count of WA SA2s with non-null wheat area in the ABS census."""
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(DISTINCT r.region_code) "
        "FROM regions r "
        "JOIN observations o ON o.region_code = r.region_code "
        "WHERE o.year_id=? AND r.region_code LIKE '5%' "
        "  AND LENGTH(r.region_code)=9 "
        "  AND o.commodity_code='AGCEREAL_AHAWHT_F' "
        "  AND o.estimate IS NOT NULL",
        (year_id,),
    )
    return cur.fetchone()[0]


def query_wa_wheat_nonnull_regions(conn: sqlite3.Connection, year_id: int) -> dict:
    """Return {region_code: region_label} for all WA SA2s with non-null wheat area."""
    cur = conn.cursor()
    cur.execute(
        "SELECT r.region_code, r.region_label "
        "FROM regions r "
        "JOIN observations o ON o.region_code = r.region_code "
        "WHERE o.year_id=? AND r.region_code LIKE '5%' "
        "  AND LENGTH(r.region_code)=9 "
        "  AND o.commodity_code='AGCEREAL_AHAWHT_F' "
        "  AND o.estimate IS NOT NULL",
        (year_id,),
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def compute_wa_diagnostics(
    wa_sa2s: dict,
    wa_map: dict,
    rows: list[dict],
    abs_conn: sqlite3.Connection,
    year_id: int,
) -> dict:
    """Compute WA-specific diagnostics for --dry-run output."""
    qgis_main_codes = set(wa_map.values())

    wa_wheat_rows = [
        r for r in rows
        if r["state"] == "Western Australia" and r["crop"] == "wheat"
    ]
    qgis_nonnull = [r for r in wa_wheat_rows if r["area_ha"] is not None]
    qgis_null = [(r["sa2_code"], r["sa2_name"]) for r in wa_wheat_rows if r["area_ha"] is None]

    abs_wa_regions = query_wa_wheat_nonnull_regions(abs_conn, year_id)
    excluded = {code: label for code, label in abs_wa_regions.items() if code not in qgis_main_codes}

    return {
        "qgis_count": len(wa_sa2s),
        "qgis_nonnull_wheat_count": len(qgis_nonnull),
        "abs_nonnull_count": len(abs_wa_regions),
        "abs_excluded": excluded,
        "qgis_null_regions": qgis_null,
    }


def print_summary(
    rows: list[dict],
    stats: dict,
    wa_wheat_abs_count: Optional[int] = None,
    wa_diag: Optional[dict] = None,
) -> None:
    print("\n--- Validation Summary ---")

    if wa_diag:
        print("\nWA Universe (QGIS 28-region):")
        print(f"  WA QGIS universe:                     {wa_diag['qgis_count']} SA2s")
        print(f"  WA QGIS with non-null ABS wheat area: {wa_diag['qgis_nonnull_wheat_count']}")
        print(f"  ABS WA wheat non-null total:          {wa_diag['abs_nonnull_count']}")
        excl = wa_diag["abs_excluded"]
        print(f"  ABS non-null regions excluded by QGIS ({len(excl)}):")
        for code, label in sorted(excl.items()):
            print(f"    {code}  {label}")
        null_rgns = wa_diag["qgis_null_regions"]
        print(f"  QGIS regions with null wheat area ({len(null_rgns)}):")
        for code, name in sorted(null_rgns):
            print(f"    {code}  {name}")

    print(f"\nTotal universe SA2s: {stats['n_geojson_sa2s']}")
    if wa_wheat_abs_count is not None and wa_diag is None:
        print(f"ABS WA wheat non-null SA2s:    {wa_wheat_abs_count}  (universe is GeoJSON clip, not this)")
    print(f"Mapped to ABS:                 {stats['n_mapped_to_abs']}")
    if stats["unmatched_sa2s"]:
        print(f"Unmatched SA2s ({len(stats['unmatched_sa2s'])}): {stats['unmatched_sa2s']}")
    else:
        print("Unmatched SA2s:                0")
    print(f"Rows written:                  {stats['n_rows']}")
    print("\nNull/suppressed counts by metric:")
    for metric, count in stats["null_counts"].items():
        print(f"  {metric:<16} {count}")
    print("\nTop crop by area per state:")
    for state, (crop, total) in top_crop_by_area_per_state(rows).items():
        print(f"  {state:<25} {crop:<10} {total:,.0f} ha")
    print()


def write_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()

    if not args.abs_db.exists():
        print(f"ERROR: ABS database not found: {args.abs_db}", file=sys.stderr)
        return 1
    if not args.config.exists():
        print(f"ERROR: Config not found: {args.config}", file=sys.stderr)
        return 1

    geojson_path = REPO_ROOT / "data" / "meta" / "SA2_ABS_Regions.geojson"
    wa_universe_path = DEFAULT_WA_UNIVERSE

    if not wa_universe_path.exists():
        print(f"ERROR: WA universe file not found: {wa_universe_path}", file=sys.stderr)
        return 1

    cfg = load_config(args.config)

    # WA: authoritative universe from QGIS 28-region list (2021 ASGS codes)
    wa_sa2s, wa_map = load_wa_wheatbelt_universe(wa_universe_path)

    # Non-WA: universe from GeoJSON wheat boundary (2016 ASGS codes)
    geojson_sa2s_all = load_geojson_sa2s(geojson_path)
    geojson_map_all = load_geojson_mapping(geojson_path)
    non_wa_sa2s = {k: v for k, v in geojson_sa2s_all.items() if v["state"] != "Western Australia"}
    non_wa_map = {k: geojson_map_all[k] for k in non_wa_sa2s if k in geojson_map_all}

    # Combined universe: WA from QGIS, all other states from GeoJSON
    universe_sa2s = {**non_wa_sa2s, **wa_sa2s}
    universe_map = {**non_wa_map, **wa_map}

    abs_conn = sqlite3.connect(args.abs_db)
    try:
        year_id = get_year_id(abs_conn, cfg["baseline_year"])
        rows, stats = build_rows(universe_sa2s, universe_map, abs_conn, cfg)
        wa_diag = compute_wa_diagnostics(wa_sa2s, wa_map, rows, abs_conn, year_id)
    finally:
        abs_conn.close()

    print_summary(rows, stats, wa_diag=wa_diag)

    if args.dry_run:
        print("Dry run — output file not written.")
        return 0

    write_csv(rows, args.output)
    print(f"Written: {args.output} ({stats['n_rows']} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
