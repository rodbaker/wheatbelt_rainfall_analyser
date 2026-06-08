# SA2-Broadacre Station Universe + Concurrent Ingest — Design Spec

**Date:** 2026-06-08
**Status:** Approved for planning
**Author:** Rod Baker (with Claude)

---

## 1. Problem & Goal

The automated daily SILO ingest (`scripts/cron_schedule.sh`) currently pulls only the
**16 hand-picked `active`-tier stations** from `config/silo_sources.yaml`. Meanwhile the
rainfall analysis operates at **ABS SA2 resolution** across the national broadacre
wheatbelt. There is a large, undocumented gap between the stations ingested daily and
the SA2 regions the analysis claims to cover.

**Goal:** Derive the daily station universe from the SA2 regions where broadacre cropping
is actually conducted, ingest **complete** rainfall coverage for those SA2s, and make the
(now much larger) ingest fast enough to run via configurable concurrency.

This is **complete coverage**, not minimal station count. If a broadacre SA2 is included,
it must either have its internal BOM stations ingested, or be covered by the existing
hybrid / Data Drill gap-fill path — and any SA2 that is neither must be surfaced as an
unresolved gap, never silently dropped.

---

## 2. Source of Truth

### 2.1 Broadacre-cropping SA2s

**File: `data/meta/crop_context_sa2.csv`** — ABS Agricultural Census 2020-21, normalised
to one row per SA2 × crop.

- **188 SA2s**, covering all 5 cropping states (WA, SA, VIC, NSW, QLD).
- **5 crops, all broadacre:** wheat, barley, canola, lupins, oats. Because the file
  contains *only* broadacre crops, "every row is broadacre" — there is no crop-selection
  judgement to make. Inclusion sums across all crops in the file.
- **Inclusion metric:** sum of `area_ha` across crops, per SA2. The alternative column
  `area_ha_for_weighting` is available and configurable via `coverage.sa2_broadacre.area_column`.
  (Note: existing *analysis* scripts such as `state_sa2_area_weighted_drill.py` filter to
  `crop == "wheat"` for area-*weighting*; that is a separate concern from *inclusion* and
  is not changed by this work.)

### 2.2 Join key: crop areas ↔ stations

`crop_context_sa2.csv.station_sa2_5dig16` (5-digit, 2016 boundaries)
↔ `data/meta/wheatbelt_stations.csv.SA2_5DIG16`.

This is a clean 1:1 bridge — the `station_sa2_5dig16` column exists precisely to join crop
data to station metadata. Station IDs and SA2 codes are normalised with `zfill` to avoid
leading-zero mismatches.

### 2.3 Threshold profiling (informs the default)

Summed `area_ha` per SA2: 10th pct ≈ 2,441 ha, median ≈ 38,658 ha.

| Threshold (ha) | Target SA2s | Stations | SA2s w/ 0 internal stations |
|---:|---:|---:|---:|
| 0 (any cropping) | 188 | 1,373 | 15 |
| **5,000 (default)** | **159** | **1,293** | 6 |
| 10,000 | 135 | 1,143 | 4 |
| 20,000 | 118 | 1,066 | 3 |
| 50,000 | 83 | 824 | 3 |

**Key finding:** the crop file already maps to 175 station-SA2s covering 1,373 of the 1,376
BOM stations, so "SA2 has cropping" alone barely filters. The threshold is what trims the
fringe. At **5,000 ha** the default keeps 159 SA2s / ~1,293 stations while dropping only the
genuinely tiny bottom ~15%.

---

## 3. Coverage Decisions (locked)

- **Station density:** **all** stations whose SA2 passes the threshold are ingested — no
  ranking or capping model. The goal is complete coverage, not a minimal set.
- **Default threshold:** `min_broadacre_area_ha = 5000`, configurable.
  - `0` → every SA2 present in the crop file (row-presence inclusion; all 188 — see null-area note below).
  - `5000` → default "meaningful broadacre presence".
  - `10000`+ → narrower / core-region settings.
- **Null-area semantics (resolves test/impl ambiguity):** `total_area_ha` is the
  **NaN-skipping sum** of `area_ha` across an SA2's crop rows — an SA2 whose every crop row
  has a missing `area_ha` therefore gets `total_area_ha = 0.0` (not dropped). Two such SA2s
  exist in the current file: **11172 Albury - East** and **21007 Smythes Creek** (both VIC).
  Inclusion is `total_area_ha >= min_broadacre_area_ha`, so `0` includes these two (row
  presence) and any `>= 1` threshold — including the 5,000 default — excludes them. This
  makes "threshold 0 → all 188" exactly consistent with the function contract in §4.1; a
  strictly-positive test (which would yield 186) is **not** used.
- **Gap handling (per-SA2 guarantee):** for *every* included SA2 with zero internal BOM
  stations, the implementation must **either** generate/identify at least one Data Drill
  point that falls **inside that SA2's polygon**, **or** classify it `unresolved_gap`.
  This is a per-SA2 obligation, not a regional-grid side effect — see §4.3.1. Each included
  SA2 is then classified in the coverage report (see §4.4).
