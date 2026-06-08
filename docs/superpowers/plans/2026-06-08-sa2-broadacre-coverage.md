# SA2-Broadacre Station Universe + Concurrent Ingest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive the daily SILO station universe from broadacre-cropping SA2s (default `area_ha >= 5000`), ingest all internal stations with a guaranteed Data Drill gap-fill per zero-station SA2, and run it fast via configurable concurrency — while preserving the legacy active-tier path as a fallback.

**Architecture:** A new pure module `src/common/sa2_coverage.py` derives the SA2 target set, the station universe, the per-SA2 Data Drill gap points, and a reviewable coverage report. A new `src/agents/silo_wrangler/concurrent_ingest.py` orchestrates parallel fetch/process with serialized writes. `run_ingest.py` is rewired to choose coverage mode, use the concurrent orchestrator, inject gap points, and emit a run summary.

**Tech Stack:** Python 3.10, pandas, shapely (already a dependency — see `stations_loader.generate_data_drill_grid`), DuckDB, click, pytest.

**Spec:** `docs/superpowers/specs/2026-06-08-sa2-broadacre-coverage-design.md`

---

## File Structure

**Create:**
- `src/common/sa2_coverage.py` — SA2 area aggregation, target selection, station-universe derivation, polygon index + gap-point resolution, coverage report builder. One responsibility: *turn crop-area data into a coverage plan.*
- `src/agents/silo_wrangler/concurrent_ingest.py` — `StationResult` dataclass + `ingest_concurrently()`. One responsibility: *run a worker over many stations with bounded concurrency and serialized writes.*
- `tests/test_sa2_coverage.py`
- `tests/test_concurrent_ingest.py`

**Modify:**
- `config/silo_sources.yaml` — `coverage:` block + `api.concurrency`.
- `src/agents/silo_wrangler/run_ingest.py` — coverage-mode station loading, concurrent loop, gap injection, run summary, logfile newline fix.
- `scripts/cron_schedule.sh` — daily call → `--coverage-mode sa2_broadacre` (per-SA2 gap-fill is driven by `coverage.sa2_broadacre.enable_data_drill_gaps`, **not** `--hybrid`).
- `CLAUDE.md` — document default daily coverage.

**Conventions to follow:** tests are plain functions importing `from src.…`; run with `python3 -m pytest`. Station IDs are zero-padded to 6 (`str.zfill(6)`). All output CSVs go through `atomic_csv_write` / `append_to_daily_observations`.

---

## Task 1: SA2 area aggregation + target selection

**Files:**
- Create: `src/common/sa2_coverage.py`
- Test: `tests/test_sa2_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sa2_coverage.py
import pandas as pd
import pytest

from src.common.sa2_coverage import load_broadacre_sa2_areas, select_target_sa2s


def _write_crop_csv(tmp_path):
    # Two crop rows for a big SA2, one for a small SA2, and an all-null-area SA2.
    rows = [
        # sa2_code (9-dig), station_sa2_5dig16 (5-dig), sa2_name, state, crop, area_ha
        ("103011060", "11060", "Big Region", "New South Wales", "wheat", "4000"),
        ("103011060", "11060", "Big Region", "New South Wales", "barley", "1500"),
        ("201021007", "21007", "Null Region", "Victoria", "wheat", ""),       # all-null area
        ("201021007", "21007", "Null Region", "Victoria", "canola", ""),
        ("301011099", "11099", "Tiny Region", "Queensland", "oats", "300"),
    ]
    df = pd.DataFrame(rows, columns=[
        "sa2_code", "station_sa2_5dig16", "sa2_name", "state", "crop", "area_ha"])
    p = tmp_path / "crop_context_sa2.csv"
    df.to_csv(p, index=False)
    return p


def test_load_aggregates_area_nan_skipping(tmp_path):
    path = _write_crop_csv(tmp_path)
    areas = load_broadacre_sa2_areas(path)
    by = areas.set_index("sa2_5")["total_area_ha"].to_dict()
    assert by["11060"] == 5500.0           # 4000 + 1500
    assert by["21007"] == 0.0              # all-null -> 0.0, retained (not dropped)
    assert by["11099"] == 300.0
    assert set(areas["sa2_5"]) == {"11060", "21007", "11099"}


def test_select_threshold_zero_is_row_presence(tmp_path):
    areas = load_broadacre_sa2_areas(_write_crop_csv(tmp_path))
    assert select_target_sa2s(areas, threshold_ha=0) == {"11060", "21007", "11099"}


def test_select_threshold_excludes_null_area_and_fringe(tmp_path):
    areas = load_broadacre_sa2_areas(_write_crop_csv(tmp_path))
    # default 5000: only the big SA2 survives; null-area and tiny dropped
    assert select_target_sa2s(areas, threshold_ha=5000) == {"11060"}
    # any >=1 threshold drops the 0.0-area SA2
    assert "21007" not in select_target_sa2s(areas, threshold_ha=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sa2_coverage.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.common.sa2_coverage'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/common/sa2_coverage.py
"""SA2 broadacre coverage derivation.

Turns ABS crop-area data (crop_context_sa2.csv) into a daily station coverage
plan: which SA2s have meaningful broadacre cropping, which BOM stations sit
inside them, which zero-station SA2s need a Data Drill point, and a reviewable
coverage report.

Join key: crop_context_sa2.csv.station_sa2_5dig16 (5-digit 2016 SA2 code)
          <-> wheatbelt_stations.csv.SA2_5DIG16 (loaded as 'sa2_code').
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

CROP_SA2_KEY = "station_sa2_5dig16"   # 5-digit 2016 SA2 code in crop_context_sa2.csv
CROP_SA2_9DIG_KEY = "sa2_code"            # 9-digit 2021/2016 SA2 code (SA2_MAIN16 in geojson)


def _norm_sa2(series: pd.Series) -> pd.Series:
    """Normalise an SA2 code column to a clean integer-like string.

    Handles ints, floats (``11060.0``), and strings uniformly so the crop side
    and station side join. Non-numeric / missing -> empty string.
    """
    num = pd.to_numeric(series, errors="coerce")
    out = num.astype("Int64").astype(str)
    return out.replace("<NA>", "")


def load_broadacre_sa2_areas(crop_path, area_col: str = "area_ha") -> pd.DataFrame:
    """Aggregate broadacre area per SA2 (NaN-skipping sum).

    Returns columns: sa2_5, sa2_name, state, total_area_ha. An SA2 whose every
    crop row has a missing area gets total_area_ha == 0.0 and is RETAINED
    (row-presence inclusion at threshold 0).
    """
    df = pd.read_csv(crop_path, dtype=str)
    df[area_col] = pd.to_numeric(df[area_col], errors="coerce")
    df["sa2_5"] = _norm_sa2(df[CROP_SA2_KEY])
    df = df[df["sa2_5"] != ""]

    grouped = (
        df.groupby("sa2_5")
        .agg(
            total_area_ha=(area_col, lambda s: float(s.dropna().sum())),
            sa2_name=("sa2_name", "first"),
            state=("state", "first"),
        )
        .reset_index()
    )
    logger.info("Loaded broadacre areas for %d SA2s from %s", len(grouped), crop_path)
    return grouped


def select_target_sa2s(areas_df: pd.DataFrame, threshold_ha: float = 5000) -> Set[str]:
    """SA2 codes with total_area_ha >= threshold_ha.

    threshold_ha=0 returns every SA2 present (incl. 0.0-area ones); any value
    >= 1 drops the 0.0-area SA2s.
    """
    return set(areas_df.loc[areas_df["total_area_ha"] >= threshold_ha, "sa2_5"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_sa2_coverage.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/common/sa2_coverage.py tests/test_sa2_coverage.py
git commit -m "feat(coverage): SA2 broadacre area aggregation + target selection"
```

