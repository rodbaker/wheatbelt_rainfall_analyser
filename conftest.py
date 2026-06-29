"""Root conftest.py — adds the repo root to sys.path so that
``import scripts.xxx`` works from any test regardless of how pytest is
invoked (i.e. whether or not the package is installed in editable mode).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
