"""Load the explicit guide-crop -> BEN Agri commodity map (spec 7.2).

Explicit table, never fuzzy. Maps DPIRD guide crop names (e.g. "Wheat") to BEN
Agri commodity codes (e.g. ``wheat_incl_durum``). Dropped/out-of-scope crops live
under a separate ``dropped:`` key and are never resolved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Union

import yaml


def load_guide_commodity_map(path: Union[str, Path]) -> Dict[str, str]:
    """Return the guide-crop -> BEN Agri commodity mapping (the ``map:`` section)."""
    with open(path) as fh:
        doc = yaml.safe_load(fh) or {}
    mapping = doc.get("map") or {}
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError(f"guide_commodity_map {path}: missing or empty 'map:' section")
    return dict(mapping)


def resolve_commodity(guide_crop: str, mapping: Dict[str, str]) -> str:
    """Resolve a guide crop name to its BEN Agri commodity code.

    Raises ``KeyError`` on any unmapped crop -- explicit-only, never fuzzy.
    """
    if guide_crop not in mapping:
        raise KeyError(
            f"guide crop {guide_crop!r} has no BEN Agri commodity mapping "
            f"(unmapped or explicitly dropped)"
        )
    return mapping[guide_crop]