---

## Task 2: Station-universe derivation

**Files:**
- Modify: `src/common/sa2_coverage.py`
- Test: `tests/test_sa2_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_sa2_coverage.py
from src.common.sa2_coverage import derive_station_universe


def _stations_df():
    # Mirrors WheatbeltStationsLoader._stations_df after column rename:
    # station_id (zfilled str), name, sa2_code (the 5-dig SA2), latitude, longitude.
    return pd.DataFrame([
        {"station_id": "008137", "name": "ALPHA", "sa2_code": 11060, "latitude": -31.0, "longitude": 117.0},
        {"station_id": "009999", "name": "BETA",  "sa2_code": 11060, "latitude": -31.5, "longitude": 117.5},
        {"station_id": "055325", "name": "GAMMA", "sa2_code": 99999, "latitude": -31.2, "longitude": 150.0},
    ])


def test_derive_station_universe_filters_to_target_sa2s():
    uni = derive_station_universe({"11060"}, _stations_df())
    assert set(uni["station_id"]) == {"008137", "009999"}   # GAMMA's SA2 not in target
    assert "sa2_5" in uni.columns
    assert set(uni["sa2_5"]) == {"11060"}


def test_derive_station_universe_handles_float_sa2_codes():
    # pandas may load SA2_5DIG16 as float when NaNs present -> 11060.0
    df = _stations_df()
    df["sa2_code"] = df["sa2_code"].astype(float)
    uni = derive_station_universe({"11060"}, df)
    assert set(uni["station_id"]) == {"008137", "009999"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sa2_coverage.py -q`
Expected: FAIL — `ImportError: cannot import name 'derive_station_universe'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/common/sa2_coverage.py
def derive_station_universe(target_sa2s: Set[str], stations_df: pd.DataFrame) -> pd.DataFrame:
    """Select stations whose SA2 (column 'sa2_code', the 5-digit code as loaded
    by WheatbeltStationsLoader) is in target_sa2s. Adds a normalised 'sa2_5'.
    """
    df = stations_df.copy()
    df["sa2_5"] = _norm_sa2(df["sa2_code"])
    selected = df[df["sa2_5"].isin(target_sa2s)].copy()
    logger.info("Derived station universe: %d stations across %d target SA2s",
                len(selected), selected["sa2_5"].nunique())
    return selected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_sa2_coverage.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/common/sa2_coverage.py tests/test_sa2_coverage.py
git commit -m "feat(coverage): derive station universe from target SA2s"
```

---

## Task 3: Coverage report with gap_status classification

**Files:**
- Modify: `src/common/sa2_coverage.py`
- Test: `tests/test_sa2_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_sa2_coverage.py
from src.common.sa2_coverage import build_coverage_report

COVERAGE_COLUMNS = [
    "sa2_code", "sa2_name", "state", "broadacre_area_ha",
    "n_stations", "station_ids", "gap_status",
]


def test_coverage_report_classifies_gap_status():
    areas = pd.DataFrame([
        {"sa2_5": "11060", "sa2_name": "Big",   "state": "NSW", "total_area_ha": 5500.0},
        {"sa2_5": "21007", "sa2_name": "GapDD",  "state": "VIC", "total_area_ha": 9000.0},
        {"sa2_5": "31000", "sa2_name": "GapNone","state": "QLD", "total_area_ha": 7000.0},
    ])
    universe = pd.DataFrame([
        {"station_id": "008137", "sa2_5": "11060"},
        {"station_id": "009999", "sa2_5": "11060"},
    ])
    target = {"11060", "21007", "31000"}
    dd_covered = {"21007"}    # 21007 got a Data Drill point; 31000 did not

    rep = build_coverage_report(target, areas, universe, dd_covered_sa2s=dd_covered)
    assert list(rep.columns) == COVERAGE_COLUMNS
    by = rep.set_index("sa2_code")
    assert by.loc["11060", "gap_status"] == "internal_bom"
    assert by.loc["11060", "n_stations"] == 2
    assert by.loc["11060", "station_ids"] == "008137;009999"
    assert by.loc["21007", "gap_status"] == "data_drill_gapfill"
    assert by.loc["31000", "gap_status"] == "unresolved_gap"
    assert by.loc["31000", "n_stations"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sa2_coverage.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_coverage_report'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/common/sa2_coverage.py
COVERAGE_COLUMNS = [
    "sa2_code", "sa2_name", "state", "broadacre_area_ha",
    "n_stations", "station_ids", "gap_status",
]


def build_coverage_report(
    target_sa2s: Set[str],
    areas_df: pd.DataFrame,
    station_universe: pd.DataFrame,
    dd_covered_sa2s: Optional[Set[str]] = None,
) -> pd.DataFrame:
    """One row per included SA2 with a controlled gap_status:
    internal_bom | data_drill_gapfill | unresolved_gap.
    """
    dd_covered_sa2s = dd_covered_sa2s or set()
    area_lookup = areas_df.set_index("sa2_5")
    ids_by_sa2: Dict[str, List[str]] = {}
    if not station_universe.empty:
        for sa2, grp in station_universe.groupby("sa2_5"):
            ids_by_sa2[sa2] = sorted(grp["station_id"].astype(str))

    rows = []
    for sa2 in sorted(target_sa2s):
        ids = ids_by_sa2.get(sa2, [])
        n = len(ids)
        if n > 0:
            status = "internal_bom"
        elif sa2 in dd_covered_sa2s:
            status = "data_drill_gapfill"
        else:
            status = "unresolved_gap"
        meta = area_lookup.loc[sa2] if sa2 in area_lookup.index else None
        rows.append({
            "sa2_code": sa2,
            "sa2_name": "" if meta is None else meta["sa2_name"],
            "state": "" if meta is None else meta["state"],
            "broadacre_area_ha": 0.0 if meta is None else round(float(meta["total_area_ha"]), 2),
            "n_stations": n,
            "station_ids": ";".join(ids),
            "gap_status": status,
        })
    return pd.DataFrame(rows, columns=COVERAGE_COLUMNS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_sa2_coverage.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/common/sa2_coverage.py tests/test_sa2_coverage.py
git commit -m "feat(coverage): coverage report with gap_status classification"
```

