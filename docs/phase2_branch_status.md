# Phase 2 — `feat/sowing-window-evidence` branch status

**Status:** IMPLEMENTATION FROZEN (bug fixes only). **DO NOT MERGE** until the
wheat sowing window has a human agronomic sign-off.
**Branch:** `feat/sowing-window-evidence` (based on `fix/netcdf-rainfall-mtd-and-baseline`, per D1)
**Date:** 2026-06-09
**Deliverable:** `sowing_window_area_pressure.csv` (contract `swp-1`) for crop-forecast.

---

## Why the branch is held

The code path is shippable, but **`config/sowing_windows_wa.csv` is contract data**.
Even with the faithful Table 15 extraction, two properties require human agronomic
sign-off before merge:
- the **maturity-collapse** choice (one wheat window = full envelope of Slow..Quick,
  southern-only winter wheat excluded), and
- **`confidence=low`** on every row.

The merge gate is agronomic acceptance of that data file — not the architecture.

## What is complete (and verified)

End-to-end v1 pipeline, all TDD'd, 87 sowing tests green:

| layer | module | role |
|---|---|---|
| region gate | `src/sowing/region_ref.py` | consume vendored `region_reference.csv`; `sd_region` validation |
| allowlist + resolver | `src/sowing/crosswalk.py` | 7 WA BEN Agri SDs by SD_CODE11; drop non-grain/interstate, fail loud on unknown |
| loader (R6) | `src/sowing/crosswalk.py::load_sa2_breaks` | features⋈concordance (9-digit) + ⋈broadacre (5-digit); fail loud / warn+weight0 |
| rollup (R2) | `src/sowing/crosswalk.py::rollup_breaks_to_sd` | area-weighted SD break DOY + coverage guard (60%) |
| percentile (R3) | `src/sowing/evidence.py::break_percentile_vs_history` | SD-history-first; min 10 yr else low |
| evidence | `src/sowing/evidence.py::generate_pressure_rows` | `at_risk` only, no neutral, no hectares |
| commodity map | `config/guide_commodity_map.yaml` + `commodity_map.py` | guide crop → BEN Agri code |
| windows | `config/sowing_windows_wa.csv` + `windows.py` | **wheat only**, SD grain, conf=low |
| orchestration | `scripts/build_sowing_window_pressure.py` | load → rollup → evidence → latest + dated archive |
| contract export | `evidence.write_pressure_csv` + `test_sowing_contract_export.py` | exact swp-1 columns, WA-only |

Vendored data (with provenance): `data/meta/region_reference.csv`,
`data/meta/sa2_2021_to_sd_2011_concordance_wa.csv`.

Real-data smoke (2026): 5 low-band `at_risk` wheat rows; Geraldton 51285/51287
correctly warned + dropped (no broadacre weight).

## Review checklist (recommended next steps)

1. **Freeze** implementation except bug fixes. *(in effect)*
2. **Review** `config/sowing_windows_wa.csv` + `config/sowing_windows_wa.provenance.txt`
   for wheat (values `105/105/158/165`; full-envelope method; citations to Table 15 p31).
3. **Decide** whether wheat-only WA v1 is acceptable, with the other 8 crops deferred
   (no authoritative window table in the guide — prose only).
4. **If accepted:** run final verification and merge.
5. **If not accepted:** adjust only the window **config/provenance**, not the evidence
   architecture.

## Caveats carried into the merge summary

- **Wheat window** is a maturity-collapsed full envelope; may **under-emit** `at_risk`
  for quick/mid-dominant SDs (documented in the provenance sidecar). A future
  schema/version should add a maturity class before tightening.
- **Other crops deferred** — drafting them would require interpolation beyond the guide.
- **One unrelated pre-existing test failure:** `tests/test_run_yield_analogue.py::
  test_2026_nsw_analogues` fails on the branch base (present before any sowing work)
  and does **not** touch sowing outputs. Note as pre-existing/unrelated; not a Phase 2
  blocker unless it begins affecting sowing outputs.

## Housekeeping

A locked agent worktree from concurrent work remains:
`.claude/worktrees/agent-aefe7c0d3c3d742b7` (its own branch). Harmless; remove with
`git worktree remove` when convenient.

## Key design decisions (for the reviewer)

- **D1** base branch (MTD/baseline fixes), **D2** SD grain / no agzone — see
  `docs/sowing_evidence_integration_notes.md`.
- **R2/R3** aggregation + percentile/history semantics, **R5** vendoring, **R6** join keys —
  see `docs/sa2_join_key_investigation_notes.md`.
- **Wheat transcription** decision + faithful extraction — see
  `docs/sowing_windows_transcription_notes.md` and the CSV provenance sidecar.
