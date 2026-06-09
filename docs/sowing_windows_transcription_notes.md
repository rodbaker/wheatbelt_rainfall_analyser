# Sowing-Windows Transcription — findings before drafting `sowing_windows_wa.csv`

**Status:** RESOLVED — Option B chosen (full-envelope wheat draft, no PDF install).
`config/sowing_windows_wa.csv` drafted (wheat only, `confidence=low`) for manual
agronomic review; see that file's provenance sidecar. Other crops still deferred.
**Date:** 2026-06-09
**Source examined:** `docs/DPIRD-2026-WA-Crop-Sowing-Guide.md` (8197 lines) and
`docs/DPIRD-2026-WA-Crop-Sowing-Guide.pdf` (Bulletin 4937).

---

## 1. Finding that *validates D2* (SD-grain, no agzone)

The guide's sowing-time tables (e.g. **Table 15** for wheat, line 786) are
calendar grids headed **"AGZONES 1–6"** — i.e. one window **per maturity class
across all six agzones combined**, **not** differentiated by agzone. Sub-state
nuance is only ever qualitative prose (e.g. line 796: "quick winter wheats …
only applicable in the southern areas of WA").

**Implication:** the guide does not encode per-agzone *numeric* windows, so D2's
choice (key to BEN Agri SD, replicate the WA-wide window across the 7 SDs) loses
**no** real resolution. Keying to agzone would have fabricated precision the guide
doesn't contain. D2 is the faithful representation, not a compromise.

## 2. Blocker: the structured window data is not recoverable from in-repo sources

The actual window boundaries (earliest / optimal_start / optimal_end /
latest_viable) live in the **colour-coded cells** of each crop's sowing-time table
(legend, line 794: "= earlier than ideal  = optimum sowing time  = later than
ideal but acceptable").

- **Markdown:** the extraction kept the variety lists and week headers but
  **dropped the cell colouring** — so which weeks are *optimum* vs *acceptable*
  for each variety is **not present** in the `.md`. Precise DOY windows cannot be
  transcribed faithfully from the markdown.
- **PDF:** cannot be rendered in this environment — `pdftoppm`/poppler-utils is
  not installed, so the colour cells can't be read visually either.

Crops needing windows (guide sections present): wheat (l.202), barley (l.1558),
canola (l.3692), oats (l.4310), lupin (l.5914), chickpea (l.6348), faba bean
(l.6774), field pea (l.7136), lentil (l.7610). Vetch is dropped (§7.2, no BEN Agri
code). For most of these the only window signal is the colour-coded table.

## 3. What *is* textually stated (example: wheat)

Faithfully quotable, but coarse and narrative-only — not a per-band window:
- "peak yields generally occurred from a **late April to early May** sowing"
  (Figure 2 narrative, l.752).
- "Most of the main season wheat NVTs are **germinated from mid-May onwards**"
  (l.752 region).
- Table 15 calendar spans **March wk4 → June wk4**; trial sowing axis 4-Apr to
  13-Jun (l.791).
- "spring wheats generally have a **lower yield potential if sown before late
  April**" (l.782); winter/very-slow types "more competitive when sown in **early
  to mid-April** in southern, longer season environments" (l.772).

Turning these into earliest/optimal/latest DOY still requires judgement calls the
brief rules out ("no agronomic interpolation beyond what the guide actually
says"). And several crops (esp. pulses) give no comparable narrative DOYs at all —
only the colour table — so a narrative-only pass would leave them empty or guessed.

## 4. Options (need your call)

| # | path | fidelity | cost |
|---|---|---|---|
| **A** | Install `poppler-utils` (apt) so I can render + read the PDF tables and transcribe the actual colour-coded windows per crop, with page/cell citations and conservative confidence. | **High** (faithful to the guide) | system install (needs your OK) + careful per-crop transcription |
| **B** | I draft a **coarse, WA-wide, `confidence=low`** table from narrative text only — likely wheat (+ maybe barley/canola), pulses left out for lack of stated DOYs. Clearly provisional. | Low–medium; partial coverage | low |
| **C** | You supply the structured window table (or a cleaner extract). | High | external |

## 5. Decision (2026-06-09): Option B, full-envelope wheat

Chosen: draft now from narrative (no `poppler` install), **wheat only**, as a
**maturity-collapsed full envelope** (union of the Slow..Quick rows), excluding
the southern-only winter-wheat special case. The full envelope is the widest
defensible window → under-emits `at_risk` rather than over-emits (directional,
citation-only evidence; silence beats confident-but-wrong). DOY boundaries,
citations, and the four review caveats are recorded in
`config/sowing_windows_wa.provenance.txt`. The other 8 crops remain deferred until
a faithful source (PDF tables or supplied extract) is available.