---

## Task 4: Deterministic per-SA2 Data Drill gap points

Addresses the reviewer's named risk: the SA2→polygon lookup must be **deterministic by SA2 code**. We map the 5-digit SA2 to its 9-digit `SA2_MAIN16` via the crop table, index the GeoJSON by that code, and use `representative_point()` (always inside the polygon, deterministic for a fixed geometry).

**Files:**
- Modify: `src/common/sa2_coverage.py`
- Test: `tests/test_sa2_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_sa2_coverage.py
from src.common.sa2_coverage import build_sa2_polygon_index, resolve_gap_points


def _geo_crop(tmp_path):
    # crop table mapping 5-dig <-> 9-dig
    crop = pd.DataFrame([
        {"sa2_code": "201021007", "station_sa2_5dig16": "21007", "sa2_name": "GapDD",
         "state": "Victoria", "crop": "wheat", "area_ha": "9000"},
        {"sa2_code": "301031000", "station_sa2_5dig16": "31000", "sa2_name": "GapNone",
         "state": "Queensland", "crop": "oats", "area_ha": "7000"},
    ])
    crop_path = tmp_path / "crop.csv"
    crop.to_csv(crop_path, index=False)

    # GeoJSON: a unit square per SA2, keyed by 9-digit SA2_MAIN16.
    def square(cx, cy):
        return {"type": "Polygon", "coordinates": [[
            [cx, cy], [cx + 1, cy], [cx + 1, cy + 1], [cx, cy + 1], [cx, cy]]]}
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"SA2_MAIN16": 201021007},
         "geometry": square(117.0, -32.0)},
        {"type": "Feature", "properties": {"SA2_MAIN16": 301031000},
         "geometry": square(140.0, -34.0)},
    ]}
    import json
    geo_path = tmp_path / "regions.geojson"
    geo_path.write_text(json.dumps(gj))
    return crop_path, geo_path


def test_polygon_index_keyed_by_5dig(tmp_path):
    crop_path, geo_path = _geo_crop(tmp_path)
    crop = pd.read_csv(crop_path, dtype=str)
    idx = build_sa2_polygon_index(crop, geo_path)
    assert set(idx.keys()) == {"21007", "31000"}


def test_resolve_gap_points_injects_inside_polygon(tmp_path):
    crop_path, geo_path = _geo_crop(tmp_path)
    crop = pd.read_csv(crop_path, dtype=str)
    idx = build_sa2_polygon_index(crop, geo_path)

    points = resolve_gap_points({"21007", "31000"}, idx)
    assert set(points.keys()) == {"21007", "31000"}
    # representative point of the 117..118 / -32..-31 square is inside it
    lat, lon = points["21007"]
    assert 117.0 <= lon <= 118.0 and -32.0 <= lat <= -31.0
    # deterministic: same call -> same point
    assert resolve_gap_points({"21007"}, idx)["21007"] == points["21007"]


def test_resolve_gap_points_reuses_existing_grid_point(tmp_path):
    crop_path, geo_path = _geo_crop(tmp_path)
    crop = pd.read_csv(crop_path, dtype=str)
    idx = build_sa2_polygon_index(crop, geo_path)
    existing = [(-31.5, 117.5)]   # inside the 21007 square
    points = resolve_gap_points({"21007"}, idx, existing_points=existing)
    assert points["21007"] == (-31.5, 117.5)


def test_resolve_gap_points_skips_sa2_without_polygon(tmp_path):
    crop_path, geo_path = _geo_crop(tmp_path)
    crop = pd.read_csv(crop_path, dtype=str)
    idx = build_sa2_polygon_index(crop, geo_path)
    points = resolve_gap_points({"99999"}, idx)   # no polygon -> unresolved
    assert "99999" not in points
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sa2_coverage.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_sa2_polygon_index'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/common/sa2_coverage.py
def build_sa2_polygon_index(crop_df: pd.DataFrame, geojson_path) -> Dict[str, "object"]:
    """Map 5-digit SA2 code -> shapely polygon.

    Deterministic by code: the 5-digit code is mapped to its 9-digit SA2_MAIN16
    via the crop table, and the GeoJSON is indexed by SA2_MAIN16.
    """
    import json
    from shapely.geometry import shape

    codes = crop_df[[CROP_SA2_9DIG_KEY, CROP_SA2_KEY]].copy()
    codes["nine"] = _norm_sa2(codes[CROP_SA2_9DIG_KEY])
    codes["five"] = _norm_sa2(codes[CROP_SA2_KEY])
    nine_to_five = dict(zip(codes["nine"], codes["five"]))

    with open(geojson_path) as f:
        gj = json.load(f)

    index: Dict[str, object] = {}
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        nine = _norm_sa2(pd.Series([props.get("SA2_MAIN16")])).iloc[0]
        five = nine_to_five.get(nine)
        if five and feat.get("geometry"):
            index[five] = shape(feat["geometry"])
    logger.info("Built SA2 polygon index for %d SA2s", len(index))
    return index


def resolve_gap_points(
    zero_station_sa2s: Set[str],
    polygon_index: Dict[str, "object"],
    existing_points: Optional[List[Tuple[float, float]]] = None,
) -> Dict[str, Tuple[float, float]]:
    """For each zero-station SA2 with a known polygon, return a (lat, lon) point
    inside it. Reuses an existing grid point if one already falls inside;
    otherwise injects the polygon's representative point. SA2s with no polygon
    are omitted (caller marks them unresolved_gap).
    """
    from shapely.geometry import Point

    existing_points = existing_points or []
    result: Dict[str, Tuple[float, float]] = {}
    for sa2 in sorted(zero_station_sa2s):
        poly = polygon_index.get(sa2)
        if poly is None:
            continue
        reused = None
        for lat, lon in existing_points:           # Point(x=lon, y=lat)
            if poly.contains(Point(lon, lat)):
                reused = (round(float(lat), 4), round(float(lon), 4))
                break
        if reused is not None:
            result[sa2] = reused
        else:
            rp = poly.representative_point()
            result[sa2] = (round(float(rp.y), 4), round(float(rp.x), 4))
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_sa2_coverage.py -q`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/common/sa2_coverage.py tests/test_sa2_coverage.py
git commit -m "feat(coverage): deterministic per-SA2 Data Drill gap points"
```

---

## Task 5: Concurrent ingest orchestrator

**Files:**
- Create: `src/agents/silo_wrangler/concurrent_ingest.py`
- Test: `tests/test_concurrent_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_concurrent_ingest.py
import pandas as pd

