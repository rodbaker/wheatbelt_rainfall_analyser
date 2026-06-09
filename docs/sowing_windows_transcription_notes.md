# Sowing-Windows Transcription — findings before drafting `sowing_windows_wa.csv`

**Status:** blocked on a faithful source; no CSV drafted (would require fabricating
agronomic numbers, which the review brief forbids). Decision input needed.
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

**Recommendation: A.** It's the only in-repo path to the conservative,
source-grounded data the brief asks for. I'd transcribe one WA-wide window per
commodity (collapsing maturity detail per spec §7.1), `rainfall_regime` per the
region, exact page citations in a sidecar, and `window_confidence` no higher than
the guide's own precision supports — then replicate across the 7 SDs for the
SD-grain schema.

---

## 5. UPDATE — Option A executed (PDF read via pymupdf, no sudo)

`poppler-utils` couldn't be installed (sudo needs a password), so the PDF was read
with **pymupdf** (installed into `.venv` for transcription only — *not* a runtime
dep, not in `requirements.txt`). Pages located by caption; wheat Table 15 (p31)
cells extracted **programmatically** from the fill rectangles (exact, reproducible)
and cross-checked against a rendered image.

### 5.1 Wheat — Table 15, faithfully extracted (p31)

Colour legend: light-blue = earlier than ideal · dark-green = **optimum** · orange =
later than ideal but acceptable. Columns are weeks (Mar wk4 … Jun wk4).

| maturity class | earlier | **optimum** | acceptable |
|---|---|---|---|
| Winter wheat (quick) †| — | Apr wk1–2 | Apr wk3 |
| Very slow | — | Apr wk1–2 | Apr wk3 |
| Slow | — | Apr wk3 – May wk1 | May wk2 |
| Mid–slow | Apr wk3 | Apr wk4 – May wk2 | May wk3 |
| Quick–mid to mid | May wk1 | May wk2 – wk4 | Jun wk1 |
| Quick | May wk2 | May wk3 – Jun wk1 | Jun wk2 |

† Winter wheat is footnoted as applicable **only in southern areas of WA** (Fig 2).

DOY conversion (2026, non-leap; wk1=1–7, wk2=8–14, wk3=15–21, wk4=22–EOM):
Apr1=DOY91, May1=121, Jun1=152.

### 5.2 Other crops — prose only, no authoritative window table

Barley, canola, oats, lupin, chickpea, faba bean, field pea, lentil have **no
colour-coded suggested-sowing-times table** — only scattered, variety-specific or
observational prose (e.g. oats p168 "target April sowing"; lentil p251 "mid to late
April … good yields, also May albeit slower"; canola p136/140 NVT sown "24 Apr–11
May" / "25 Apr–1 Jun"). Turning these into per-commodity DOY windows would be
interpolation beyond what the guide states — out of bounds per the brief.

### 5.3 Two decisions this raises (pending)

1. **Wheat maturity collapse** (schema has no maturity column → one window per
   commodity). Candidate representative windows (earliest / opt_start / opt_end /
   latest_viable, DOY):
   - **Main-season dominant** (Quick–mid to mid; the bulk of WA area): 121 / 128 / 151 / 158
   - **Full envelope** (Slow→Quick, excl. southern-only winter): 105 / 105 / 158 / 165
   - **Quick-dominant** (latest-sown / frost-managed): 128 / 135 / 158 / 165
2. **Cross-crop scope:** wheat-only v1 (faithful) · draft others from prose at
   `confidence=low` (some interpolation) · supplied externally.

*Still no `sowing_windows_wa.csv` drafted — pending the two decisions above.*
