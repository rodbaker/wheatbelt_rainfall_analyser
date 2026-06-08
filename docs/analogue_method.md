# Wheat Yield Analogue Method

## Overview

`scripts/run_yield_analogue.py` selects historical analogue years by matching
area-weighted seasonal rainfall windows against a target year, then uses ABARES
state-level wheat area data to produce implied production estimates.

---

## Seasonal Windows

Three rainfall windows are defined to capture distinct agronomic phases of the
Australian wheat season:

| Window | Months | Agronomic role |
|--------|--------|----------------|
| `jan-mar` | January–March | Summer moisture storage. Pre-sowing rain determines soil moisture recharge and drives early establishment in lower-rainfall zones. Strong summer rain (particularly in NSW and QLD) can improve subsoil moisture that persists through the growing season. |
| `apr-may` | April–May | Seeding rain. The autumn break triggers sowing decisions. Germination rain in April–May sets plant density and early tiller counts. Dry autumns delay sowing, reduce effective growing season, and constrain final yield potential. |
| `jun-oct` | June–October | In-crop growth rain. Covers the entire vegetative and reproductive phase for most of the wheatbelt. Rainfall during stem elongation (Aug–Sep) and grain fill (Sep–Oct) is particularly yield-critical. |

---

## Analogue Selection Algorithm

### 2-Window Mode (default)

Distance is computed using standardised Euclidean distance on `jan_mar` and
`apr_may` values:

1. For each state, compute area-weighted mean rainfall per window per year.
2. Standardise each window using the mean and standard deviation of historical
   years (all years < target year with non-null window data).
3. Compute Euclidean distance between the target year and each historical year
   in standardised 2D space.
4. Return the top-3 nearest years as analogues.

### 3-Window Mode — Complete Year (Case B)

When all three windows are available for the target year (e.g. running
retrospectively for 2024), the same procedure is applied in 3D standardised
space:

```
distance = sqrt(
    ((jan_mar_target - jan_mar_hist) / std_jan_mar)^2 +
    ((apr_may_target - apr_may_hist) / std_apr_may)^2 +
    ((jun_oct_target - jun_oct_hist) / std_jun_oct)^2
)
```

### 3-Window Mode — Conditional (Case A, current year)

When the target year has no Jun-Oct data (e.g. running in May 2026, before the
winter crop season is underway):

1. Analogues are selected on (jan-mar, apr-may) only — same as 2-window mode.
2. For each of the 3 analogue years, the historical Jun-Oct rainfall is looked
   up. This gives a range of plausible in-crop rainfall outcomes.
3. Implied production is reported as **low / mid / high** corresponding to the
   analogue year with lowest / mean / highest Jun-Oct rainfall.
4. The script prints a note: *"Jun-Oct data not yet available. Showing Jun-Oct
   dispersion across (jan-mar, apr-may) analogues."*

This approach is conservative — it does not extrapolate Jun-Oct, but instead
reports the uncertainty range that the confirmed analogues carry.

---

## Implied Production

For each state and each analogue year:

```
yield_analogue_yr = production_t / area_ha   (from ABARES)
mean_yield = average of analogue year yields
implied_production_mt = mean_yield × area_2025_ha / 1,000,000
```

The 2025 ABARES area is used as the base (status: `forecast` in the March 2026
bulletin). This is appropriate because the 2026 season is sown into the same
paddocks; structural area change within one year is small relative to yield
variation.

---

## Partial May Handling

The canonical monthly rainfall CSV (`sa2_monthly_rainfall_history_national.csv`)
includes May 2026 as a **partial month** (`is_partial_month=True`,
`partial_month_through_day=19`).

- **Historical baseline**: Partial months are excluded. Only full months are used
  to compute state means and standard deviations. This prevents bias from
  comparing 19-day May accumulations against full-month historical values.
- **Target year**: The partial May row is included as-is for the target year.
  Because both Jan-Mar and Apr-May windows for 2026 use the same partial-month
  exclusion rule for history, the target year's Apr-May value (which includes a
  partial May) is still compared against a distribution of **full-month** Apr-May
  values from history. This slightly understates 2026 Apr-May relative to
  history, which makes the analogue selection conservative (the actual full-month
  May will be ≥ the partial value, so analogues may shift when May completes).

---

## ABARES crop_season Alignment

ABARES uses financial-year labels (e.g. `1989–90`, season `1989/90`) but the
`crop_season` integer column records the **calendar year of sowing** (e.g. 1989).

Australian wheat is sown in autumn (May–June) and harvested in November–January.
Both sowing and the bulk of the growing season fall in the same calendar year as
the financial-year start. The harvest technically crosses into the next calendar
year, but ABARES attributes the full season's production to the sowing year.

**No offset is needed.** `ABARES.crop_season == rainfall_data.year` is the
correct join.

Verification example: NSW 2022 (`crop_season=2022`) corresponds to the 2022–23
financial year. ABARES reports NSW wheat production of approximately 14.2 Mt for
that year. The SA2 monthly rainfall history for 2022 (Jan-Oct 2022) reflects the
same season. The join `crop_season=2022, rainfall.year=2022` is correct.

---

## State Coverage

| State | SA2 rainfall data | ABARES data | Notes |
|-------|-------------------|-------------|-------|
| NSW   | Yes | Yes | |
| WA    | Yes | Yes | |
| SA    | Yes | Yes | |
| VIC   | Yes | Yes | |
| QLD   | Yes | Yes | |
| TAS   | No  | Yes | No SA2 rainfall data; omitted from state output |

Tasmania has negligible wheat production and no SA2 entries in
`data/meta/crop_context_sa2.csv`. It is excluded from analogue selection but
could be added to the national total using ABARES production directly if needed.

---

## Output Files

| File | Description |
|------|-------------|
| `data/features/wheat_yield_analogue_summary.csv` | Per-state analogue years, distances, implied production |

### Column reference (2-window mode)

| Column | Description |
|--------|-------------|
| `state` | State name |
| `target_year` | Analysis year |
| `windows_used` | Comma-separated window names used for selection |
| `analogue_year_1/2/3` | Top-3 nearest historical years (nearest first) |
| `dist_1/2/3` | Standardised Euclidean distance for each analogue |
| `mean_analogue_yield_t_ha` | Mean yield across analogue years |
| `implied_production_mt` | Implied state production (megatonnes) |
| `area_2025_ha` | 2025 ABARES wheat area used as base |

### Additional columns (3-window conditional / dispersion mode)

| Column | Description |
|--------|-------------|
| `jun_oct_low_mm` | Lowest Jun-Oct rainfall among analogue years |
| `jun_oct_high_mm` | Highest Jun-Oct rainfall among analogue years |
| `implied_production_low_mt` | Production implied by lowest Jun-Oct analogue |
| `implied_production_mid_mt` | Production implied by mean of analogue yields |
| `implied_production_high_mt` | Production implied by highest Jun-Oct analogue |