from src.agents.silo_wrangler.concurrent_ingest import StationResult, ingest_concurrently


def test_failure_isolation_and_summary():
    items = [("001", "A"), ("002", "B"), ("003", "C"), ("004", "D")]

    def worker(sid, name):
        if sid == "002":
            raise RuntimeError("boom")          # exception must be isolated
        if sid == "003":
            return StationResult(sid, "no_data")
        return StationResult(sid, "success", records=pd.DataFrame({"x": [1, 2]}))  # 2 rows each

    written = []

    def writer(result):
        written.append(result.station_id)
        return True

    summary = ingest_concurrently(items, worker, writer, concurrency=3)

    assert summary["requested"] == 4
    assert summary["succeeded"] == 2
    assert summary["failed"] == 1                # 002 raised
    assert summary["skipped_no_data"] == 1       # 003
    assert summary["records_processed"] == 4     # 2 successful writes x 2 rows
    assert sorted(written) == ["001", "004"]     # only successes written
    assert "elapsed_s" in summary
    assert sorted(summary["failed_ids"]) == ["002"]


def test_concurrency_one_matches_concurrency_n():
    items = [(f"{i:03d}", "x") for i in range(10)]

    def worker(sid, name):
        return StationResult(sid, "success", records=pd.DataFrame({"x": [1]}))

    def writer(result):
        return True

    s1 = ingest_concurrently(items, worker, writer, concurrency=1)
    sn = ingest_concurrently(items, worker, writer, concurrency=5)
    assert s1["succeeded"] == sn["succeeded"] == 10


