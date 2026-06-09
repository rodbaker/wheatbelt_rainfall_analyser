"""Consume crop-forecast's ``region_reference.csv`` -- the BEN Agri SD
``region_code`` source of truth -- as the ``sd_region`` validation gate.

crop-forecast owns the ``region_code`` vocabulary (e.g. ``WA_MIDLANDS``). This
module loads the vendored copy (``data/meta/region_reference.csv``) and validates
that any ``sd_region`` we emit is a known member, so emitted codes cannot drift
(Phase 2, contract ``swp-1``; spec 5.9 / 8).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Optional, Set, Union

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGION_REFERENCE_PATH = REPO_ROOT / "data" / "meta" / "region_reference.csv"

REQUIRED_COLUMNS = ["region_code", "state", "region_name", "region_level"]


class UnknownRegionError(ValueError):
    """Raised when an ``sd_region`` is not a member of the region_reference set."""


def load_region_reference(
    path: Optional[Union[str, Path]] = None,
) -> Set[str]:
    """Load region_reference.csv and return the set of valid ``region_code`` strings.

    Raises ``FileNotFoundError`` if the file is absent, and ``ValueError`` if a
    required column is missing or the file yields no codes.
    """
    path = Path(path) if path is not None else DEFAULT_REGION_REFERENCE_PATH
    if not path.exists():
        raise FileNotFoundError(f"region_reference not found: {path}")

    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            raise ValueError(
                f"region_reference {path} missing required columns: {missing}"
            )
        codes = {
            row["region_code"].strip()
            for row in reader
            if (row.get("region_code") or "").strip()
        }

    if not codes:
        raise ValueError(f"region_reference {path} contains no region_code rows")
    return codes


def assert_sd_known(sd_region: str, ref: Iterable[str]) -> None:
    """Raise ``UnknownRegionError`` if ``sd_region`` is not in the reference set."""
    if sd_region not in set(ref):
        raise UnknownRegionError(
            f"unknown sd_region {sd_region!r}: not in region_reference"
        )
