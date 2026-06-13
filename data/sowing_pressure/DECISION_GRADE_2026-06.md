# Decision-grade gate — June 2026 sowing-window snapshot

Snapshot: `sowing_window_area_pressure_2026-06-12.csv` (generated_at=2026-06-12)
Coverage artifact: `data/meta/sa2_obs_freshness_report.csv` (cutoff 2026-06-08)
Gate run: `scripts/build_sa2_obs_freshness_report.py --cutoff 2026-06-08`, 2026-06-13

| # | Criterion (spec 2026-06-12) | Result |
|---|---|---|
| 1 | All WA cropping SA2s assessed, or named exclusions with reason | **21/26 current**; 5 `no_data`, none yet named as defensible exclusions → FAIL |
| 2 | Coverage current to stated cutoff (target ≥ 2026-06-08) | cutoff used: 2026-06-08; the 21 current SA2s reach 2026-06-12 (0 days behind), but `decision_grade_coverage=FAIL` overall → **FAIL** |
| 3 | No stale `not_assessed` leakage for major cropping SA2s | FAIL — Esperance (51274) is a major cropping SA2 with 0 SILO stations / no obs |
| 4 | Empty snapshot acceptable only if 1–3 hold | snapshot is **non-empty** (1 `at_risk` row: WA_CENTRAL `wheat_incl_durum`, band `low`, break 2026-05-28 on_time, −9d vs latest viable). The row is a real signal but rests on incomplete coverage; criteria 1–3 fail, so it is not decision-grade. |

**Verdict: NOT DECISION-GRADE** (mechanical coverage gate).
**Pin decision: NO PIN.** `crop-forecast/config/feeder.yaml` `house.evidence_snapshot`
stays `null` — manual-only path, guards 1/1b remain active.
**Recorded by:** automated coverage gate, 2026-06-13. Not yet ratified by Rod.

## Why it failed, and the path to PASS

Coverage *where stations exist* is strong: all 21 assessed SA2s are current to
2026-06-12, comfortably past the 2026-06-08 cutoff. The gate fails on 5 SA2s only:

| SA2 | Name | Stations | Status | Nature |
|---|---|---|---|---|
| 51007 | Capel | 0 | no_data | structural — no SILO station in SA2 |
| 51226 | Albany Surrounds | 0 | no_data | structural — no SILO station in SA2 |
| 51274 | Esperance | 0 | no_data | structural — major cropping SA2, no station |
| 51236 | Chittering | 1 | no_data | single station, no obs in window |
| 51289 | Irwin | 1 | no_data | single station, no obs in window |

Two routes to a decision-grade PASS for a later round:

1. **Backfill coverage** — add/repair SILO stations (or a monthly-only fallback) for
   the 5 SA2s, re-run the gate.
2. **Named exclusions (Rod's call)** — if any of these are not material cropping SA2s
   for the WA ledger this round, Rod names them as defensible exclusions with a written
   reason, which would let criterion 1 pass on the remaining set. Esperance is unlikely
   to be excludable; Capel / Albany Surrounds / Chittering / Irwin are more arguable.

Per the round's fallback, the June build proceeds **manual-only** with the snapshot
unpinned; WA canola candidates (CAND-2026-06-0001/0002) stay deferred pending either
route above or a named-source manual basis.
