# SA2 Join-Key Investigation (R6) — read-only, pre-loader

**Status:** investigation only. No loader written. Decision input for the
`Sa2Break` assembly layer (Task 2.1, step 5 follow-on).
**Date:** 2026-06-09
**Question:** can break features (2016-vintage SA2 codes) be joined safely to the
vendored SA2→SD concordance (2021-vintage `SA2_CODE21`) and to the broadacre
weights, or is a 2016→2021 SA2 bridge required first?

**Verdict: clean direct join — no bridge needed.** All 28 WA break-feature SA2s
match the 2021 concordance on the 9-digit code, and all land in the 7 BEN Agri
grain SDs. The vintage gap does not bite for the WA grain belt.

---

## 1. WA break-feature SA2s by code system

Source: `data/features/rainfall_features_sa2_season.csv`, rows where
`state_name == "Western Australia"`. Two SA2 code columns:

| column | meaning | distinct WA values |
|---|---|---|
| `sa2_code` | 5-digit short code (SA2_5DIG, 2016 lineage) | 28 |
| `sa2_code_9dig` | 9-digit main code (SA2_MAIN) | 28 |

(28 grain-belt SA2s — the analyser's wheatbelt subset, not all ~265 WA SA2s.)

## 2. Direct matches to vendored `SA2_CODE21`

Vendored concordance: `data/meta/sa2_2021_to_sd_2011_concordance_wa.csv`
(`SA2_CODE21` is the 9-digit 2021 code; 265 distinct WA SA2s).

| join | result |
|---|---|
| feature `sa2_code_9dig` ∩ concordance `SA2_CODE21` | **28 / 28 (100%)** |
| feature SA2s with **no** concordance row | **0** |
| feature SA2s mapping outside the 7 grain SDs (Pilbara/Kimberley/interstate) | **0** |

SD distribution of the 28 (by overlap): Perth 2, South West 5, Lower Great
Southern 9, Upper Great Southern 11, Midlands 13, South Eastern 5, Central 7
(overlap counts exceed 28 because split SA2s touch >1 SD — see §3).

## 3. Non-matches and edge cases

- **9-digit non-matches: none.** So `sa2_code_9dig` is effectively concordant
  with the 2021 `SA2_CODE21` for every grain SA2 — either the 9-digit codes are
  stable 2016→2021 for these SA2s, or the feature column already carries 2021
  codes. Either way the join is exact.
- **Split SA2s (map to >1 SD): 14 of 28**, but the split is cosmetic — one SD
  carries `allocation_ratio` ≈ 1.0 and the rest ≈ 0.0. The only materially split
  SA2 is `511011275 Esperance Surrounds` → South Eastern 0.981 / Lower Great
  Southern 0.019. Because the rollup weights by `allocation_ratio × broadacre_ha`,
  these sub-1% fractions self-cancel; no special handling needed.
- **2 feature SA2s lack a broadacre weight** (absent from
  `data/meta/sa2_coverage_report.csv` entirely):
  `511041285 Geraldton (51285)` and `511041287 Geraldton - North (51287)`.
  These coastal SA2s fell below the coverage report's broadacre floor. With no
  weight they contribute 0 to the rollup (effectively dropped). **Open item for
  review:** confirm Geraldton - North carries no material winter cropping; if it
  does, it needs a broadacre weight or it silently drops from its SD.
- **broadacre join (5-digit):** feature `sa2_code` ∩ coverage `sa2_code` = 26/28
  (the 2 Geraldton SA2s are the only misses).

## 4. Is there a 2016→2021 SA2 bridge?

**No bridge file exists** — searched the repo (`*correspond*`, `*2016*2021*`,
`*sa2*2016*`) and the ABS sibling `…/acf_historical/concordances/` (only the
SA2(2021)→SD(2011) overlay and its summary live there). None is needed given the
28/28 direct match. The recommended fail-loud behavior (below) makes the absence
safe: any future SA2 that fails to match stops the build rather than mis-joining.

## 5. Recommended loader key + failure behavior

**Join keys**
- **break features ⋈ concordance:** join on the **9-digit code**
  (`sa2_code_9dig` ⟷ `SA2_CODE21`). Exact, 28/28. *Do not* join on the 5-digit
  code to the concordance (the concordance has no 5-digit column).
- **break features ⋈ broadacre weight:** join on the **5-digit code**
  (`sa2_code` ⟷ coverage `sa2_code`).
- **SA2→SD weight:** `allocation_ratio` from the concordance (one `Sa2Break` per
  feature-SA2 × concordance-SD-overlap); `weight = allocation_ratio ×
  broadacre_area_ha`, which already handles splits and self-cancels tiny fractions.

**Failure behavior**
| condition | behavior | rationale |
|---|---|---|
| feature SA2 `sa2_code_9dig` not in concordance | **fail loud** | unexpected (currently 0); a silent miss would drop real grain area / mis-join across vintages |
| feature SA2 has no broadacre weight | **weight = 0.0 + warn** (don't fail) | expected for sub-floor coastal SA2s (Geraldton); a warning keeps it visible |
| concordance SD not in the 7-SD allowlist | **drop with rationale** | already handled by `resolve_sd_region` (non-grain WA / interstate edge) |
| unknown SD code | **fail loud** | already handled by `UnknownSdError` |

**Net:** the loader is low-risk. Build it to join on 9-digit for SD mapping and
5-digit for broadacre weight, fail loud on an unmatched 9-digit SA2, and warn
(weight 0) on a missing broadacre weight. The only judgement call to confirm is
the 2 Geraldton SA2s (§3).

*No loader code was written. This note is the only artifact.*