def test_writer_failure_counts_as_failed():
    items = [("001", "A")]

    def worker(sid, name):
        return StationResult(sid, "success", records=pd.DataFrame({"x": [1]}))

    def writer(result):
        return False        # write failed

    summary = ingest_concurrently(items, worker, writer, concurrency=2)
    assert summary["succeeded"] == 0
    assert summary["failed"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_concurrent_ingest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.silo_wrangler.concurrent_ingest'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/agents/silo_wrangler/concurrent_ingest.py
"""Bounded-concurrency station ingest with serialized writes.

The network-bound worker (fetch -> process -> quality) runs across threads; the
writer (atomic CSV append + DuckDB upsert) is invoked only on the main thread,
from the as_completed loop, so shared-state writes are never concurrent.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class StationResult:
    station_id: str
    status: str                                  # success | no_data | error | excluded
    records: Optional[pd.DataFrame] = None
    detail: str = ""


def ingest_concurrently(
    items: List[Tuple[str, str]],
    worker: Callable[[str, str], StationResult],
    writer: Callable[[StationResult], bool],
    concurrency: int = 10,
) -> dict:
    """Run `worker` over (station_id, name) items with up to `concurrency`
    threads; call `writer` (main thread) for each success. Returns a summary.

    `worker` must be thread-safe and must NOT raise for ordinary failures — but
    if it does raise, the exception is caught and counted as a failure so one
    bad station never aborts the batch.
    """
    requested = len(items)
    succeeded = skipped = failed = 0
    records_processed = 0
    failed_ids: List[str] = []
    skipped_ids: List[str] = []
    start = time.time()

    def _run(item: Tuple[str, str]) -> StationResult:
        sid, name = item
        try:
            return worker(sid, name)
        except Exception as exc:                 # isolation: never abort the batch
            logger.error("Worker error for station %s: %s", sid, exc, exc_info=True)
            return StationResult(sid, "error", detail=str(exc))

    max_workers = max(1, int(concurrency))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run, it): it for it in items}
        for fut in as_completed(futures):
            result = fut.result()                # _run never raises
            if result.status == "success" and result.records is not None:
                if writer(result):               # serialized on main thread
                    succeeded += 1
                    records_processed += len(result.records)
                else:
                    failed += 1
                    failed_ids.append(result.station_id)
            elif result.status == "no_data":
                skipped += 1
                skipped_ids.append(result.station_id)
            else:
                failed += 1
                failed_ids.append(result.station_id)

    elapsed = round(time.time() - start, 2)
    summary = {
        "requested": requested,
        "succeeded": succeeded,
        "failed": failed,
        "skipped_no_data": skipped,
        "records_processed": records_processed,
        "elapsed_s": elapsed,
        "failed_ids": failed_ids,
        "skipped_ids": skipped_ids,
    }
    logger.info(
        "Concurrent ingest: requested=%d succeeded=%d failed=%d skipped_no_data=%d elapsed=%ss",
        requested, succeeded, failed, skipped, elapsed,
    )
    return summary
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_concurrent_ingest.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/agents/silo_wrangler/concurrent_ingest.py tests/test_concurrent_ingest.py
git commit -m "feat(ingest): bounded-concurrency orchestrator with serialized writes"
```

---

## Task 6: Config — coverage block + concurrency

**Files:**
- Modify: `config/silo_sources.yaml`
- Test: `tests/test_sa2_coverage.py`

- [ ] **Step 1: Write the failing test** (cron-coverage guard + config parses)

```python
# append to tests/test_sa2_coverage.py
from pathlib import Path
from src.common.config_loader import load_config

_ROOT = Path(__file__).resolve().parents[1]


def test_shipped_config_defaults_to_sa2_broadacre():
    cfg = load_config(str(_ROOT / "config" / "silo_sources.yaml"))
    cov = cfg["coverage"]
    assert cov["mode"] == "sa2_broadacre"
    assert cov["sa2_broadacre"]["min_broadacre_area_ha"] == 5000
    assert cov["sa2_broadacre"]["area_column"] == "area_ha"
    assert cov["sa2_broadacre"]["enable_data_drill_gaps"] is True
    assert cfg["api"]["concurrency"] >= 1


def test_default_config_derives_many_stations():
    # Guard against silent regression to the 16-station active tier.
    cfg = load_config(str(_ROOT / "config" / "silo_sources.yaml"))
    cov = cfg["coverage"]["sa2_broadacre"]
    areas = load_broadacre_sa2_areas(_ROOT / cov["crop_context_file"], cov["area_column"])
    target = select_target_sa2s(areas, cov["min_broadacre_area_ha"])
    assert len(target) > 100        # ~159 SA2s at 5000 ha; far more than the 16 active tier
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sa2_coverage.py -k config_or_derives -q`
(Use: `python3 -m pytest "tests/test_sa2_coverage.py::test_shipped_config_defaults_to_sa2_broadacre" "tests/test_sa2_coverage.py::test_default_config_derives_many_stations" -q`)
Expected: FAIL — `KeyError: 'coverage'`

- [ ] **Step 3: Add config block**

Add to `config/silo_sources.yaml` immediately after the `api:` block (keep existing `api` keys; add `concurrency`):

```yaml
# Append this key inside the existing api: block
api:
  # ... existing base_url/username/rate_limit_seconds/timeout_seconds/max_retries ...
  concurrency: 10               # parallel station requests.
                                # concurrency: 1 = legacy sequential execution mechanics
                                #   (one request at a time). NOTE: daily SCOPE is set by
                                #   coverage.mode below — legacy 16-station daily behaviour
                                #   is coverage.mode: active_tier, not concurrency: 1.

# Coverage selection: how the daily station universe is chosen.
coverage:
  mode: "sa2_broadacre"        # sa2_broadacre | active_tier  (active_tier = legacy fallback)
  sa2_broadacre:
    crop_context_file: "data/meta/crop_context_sa2.csv"
    area_column: "area_ha"
    min_broadacre_area_ha: 5000   # 0 = any cropping; 5000 = meaningful (default); 10000+ = core regions
    enable_data_drill_gaps: true
    coverage_report: "data/meta/sa2_coverage_report.csv"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest "tests/test_sa2_coverage.py::test_shipped_config_defaults_to_sa2_broadacre" "tests/test_sa2_coverage.py::test_default_config_derives_many_stations" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/silo_sources.yaml tests/test_sa2_coverage.py
git commit -m "feat(config): add sa2_broadacre coverage block + api.concurrency"
```

---

## Task 7: Coverage-mode station loading in run_ingest

Extract station selection into a testable helper that branches on coverage mode, then call it from the click command.

**Files:**
- Modify: `src/agents/silo_wrangler/run_ingest.py`
- Test: `tests/test_sa2_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_sa2_coverage.py
from src.agents.silo_wrangler.run_ingest import load_coverage_stations


def test_active_tier_mode_uses_config_tiers():
    cfg = load_config(str(_ROOT / "config" / "silo_sources.yaml"))
    stations = load_coverage_stations(cfg, coverage_mode="active_tier", tiers="active")
    # active tier is the small hand-picked set
    assert 5 <= len(stations) <= 40
    assert all(isinstance(k, str) for k in stations)


def test_sa2_broadacre_mode_returns_large_universe():
    cfg = load_config(str(_ROOT / "config" / "silo_sources.yaml"))
    stations = load_coverage_stations(cfg, coverage_mode="sa2_broadacre", tiers="active")
    assert len(stations) > 500       # ~1,293 stations at the 5000 ha default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest "tests/test_sa2_coverage.py::test_active_tier_mode_uses_config_tiers" "tests/test_sa2_coverage.py::test_sa2_broadacre_mode_returns_large_universe" -q`
Expected: FAIL — `ImportError: cannot import name 'load_coverage_stations'`

- [ ] **Step 3: Add helper to run_ingest.py**

Add near the top of `src/agents/silo_wrangler/run_ingest.py` (after imports, before the click command). Reuse the existing `load_stations_by_tier` for the active-tier branch:

```python
from pathlib import Path as _Path
from src.common.sa2_coverage import (
    load_broadacre_sa2_areas, select_target_sa2s, derive_station_universe,
)
from src.common.stations_loader import WheatbeltStationsLoader


def load_coverage_stations(silo_config, coverage_mode=None, tiers="active"):
    """Return {station_id: station_name} for the configured coverage mode.

    coverage_mode: 'sa2_broadacre' | 'active_tier'. Defaults to
    silo_config['coverage']['mode'] (or 'active_tier' if absent).
    """
    cov = silo_config.get("coverage", {})
    mode = coverage_mode or cov.get("mode", "active_tier")

    if mode == "active_tier":
        return load_stations_by_tier(silo_config, tiers)

    if mode == "sa2_broadacre":
        sb = cov["sa2_broadacre"]
        areas = load_broadacre_sa2_areas(sb["crop_context_file"], sb.get("area_column", "area_ha"))
        target = select_target_sa2s(areas, sb.get("min_broadacre_area_ha", 5000))
        loader = WheatbeltStationsLoader(silo_config["bom_dataset"]["file_path"])
        universe = derive_station_universe(target, loader._stations_df)
        logger.info("sa2_broadacre coverage: %d SA2s -> %d stations",
                    len(target), len(universe))
        return dict(zip(universe["station_id"], universe["name"]))

    raise ValueError(f"Unknown coverage mode: {mode}")
```

Add a CLI option to the click command (alongside the existing options):

```python
@click.option('--coverage-mode', default=None,
              help='Override coverage.mode: sa2_broadacre | active_tier')
```

And add `coverage_mode` to the function signature. In the station-loading `else` branch (currently `# Load stations by tier from config`), replace:

```python
        else:
            # Load stations by tier from config
            station_list = load_stations_by_tier(silo_config, tiers)
            silo_config['stations'] = station_list
            logger.info(f"Using {tiers} tier stations: {len(station_list)} stations loaded")
```

with:

```python
        else:
            station_list = load_coverage_stations(silo_config, coverage_mode, tiers)
            silo_config['stations'] = station_list
            mode = coverage_mode or silo_config.get('coverage', {}).get('mode', 'active_tier')
            logger.info(f"Coverage mode '{mode}': {len(station_list)} stations loaded")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest "tests/test_sa2_coverage.py::test_active_tier_mode_uses_config_tiers" "tests/test_sa2_coverage.py::test_sa2_broadacre_mode_returns_large_universe" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agents/silo_wrangler/run_ingest.py tests/test_sa2_coverage.py
git commit -m "feat(ingest): coverage-mode station loading (sa2_broadacre|active_tier)"
```

---

## Task 8: Wire the concurrent orchestrator into run_ingest

Replace the sequential per-station `for` loop (current `run_ingest.py:153-266`) with worker/writer closures driven by `ingest_concurrently`.

**Files:**
- Modify: `src/agents/silo_wrangler/run_ingest.py`

- [ ] **Step 1: Add import**

At the top of `run_ingest.py`:

```python
from src.agents.silo_wrangler.concurrent_ingest import StationResult, ingest_concurrently
```

- [ ] **Step 2: Replace the per-station loop**

Replace the block from `successful_stations = []` through the end of the `for station_id, station_name in silo_config['stations'].items():` loop (the body that fetches, processes, quality-checks, and writes — current lines ~149-266) with:

```python
        concurrency = silo_config.get('api', {}).get('concurrency', 1)

        def _worker(station_id, station_name):
            # Determine date range (same logic as before)
            if target_date:
                _d = target_date.replace('-', '')
                raw_data = api_client.get_daily_data(station_id, _d, _d)
            elif days:
                raw_data = api_client.get_rolling_window_data(station_id, days)
            elif silo_config['collection']['mode'] == 'rolling_window':
                raw_data = api_client.get_rolling_window_data(
                    station_id, silo_config['collection']['rolling_days'])
            else:
                raw_data = api_client.get_yesterday_data(station_id)

            if raw_data is None or raw_data.empty:
                return StationResult(station_id, "no_data")

            processed = data_processor.process_station_data(raw_data, station_id)
            if processed.empty:
                return StationResult(station_id, "error", detail="processing_failed")

            assessment = quality_checker.assess_data_quality(processed, station_id)
            auto_exclude = silo_config.get('quality', {}).get('auto_exclude_poor_stations', False)
            min_conf = silo_config.get('quality', {}).get('min_confidence_threshold', 0.3)
            if auto_exclude and not include_poor and assessment['confidence_score'] < min_conf:
                return StationResult(station_id, "error",
                                     detail=f"auto_excluded_low_confidence_{assessment['confidence_score']:.2f}")

            filtered = quality_checker.filter_by_quality(processed)
            return StationResult(station_id, "success", records=filtered)

        def _writer(result):
            if dry_run:
                return True
            ok = data_processor.append_to_daily_observations(result.records)
            if ok:
                duckdb_df = result.records.rename(columns={
                    'min_temperature': 'min_temp',
                    'max_temperature': 'max_temp',
                    'min_temperature_quality': 'min_temp_quality',
                    'max_temperature_quality': 'max_temp_quality',
                    'timestamp_processed': 'ingested_at',
                })
                duckdb_cols = ['station_id', 'date', 'min_temp', 'max_temp', 'rainfall',
                               'min_temp_quality', 'max_temp_quality', 'rainfall_quality', 'ingested_at']
                storage.upsert_observations(duckdb_df[[c for c in duckdb_cols if c in duckdb_df.columns]])
            return ok

        summary = ingest_concurrently(
            list(silo_config['stations'].items()), _worker, _writer, concurrency=concurrency)
        total_records = summary['records_processed']   # rows written, not station count
```

Note: the old `successful_stations` / `failed_stations` lists and their per-iteration appends are removed; downstream `run_metadata` now uses `summary` (Task 9 updates that).

**`--hybrid` decision (single model):** the pre-existing `--hybrid` broad-grid block (current `run_ingest.py:268-365`) is left in place **but is gated by its existing `if hybrid:` flag and is NOT enabled for daily SA2 coverage.** Daily per-SA2 gap-fill is driven solely by `coverage.sa2_broadacre.enable_data_drill_gaps` (Task 9) — a targeted, per-zero-station-SA2 path, independent of `--hybrid`. A user may still pass `--hybrid` explicitly for the broad regional grid, but the cron job does not.

- [ ] **Step 3: Run the existing CLI smoke + coverage tests**

Run: `python3 -m pytest tests/test_cli_smoke.py tests/test_concurrent_ingest.py -q`
Expected: PASS (no import/wiring errors). If `test_cli_smoke.py` invokes `--help`, the new option appears.

- [ ] **Step 4: Manual dry-run sanity (small, no writes)**

Run: `python3 src/agents/silo_wrangler/run_ingest.py --coverage-mode active_tier --date 2026-06-01 --dry-run -v 2>&1 | tail -20`
Expected: log shows "Concurrent ingest: requested=… succeeded=… elapsed=…s"; no exceptions.

- [ ] **Step 5: Commit**

```bash
git add src/agents/silo_wrangler/run_ingest.py
git commit -m "refactor(ingest): drive station loop via concurrent orchestrator"
```

---

## Task 9: Run summary, coverage report, gap injection, logfile fix

**Files:**
- Modify: `src/agents/silo_wrangler/run_ingest.py`

- [ ] **Step 1: Emit the coverage report + targeted gap points (sa2_broadacre mode)**

After stations are loaded and before/around the existing `--hybrid` block, when coverage mode is `sa2_broadacre`, compute zero-station SA2s and resolve gap points. Add this helper near `load_coverage_stations`:

```python
from src.common.sa2_coverage import (
    build_sa2_polygon_index, resolve_gap_points, build_coverage_report,
)
from src.common.file_utils import atomic_csv_write
import pandas as _pd


def emit_coverage_plan(silo_config):
    """For sa2_broadacre mode: return (gap_points, write_report_fn, zero_station_sa2s).

    gap_points maps sa2_5 -> (lat, lon) for resolvable zero-station included SA2s.
    write_report_fn(dd_covered_sa2s) writes the coverage report CSV.
    zero_station_sa2s is the full set of included SA2s with no internal station
    (a superset of gap_points keys; the difference are SA2s with no polygon).
    """
    sb = silo_config['coverage']['sa2_broadacre']
    areas = load_broadacre_sa2_areas(sb['crop_context_file'], sb.get('area_column', 'area_ha'))
    target = select_target_sa2s(areas, sb.get('min_broadacre_area_ha', 5000))
    loader = WheatbeltStationsLoader(silo_config['bom_dataset']['file_path'])
    universe = derive_station_universe(target, loader._stations_df)

    covered = set(universe['sa2_5'])
    zero_station = target - covered

    gap_points = {}
    if sb.get('enable_data_drill_gaps', True) and zero_station:
        crop_df = _pd.read_csv(sb['crop_context_file'], dtype=str)
        geojson = silo_config.get('data_drill', {}).get('wheatbelt_geojson')
        idx = build_sa2_polygon_index(crop_df, geojson)
        gap_points = resolve_gap_points(zero_station, idx)

    def write_report(dd_covered_sa2s):
        report = build_coverage_report(target, areas, universe, dd_covered_sa2s=dd_covered_sa2s)
        atomic_csv_write(report, sb['coverage_report'], backup=False)
        unresolved = report[report['gap_status'] == 'unresolved_gap']
        for _, r in unresolved.iterrows():
            logger.warning("UNRESOLVED COVERAGE GAP: SA2 %s (%s) has no station and no Data Drill point",
                           r['sa2_code'], r['sa2_name'])
        logger.info("Coverage report -> %s | internal_bom=%d data_drill_gapfill=%d unresolved_gap=%d",
                    sb['coverage_report'],
                    int((report['gap_status'] == 'internal_bom').sum()),
                    int((report['gap_status'] == 'data_drill_gapfill').sum()),
                    int((report['gap_status'] == 'unresolved_gap').sum()))
        return report

    return gap_points, write_report, zero_station
```

In the click command, after `silo_config['stations']` is set and `summary` computed, when mode is `sa2_broadacre`, ingest the resolved gap points through the existing Data Drill path and record which SA2s succeeded:

```python
        coverage_mode_eff = coverage_mode or silo_config.get('coverage', {}).get('mode', 'active_tier')
        dd_covered_sa2s = set()
        if coverage_mode_eff == 'sa2_broadacre':
            gap_points, write_report, zero_station_sa2s = emit_coverage_plan(silo_config)
            if dry_run:
                # Dry-run: ingest nothing and write NO canonical report. data_drill_gapfill
                # means "successfully ingested", which a dry run cannot establish, and
                # --dry-run is documented as writing no output files. Log a preview only.
                resolvable = set(gap_points)
                logger.info(
                    "[DRY RUN] sa2_broadacre plan: zero_station_sa2s=%d "
                    "resolvable_via_data_drill=%d unresolvable=%d (no report written)",
                    len(zero_station_sa2s), len(resolvable),
                    len(zero_station_sa2s - resolvable))
            else:
                for sa2_5, (lat, lon) in gap_points.items():
                    try:
                        raw = api_client.get_data_drill_data(
                            lat, lon, *_gap_date_range(target_date, days, silo_config))
                        if raw is None or raw.empty:
                            continue
                        proc = data_processor.process_station_data(raw, f"DD_{lat:.2f}_{lon:.2f}")
                        if proc.empty:
                            continue
                        filt = quality_checker.filter_by_quality(proc)
                        # SAME write path as station successes: CSV append + DuckDB upsert.
                        if _writer(StationResult(f"DD_{lat:.2f}_{lon:.2f}", "success", records=filt)):
                            dd_covered_sa2s.add(sa2_5)
                    except Exception as exc:
                        logger.error("Gap-fill Data Drill failed for SA2 %s (%s,%s): %s",
                                     sa2_5, lat, lon, exc)
                write_report(dd_covered_sa2s)
```

The gap-fill reuses the Task 8 `_writer` closure, so Data Drill points are written to
**both** `obs_daily.csv` and DuckDB exactly like station successes (no divergent write
path). `_writer` and `StationResult` are already in scope from Task 8.

Add the small date-range helper (factor the existing inline date logic):

```python
def _gap_date_range(target_date, days, silo_config):
    from datetime import datetime as _dt, timedelta as _td
    if target_date:
        d = target_date.replace('-', '')
        return d, d
    if days:
        return ((_dt.now() - _td(days=days)).strftime('%Y%m%d'), _dt.now().strftime('%Y%m%d'))
    if silo_config['collection']['mode'] == 'rolling_window':
        r = silo_config['collection']['rolling_days']
        return ((_dt.now() - _td(days=r)).strftime('%Y%m%d'), _dt.now().strftime('%Y%m%d'))
    y = (_dt.now() - _td(days=1)).strftime('%Y%m%d')
    return y, y
```

- [ ] **Step 2: Update run_metadata + summary logging and fix the logfile newline**

Replace the `run_metadata.update({...})` block that referenced `successful_stations`/`failed_stations` with a `summary`-based version:

```python
        run_metadata.update({
            'end_time': datetime.now().isoformat(),
            'summary': summary,
            'coverage_mode': coverage_mode_eff,
            'data_drill_gapfill_sa2s': sorted(dd_covered_sa2s),
            'total_records_processed': total_records,
        })

        logger.info("SILO Wrangler ingestion completed:")
        logger.info("  requested=%d succeeded=%d failed=%d skipped_no_data=%d elapsed=%ss",
                    summary['requested'], summary['succeeded'], summary['failed'],
                    summary['skipped_no_data'], summary['elapsed_s'])
```

Fix the JSONL newline bug at the former `run_ingest.py:442` (`log_run_results`): change `f.write(json.dumps(run_metadata) + '\\n')` to a real newline:

```python
            f.write(json.dumps(run_metadata) + "\n")
```

- [ ] **Step 3: Run tests + dry-run sanity**

Run: `python3 -m pytest tests/test_cli_smoke.py tests/test_sa2_coverage.py tests/test_concurrent_ingest.py -q`
Expected: PASS

Run: `python3 src/agents/silo_wrangler/run_ingest.py --coverage-mode sa2_broadacre --date 2026-06-01 --dry-run -v 2>&1 | tail -25`
Expected: a `[DRY RUN] sa2_broadacre plan: zero_station_sa2s=… resolvable_via_data_drill=… unresolvable=… (no report written)` line and the run summary line. **No** `data/meta/sa2_coverage_report.csv` is written (dry-run writes no output). Confirm absence: `test ! -f data/meta/sa2_coverage_report.csv && echo "no report (correct)"` (if the file pre-existed from a prior live run, note its mtime is unchanged).

- [ ] **Step 4: Inspect the coverage report (live run — network-heavy, ~5–8 min)**

The coverage report is only written by a real (non-dry-run) ingest, because `data_drill_gapfill` means *successfully ingested*. Run one live date to produce it:

Run: `python3 src/agents/silo_wrangler/run_ingest.py --coverage-mode sa2_broadacre --date 2026-06-01 -v 2>&1 | tail -30`
Then: `head -3 data/meta/sa2_coverage_report.csv && echo "rows: $(wc -l < data/meta/sa2_coverage_report.csv)" && cut -d, -f7 data/meta/sa2_coverage_report.csv | sort | uniq -c`
Expected: ~160 rows; `gap_status` counts with most `internal_bom`, a few `data_drill_gapfill`, ideally zero `unresolved_gap`. The run-summary log line shows `requested≈1293 succeeded=… elapsed=…s`. (This hits the live SILO API for the full universe — expect several minutes.)

- [ ] **Step 5: Commit**

```bash
git add src/agents/silo_wrangler/run_ingest.py
git commit -m "feat(ingest): coverage report, per-SA2 gap-fill, run summary, jsonl newline fix"
```

---

## Task 10: Cron + docs — make daily scope obvious

**Files:**
- Modify: `scripts/cron_schedule.sh`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the cron daily call**

Note on the interpreter: keep whatever the existing cron line already uses (`python`) so this task doesn't change the production interpreter. (This dev environment only has `python3`, which is why the plan's *verification* commands use `python3`; the cron's runtime may activate a venv where `python` resolves.)

In `scripts/cron_schedule.sh`, change the Step 1 ingest line from:

```bash
python src/agents/silo_wrangler/run_ingest.py --date "$TARGET_DATE"
```

to (explicit coverage + gap-fill; the comment states the volume change):

```bash
# Daily coverage = broadacre-cropping SA2s (~1,293 stations at the 5,000 ha default),
# up from the legacy 16 active-tier stations. Fallback: --coverage-mode active_tier.
python src/agents/silo_wrangler/run_ingest.py --date "$TARGET_DATE" --coverage-mode sa2_broadacre
```

- [ ] **Step 2: Document in CLAUDE.md**

Under the "SILO Wrangler" / data section of `wheatbelt_rainfall_analyser/CLAUDE.md`, add:

```markdown
### Daily coverage (default)

The daily ingest pulls the **SA2-broadacre station universe** — every BOM station inside an
ABS SA2 with total broadacre `area_ha >= 5000` (config: `coverage.mode: sa2_broadacre`,
`min_broadacre_area_ha`). That is ~1,293 stations, up from the legacy 16 hand-picked
`active`-tier stations. Zero-station included SA2s are gap-filled with a targeted SILO Data
Drill point; the result is summarised in `data/meta/sa2_coverage_report.csv` with
`gap_status` ∈ {`internal_bom`, `data_drill_gapfill`, `unresolved_gap`}.

Speed comes from `api.concurrency` (default 10). `concurrency: 1` = legacy sequential
execution mechanics. To restore the legacy small daily run, use
`--coverage-mode active_tier` (or set `coverage.mode: active_tier`).
```

- [ ] **Step 3: Verify cron script still parses**

Run: `bash -n scripts/cron_schedule.sh && echo OK`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add scripts/cron_schedule.sh CLAUDE.md
git commit -m "docs: switch daily cron to sa2_broadacre coverage + document scope"
```

---

## Task 11: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (all pre-existing tests + the new `test_sa2_coverage.py` and `test_concurrent_ingest.py`). Investigate any failure before proceeding.

- [ ] **Step 2: Lint the new/changed Python**

Run: `flake8 src/common/sa2_coverage.py src/agents/silo_wrangler/concurrent_ingest.py src/agents/silo_wrangler/run_ingest.py`
Expected: no errors (match existing repo style; fix any reported).

- [ ] **Step 3: Confirm only intended files changed**

Run: `git status --short`
Expected: working tree shows only this feature's files committed on the branch; the untracked items from session start (`.venv/`, `data/external`, drill scripts, figures, backfill logs, the W21 edit) remain **unstaged and untouched**. Do not `git add` them.

- [ ] **Step 4: Final commit (if any lint fixes were made)**

```bash
git add -p   # stage only intended hunks
git commit -m "chore: lint fixes for sa2_broadacre coverage"
```

---

## Notes on residual risks (carried from review)

- **Deterministic polygon lookup (Task 4):** handled by mapping 5-dig→9-dig via the crop
  table and indexing the GeoJSON by `SA2_MAIN16`, with `representative_point()` for a stable
  interior point. If a target SA2's 9-digit code is absent from the GeoJSON, it surfaces as
  `unresolved_gap` (logged at WARNING) rather than failing silently.
- **DuckDB single-connection writes:** all writes are serialized on the main thread (Task 5
  design), so the single DuckDB connection and atomic CSV appends are never hit concurrently.
- **Politeness to SILO:** `api.rate_limit_seconds` (0.2) still applies per request inside each
  worker thread; combined with `concurrency: 10` this is ~50 req/s worst case. Lower
  `concurrency` if SILO pushes back.
