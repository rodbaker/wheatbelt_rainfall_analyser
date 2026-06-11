# Australian Grain Belt Rainfall Outlook — Week 21, 2026

```vintage
status: frozen
report_date: 2026-05-20
coverage_month: 2026-05
through_day: 19
baseline_years: [2005, 2025]
```

*Compiled 2026-05-20 · audience: grain traders, brokers, farm advisors, ag bankers*
*Data through 2026-05-19 · BOM Jun–Aug 2026 outlook overlay*

---

> ## ⚠️ Correction notice — appended 2026-06-11
>
> **A WA Statistical-Division geography error was found in this frozen report.**
> The status remains `frozen` (the body below is preserved as-published); this
> notice records what is wrong and what still stands.
>
> **What is wrong — WA SD tables (§1, §2, §7) and the per-state WA commentary.**
> The WA SD rollup used a broken SA2→SD mapping that **dropped ~956 kha of WA
> wheat area (≈22% of the state)** — chiefly **Morawa (561 kha)**, which belongs
> in **Central**, and **Esperance Surrounds (389 kha)**, which belongs in **South
> Eastern**. As a result this report carries WA at **3,434 kha** with **Central =
> 469 kha** and **South Eastern = 32 kha**. The corrected canonical geography
> (used by every build from 1 June onward) is **WA = 4,390 kha**, with **Central =
> 1,029 kha** and **South Eastern = 414 kha**. The error is also internally
> inconsistent here: the §7 SA2 callouts list Morawa under Central, yet the
> Central SD total excludes its area.
>
> **Consequence — the §3 claim that "the dry signal is uniform across the WA
> wheatbelt" is overstated.** On the corrected geography WA is two-speed: the dry
> story is real for the **Midlands inland core** and **Upper Great Southern**, but
> **Central (incl. Morawa)** and **South Eastern (incl. Esperance)** are
> **above median** on March-to-date accumulation (decile ≈6.7 and ≈8.6
> respectively). About a third of WA wheat area was sitting above median, not dry.
>
> **What still stands — the §4/§5 production scenarios are UNAFFECTED.** The
> analogue engine weights WA rainfall over the **complete** wheat universe
> (Morawa and Esperance Surrounds both included at full weight) and aggregates
> SA2→state directly, never touching the broken SD mapping. Regenerating WA on the
> corrected geography at this report's own data vintage returns the **identical
> analogues (2009 / 2018 / 2020)** and the **identical BOM-weighted central of
> 8.85 Mt**; the national ~24 Mt roll-up is likewise unchanged. (Refreshing to the
> completed-May data shifts the analogue set to 2011 / 2020 / 2015 but moves the
> WA central only to ~8.90 Mt.)
>
> **Corrected sources:** completed-May monitor
> `reports/monthly/2026-05_rainfall_monitor_sd.md`; WA SD drill-down and the
> March→MTD cumulative via `scripts/build_cumulative_window_review.py`; WA
> scenario regen via `scripts/regen_wa_scenarios_corrected.py`.

## Headline

National 2026 wheat production is tracking around **24 Mt** under BOM's published Jun–Aug outlook — a third below the 2025 record (36.0 Mt) but ~9% above the 1989–2025 long-run mean (22.3 Mt). The grain belt is split into three cohorts:

- **Eastern states (NSW/VIC/SA, 57% of national area)** are carrying record-to-strong summer subsoil moisture; SA and VIC posted their wettest Jan–Mar in 22 years of SA2-level records. The autumn break has effectively arrived.
- **Western Australia (35% of national area)** is on the **driest May since 2005** at the area-weighted state level, with BOM forecasting a 70% chance of below-median Jun–Aug rainfall continuing the dry pattern.
- **Queensland (8%)** is in a top-3-driest Apr–May start despite a near-median Jan–Mar.

