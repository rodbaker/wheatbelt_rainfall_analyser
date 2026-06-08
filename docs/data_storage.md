# Data storage layout — bulk data on HDD

**Migrated 2026-06-01.** Bulky, read-mostly data directories are stored on the
HDD at `/mnt/d` (1.8 TB free) and **symlinked** back into `data/`. The active
operational store stays on the local ext4 filesystem.

This is "Option C": symlink now, with the option to add a configurable
`BULK_DATA_ROOT` later if the project ever needs to run on another machine.
All scripts continue to use the original `data/...` paths unchanged — the
symlinks make the relocation transparent.

## What lives where

**On the HDD** (`/mnt/d/grains-data-store/wheatbelt_rainfall_analyser/data/...`,
reached via symlinks):

| Path | What |
|---|---|
| `data/meta/monthly_rain/` | SILO monthly rainfall grids (NetCDF) |
| `data/meta/max_temp/` | SILO max-temp grid (NetCDF) |
| `data/meta/daily_rain/` | SILO daily rainfall grids (NetCDF, re-pulled on refresh) |
| `data/external/` | Large external NetCDF reference (~850 MB) |
| `data/meta/shapefiles/*.zip` | Archived boundary/commodity download ZIPs |

**Stays local** (fast ext4, never symlinked off):

- `data/weather.duckdb` — DuckDB does memory-mapped IO + file locking that is
  unreliable over the Windows drive mount (`drvfs`). **Never move this to D:.**
- `data/obs/`, `data/derived/`, `data/features/`, `data/interim/`, `data/exports/`
  — frequently rewritten; small-file random writes are slow on drvfs.
- `data/meta/shapefiles/STE_2021_AUST_GDA2020/` — WA outline, used unzipped, small.
- Source code, `.venv`, `.git`, caches.

## Dependency & caveats

- **The symlinks dangle if `/mnt/d` is not mounted** (e.g. the repo is opened on
  another machine, or the drive is offline). The grids are all re-downloadable
  from SILO, so this is recoverable, not fatal.
- Check the links resolve with: `ls -la data/meta/monthly_rain` (should show
  `-> /mnt/d/grains-data-store/...`).
- NetCDF reads over drvfs benchmark the same as local (~0.4 s for a 14 MB grid);
  bulk sequential reads are fine on the HDD.
- The symlinks and the `*.bak-premigrate` backups are gitignored (covered by the
  existing bulk-data patterns), so git status stays clean.

## daily_rain re-pull safety (downloader hardened 2026-06-01)

`data/meta/daily_rain/` is re-pulled during SILO refresh, so it is the one
relocated path with active write behaviour. `scripts/download_silo_daily_rain.py`
has been hardened (TDD, see `tests/test_download_silo_daily_rain.py`):

1. Writes to a temp file **inside `daily_rain/`** (so temp + final are both on
   `/mnt/d` and the rename stays intra-filesystem).
2. **Validates** the NetCDF (variable + lat/lon dims + time coords, and full-year
   completeness unless `--skip-validate`) — *before* `os.replace()`.
3. On success, `os.replace()` swaps the temp over the prior file (atomic).
4. On validation failure or fetch error, **preserves the existing final file**
   and removes the temp. A bad download can never clobber a good grid.

A `--replace` flag now re-downloads + validates + atomically swaps an existing
file, retiring the old manual "move the `.bak` aside first" workaround.

**Still keep `data/meta/daily_rain.bak-premigrate/` until one real SILO refresh
through the hardened downloader has succeeded** (the tests use fixtures, not the
live S3 fetch). Once a real `--replace` refresh lands cleanly, delete that backup
to reclaim the last 485 MB. The other six originals were already deleted after
checksum + read verification.

## Migration / rollback tool

`scripts/_migrate_bulk_to_hdd.sh`:

- `migrate` — copy → verify (count + bytes + sha256) → rename original to
  `*.bak-premigrate` → symlink → read-test. Leaves backups in place.
- `cleanup` — deletes **all** `*.bak-premigrate` backups indiscriminately.
  ⚠️ Do **not** run this until the daily_rain follow-up is done — it would
  remove `daily_rain.bak-premigrate` too. The other backups were deleted
  individually on 2026-06-01, not via this command.

To roll back a directory: copy it from `/mnt/d/grains-data-store/...` back into
`data/`, remove the symlink, and restore the real directory in place.
