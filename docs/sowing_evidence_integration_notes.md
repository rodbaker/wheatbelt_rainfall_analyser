# Sowing Evidence Integration Notes (Phase 2, Task 2.0 — discovery)

**Status:** discovery only. No code written. Stop-for-review checkpoint.
**Date:** 2026-06-09
**Repo:** `wheatbelt_rainfall_analyser`
**Produces (Phase 2 deliverable):** `sowing_window_area_pressure.csv` (contract `swp-1`) consumed by
`crop-forecast`'s house-area build as an optional, citation-only evidence snapshot. **Directional only —
no hectares, ever.**

This note answers the six Task-2.0 discovery questions, records the output contract we must hit, and
lists risks + recommended file locations. It deliberately makes **no** code changes.

---

## 0. Base-branch state (read before starting Phase 2)

The instruction was "start Phase 2 from **updated master**". The working tree is **not** on master:

| Fact | Evidence |
|---|---|
| Current branch | `fix/netcdf-rainfall-mtd-and-baseline`, **3 commits ahead of `master`, 0 behind** |
| Unmerged commits | `7f8002a` docs MTD report · `e2df287` MTD month-end slice fix · `6f05a1c` exclude partial months from weighted baselines + atomic history write |
| On master already | `92da009` unify decile convention + Vintage Pinning v1 |
| Working tree | dirty — `reports/weekly/2026-W21_outlook_v2.md` modified + many untracked scripts/data/figures |

**Implication:** "updated master" is ambiguous. The decile-convention unification (which the percentile
work leans on) **is** on master, but the MTD / partial-month-baseline fixes are **not** — they sit on
`fix/netcdf-rainfall-mtd-and-baseline`. Phase 2's `break_percentile_vs_history` derivation depends on
clean historical baselines; if it should sit on top of the MTD/baseline fixes, branch Phase 2 from
`fix/netcdf-rainfall-mtd-and-baseline` (or merge that branch to master first), **not** from bare master.
**Resolved — see Decisions D1 below.**

---

## Decisions locked for Task 2.1

Two items (formerly R1, R4) were blocking design choices, not review nits. Resolved with the user
2026-06-09:

### D1 — Phase 2 base branch (was R1)
**Decision:** Base Phase 2 on the branch carrying the MTD / partial-month-baseline fixes
(`fix/netcdf-rainfall-mtd-and-baseline`), **or merge those fixes into master first** and base off the
updated master. Do **not** start Task 2.1 on bare master.
**Reason:** `break_percentile_vs_history` depends on historical comparability. Building on known-bad or
stale rainfall baselines produces evidence rows that may later need **semantic** correction (re-stating the
agronomic signal), not just code cleanup — far costlier than getting the base right once.

### D2 — Regionalisation grain: SD-direct, no agzone (was R4)
**Decision:** For WA-only v1, **key sowing windows directly to BEN Agri SD / `region_code`** and skip the
agzone intermediary entirely. `config/sowing_windows_wa.csv` is transcribed at **SD grain**, not agzone.
The agzone path is a deferred future enhancement, to be revisited only once a sourceable agzone→SA2
crosswalk exists.
**Reason:** Phase 2 needs a defensible contract quickly (`sowing_window_area_pressure.csv` by region).
With agzone→SA2 missing, inventing or hand-waving that crosswalk is higher-risk than explicitly declaring
v1 = SD-level WA sowing windows. SD is the contract grain; `region_reference.csv` is the validation gate.

### D2 corollary — `src/sowing/crosswalk.py` scope guard
`crosswalk.py` stays **narrowly** about **SA2 → BEN Agri SD rollup + SD validation**. It must **not**:
- become a national/general regionalisation layer (WA-first; SD is the grain), or
- contain or imply agzone logic (no agzone module, mapping, or stubs in v1).

Its only jobs: (a) roll SA2-level break features up to BEN Agri SD using the SA2→SD concordance, and
(b) validate emitted `sd_region` against `region_reference.csv`. If a future agzone layer is built, it
lands in its own module, not here.

