#!/usr/bin/env bash
# One-off bulk-data relocation to the HDD (/mnt/d).
# Option C: symlink bulky read-mostly dirs/files to a store on D:.
# Copies -> verifies (count + bytes + sha256) -> renames original to .bak-premigrate
# -> symlinks -> read-tests. Does NOT delete backups; that is a separate pass.
#
# Usage:
#   scripts/_migrate_bulk_to_hdd.sh migrate    # copy+verify+symlink+readtest (idempotent-ish)
#   scripts/_migrate_bulk_to_hdd.sh cleanup    # delete *.bak-premigrate AFTER you have verified
set -euo pipefail

REPO="/home/roddyb/projects/wheatbelt_rainfall_analyser"
DEST_BASE="/mnt/d/grains-data-store/wheatbelt_rainfall_analyser"
cd "$REPO"

# Relative paths to relocate (dirs and individual files), all under data/.
ITEMS=(
  "data/meta/monthly_rain"
  "data/meta/max_temp"
  "data/meta/daily_rain"
  "data/external"
  "data/meta/shapefiles/SA2_2021_AUST_SHP_GDA2020.zip"
  "data/meta/shapefiles/clum_commodities_2023.zip"
  "data/meta/shapefiles/1270055006_CG_SA2_2011_SD_2011.zip"
)

hash_tree() {  # deterministic combined checksum of a path (dir or file)
  local p="$1"
  if [ -d "$p" ]; then
    find "$p" -type f -print0 | sort -z | xargs -0 sha256sum | awk '{print $1}' | sha256sum | awk '{print $1}'
  else
    sha256sum "$p" | awk '{print $1}'
  fi
}

bytes_of() { du -sb "$1" | awk '{print $1}'; }
count_of() { if [ -d "$1" ]; then find "$1" -type f | wc -l; else echo 1; fi; }

migrate_one() {
  local rel="$1"
  local src="$REPO/$rel"
  local dst="$DEST_BASE/$rel"

  if [ -L "$src" ]; then
    echo "SKIP  $rel  (already a symlink -> $(readlink "$src"))"
    return 0
  fi
  if [ ! -e "$src" ]; then
    echo "WARN  $rel  (source missing, skipping)"
    return 0
  fi

  echo "----------------------------------------------------------------"
  echo "MIGRATE  $rel"
  local s_bytes s_count s_hash
  s_bytes=$(bytes_of "$src"); s_count=$(count_of "$src"); s_hash=$(hash_tree "$src")
  echo "  source : ${s_count} files, ${s_bytes} bytes, sha=${s_hash:0:16}…"

  mkdir -p "$(dirname "$dst")"
  rm -rf "$dst"                 # clean any partial prior copy
  cp -a "$src" "$dst"

  local d_bytes d_count d_hash
  d_bytes=$(bytes_of "$dst"); d_count=$(count_of "$dst"); d_hash=$(hash_tree "$dst")
  echo "  dest   : ${d_count} files, ${d_bytes} bytes, sha=${d_hash:0:16}…"

  if [ "$s_count" != "$d_count" ] || [ "$s_bytes" != "$d_bytes" ] || [ "$s_hash" != "$d_hash" ]; then
    echo "  FAIL   verification mismatch — leaving original untouched, removing bad copy"
    rm -rf "$dst"
    return 1
  fi
  echo "  OK     count+bytes+sha256 all match"

  mv "$src" "${src}.bak-premigrate"
  ln -s "$dst" "$src"
  echo "  LINK   $rel -> $dst   (original kept as ${rel}.bak-premigrate)"
}

readtest() {
  echo "----------------------------------------------------------------"
  echo "READ-TEST through symlinks"
  .venv/bin/python - <<'PY'
import xarray as xr, zipfile, glob, sys
ok = True
# NetCDF read through monthly_rain symlink
f = sorted(glob.glob("data/meta/monthly_rain/*.nc"))[-1]
ds = xr.open_dataset(f); _ = ds.monthly_rain.isel(time=0).values
print(f"  netcdf  {f}: shape {ds.monthly_rain.shape} OK")
# zip read through shapefile symlink
z = "data/meta/shapefiles/SA2_2021_AUST_SHP_GDA2020.zip"
n = len(zipfile.ZipFile(z).namelist())
print(f"  zip     {z}: {n} members OK")
sys.exit(0 if ok else 1)
PY
}

case "${1:-}" in
  migrate)
    for it in "${ITEMS[@]}"; do migrate_one "$it"; done
    readtest
    echo "================================================================"
    echo "DONE migrate+verify+link+readtest. Backups kept as *.bak-premigrate."
    echo "Run with 'cleanup' to delete backups once you are satisfied."
    ;;
  cleanup)
    for it in "${ITEMS[@]}"; do
      b="$REPO/${it}.bak-premigrate"
      if [ -e "$b" ]; then echo "RM  ${it}.bak-premigrate"; rm -rf "$b"; fi
    done
    echo "Backups removed."
    ;;
  *)
    echo "usage: $0 {migrate|cleanup}"; exit 2;;
esac