- **Fallback:** the legacy `active`-tier path is fully preserved and selectable.

---

## 4. Architecture

### 4.1 `src/common/sa2_coverage.py` (new — pure, testable, no side effects beyond CSV reads)

| Function | Responsibility |
|---|---|
| `load_broadacre_sa2_areas(crop_path, area_col="area_ha") -> DataFrame` | Aggregate area per `station_sa2_5dig16` → `[sa2_5, sa2_name, state, total_area_ha]`. `total_area_ha` = **NaN-skipping sum** (all-null-area SA2 → `0.0`, retained) |
| `select_target_sa2s(areas_df, threshold_ha=5000) -> set[str]` | `total_area_ha >= threshold_ha` → set of 5-digit SA2 codes. `threshold_ha=0` therefore returns all 188 (incl. the two `0.0`-area SA2s); `>=1` drops them |
| `derive_station_universe(target_sa2s, stations_df) -> DataFrame` | Stations whose `SA2_5DIG16` ∈ target set (zfill-safe) → `[station_id, name, sa2_5, latitude, longitude, ...]` |
| `build_coverage_report(target_sa2s, areas_df, station_universe, dd_covered_sa2s) -> DataFrame` | One row per included SA2 (see §4.4) |

### 4.2 Config additions (`config/silo_sources.yaml`)

```yaml
coverage:
  mode: "sa2_broadacre"        # sa2_broadacre | active_tier  (active_tier = legacy fallback)
  sa2_broadacre:
    crop_context_file: "data/meta/crop_context_sa2.csv"
    area_column: "area_ha"
    min_broadacre_area_ha: 5000   # 0 = any cropping; 5000 = meaningful (default); 10000+ = core regions
    enable_data_drill_gaps: true
    coverage_report: "data/meta/sa2_coverage_report.csv"

api:
  # ... existing keys ...
  concurrency: 10               # parallel station requests.
                                # concurrency: 1 = legacy sequential execution mechanics
                                #   (one request at a time). NOTE: scope is still set by
                                #   coverage.mode — legacy 16-station DAILY behaviour is
                                #   coverage.mode: active_tier, not concurrency: 1.
```

The existing `stations:` tiers (`active` / `unverified` / `inactive`) are untouched and are
used when `coverage.mode: active_tier` (or `--coverage-mode active_tier`).

### 4.3 Concurrent ingest (`run_ingest.py`)

Replace the sequential `for station` loop with a `ThreadPoolExecutor(max_workers=concurrency)`:

- **Parallelised (network-bound):** per-station `fetch → process → quality-check`. These use
  per-call `requests` and stateless processors, so they are safe to run across threads.
- **Serialised (main thread):** all writes — `append_to_daily_observations` (atomic CSV) and
  DuckDB `upsert_observations` (single connection) — are consumed via `as_completed` in the
  main thread. This preserves atomic writes and prevents CSV/DuckDB corruption.
- **Preserved untouched:** per-station `try/except` isolation, and the existing retry +
  exponential backoff inside `api_client`.
- **`concurrency: 1`** reproduces the legacy sequential **execution mechanics** (one request
  at a time, same retry/backoff). It does **not** restore legacy *daily scope* — under
  `coverage.mode: sa2_broadacre` it still runs the full ~1,293-station universe, just
  serially. Legacy *daily behaviour* (the 16-station set) is `coverage.mode: active_tier`.
- Zero-station included SA2s are gap-filled via the existing Data Drill machinery, subject
  to the per-SA2 guarantee in §4.3.1.

#### 4.3.1 Per-SA2 Data Drill gap guarantee

The current `--hybrid` path generates a **broad regional grid** and suppresses points within
`proximity_threshold_deg` of *any* of the 1,376 BOM stations. That gives good regional
coverage but **does not guarantee a point inside each specific zero-station target SA2** —
a small SA2 wedged between stations could end up with no internal grid point yet not be
flagged. This work must close that gap explicitly:

For each included SA2 with zero internal BOM stations:
1. Test whether any generated Data Drill point falls inside the SA2's polygon
   (`shapely` containment against `SA2_ABS_Regions.geojson`).
2. If none does, **inject a targeted Data Drill point at the SA2's polygon
   representative point** (centroid clamped to inside the polygon) and ingest it.
3. If a point is present/injected and successfully ingested → `data_drill_gapfill`.
   If injection or ingestion fails (e.g. Data Drill returns no data, or
   `enable_data_drill_gaps: false`) → `unresolved_gap`, logged at WARNING.

No included SA2 may silently end with neither an internal station nor a Data Drill point.

### 4.4 Coverage report (`data/meta/sa2_coverage_report.csv`, atomic write)

One row per included SA2, reviewable:

| Column | Meaning |
|---|---|
| `sa2_code` | 5-digit 2016 SA2 code |
| `sa2_name` | SA2 name |
| `state` | State |
| `broadacre_area_ha` | Summed broadacre area (the inclusion metric) |
| `n_stations` | Count of internal BOM stations ingested |
| `station_ids` | Semicolon-joined station IDs |
| `gap_status` | One of the controlled values below |

**`gap_status` controlled vocabulary:**

- `internal_bom` — SA2 has ≥1 internal BOM station ingested.
- `data_drill_gapfill` — SA2 has 0 internal stations but a Data Drill point inside its
  polygon (grid point or §4.3.1-injected representative point) was successfully ingested.
- `unresolved_gap` — SA2 has 0 internal stations and no successfully-ingested Data Drill
  point inside its polygon (gaps disabled, or Data Drill returned no data). Must be surfaced
  loudly (logged at WARNING; counted in the run summary). Never silent.

Only the handful of zero-station SA2s (~6 at the default threshold) require the polygon
containment test and possible point injection, so the cost is negligible.

### 4.5 Run summary (end of run)

Logged and added to `run_metadata`:

```
requested · succeeded · failed · skipped (no-data) · elapsed_s
```

Plus a coverage line: `included_sa2s · internal_bom · data_drill_gapfill · unresolved_gap`.

**Adjacent bug (optional, flagged not silently expanded):** `run_ingest.py:442` writes a
literal `\n` string instead of a newline into `logs/ingest_runs.jsonl`, so the run-log is
not valid JSONL. A 1-character fix. The plan may include it; it is called out here rather
than bundled silently.

### 4.6 Cron / daily-scope change (`scripts/cron_schedule.sh`)

**This change increases daily ingest volume from ~16 stations to ~1,293 stations** (at the
default 5,000 ha threshold), plus Data Drill gap points for the ~6 zero-station SA2s.

- The daily call changes from the implicit active-tier run to explicit
  `--coverage-mode sa2_broadacre` (with `--hybrid` for gap-fill).
- Expected wall-clock: ~75 min sequential today → **~5–8 min at concurrency 10** (network
  RTT bound; observed ~3.4 s/station sequential).
- CLAUDE.md and `silo_sources.yaml` comments state the default daily coverage plainly so the
  scope is obvious to a future reader.
- The `active_tier` fallback remains available for quick/manual runs and for rollback.

---

## 5. Tests

`tests/test_sa2_coverage.py`:

- **Threshold selection:** SA2 at 4,999 ha excluded; at 5,000 ha included; default == 5,000.
- **Null-area semantics:** an all-null-`area_ha` SA2 (e.g. 11172 Albury - East) has
  `total_area_ha == 0.0`; `threshold_ha=0` returns all 188 SA2s (incl. both null-area ones);
  any `threshold_ha >= 1` excludes them. Guards the test/impl agreement from review finding #2.
- **Station universe derivation:** in-set station included, out-of-set excluded, zfill
  robustness (e.g. `8137` vs `008137`).
- **Coverage report:** zero-station SA2 → `gap_status` is `data_drill_gapfill` or
  `unresolved_gap` (not `internal_bom`); populated `station_ids` for internal SA2s;
  `internal_bom` assigned when ≥1 station present.
- **Per-SA2 gap guarantee (§4.3.1):** a zero-station target SA2 with no covering grid point
  triggers an injected representative point → `data_drill_gapfill` on success; with gaps
  disabled (or no Data Drill data) → `unresolved_gap`. No zero-station SA2 is left
  unclassified.
- **Cron-coverage guard:** the shipped default config (`sa2_broadacre`, 5,000 ha) derives
  ≫16 stations — prevents a silent regression back to the tiny active-tier set.

Ingest concurrency test (with mocked `api_client`):

- **Failure isolation:** mixed success / raised-exception stations → failures land in the
  failed list, all successes are written, output is not corrupted, result is independent of
  completion order.
- `concurrency: 1` and `concurrency: N` produce the same successful station set.

---

## 6. Files Touched

**New:**
- `src/common/sa2_coverage.py`
- `tests/test_sa2_coverage.py`
- `data/meta/sa2_coverage_report.csv` (generated artifact)

**Modified:**
- `config/silo_sources.yaml` (coverage block, `api.concurrency`)
- `src/agents/silo_wrangler/run_ingest.py` (coverage-mode branch, concurrent loop, run summary)
- `scripts/cron_schedule.sh` (daily scope → `sa2_broadacre`)
- `CLAUDE.md` (document default daily coverage)

---

## 7. Scope Guards

- Smallest safe change. **No station ranking/capping model.**
- Existing reports under `reports/` are not regenerated or touched.
- Output column names and `data/derived/` + `reports/weekly/` paths the downstream
  assembler depends on are unchanged.
- New untracked working-tree files (`.venv/`, `data/external` symlinks, the 2026 drill
  scripts, figures, backfill logs) are **not** swept into commits — only the files this work
  touches are staged.