**Explicit WA SD allowlist (decided).** The SA2→SD rollup must be driven by an **explicit allowlist/map of
exactly the 7 BEN Agri WA SDs** (`WA_SOUTH_EASTERN`, `WA_LOWER_GREAT_SOUTHERN`, `WA_UPPER_GREAT_SOUTHERN`,
`WA_MIDLANDS`, `WA_CENTRAL`, `WA_SOUTH_WEST`, `WA_PERTH`) — not "whatever SDs the concordance yields". The
concordance covers all 61 national SDs, so the rollup will surface:
- **Non-BEN-Agri WA SDs** (e.g. Kimberley, Pilbara, Central WA pastoral) — outside the grain belt. These
  must be **excluded by allowlist**, with the exclusion rationale recorded ("non-BEN-Agri WA SD, outside
  grain belt").
- **Tiny interstate edge overlaps** (split SA2s whose `allocation_ratio` bleeds into a neighbouring state's
  SD) — must be **failed or explicitly dropped with rationale**, never silently mapped.

Rule: an SA2→SD mapping that lands on an SD **not** in the allowlist either **fails loudly** (unknown WA
grain SD — investigate) or is **dropped with a logged rationale** (known non-grain / interstate edge). No
silent pass-through. This is the same membership discipline as the `region_reference.csv` gate, applied one
step earlier at rollup time.

---

## 1. Package / module layout for new sowing-evidence code

**Package root is `src/`** (`pyproject.toml` → `[tool.setuptools] packages = ["src"]`; `setup.py` uses
`find_packages()`; every internal import is `from src.<sub> import …`, 53 call-sites). Existing top-level
subpackages: `src/agents/{silo_wrangler,risk_engine,insight_publisher}`, `src/common`, `src/data`,
`src/rainfall`.

The plan's placeholder `src/.../sowing/` therefore resolves to **`src/sowing/`**, imported as
`from src.sowing.<module> import …` (mirrors `src/rainfall`). Recommended files (plan §"File structure",
Phase 2) plus one addition the plan omits:

```
config/sowing_windows_wa.csv            CREATE  DATA — transcribed DPIRD windows (manual)
config/guide_commodity_map.yaml         CREATE  guide crop -> BEN Agri commodity
src/sowing/__init__.py                  CREATE
src/sowing/windows.py                   CREATE  load + validate sowing_windows
src/sowing/region_ref.py                CREATE  consume crop-forecast region_reference.csv
src/sowing/crosswalk.py                 CREATE  *** NOT in plan *** SA2 -> BEN Agri SD rollup + SD validation ONLY (no agzone; see D2)
src/sowing/evidence.py                  CREATE  break (x) window -> pressure rows + band/direction
scripts/build_sowing_window_pressure.py CREATE  entry point; emits latest + dated archive
tests/test_sowing_windows.py            CREATE
tests/test_sowing_evidence.py           CREATE
tests/test_sowing_contract_export.py    CREATE
```

Conventions to match (from existing code + crop-forecast plan): tests run with
`env -u VIRTUAL_ENV poetry run pytest` (shared-venv gotcha — but note this repo uses `requirements.txt` +
`setup.py`, *not* Poetry; confirm the actual test invocation against `tests/test_cli_smoke.py` before
copying the crop-forecast incantation). `scripts/*.py` are the runnable entry points; reusable logic lives
under `src/`. Dated-archive + stable-latest output pattern already exists — follow
`docs/rainfall_handoff_v1_contract.md`.

---

## 2. Existing autumn-break feature outputs and column names

Producer: **`scripts/build_sa2_rainfall_features.py`** → **`data/features/rainfall_features_sa2_season.csv`**.
Break detection function `_detect_autumn_break` at lines ~337–378.

**Break columns (SA2 × season grain):**

| Column | Type | Notes |
|---|---|---|
| `autumn_break_date` | ISO date (nullable) | First qualifying event in Apr–Jun: single day ≥ 10 mm **or** trailing 7-day ≥ 25 mm |
| `autumn_break_7d_mm` | float (nullable) | 7-day rolling total at the break date |
| `autumn_break_status` | enum | `early` (<May 15) · `on_time` (May 15–Jun 15) · `late` (>Jun 15) · `absent` (daily data, no event) · `not_assessed` (no daily data — monthly-only source) |

**Grain / join keys** in that table: `season_year` (int), `sa2_code` (5-digit str), `sa2_code_9dig`
(9-digit ABS), `state_name`, `sa2_name`.

**Downstream:** `scripts/join_sa2_rainfall_crop_context.py` joins features to crop context on
`sa2_code` ⟷ `station_sa2_5dig16`, emitting `data/features/sa2_rainfall_crop_context.csv`. **Caveat:** that
join carries `autumn_break_date` and `autumn_break_status` but **drops `autumn_break_7d_mm`**
(see `RAINFALL_FEATURE_COLS`). If the pressure calc needs the 7-day amount, read it from
`rainfall_features_sa2_season.csv`, not the joined crop-context file.

**Contract docs** for these exist already: `docs/data_contracts.md` §3 (`rainfall_features_station_season`),
§4 (`rainfall_features_region_season`, with `region_type` ∈ {`sa2`,`sa3`,`sa4`,`lga`,`dpird_agzone`}), §5a
(`autumn_break_status` vocabulary). The §4 region table is a **spec** ("code converges toward it"), not a
built artifact for breaks — see §3 below.

---

## 3. SD-level break features — do they exist? **No. Must be aggregated from SA2.**

- Autumn-break columns are produced **at SA2 level only** (`build_sa2_rainfall_features.py`).
- The SD scripts — `scripts/build_sd_sa2_breakdown.py`, `scripts/build_sd_monthly_rainfall_review.py` —
  roll **monthly / seasonal-window totals** up to SD. They contain **zero** references to `autumn_break*`.
  No SD-level break feature is produced anywhere.
- The §4 `rainfall_features_region_season` contract *describes* area-weighted/modal break fields at region
  level, but no code builds them.

**So Phase 2 must aggregate SA2 breaks → SD itself.** The rollup machinery already exists and is reusable:
`build_sd_sa2_breakdown.py` weights SA2 values to SD via the SA2→SD concordance (`allocation_ratio`) and a
`weighted_mean` helper. Open design decisions for break aggregation (R2): modal `autumn_break_status`?
area-weighted vs earliest `autumn_break_date`? weight by `allocation_ratio` and/or
`broadacre_area_ha` (from `data/meta/sa2_coverage_report.csv`)?

---

## 4. `break_percentile_vs_history` — does it exist? **No. Must be derived.**

- No column or value named `break_percentile_vs_history` (or equivalent) exists anywhere in the repo.
- Spec intent (§7, line 227): *"`break_percentile_vs_history` = lateness vs the region's own climatology
  (1911→ baselines already exist), so 'late' is relative."* So this is **break-timing lateness expressed as
  a 0–100 percentile against the region's historical break-date distribution**, not a rainfall percentile.

**Raw materials available to derive it:**
- Historical per-SA2 break dates: `autumn_break_date` across past `season_year`s in
  `rainfall_features_sa2_season.csv` (convert to day-of-year ordinal).
- Percentile primitive: `src/rainfall/analytics.py` → `percentile_rank(values, target)` (house convention:
  ties don't lift rank, NaNs ignored), plus `decile_rank` / `decile_score`.

**Derivation order (decided) — rank at SD grain against SD's own history, do NOT roll SA2 percentiles up:**
1. **Build SD historical break dates first.** Aggregate SA2 break dates → BEN Agri SD per historical
   `season_year` (using the §3 SA2→SD rollup), producing a per-SD time series of historical break dates.
2. **Rank the current SD break date against that same SD's own history.** `break_percentile_vs_history`
   = `percentile_rank(SD historical break-date ordinals, current SD break-date ordinal)`.

Each SD is ranked **against its own climatology only** — this is what "late is relative" means (spec §7).
**Do not** compute SA2-level percentiles and average/roll them up to SD; that is a different statistic
(a mean of within-SA2 ranks, not the SD's rank in its own history) and is explicitly **out of scope for v1**
unless chosen later.

**Caveats (R3):** historical break dates only exist where **daily** data backs the season;
`autumn_break_status='not_assessed'` marks monthly-only seasons with no break date, so the per-SD
climatology sample may be shallow/recent. Decide the historical window and a min-sample rule; set
`window_confidence` accordingly when the SD's history is thin.

---

## 5. agzone → SA2 → BEN Agri SD crosswalk — sources

| Link | Source | Status |
|---|---|---|
| **SA2 ↔ SA3/SA4** | `data/meta/sa2_sa3_lookup.csv` (cols `sa2_code, sa2_name_geo, sa3_name, sa3_code, sa4_name, sa4_code, state`), built by `scripts/build_sa2_sa3_lookup.py` from `data/meta/SA2_ABS_Regions.geojson` | ✅ in-repo |
| **Station ↔ SA2/SA3/SA4** | `data/meta/station_regions.csv`, built by `scripts/build_station_regions.py` | ✅ in-repo |
| **SA2 ↔ SD (Statistical Division 2011)** | `…/projects/ABS Census Data/…/concordances/sa2_2021_to_sd_2011_area_overlay.csv` (cols incl. `SA2_CODE21, SD_CODE11, SD_NAME11, allocation_ratio, is_split_sa2`). Used by `build_sd_sa2_breakdown.py` (line ~25) and `build_sd_monthly_rainfall_review.py` (line ~58). **Use `allocation_ratio` (sums to 1.0 per SA2), not `raw_overlap_ratio`.** | ⚠️ **external** to this repo (sibling project) |
| **SA2 broadacre weights** | `data/meta/sa2_coverage_report.csv` (`sa2_code, broadacre_area_ha, n_stations, …`) | ✅ in-repo |
| **agzone ↔ SA2** | — | ❌ **MISSING** |
| **"BEN Agri SD" definition** | — (authority is crop-forecast `region_reference.csv`, §6) | ❌ not in this repo |

**agzone gap (resolved by D2):** DPIRD agzones 1–6 are referenced only in prose — `config/crop_calendars.yaml`
(comment, citing DPIRD 2026 WA Crop Sowing Guide Bulletin 4937) and `docs/data_contracts.md`
(`dpird_agzone` as a possible `region_type`). **No agzone boundary file and no agzone→SA2 mapping exist.**
**Per D2, v1 sidesteps this entirely:** sowing windows are transcribed directly at BEN Agri SD grain, so
no agzone→SA2 crosswalk is built or implied. The only crosswalk v1 needs is **SA2 → BEN Agri SD** (for
rolling break features up), which the SA2↔SD concordance above already supports.

**BEN Agri SD = crop-forecast `region_code`.** The `SD_NAME11` values in the concordance must map to
crop-forecast's WA SD codes (`WA_SOUTH_EASTERN`, `WA_LOWER_GREAT_SOUTHERN`, `WA_UPPER_GREAT_SOUTHERN`,
`WA_MIDLANDS`, `WA_CENTRAL`, `WA_SOUTH_WEST`, `WA_PERTH`). Encouraging signal: the concordance maps Merredin
/ Kulin SA2s → SD `530 "South Eastern"`, which matches `WA_SOUTH_EASTERN`. But the full
`SD_NAME11`→`region_code` join must be verified for all 7 WA SDs (R6).

---

## 6. Consuming crop-forecast's `region_reference.csv` contract

**Authority module:** `crop-forecast/src/crop_forecast/region_reference.py` (commit `b2fd172`, merged to
crop-forecast master `4d4770a`). It is the **source of truth for `sd_region` strings** so emitted codes
can't drift.

**Schema (4 columns, fixed order, no version field):**

```
region_code, state, region_name, region_level
```

| Column | Meaning |
|---|---|
| `region_code` | machine key — `{STATE}_{SLUG}` for SDs (`WA_MIDLANDS`), bare state abbr for totals (`WA`), `AUS` for national. **This is the join key; no translation layer.** |
| `state` | state abbreviation (e.g. `QLD`, `NSW`, `VIC`, `SA`, `WA` — 2 or 3 letters) or `AUS` |
| `region_name` | human label (SD name / full state name / "Australia") |
| `region_level` | `sd` \| `state_total` \| `national` |

41 rows total for the 5-state config; **7 WA SD rows** (listed in §5). Slug rule = uppercase, non-alnum →
`_`, strip edges (identical to crop-forecast `percrop_tabs._slug`). No version column — schema treated as
stable v1; breaking changes would ship as a new export name.

**Generated by:**
`python -m crop_forecast.cli region-reference config/feeder.yaml [--out PATH]` →
default `crop-forecast/data/house/region_reference.csv`.

**Not currently materialised.** As of 2026-06-09 the file does **not** exist on disk — `crop-forecast/data/house/`
is absent and no `region_reference.csv` is checked in or built anywhere in that repo (the export is
implemented and tested, but nothing has run it to a persisted path). **Task 2.1 must either run the CLI to
generate it, or vendor a pinned copy** into this repo (see R5) before `region_ref.py` can consume it.

**Consume via `src/sowing/region_ref.py`** (plan Task 2.2): `load_region_reference(path)` → set of valid
`region_code`s; `assert_sd_known(sd_region, ref)` raises on non-member. Every emitted `sd_region` in our
output must be validated against this set (spec §5.9 / §8). **Fallback if the file isn't available:** a
**hard duplicated-code test** asserting every emitted `sd_region` is a member of the BEN Agri set — the
export now exists, so prefer consuming the file; keep the duplicated-code test as a guard.

**Sourcing decision (R5):** the file is not yet materialised (above). Decide: run crop-forecast's CLI and
read the output cross-repo by path, or **vendor a pinned copy** into `data/meta/region_reference.csv` (more
reproducible; must be refreshed when crop-forecast's region config changes). Vendoring is recommended for
build reproducibility.

---

## 7. Output contract we must emit — `sowing_window_area_pressure.csv` (`swp-1`)

Spec §9. One row per `(season, sd_region, commodity)` where a directional signal fires. **No hectares /
deltas.** Stable latest file **+ dated archive snapshot**; crop-forecast pins a dated snapshot per house
vintage (sha in its manifest).

| column | type | notes |
|---|---|---|
| `schema_version` | str | `swp-1` |
| `evidence_id` | str | `SWP-{season_year}-{sd_region}-{commodity}-{reason_abbrev}` (§8) |
| `generated_at` | date | run date |
| `rainfall_run_id` | str | which feature build produced break data |
| `season` | str | BEN Agri slash form `2026/27` |
| `season_year` | int | sowing calendar year `2026` |
| `state` | str | `WA` (v1 WA-only) |
| `sd_region` | str | crop-forecast `region_code` — validated against `region_reference.csv` |
| `commodity` | str | BEN Agri code (mapping done analyser-side via `guide_commodity_map.yaml`) |
| `pressure_direction` | enum | `at_risk` \| `favoured` (**no `neutral`** — expressed as no row) |
| `pressure_band` | enum | `low` \| `medium` \| `high` \| `extreme` (crop-forecast treats as opaque ordinal) |
| `counterparty_commodity` | str | BEN Agri code \| `unknown` |
| `reason_code` | enum | `season_break_forced_switch` (v1) |
| `rationale` | str | templated, human-readable |
| `break_date` | date | |
| `break_status` | enum | `early` \| `on_time` \| `late` |
| `break_percentile_vs_history` | float | 0–100 (derived — §4) |
| `window_overlap_days` | int | |
| `days_after_latest_viable` | int | |
| `establishment_risk_flag` | bool | |
| `guide_source_document` · `guide_source_year` | str · int | |
| `window_confidence` | enum | `high` \| `medium` \| `low` |

Band/direction thresholds are **analyser-internal and documented here-side** (spec §7.6): `on_time` break ⇒
**no row**; `late`-past-`latest_viable` ⇒ `at_risk`, escalating with `days_after_latest_viable`; `extreme`
= well past `latest_viable` **and** `break_percentile` in the late tail. Season mapping is winter convention
`2026 → 2026/27` (summer crops out of scope v1).

---

## 8. Risks & open decisions

| # | Risk / decision | Why it matters | Suggested resolution |
|---|---|---|---|
| **R1** | ✅ **RESOLVED → D1.** Base branch ambiguous ("updated master" vs unmerged MTD/baseline fixes). | `break_percentile_vs_history` leans on clean historical baselines; pre-fix baselines cause semantic (not just code) corrections later. | **Decided:** base Phase 2 on `fix/netcdf-rainfall-mtd-and-baseline`, or merge it to master first. See D1. |
| **R2** | **No SD-level breaks** — must aggregate SA2→SD. Aggregation semantics undefined (modal status? area-weighted vs earliest date? weight source?). | Determines the headline `break_status` / `break_date` per SD. | Reuse `build_sd_sa2_breakdown.py` weighting in `src/sowing/crosswalk.py`; decide modal-status + area-weighted-date, weight by `allocation_ratio`×`broadacre_area_ha`. Write it down in a contract section. |
| **R3** | **`break_percentile_vs_history` must be derived** from a possibly shallow climatology (`not_assessed` seasons have no break date). | Drives `pressure_band` escalation; thin history → unstable percentiles. | Pick a defensible historical window; document min-sample handling; set `window_confidence` accordingly. |
| **R4** | ✅ **RESOLVED → D2.** agzone→SA2 crosswalk missing. | If windows were agzone-keyed we couldn't reach SD without it. | **Decided:** v1 transcribes DPIRD windows **directly to BEN Agri SD**, skips agzone. `crosswalk.py` does SA2→SD rollup + validation only (D2 corollary). Agzone deferred. |
| **R5** | **External + cross-repo file deps.** SA2→SD concordance lives in sibling `ABS Census Data`; `region_reference.csv` lives in crop-forecast. | Fragile absolute paths; non-reproducible builds. | Vendor pinned copies into `data/meta/` (concordance) and `data/meta/region_reference.csv`; record their provenance/sha. |
| **R6** | **SD name reconciliation + allowlist.** ABS `SD_NAME11` (2011) vs crop-forecast BEN Agri SD names; concordance also yields non-BEN-Agri WA SDs (Kimberley/Pilbara) and tiny interstate edge overlaps. | A mismatch breaks the `sd_region` gate for whole SDs; un-allowlisted overlaps leak non-grain or interstate rows. | Explicit allowlist/map of the **7 BEN Agri WA SDs** → `region_code`; non-allowlisted SDs **fail loudly** (unknown WA grain SD) or **drop with logged rationale** (non-grain / interstate edge). Test all 7 against `region_reference.csv`. See D2 corollary. |
| **R7** | **V1 scope is WA-only** (sowing_windows WA only) while `region_reference.csv` spans 5 states. | Don't accidentally emit non-WA rows. | Emit only `state == 'WA'` rows; assert it in `test_sowing_contract_export.py`. |
| **R8** | This repo is **not** Poetry (uses `requirements.txt`/`setup.py`); the crop-forecast plan's `env -u VIRTUAL_ENV poetry run pytest` may not apply. | Wrong test command in CI/docs. | Confirm actual invocation against existing `tests/` before copying the incantation. |

---

## 9. Recommended next step

Blocking decisions are now resolved (**D1** base branch, **D2** SD-direct / no agzone). Before writing
Task 2.1 code: check out / prepare the D1 base branch, then proceed TDD per the plan's Phase 2 task list,
starting with `src/sowing/region_ref.py` (smallest, unblocks the validation gate) and
`src/sowing/windows.py` (now keyed at SD grain per D2). Remaining open items are R2/R3 (break→SD
aggregation + percentile climatology semantics) and R5/R6 (vendoring + SD-name reconciliation) — design
work for Task 2.1's contract section, not blockers.

*No code was changed in this task — this note is the only artifact.*
