# Phase 2 — `feat/sowing-window-evidence` branch status

**Status:** Wheat window **agronomically reviewed & ACCEPTED** (2026-06-09); review
branch `review/wa-sowing-agronomics` merged into this branch (merge `a5a68a6`).
Implementation otherwise frozen (bug fixes only). The remaining gate is the Phase-2
→ `master` (or onward) merge decision, which is the operator's call.
**Branch:** `feat/sowing-window-evidence` (based on `fix/netcdf-rainfall-mtd-and-baseline`, per D1)
**Date:** 2026-06-09
**Deliverable:** `sowing_window_area_pressure.csv` (contract `swp-1`) for crop-forecast.

---

## Agronomic review outcome (accepted)

`config/sowing_windows_wa.csv` is contract data and was reviewed on its own branch.
Accepted wheat window: **`120 / 127 / 150 / 157`** (earliest Apr 30, optimum May 7–30,
latest-viable Jun 6) — a **2025 area-weighted** maturity-mix collapse (Table 1 × Table 15),
representing 91.3% of 2025 WA wheat area. Barley/canola/lupins/oats remain **deferred**
(no source-backed sowing-time table; not to be added without one). Full detail:
`docs/wa_sowing_agronomic_review_findings.md` + the CSV provenance sidecar.

## Two confidence concepts — do NOT conflate

These are **different things** and a reader must keep them apart:

| field | meaning | current |
|---|---|---|
| `config/sowing_windows_wa.csv` → `confidence` | **window-source / agronomic** confidence in the *window itself* (how well the guide pins the DOY band) | **medium** (faithful tables, area-weighted, 91.3% represented) |
| exported `sowing_window_area_pressure.csv` → `window_confidence` | **per-row run-time** confidence, = the window-source confidence **monotonically downgraded to `low`** if the SD's valid break-date coverage < 60% **or** historical break climatology < 10 yr | often **low** on real data today (see below) |

So a row can cite a **medium**-confidence window yet be exported at **`window_confidence=low`**
because that SD had thin break coverage this season or has no multi-year break history.
That downgrade is by design (R2 coverage guard + R3 history guard) and is *not* a
contradiction of the window's medium source confidence.

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
| windows | `config/sowing_windows_wa.csv` + `windows.py` | **wheat only**, SD grain, area-weighted, source-conf=medium |
| orchestration | `scripts/build_sowing_window_pressure.py` | load → rollup → evidence → latest + dated archive |
| contract export | `evidence.write_pressure_csv` + `test_sowing_contract_export.py` | exact swp-1 columns, WA-only |

Vendored data (with provenance): `data/meta/region_reference.csv`,
`data/meta/sa2_2021_to_sd_2011_concordance_wa.csv`.

Real-data smoke (2026, area-weighted window): **0 rows** — 2026 broke early (late
April), in-time for the quick-mid crop mix, so no downward pressure (correct, not a
defect; firing on genuinely late breaks is covered by synthetic contract tests).
Geraldton 51285/51287 correctly warned + dropped (no broadacre weight).

## Review checklist (status)

1. **Freeze** implementation except bug fixes. ✅ *(in effect)*
2. **Review** the wheat window/provenance. ✅ *(done on `review/wa-sowing-agronomics`)*
3. **Decide** wheat-only WA v1 with other crops deferred. ✅ **accepted**
4. **Accepted:** review branch merged (`a5a68a6`); final verification run (87 sowing
   tests + full suite green bar the one unrelated pre-existing failure). The Phase-2 →
   `master` merge remains the operator's call.
5. *(If future adjustments wanted: change only the window config/provenance, not the
   architecture.)*

## Caveats carried into the merge summary

- **Wheat window** is a maturity-collapsed, **2025-area-weighted** single window
  (`120/127/150/157`, source-conf medium). Statewide weights applied to all 7 SDs;
  frost not modelled (Table 15 assumes low frost risk). See provenance for the four
  detailed caveats.
- **Exported `window_confidence` ≠ window-source `confidence`** — see the confidence
  table above; rows may export at `low` via the coverage/history guards even though the
  window source is `medium`.
- **Break-feature history is 2025–2026 only** (earlier seasons `not_assessed`), so
  `break_percentile_vs_history` (R3) currently has ~no climatology and the history guard
  forces `window_confidence=low`. This is a feature-data matter (autumn-break features),
  not the window config — a future evidence-layer/data decision.
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
