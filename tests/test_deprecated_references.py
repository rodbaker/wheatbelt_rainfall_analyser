"""Ensure no live files reference deprecated ingest pipeline paths."""
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEPRECATED_PATHS = [
    "scripts/daily_ingest.py",
    "scripts/backfill_historical.py",
    "src/data/silo_ingest.py",
]

SCAN_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".sh", ".rst", ".toml"}

EXCLUDE_DIRS = {"archive", ".git", "docs", "tests"}


def _candidate_files():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.name == "task_manager.md":
            continue
        if path.suffix in SCAN_SUFFIXES:
            yield path


class TestNoDeprecatedReferences(unittest.TestCase):

    def test_no_deprecated_references(self):
        hits = []
        for candidate in _candidate_files():
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for dep in DEPRECATED_PATHS:
                if dep in text:
                    hits.append(f"{candidate.relative_to(REPO_ROOT)}: references '{dep}'")
        self.assertFalse(hits, "Deprecated path references found:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