**The dominant uncertainty in the 2026 outlook is September–October rainfall**, which is currently unobserved and unforecast (BOM's Aug–Oct outlook lands late July). September is the make-or-break month for winter wheat yield — BOM's current outlook tells us about mid-winter moisture maintenance, not the spring finish.

---

QLD-Commentary April Crop Report 26th April 2026
Queensland enters the main planting window with the weakest moisture profile nationally. Southern QLD and Border regions remain dry, April rainfall has been limited, and near-term forecasts have not provided enough confidence for a broad planting push. Growers are protecting capital and current area estimates could come under further pressure through May if a meaningful break fails to arrive. The dry outlook is already being reflected in markets, with buyers stretching accumulation into Central NSW and drought premiums moving south.

| New South Wales | 107.8 | 142.9 | −35.1 | 29th | **Spatially bimodal — see below** |

### NSW spatial picture (Jan–Mar 2026 SA2 deciles)

The state-aggregated 29th percentile **masks a sharp north–south split** that matters more than the headline for production risk:

| Zone | SA2 count | Decile range | Status |
|---|---|---|---|
| **Northern Slopes / Liverpool Plains / Inverell** | **16 SA2s** | **Mostly decile 1–2** | Severe Jan–Mar deficit. Grafton 32% of median (decile 1); Gunnedah, Moree, Coonabarabran, Inverell East all decile 1; Tamworth/Quirindi/Inverell decile 2. **Prime NSW winter wheat country running on profoundly depleted subsoil.** Apr–May rains helped germination but did not refill the profile. |
| Central West / Lachlan | ~7 SA2s | Mixed decile 2–7 | Boundary zone. Parkes Region and Condobolin still dry (decile 2 at 49–72% of median); Forbes (decile 7) and Cowra (decile 6) near-normal. Bimodal across short distances. |
| **Riverina + Murray + Southern Slopes** | **9 SA2s** | **Decile 8–10** | **Above-median to record-wet.** Wentworth-Balranald 328%, Deniliquin 247%, Hay 194% of historical Jan–Mar median. Blayney, Tumut, Grenfell at decile 9–10. Subsoil-flush conditions analogous to 2010/2016 wet starts. |

**Trade read:** SA and VIC growers have full subsoil profiles entering the season — record-wet Jan–Mar at the state level. Modern stubble-retention systems preserve summer moisture in the root zone, supporting crop development even where seeding-window rainfall lags. **NSW has both extremes inside it:** the southern Riverina/Murray country is among the wettest in 22 years of records, while the northern grain belt is dead dry. The NSW state-level production estimate in this report (5.6 Mt BOM-weighted) assumes spatially-uniform conditions and likely understates the bimodal risk — a dry Sep–Oct would disproportionately hit the northern zone.

---

## 2. Sowing window — Apr–May 2026 month-to-date (19 days of May)

| State | Apr+May MTD (mm) | Historical median | Δ vs median | Percentile rank | Read |
|---|---|---|---|---|---|
| Victoria | 54.5 | 59.3 | −4.8 | 43rd | Within normal range |
| South Australia | 53.5 | 61.5 | −8.0 | 33rd | Within normal range |
| New South Wales | 48.6 | 59.9 | −11.3 | 43rd | Catching up — rescued by May 13–19 front |
| **Western Australia** | **28.1** | 49.6 | **−21.5** | 29th | Driest May since 2005 (May alone: 5th percentile) |
| **Queensland** | **15.4** | 39.0 | **−23.6** | **14th** | Top-3 driest Apr–May since 2005 |

**Trade read:** NSW received 28.8 mm of rain in the May 13–19 window alone — 6× April's monthly total. Central NSW SA2s (Parkes, Narromine, Forbes) are now sitting at 2–3× their historical full-May median with 12 days still to run. WA central wheatbelt registered <1 mm of May rain at many locations through May 19.

---

## 3. Mid-winter outlook — BOM Jun–Aug 2026 (chance of above-median rainfall)

Source: Bureau of Meteorology 3-month outlook, accessed 2026-05-20. Probabilities are area-centred reads of the BOM tercile map at each state's grain belt centroid.

| State | BOM P(Jun–Aug above-median) | Implied P(below-median) | Direction |
|---|---|---|---|
| **Western Australia** | **30%** ± 5pp | 70% | **Strongly dry-tilted** |
| South Australia | 40% ± 5pp | 60% | Modestly dry-tilted |
| Victoria | 47% ± 5pp | 53% | Essentially neutral |
| New South Wales | 57% ± 5pp | 43% | Modestly wet-tilted |
| Queensland | 57% ± 5pp | 43% | Modestly wet-tilted |

**What this actually tells us:** BOM's Jun–Aug forecast covers the tillering and stem-elongation phase — when crops have low water demand because winter temperatures suppress evapotranspiration. It tells us about **whether crops will be alive and developing going into September**, not whether they will set good yield. Sep–Oct rainfall — when flowering opens and grain fill begins — is what actually determines the yield outcome, and BOM hasn't issued an outlook covering that window yet.

**WA spatial caveat:** The dry signal is uniform across the WA wheatbelt — no internal contradiction. South-coast strip slightly less dry (~35% above-median) but central, northern and eastern wheatbelt all dark-orange (25–30% above-median).

---

## 4. Production scenarios — by state, BOM-weighted, with Sep–Oct residual uncertainty

Method: For each state, the closest 3 historical years on joint (Jan–Mar, Apr–May) rainfall distance are taken as analogues. Each analogue's Jun–Aug rainfall is bucketed above/below long-run median, and its actual ABARES yield is recorded. The above-median / below-median scenario yields are then weighted by BOM's Jun–Aug probability and multiplied by 2025 ABARES area.

The Sep–Oct dispersion across the same analogues gives the residual uncertainty that BOM's current outlook does not constrain.

### New South Wales

| Analogue year | Jun–Aug rain | Sep–Oct rain | Yield (t/ha) | Production (Mt) |
|---|---|---|---|---|
| 2017 | 54 mm (below) | 63 mm (above) | 1.68 | 4.70 |
| 2019 | 43 mm (below) | 13 mm (below) | 0.83 | 1.77 |
| 2023 | 82 mm (below) | 27 mm (below) | 2.15 | 7.09 |

- All three NSW analogues had below-median Jun–Aug rainfall, so BOM's 57% above-median signal cannot discriminate yield within this analogue set.
- **BOM-weighted central:** 5.6 Mt (vs 2025 actual 11.2 Mt)
- **Sep–Oct residual range:** 13–63 mm across the three analogues — the analogue that received the wettest Sep–Oct (2017, 63 mm) yielded 1.68 t/ha; the analogue that received almost no Sep–Oct rain (2019, 13 mm) yielded 0.83 t/ha. **This is the yield-determining dispersion.**

### Western Australia

| Analogue year | Jun–Aug rain | Sep–Oct rain | Yield (t/ha) | Production (Mt) |
|---|---|---|---|---|
| 2009 | 159 mm (above) | 44 mm (above) | 1.62 | 8.11 |
| 2018 | 166 mm (above) | 38 mm (below) | 2.28 | 9.98 |
| 2020 | 115 mm (below) | 21 mm (below) | 2.00 | 8.79 |

- **Counter-intuitive finding:** the WA analogue with the *driest* Jun–Aug (2020) had a *higher* yield than two of the wetter Jun–Aug analogues. The analogue yields are driven more by Sep–Oct rainfall than by Jun–Aug.
- **BOM-weighted central:** 8.85 Mt (vs 2025 actual 13.4 Mt)
- **Sep–Oct residual range:** 21–44 mm — narrow band, all below the long-run WA Sep–Oct median (43 mm). The analogue set is showing that "dry-start years tend to stay drier through spring", which is the relevant 2026 risk.

### South Australia

| Analogue year | Jun–Aug rain | Sep–Oct rain | Yield (t/ha) | Production (Mt) |
|---|---|---|---|---|
| 2012 | 131 mm (above) | 31 mm (below) | 1.74 | 3.68 |
| 2016 | 161 mm (above) | 133 mm (above) | 2.82 | 6.13 |
| 2017 | 109 mm (below) | 44 mm (above) | 2.05 | 4.05 |

- **BOM-weighted central:** 4.28 Mt (vs 2025 actual 4.74 Mt)
- **Sep–Oct residual range:** 31–133 mm — very wide. 2016's exceptional Sep–Oct (133 mm) drove the strongest SA yield in the analogue set; the bulk of SA's 2026 production uncertainty sits in this Sep–Oct window.
- SA's record-wet Jan–Mar gives it a buffer that the other below-median Jun–Aug states don't have.

### Victoria

| Analogue year | Jun–Aug rain | Sep–Oct rain | Yield (t/ha) | Production (Mt) |
|---|---|---|---|---|
| 2012 | 135 mm (above) | 56 mm (below) | 2.15 | 3.42 |
| 2021 | 151 mm (above) | 101 mm (above) | 2.94 | 4.25 |
| 2024 | 91 mm (below) | 63 mm (above) | 2.33 | 3.50 |

- **BOM-weighted central:** 3.58 Mt (vs 2025 actual 4.25 Mt)
- **Sep–Oct residual range:** 56–101 mm — narrowest of any state.
- VIC's record wet Jan–Mar combined with neutral BOM signal gives it the most stable outlook of the five states.

### Queensland

| Analogue year | Jun–Aug rain | Sep–Oct rain | Yield (t/ha) | Production (Mt) |
|---|---|---|---|---|
| 2008 | 92 mm (above) | 89 mm (above) | 1.98 | 2.02 |
| 2014 | 55 mm (below) | 38 mm (below) | 1.56 | 0.99 |
| 2016 | 160 mm (above) | 155 mm (above) | 2.41 | 1.50 |

- **BOM-weighted central:** 1.69 Mt (vs 2025 actual 2.31 Mt)
- **Sep–Oct residual range:** 38–155 mm — very wide. QLD's yields move strongly with Sep–Oct in this set.
- 2014 is the warning analogue: dry Jun–Aug + dry Sep–Oct → 0.99 Mt.

---

## 5. National roll-up

| Scenario | National wheat production |
|---|---|
| All states Jun–Aug below median (lower bound) | **23.4 Mt** |
| **BOM-weighted central** | **24.0 Mt** |
| All states Jun–Aug above median (upper bound) | **24.5 Mt** |
| 2025 actual (record) | 36.0 Mt |
| 2024 actual | 34.1 Mt |
| 2022 actual (prior record) | 40.5 Mt |
| 1989–2025 long-run mean | 22.3 Mt |

**Critical observation:** The BOM Jun–Aug signal moves the national estimate by only ±0.5 Mt around the central case. The **Sep–Oct residual uncertainty is the dominant unmodelled risk** — across the five states, Sep–Oct rainfall ranges from 13 mm (NSW 2019) to 155 mm (QLD 2016) in our analogue set, which corresponds to a yield range of roughly ±0.5 t/ha at state level. If WA's 2026 Sep–Oct lands like 2009's 44 mm, the WA crop is around 7–8 Mt; if it lands like 2018's 38 mm but with better timing, closer to 10 Mt.

Practical national range incorporating both Jun–Aug uncertainty and Sep–Oct residual: **roughly 21–28 Mt**.

---

## 6. What changes the picture from here

| Signal | Expected timing | Impact on outlook |
|---|---|---|
| WA continued rain through May 31 | Within 2 weeks | Updates Apr+May into May full-month; would shift WA from 5th percentile to ~10–20th if continued |
| BOM Aug–Oct outlook | ~late July | First forecast covering the September yield-determining window. Biggest single shift in outlook from this point. |
| ABARES June crop report | Early June | Updates national area estimate; if WA growers cut wheat area on the dry start, national implied production drops further |
| Spring (Sep–Oct) rainfall observations | Sep–Oct in real time | Direct resolution of the residual uncertainty |

---

## 7. SA2 / SD regional breakdown — where the state averages are coming from

The state-level reads in §1–2 mask a lot of within-state variation. The table below decomposes each state into its ABS **Statistical Divisions (SD_2011 boundaries — the legacy geography our crop report uses)**, with wheat-area weighting applied through the SA2_2021 → SD_2011 area-overlay concordance (`ABS Census Data/Modernised_Census_2022_2025/.../concordances/sa2_2021_to_sd_2011_area_overlay.csv`).

- **STD (Jan–Apr 2026)** = sum of Jan, Feb, Mar, Apr 2026 monthly rainfall, area-overlay × 2020-21 ABS wheat-area weighted to SD.
- **Apr 2026** = April-only monthly rainfall, same weighting.
- **Decile** = rank of the 2026 value within the SD's 2005–2025 history (1 = driest, 10 = wettest of the 22-year record).
- All grain-belt SDs with ≥10,000 ha 2020-21 wheat area are included (29 SDs total).
- May 2026 is partial through day 19 and is **not** included in either column. The Apr+May MTD framing of §2 is the right place for the very-recent May front; this section reports clean full-month numbers.

| SD (state) | Wheat (kha) | Jan–Apr 2026 (mm) | % median | Decile | Apr 2026 (mm) | % median | Decile |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Western Australia** | | | | | | | |
| Midlands (WA) | 2,103 | 89 | 125% | 7 | 23 | 151% | 7 |
| Upper Great Southern (WA) | 502 | 63 | 79% | 3 | 23 | 109% | 5 |
| Central (WA) | 469 | 109 | 169% | 9 | 14 | 153% | 6 |
| Lower Great Southern (WA) | 328 | 78 | 92% | 4 | 17 | 61% | 4 |
| South Eastern (WA) | 32 | 132 | 137% | 7 | 62 | 235% | 9 |
| **New South Wales** | | | | | | | |
| North Western (NSW) | 1,126 | 92 | 52% | **2** | 0 | 0% | **1** |
| Northern (NSW) | 864 | 97 | 46% | **1** | 0 | 1% | **1** |
| Central West (NSW) | 803 | 128 | 77% | 3 | 1 | 6% | **1** |
| Murrumbidgee (NSW) | 674 | 113 | 78% | 5 | 9 | 35% | 2 |
| Murray (NSW) | 482 | 140 | 114% | 6 | 8 | 30% | 2 |
| South Eastern (NSW) | 82 | 177 | 87% | 5 | 11 | 32% | 3 |
| **South Australia** | | | | | | | |
| Eyre (SA) | 852 | 95 | 116% | 7 | 20 | 99% | 5 |
| Murray Lands (SA) | 286 | 125 | 189% | 9 | 12 | 62% | 5 |
| Yorke and Lower North (SA) | 260 | 110 | 138% | 8 | 20 | 76% | 5 |
| Northern (SA) | 218 | 118 | 138% | 7 | 15 | 61% | 5 |
| Outer Adelaide (SA) | 60 | 70 | 86% | 4 | 19 | 68% | 5 |
| South East (SA) | 51 | 96 | 123% | 7 | 23 | 100% | 6 |
| **Victoria** | | | | | | | |
| Mallee (VIC) | 529 | 179 | 236% | **10** | 4 | 23% | **2** |
| Wimmera (VIC) | 396 | 120 | 135% | 8 | 10 | 49% | 3 |
| Goulburn (VIC) | 188 | 144 | 107% | 6 | 12 | 43% | 4 |
| Central Highlands (VIC) | 91 | 98 | 75% | 3 | 23 | 71% | 3 |
| Loddon (VIC) | 82 | 182 | 157% | 8 | 11 | 41% | 4 |
| Western District (VIC) | 72 | 99 | 68% | 3 | 38 | 105% | 6 |
| Barwon (VIC) | 38 | 99 | 78% | 4 | 28 | 88% | 5 |
| Ovens-Murray (VIC) | 11 | 152 | 86% | 5 | 20 | 72% | 4 |
| **Queensland** | | | | | | | |
| Darling Downs (QLD) | 543 | 172 | 78% | 4 | 1 | 7% | **1** |
| South West (QLD) | 299 | 170 | 91% | 4 | 0 | 0% | **1** |
| Fitzroy (QLD) | 73 | 390 | 135% | 10 | 0 | 1% | **1** |
| Mackay (QLD) | 43 | 387 | 139% | 8 | 26 | 222% | 7 |

### May 2026 month-to-date by SD (May 1–19, 19 of 31 days) + BOM 8-day outlook (May 21–28)

Three columns: observed May MTD (mm through day 19); full-May historical median; BOM 8-day forecast accumulation (read from BOM PME maps `pme1to4.png` + `pme5to8.png` issued 20/05/2026 covering 21–28 May, by visual interpretation of the colour bands at SD centroids — precision ±5 mm). The **projected May finish** is observed + 8-day outlook midpoint expressed as a % of full-May median; days 29–31 are unobserved and unforecast.

| SD (state) | Wheat (kha) | May 1–19 2026 (mm) | Full-May median (mm) | 8-day outlook (mm, May 21–28) | Projected May finish vs median |
|---|---:|---:|---:|---:|---:|
| **Western Australia** | | | | | |
| Midlands (WA) | 2,103 | 1 | 20 | 2–10 | **~30% — decile 1 territory** |
| Upper Great Southern (WA) | 502 | 1 | 33 | 10–25 | ~55% — decile 2 |
| Central (WA) | 469 | 0 | 20 | 2–10 | **~30% — decile 1 territory** |
| Lower Great Southern (WA) | 328 | 7 | 32 | 30–50 | ~140% — above median |
| South Eastern (WA) | 32 | 31 | 32 | 15–30 | ~170% — well above |
| **New South Wales** | | | | | |
| North Western (NSW) | 1,126 | 48 | 26 | 5–15 | ~225% — well above |
| Northern (NSW) | 864 | 23 | 26 | 15–25 | ~165% — above |
| Central West (NSW) | 803 | 70 | 29 | 10–25 | ~300% — well above |
| Murrumbidgee (NSW) | 674 | 42 | 32 | 15–25 | ~195% — well above |
| Murray (NSW) | 482 | 43 | 28 | 20–35 | ~245% — well above |
| South Eastern (NSW) | 82 | 58 | 42 | 30–50 | ~235% — well above |
| **South Australia** | | | | | |
| Eyre (SA) | 852 | 44 | 29 | 10–25 | ~210% — well above |
| Murray Lands (SA) | 286 | 31 | 26 | 5–15 | ~160% — above |
| Yorke and Lower North (SA) | 260 | 34 | 41 | 10–20 | ~120% — above |
| Northern (SA) | 218 | 38 | 40 | 5–20 | ~125% — above |
| Outer Adelaide (SA) | 60 | 29 | 44 | 15–25 | ~110% — at median |
| South East (SA) | 51 | 40 | 47 | 15–25 | ~130% — above |
| **Victoria** | | | | | |
| Mallee (VIC) | 529 | 36 | 20 | 10–20 | **~255% — decile 10 territory** |
| Wimmera (VIC) | 396 | 45 | 34 | 15–25 | ~190% — well above |
| Goulburn (VIC) | 188 | 41 | 33 | 20–30 | ~200% — well above |
| Central Highlands (VIC) | 91 | 42 | 42 | 20–30 | ~160% — well above |
| Loddon (VIC) | 82 | 42 | 31 | 20–30 | ~220% — well above |
| Western District (VIC) | 72 | 48 | 53 | 20–30 | ~140% — above |
| Barwon (VIC) | 38 | 33 | 40 | 25–35 | ~160% — well above |
| Ovens-Murray (VIC) | 11 | 44 | 39 | 20–30 | ~175% — well above |
| **Queensland** | | | | | |
| Darling Downs (QLD) | 543 | 16 | 22 | 10–20 | ~140% — above |
| South West (QLD) | 299 | 13 | 17 | 5–15 | ~135% — above |
| Fitzroy (QLD) | 73 | 2 | 13 | 5–15 | ~90% — at median |
| Mackay (QLD) | 43 | 4 | 9 | 5–15 | ~155% — above |

**Trade read — May projected to month-end with 8-day outlook overlay:**

- **WA Midlands and Central — the 2.57 Mha core of the WA wheat belt (56% of state) — are projected to finish May at ~30% of median, decile 1 territory.** The 8-day outlook delivers only 2–10 mm to the inland zone, leaving the cumulative ~6 mm vs 20 mm median gap unclosed. Three days (29–31 May) of unobserved rainfall would need to deliver ~15 mm to lift these SDs to median — historically rare in late May for inland WA. **This is now a high-confidence dry-finish call for the inland WA wheat belt.**
- **WA Lower Great Southern (Albany hinterland, 328 kha wheat) and South Eastern WA (Esperance, 32 kha) project to above median.** The south-coast strip has captured the May front the inland belt missed.
- **WA Upper Great Southern (502 kha) splits the difference**: outlook delivers 10–25 mm to a mixed zone (Katanning/Wagin coastal-leaning vs Kojonup/Williams inland-leaning) — projects to ~55% of median, decile 2. Marginal.
- **NSW eastern half projects to 165–300% of May median** across every SD. Central West NSW is the standout at ~300% (decile 10 territory for May standalone, on top of decile 3 Jan–Apr — a partial-but-meaningful subsoil recharge for the northern slopes).
- **VIC Mallee projects to ~255% of May median**, decile 10. Wimmera, Loddon, Goulburn, Ovens-Murray all project 175–220%. The Vic wheat belt has now had a record-wet Jan–Mar followed by a wet May — the seeding window is closed positively.
- **SA across the board projects above median**, led by Eyre at ~210%. Outer Adelaide is the closest to median at ~110%.
- **QLD Darling Downs and South West project to ~135–140% of May median.** The 8-day outlook of 10–20 mm closes the small remaining gap and pushes the wheat-belt SDs back above median. **Fitzroy projects to ~90% — the only SD nationally not expected to clear median.**

**Net read:** The dominant signal in the May 8-day forecast is that the **WA inland wheat belt (Midlands + Central, 2.57 Mha) will finish May at ~30% of median**. Every other major wheat SD in the country projects to above median for May. This sharpens — does not contradict — the v2 §4 production scenarios: the **WA dry-finish risk in the WA analogue set (2009/2018/2020) gets a stronger 2026 anchor**, while the eastern states' production downside that v2 was already softening on now has further support for the upside (the Jun–Aug BOM tilt for NSW/VIC/QLD is the next signal to watch).

### Read by state

**Western Australia — Apr was actually average-to-wet; the dry signal is a May story.** Every WA SD finished Jan–Apr at or above its long-run median except Upper Great Southern (decile 3) and Lower Great Southern (decile 4). The headline 5th-percentile-May-since-2005 read in §2 reflects a **break in pattern from May 1 onwards** — it does not contradict the SD table. South Eastern WA (Esperance country) sits at decile 9 for Apr, the wettest SD in the country for the month.

**NSW — sharply bimodal, exactly as §1 described.** All three northern SDs (North Western, Northern, Central West) are decile 1–2 for Jan–Apr **and** decile 1 for Apr, confirming the Liverpool Plains / Moree / Inverell zone is running on profoundly depleted profile. Southern SDs (Murrumbidgee, Murray, South Eastern) sit at decile 5–6 for Jan–Apr but still posted dry Aprils (decile 2–3) — the recovery in §2 came from the **May 13–19 front**, not from April rain.

**SA — record-wet Jan–Mar carries through cleanly.** Every grain SD is decile 7–9 for Jan–Apr; Murray Lands (decile 9, 189% of median) leads. April moderated to decile 5 across the board but stayed near-median in absolute terms.

**Victoria — the Mallee outlier and a softer west.** Mallee posted **decile 10 Jan–Apr at 236% of median** — confirming v2's "wettest in 22 years" read at the SD level. Wimmera and Loddon at decile 8. But Western District, Barwon, and Central Highlands are sub-median (decile 3–4) — the cropping districts west of the divide are wetter than the higher-rainfall traditional zones.

**Queensland — top-3 driest April everywhere it matters.** Darling Downs (decile 1, 7% of median) and South West (decile 1, 0% of median) define the v2 "top-3-driest Apr–May" read. Fitzroy and Mackay show decile 8–10 for Jan–Apr but collapsed in April, consistent with the QLD summer-monsoon-then-dry-autumn pattern.

### SA2 callouts — driest and wettest within each SD's top wheat-area SA2s

For each SD, the table below shows the driest and wettest SA2 (by April 2026 % of median) among the SD's largest 8 wheat-area SA2s. Useful for spotting the within-SD spread.

| SD | Driest SA2 (Apr) | Wettest SA2 (Apr) |
|---|---|---|
| **Midlands (WA)** | Merredin — 17 mm, 89% median, dec 5 | Dowerin — 24 mm, 203% median, dec 8 |
| **Upper Great Southern (WA)** | Kojonup — 17 mm, 62% median, dec 4 | Esperance Surrounds — 62 mm, 248% median, dec 10 |
| **Central (WA)** | Morawa — 11 mm, 100% median, dec 6 | Northampton-Mullewa-Greenough — 17 mm, 291% median, dec 7 |
| **Lower Great Southern (WA)** | Albany Surrounds — 11 mm, 25% median, dec 2 | Esperance Surrounds — 62 mm, 248% median, dec 10 |
| **South Eastern (WA)** | Gnowangerup — 16 mm, 62% median, dec 4 | Esperance Surrounds — 62 mm, 248% median, dec 10 |
| **North Western (NSW)** | Moree Surrounds — 0 mm, 0% median, dec 1 | Griffith Surrounds — 4 mm, 16% median, dec 2 |
| **Northern (NSW)** | Moree Surrounds — 0 mm, 0% median, dec 1 | Gunnedah Surrounds — 1 mm, 5% median, dec 2 |
| **Central West (NSW)** | Condobolin — 0 mm, 0% median, dec 1 | Grenfell — 4 mm, 20% median, dec 3 |
| **Murrumbidgee (NSW)** | Condobolin — 0 mm, 0% median, dec 1 | Wagga Wagga Surrounds — 19 mm, 64% median, dec 4 |
| **Murray (NSW)** | Swan Hill Surrounds — 1 mm, 3% median, dec 1 | Wagga Wagga Surrounds — 19 mm, 64% median, dec 4 |
| **South Eastern (NSW)** | Bathurst Surrounds — 3 mm, 11% median, dec 1 | Tumut Surrounds — 47 mm, 64% median, dec 4 |
| **Eyre (SA)** | Kimba-Cleve-Franklin Harbour — 10 mm, 60% median, dec 4 | Yorke Peninsula South — 45 mm, 179% median, dec 9 |
| **Murray Lands (SA)** | Mildura Surrounds — 2 mm, 13% median, dec 2 | Murray Bridge Surrounds — 26 mm, 133% median, dec 7 |
| **Yorke and Lower North (SA)** | Wakefield-Barunga West — 8 mm, 28% median, dec 2 | Yorke Peninsula South — 45 mm, 179% median, dec 9 |
| **Northern (SA)** | Wakefield-Barunga West — 8 mm, 28% median, dec 2 | Quorn-Lake Gilles — 7 mm, 100% median, dec 6 |
| **Outer Adelaide (SA)** | Light — 11 mm, 44% median, dec 4 | Kangaroo Island — 45 mm, 135% median, dec 7 |
| **South East (SA)** | Nhill Region — 3 mm, 15% median, dec 1 | Wattle Range — 42 mm, 108% median, dec 6 |
| **Mallee (VIC)** | Swan Hill Surrounds — 1 mm, 3% median, dec 1 | Buloke — 11 mm, 50% median, dec 4 |
| **Wimmera (VIC)** | Nhill Region — 3 mm, 15% median, dec 1 | Southern Grampians — 31 mm, 100% median, dec 6 |
| **Goulburn (VIC)** | Tocumwal-Finley-Jerilderie — 3 mm, 11% median, dec 2 | Benalla Surrounds — 44 mm, 135% median, dec 7 |
| **Central Highlands (VIC)** | Stawell — 12 mm, 52% median, dec 4 | Maryborough Surrounds — 25 mm, 100% median, dec 6 |
| **Loddon (VIC)** | Rushworth — 6 mm, 20% median, dec 2 | Maryborough Surrounds — 25 mm, 100% median, dec 6 |
| **Western District (VIC)** | Stawell — 12 mm, 52% median, dec 4 | Corangamite North — 39 mm, 107% median, dec 6 |
| **Barwon (VIC)** | Gordon (Vic.) — 25 mm, 49% median, dec 3 | Corangamite North — 39 mm, 107% median, dec 6 |
| **Ovens-Murray (VIC)** | Moira — 7 mm, 27% median, dec 2 | Benalla Surrounds — 44 mm, 135% median, dec 7 |
| **Darling Downs (QLD)** | Moree Surrounds * — 0 mm, 0% median, dec 1 | Miles-Wandoan — 6 mm, 40% median, dec 3 |
| **South West (QLD)** | Moree Surrounds * — 0 mm, 0% median, dec 1 | Miles-Wandoan — 6 mm, 40% median, dec 3 |
| **Fitzroy (QLD)** | Roma Surrounds — 0 mm, 0% median, dec 1 | Clermont — 28 mm, 363% median, dec 8 |
| **Mackay (QLD)** | Central Highlands West — 0 mm, 0% median, dec 2 | Clermont — 28 mm, 363% median, dec 8 |

\* "Moree Surrounds" is dominantly a NSW SA2 that has small area overlap with the QLD SDs along the Macintyre River border — listed for completeness of the algorithm, not as a QLD wheat zone.

### What this layer adds to the state-level reads

1. **NSW north–south split is uniform at SD level** — every northern SD (North Western, Northern, Central West) is decile 1–2 for both columns. The state aggregate (29th percentile Jan–Mar in v2 §1) is the **average** of decile 1 north and decile 6 south; neither edge of the state is at the state average.
2. **VIC Mallee is the dominant wet outlier** at decile 10 Jan–Apr. The rest of VIC's wheat country (Western District, Barwon, Central Highlands) is sub-median — the state average is being pulled up by Mallee + Wimmera + Loddon, three SDs that account for ~1.0 Mha (~75%) of VIC wheat area.
3. **WA's "driest May since 2005" framing in v2 §2 holds at all SD levels** but is a **May break in pattern**, not a continuation. WA Apr deciles are 4–9, all near or above median.
4. **SA's record-wet read is wall-to-wall** — every grain SD decile 7–9 for Jan–Apr.
5. **QLD's wheat country (Darling Downs, South West) collapsed in Apr** — these are the SDs where decile 1 Apr matters for production; Fitzroy and Mackay are minor wheat zones where decile 1 Apr is less consequential.

---

## 8. Per-state commentary — May 2026 Crop Report

### Western Australia

Western Australia's cropped area sits at 9.1 Mha, down from 9.2 Mha last year and below the 9.4 Mha record but still historically large. Seeding should finish by late May or early June. April rain was solid (Midlands decile 7), supporting early-sown germination. The dry May has reversed the picture: the inland Midlands and Central — 2.57 Mha, 56% of state wheat area — have had no rain through May 19, and the 8-day outlook delivers only 2–10 mm. Both project to finish May at ~30% of median, decile 1, with soil moisture maps confirming the topsoil drying out. Albany and Esperance project above median. Top-up rain is the watch-point; BOM Jun–Aug shows a 70% chance of below-median rainfall, the strongest national dry signal.

### South Australia

South Australia is the best-placed state nationally as seeding progresses well. Every grain SD finished Jan–Apr at decile 7–9, with Murray Lands at decile 9 (189% of median) and Yorke and Lower North at decile 8, and the May 1–19 read continues that trajectory: Eyre at 44 mm and Murray Lands at 31 mm have already cleared their full-May medians. The BOM 8-day outlook adds another 5–25 mm across the cropping zones, putting every SA grain SD on track to finish May at 110–210% of median. SA2 standouts include Yorke Peninsula South (45 mm in April, decile 9) and Murray Bridge Surrounds (133% of April median). Establishment quality looks the strongest in the country; the watch-point shifts from moisture to input cost and crop-mix decisions in marginal areas.

### Victoria

Victoria is tracking exceptionally well as growers move firmly into seeding. The Mallee SD posted a record-wet Jan–Apr at decile 10 (236% of median), and combined with Wimmera and Loddon accounts for ~1.0 Mha of state wheat area, all decile 8–10. The May 1–19 read at 36 mm in Mallee already clears the 20 mm full-month median, and the BOM 8-day outlook adds 10–20 mm; every Vic grain SD projects to finish May above median, with Mallee at ~255% (decile 10 territory for May standalone), Wimmera and Loddon at 190–220%. SA2s like Buloke, Maryborough Surrounds and Benalla Surrounds confirm the broad-based recovery. Western District and Barwon, drier through April, also project above median on the May front — establishment quality is strong statewide.

### New South Wales

New South Wales has flipped sharply on the May 13–19 front. Northern and North Western SDs — 1.99 Mha combined — were at decile 1–2 through April with profoundly depleted subsoil (Moree Surrounds, Gunnedah, Inverell, Coonabarabran all decile 1 Jan–Apr), but the May front delivered 48 mm to North Western and 70 mm to Central West, and the 8-day outlook adds 5–25 mm. Every NSW grain SD now projects to finish May at 165–300% of median, with Central West NSW topping the country at ~300%. Southern NSW (Murrumbidgee, Murray) projects 195–245% on top of already-above-median subsoil. Growers have stepped up seeding pace on the rain; the bimodal subsoil concern softens for May, though northern profile recharge still depends on Jun–Aug.

### Queensland

Queensland enters May 21 with a much-improved short-term outlook than April suggested. April was decile 1 for both Darling Downs and South West (0–7% of median), but the May 1–19 read has lifted Darling Downs to 16 mm and South West to 13 mm, and the BOM 8-day outlook delivers another 10–20 mm to the wheat-belt SDs. Both Darling Downs and South West now project to finish May at 135–140% of median, recovering most of the seeding-window gap. Growers have stepped up planting on the forecast, narrowing the area risk that v2 §1 flagged under a top-3-driest Apr–May framing. Fitzroy is the national outlier still projecting near median (~90%); Miles–Wandoan and Roma Surrounds remain the driest SA2s in the cropping zone.

---

## Methodology and caveats

- **Rainfall data:** SILO monthly + daily NetCDF, extracted at ABS SA2 centroids (~190 grain SA2s nationally), area-weighted by 2020-21 ABS wheat area census. Coverage through 2026-05-19. §7 SD-level aggregation uses the ABS SA2_2021 → SD_2011 area-overlay concordance with SA2 wheat area × allocation_ratio as the weight; SD-level historical medians are recomputed from the same SA2 set across 2005–2025. §7 STD and Apr columns are full-month observed; the May MTD block adds the partial 19-day observation and overlays BOM PME 8-day forecast maps (`/fwo/IDYPME04/.../pme1to4.png` + `pme5to8.png`, issued 20/05/2026, covering 21–28 May) read visually at SD centroids — precision ±5 mm.
- **Production data:** ABARES Australian Crop Report March 2026 (No. 217); state-level Area and Production 1989–2025, derived Yield.
- **Area assumption:** 2026 planted area held at 2025 ABARES levels. In dry-start years WA growers historically cut wheat area (2017 4.06 Mha vs 2024 4.70 Mha). If WA reduces area 5–10%, national implied production drops ~0.5–1.0 Mt.
- **Analogue method:** 2-window joint distance on standardised (Jan–Mar, Apr–May); top-3 nearest historical years per state. See `docs/analogue_method.md`. Yields in the analogue set are from completed (booked) ABARES seasons.
- **BOM probabilities:** Read from the BOM Jun–Aug 2026 chance-of-above-median rainfall map at each state's grain belt centroid; ±5 pp confidence band on each value.
- **2025 yields were exceptionally high** (NSW 3.11, WA 3.01, SA 2.37 t/ha) — well above any of our analogue years. Some of that reflects improved varieties and agronomy not visible in pre-1990s data; analogue yields may slightly under-state what 2026 could deliver under modern agronomy with similar weather.
- **The 5th and 6th-percentile rainfall analogue framing applies to recorded SA2-level rainfall 2005-onwards. Pre-2005 SA2-level rainfall is not in our canonical dataset.**

---


*Sources: SILO Patched Point Dataset (LongPaddock/DAF), ABS Agricultural Census 2020-21 SA2-level crop data, ABARES Australian Crop Report March 2026, Bureau of Meteorology 3-month outlook 2026-Q3.*

*Compiled by CropForecaster (wheatbelt_rainfall_analyser) · Week 21, 2026.*
