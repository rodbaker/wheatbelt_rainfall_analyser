# CLUM Commodities 2023 — Area Summary

**Source zip**: `/home/roddyb/projects/wheatbelt_rainfall_analyser/data/meta/shapefiles/clum_commodities_2023.zip`
**Inner shapefile**: `CLUM_Commodities_2023/CLUM_Commodities_2023.shp`
**CRS**: EPSG:4283
**Total features**: 176,054
**Fields**: OBJECTID, Commod_dsc, Broad_type, Source_yr, State, Area_ha, Lucodev8n, Date, Tertiary, geometry

## Interpretation

CLUM is land-use/commodity context only. Do not use to validate or replace:
ABS Agricultural Census, ABS modernised satellite area, ACF, or ABARES estimates.
Source_yr values are mixed across polygons — not all represent 2023 data.

**Area method**: `Area_ha` was used as supplied in the shapefile attribute table.
Geometry area was NOT recalculated from GDA94 geographic coordinates (EPSG:4283).
Recalculating from degrees would be incorrect without first reprojecting to a
equal-area CRS — use the supplied field only.

## Area by Broad Type (ha)

| Broad_type | Area_ha |
|---|---|
| Animals | 61,494,361.4 |
| Other crops | 929,110.8 |
| Fruits | 393,363.8 |
| Cereals | 128,873.8 |
| Nuts | 74,266.9 |
| Pulses | 27,461.6 |
| Vegetables and herbs | 27,228.0 |
| Forest | 16,994.7 |
| Flowers and bulbs | 7,272.1 |
| Oilseeds | 3,728.9 |
| Pasture | 2,405.2 |
| Mines | 36.3 |

**Total Area_ha (source)**: 63,105,103.5
**Total Area_ha (grouped)**: 63,105,103.5
**Difference**: 0.0000 ha (rounding only — within tolerance if < 1 ha)

## Feature Counts by Source Year

| Source_yr | Features |
|---|---|
| 1967 | 3 |
| 1968 | 18 |
| 1969 | 21 |
| 1970 | 5 |
| 1971 | 74 |
| 1972 | 2 |
| 1973 | 39 |
| 1979 | 325 |
| 1980 | 4 |
| 1983 | 15 |
| 1984 | 45 |
| 1985 | 76 |
| 1986 | 12 |
| 1987 | 1 |
| 1997 | 122 |
| 2002 | 2 |
| 2007 | 2 |
| 2008 | 42 |
| 2009 | 56 |
| 2010 | 371 |
| 2011 | 182 |
| 2012 | 1,415 |
| 2013 | 596 |
| 2014 | 1,522 |
| 2015 | 22,167 |
| 2016 | 65,257 |
| 2017 | 63,440 |
| 2018 | 703 |
| 2019 | 1,012 |
| 2020 | 2,831 |
| 2021 | 5,228 |
| 2022 | 4,551 |
| 2023 | 5,915 |

## Output CSV

Columns: state, broad_type, commodity, source_year, feature_count, area_ha
Rows: 772
