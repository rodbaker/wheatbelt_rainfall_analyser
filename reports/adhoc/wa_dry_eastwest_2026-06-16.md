/home/roddyb/projects/wheatbelt_rainfall_analyser/scripts/wa_dry_sd_eastwest.py:39: UserWarning: Geometry is in a geographic CRS. Results from 'centroid' are likely incorrect. Use 'GeoSeries.to_crs()' to re-project geometries to a projected CRS before this operation.

  cent = gdf.geometry.centroid  # already EPSG:4326; fine for relative lon

## Midlands (WA) — 10 wheat SA2s, 2104 kha — west→east
| SA2 | Lon°E | Wheat kha | May→MTD mm | Mar→MTD dec (%med) | May→MTD dec (%med) |
|---|---:|---:|---:|---:|---:|
| Gingin - Dandaragan | 115.65 | 35 | 118 | 8.6 (161%) | 9.0 (162%) |
| Chittering | 116.15 | 13 | 106 | 8.6 (177%) | 9.5 (148%) |
| Toodyay | 116.46 | 15 | 63 | 7.6 (134%) | 8.1 (128%) |
| Moora | 116.54 | 415 | 71 | 8.6 (166%) | 10.0 (220%) |
| Northam | 116.69 | 25 | 51 | 7.6 (157%) | 6.7 (116%) |
| York - Beverley | 116.87 | 49 | 44 | 6.7 (127%) | 5.2 (99%) |
| Dowerin | 117.10 | 400 | 56 | 9.0 (169%) | 9.5 (160%) |
| Cunderdin | 117.47 | 207 | 44 | 6.2 (126%) | 7.1 (128%) |
| Merredin | 118.38 | 356 | 63 | 8.1 (136%) | 9.5 (221%) |
| Mukinbudin | 118.50 | 589 | 65 | 8.6 (147%) | 9.5 (265%) |
  _WEST half: area-wtd May→MTD decile = 9.7 (lon 115.65-116.69)_
  _EAST half: area-wtd May→MTD decile = 9.1 (lon 116.87-118.50)_

## Upper Great Southern (WA) — 3 wheat SA2s, 500 kha — west→east
| SA2 | Lon°E | Wheat kha | May→MTD mm | Mar→MTD dec (%med) | May→MTD dec (%med) |
|---|---:|---:|---:|---:|---:|
| Wagin | 117.07 | 40 | 52 | 7.6 (110%) | 3.8 (72%) |
| Brookton | 117.35 | 90 | 50 | 5.7 (113%) | 3.3 (83%) |
| Kulin | 118.72 | 369 | 49 | 5.2 (97%) | 8.1 (127%) |
  _WEST half: area-wtd May→MTD decile = 3.5 (lon 117.07-117.35)_
  _EAST half: area-wtd May→MTD decile = 8.1 (lon 118.72-118.72)_

## Lower Great Southern (WA) — 4 wheat SA2s, 320 kha — west→east
| SA2 | Lon°E | Wheat kha | May→MTD mm | Mar→MTD dec (%med) | May→MTD dec (%med) |
|---|---:|---:|---:|---:|---:|
| Kojonup | 117.35 | 62 | 84 | 8.1 (129%) | 8.6 (122%) |
| Katanning | 117.54 | 31 | 48 | 6.2 (113%) | 4.8 (82%) |
| Plantagenet | 117.74 | 15 | 97 | 8.1 (143%) | 9.0 (148%) |
| Gnowangerup | 118.63 | 213 | 24 | 3.8 (89%) | 1.4 (60%) |
  _WEST half: area-wtd May→MTD decile = 7.3 (lon 117.35-117.54)_
  _EAST half: area-wtd May→MTD decile = 1.9 (lon 117.74-118.63)_
