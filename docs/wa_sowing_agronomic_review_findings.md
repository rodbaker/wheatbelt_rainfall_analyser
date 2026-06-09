# WA Sowing-Window Agronomic Review — findings

**Branch:** `review/wa-sowing-agronomics` (off `feat/sowing-window-evidence`).
**Scope:** contract DATA only (`config/sowing_windows_wa.csv` + provenance). Evidence
architecture, `swp-1` schema, and orchestration were NOT changed.
**Date:** 2026-06-09. **Status:** stop for review; not merged.

---

## 1. Wheat window — area-weighted by 2025 variety mix

Revised the single `wheat_incl_durum` window using the 2025 planted-area mix:

| version | earliest/opt_start/opt_end/latest | basis |
|---|---|---|
| v0 | 91/111/134/166 | narrative estimate (superseded) |
| v1 | 105/105/158/165 | faithful Table 15 **full envelope** (superseded) |
| **v2 (current)** | **120/127/150/157** | **2025 area-weighted** (Table 1 × Table 15) |

Method: map each 2025 variety (Table 1, p11) to its Table 15 maturity row (cells
extracted from the PDF via pymupdf + visual cross-check), then area-weight the window
boundaries by 2025 area share. Represented area **91.3%**; mix is quick-mid-dominant
(Scepter-type ≈70% of mapped). Full method/coverage/assumptions in the CSV provenance
sidecar. `confidence` raised low→**medium**.

Why v2 is better than v1: the full envelope's `opt_start` (Apr 15) was pulled to the
slow-maturity extreme and over-emitted marginal `low` rows; the area-weighted
`opt_start` (May 7) sits where the bulk of WA wheat is actually sown.

## 2. Other crops — deferred (no fabrication)

A full-PDF scan for the colour-coded sowing-time grid (the `wk1..wk4` signature)
finds it **only on the wheat page (p31)**. Barley, canola, lupins, oats (and the
pulses) have **no extractable sowing-window table** — only observational prose.
Per the brief (no interpolation from prose), they are **deferred, not drafted**.

## 3. Real-data behavior (verified, not a defect)

With the area-weighted window the build emits **0 rows for every season 2015–2026**.
This is correct, for two independent reasons — **not** a silent/over-tight window:

- **Guide-year gating (spec §7.4):** the only guide is `source_year=2026`, and a guide
  is used only when `source_year ≤ season_year`. So **only season 2026 is assessable**;
  2015–2025 correctly get nothing (no period-appropriate guide).
- **2026 broke early:** all 2026 SD-aggregated breaks are DOY ≤118 (late April),
  before `opt_start=127` (May 7) → no downward pressure on the quick-mid crop mix →
  0 rows. An early break means you can still sow in the optimal May window.

The window **does** fire on genuinely late breaks: 2025's `WA_CENTRAL` break reached
DOY 136 (May 16) and resolves to `band=low` via `_band(...)` — it only fails to emit
because there is no 2025 guide. Synthetic late-break fixtures in
`tests/test_sowing_contract_export.py` confirm firing end-to-end.

## 4. Data limitations surfaced for the reviewer (pipeline, not window config)

- **Break history is 2025–2026 only.** Earlier seasons carry `autumn_break_status =
  not_assessed` (no daily data), so they contribute no eligible SD break. Consequently
  `break_percentile_vs_history` (R3) has effectively **no climatology**, and the
  ≥10-year history guard will force `window_confidence=low` on any emitted row
  regardless of the window's own confidence. This is a **feature-data** matter (the
  autumn-break features), out of scope for this data-review branch — flagged for a
  future evidence-layer/data decision.
- **Single guide vintage:** until contemporaneous guides are added, only the current
  season is assessable. Fine for v1 (the live house vintage), but worth noting.

## 5. Boundaries honoured

No yield modelling, disease risk, variety-recommendation logic, hectare deltas, or
auto-switching were added. Disease/yield remain potential **future** evidence layers
and are explicitly NOT part of `sowing_window_area_pressure.csv`. WA-only; directional
evidence only; `swp-1` schema and orchestration untouched.

## 6. Decision for the reviewer

Accept the area-weighted wheat window (120/127/150/157, confidence=medium) for v1, with
other crops deferred? If yes → merge `review/wa-sowing-agronomics` back into
`feat/sowing-window-evidence` and resume the Phase-2 merge gate. If adjustments are
wanted (e.g. a different maturity-collapse target, or redistributing the unmapped 7.1%),
change only the window config/provenance — not the architecture.
