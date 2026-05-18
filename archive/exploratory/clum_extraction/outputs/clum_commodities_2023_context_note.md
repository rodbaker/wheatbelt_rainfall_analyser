# CLUM Commodities 2023 — Analyst Context Note

This note explains how to use the extracted CLUM commodity area outputs safely.
It is not a data quality assessment and does not compare CLUM against any other
area source.

**Related outputs (same directory):**
- `clum_commodities_2023_area_by_state.csv` — 772 grouped rows
- `clum_commodities_2023_area_summary.md` — QA summary and field inventory

---

## What was extracted

176,054 polygon features were read directly from the CLUM Commodities December 2023
release (ABARES). Area conservation is exact: the sum of `Area_ha` across all 772
grouped rows equals the sum across all 176,054 source features (difference: 0.0 ha).

**Area_ha was used as supplied in the shapefile attribute table.** Geometry area was
not recalculated from GDA94 geographic coordinates (EPSG:4283). Recalculating from
degrees would require reprojecting to an equal-area CRS first — the supplied field
is the correct value to use.

Total extracted area: **63,105,103.5 ha** across all states and territories.

---

## Source vintage warning

Despite being labelled "December 2023", the majority of CLUM polygons carry earlier
survey dates. Source year is recorded per polygon in the `Source_yr` field:

| Source_yr range | Features | Share |
|---|---|---|
| 2015–2017 | 150,864 | 86% |
| 2018–2022 | 14,673 | 8% |
| 2023 | 5,915 | 3% |
| Pre-2015 | 4,602 | 3% |

The "2023" in the dataset name reflects the release date, not the field survey date
for most polygons. When using CLUM to characterise land use in a particular year,
note that most polygons reflect conditions from 2015–2017.

---

## Commodity scope and scale

CLUM captures the full range of agricultural land uses, not just broadacre crops.
By area, the layer is dominated by pastoral land:

| Broad_type | Area_ha |
|---|---|
| Animals | 61,494,361.4 |
| Other crops | 929,110.8 |
| Fruits | 393,363.8 |
| Cereals | 128,873.8 |
| Pulses | 27,461.6 |
| Oilseeds | 3,728.9 |
| *(all other types)* | *118,169.4* |

The cereal (129K ha), pulse (27K ha), and oilseed (4K ha) totals in CLUM are a
small fraction of national broadacre areas reported by ABS, ACF, or ABARES. This
is expected: CLUM is not a census or survey instrument. Its polygon coverage of
broadacre cropping is partial — it does not attempt comprehensive annual crop
mapping across the wheatbelt.

---

## Recommended use

**Use CLUM for:**
- Identifying which commodity categories are present in the land-use layer for a
  given state or region.
- Understanding broad land-use type and approximate vintage for context.
- Noting source-definition differences when discussing why area estimates from
  different sources diverge (e.g. CLUM uses land-use polygons; ABS uses
  agricultural census returns; ACF uses remote sensing).

**Do not use CLUM for:**
- Validating, correcting, scaling, or replacing area estimates from ACF, ABS
  Agricultural Census, ABS modernised satellite area, or ABARES.
- Inferring that a discrepancy between CLUM and another source indicates an error
  in either source — they measure different things with different methods.
- Joining CLUM into ACF-vs-ABS ratio tables unless every output column derived
  from that join is explicitly labelled non-comparable context.
- Treating the 2023 release date as evidence that polygon extents reflect
  2023 land use; most polygons are 2015–2017 vintage.

---

## Source

ABARES, *Catchment Scale Land Use of Australia — Commodities, December 2023*.
CRS: GDA94 geographic (EPSG:4283). Downloaded from data.gov.au.
Extraction script: `scripts/extract_clum_commodity_areas.py`
