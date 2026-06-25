#!/usr/bin/env python3
"""Build a cropland-fraction grid aligned to the SILO 0.05° rainfall grid.

Source: ABARES "Catchment Scale Land Use of Australia – Update December 2023",
50 m national land-use raster (clum_50m_2023_v2.tif, ALUM-coded UInt16).
  data.gov.au DOI 10.25814/2w2p-ph98
  https://data.gov.au/data/dataset/8af26be3-da5d-4255-b554-f615e950e46d
        /resource/6deab695-3661-4135-abf7-19f25806cfd7/download/clum_50m_2023_v2.zip

"All cropland combined" = ALUM secondary classes 3.3 Cropping (dryland, codes
330–339) AND 4.3 Irrigated cropping (430–439). This is NOT wheat-specific —
ALUM cannot separate wheat from barley/canola/pulses at the raster level; for
WA/SA/Vic the dryland class is effectively winter broadacre, while nationally it
also includes summer crops (cotton, sugar). For wheat specifically, use the SA2
wheat-area weighting instead.

Pipeline (GDAL CLI; no Python raster bindings required):
  1. gdalwarp  50 m  -> 1 km dominant class (mode), grain-belt extent
  2. gdal_calc reclassify to a 0/1 cropland binary
  3. gdalwarp  1 km  -> 0.05° with -r average  => cropland FRACTION per cell,
     on the exact SILO grid (-te/-tr below), Float32 (Byte would truncate to 0/1)
  4. gdal_translate -> NetCDF for downstream use

Output: data/meta/clum_cropfrac_005.nc  (Band1 = cropland fraction 0–1)

Usage:
  python scripts/build_clum_cropfrac.py --clum-tif /path/to/clum_50m_2023_v2.tif
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/meta/clum_cropfrac_005.nc"
DEFAULT_TIF = ("/mnt/d/grains-data-store/wheatbelt_rainfall_analyser/data/meta/"
               "shapefiles/clum_50m_2023/clum_50m_2023_v2/clum_50m_2023_v2.tif")

# SILO 0.05° grid: cell centres 112.0..154.0 lon, -44.0..-10.0 lat → edges below
TE = ["111.975", "-44.025", "154.025", "-9.975"]
# All cropland: dryland cropping (3.3 = 330–339) + irrigated cropping (4.3 = 430–439)
CALC = "((((A>=330)*(A<=339))+((A>=430)*(A<=439)))>0).astype(numpy.uint8)"


def run(cmd):
    print("›", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clum-tif", default=DEFAULT_TIF,
                    help="path to clum_50m_2023_v2.tif")
    args = ap.parse_args()
    tif = Path(args.clum_tif)
    if not tif.exists():
        raise SystemExit(f"CLUM raster not found: {tif}\n"
                         "Download clum_50m_2023_v2.zip from ABARES (see header).")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        km, binary, frac = td / "clum_1km.tif", td / "crop_1km.tif", td / "frac.tif"

        run(["gdalwarp", "-overwrite", "-t_srs", "EPSG:4326",
             "-te", *TE, "-tr", "0.01", "0.01", "-r", "mode",
             "-co", "COMPRESS=DEFLATE", tif, km])
        run(["gdal_calc.py", "-A", km, "--calc", CALC, "--outfile", binary,
             "--type", "Byte", "--NoDataValue", "255", "--quiet", "--overwrite"])
        run(["gdalwarp", "-overwrite", "-ot", "Float32", "-te", *TE,
             "-tr", "0.05", "0.05", "-r", "average", "-srcnodata", "255",
             "-dstnodata", "-1", "-co", "COMPRESS=DEFLATE", binary, frac])
        OUT.parent.mkdir(parents=True, exist_ok=True)
        run(["gdal_translate", "-of", "netCDF", frac, OUT])

    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
