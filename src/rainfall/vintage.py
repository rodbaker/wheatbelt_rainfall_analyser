"""Report data/method vintage pins and consistency guards (v1).

A pinned report carries a reader-visible fenced ``vintage`` block placed
directly under its title::

    ```vintage
    status: frozen            # frozen | live
    report_date: 2026-05-20
    coverage_month: 2026-05
    through_day: 19
    baseline_years: [2005, 2025]
    decile_method: ratio_div10_v0   # optional; omit if no decile is quoted
    inputs:                          # required for live, optional for frozen
      - data/features/sa2_2026_05_mtd.csv
    ```

Lifecycle model:

* ``frozen`` -- a dated as-published artifact. Checked only for **internal
  consistency**: the surrounding prose must agree with the block's own declared
  vintage (coverage day + decile method). Never compared to current inputs, so
  it never has to be rewritten when inputs later refresh.
* ``live`` -- expected to track current inputs. Additionally checked against the
  current input vintage (``partial_month_through_day``) and the current decile
  method/baseline. Fixture-tested only in v1; no real report is marked live.

The guard is enforced by ``tests/test_vintage_consistency.py``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import yaml

# --- method registry --------------------------------------------------------
# ``forbidden_prose`` are substrings that must NOT appear in a report whose
# block declares this method -- they describe a different (older) method.
DECILE_METHODS = {
    "rank_ceil_v1": {
        "description": "Canonical rank-based decile: ceil((#below+1)/n*10), clamped 1-10.",
        "forbidden_prose": ["÷ 10", "÷10", "/ 10"],
    },
    "ratio_div10_v0": {
        "description": "Legacy: percentile rank ÷ 10 (floor), 0-10 scale.",
        "forbidden_prose": [],
    },
}

DECILE_METHOD_ID = "rank_ceil_v1"
BASELINE_YEARS = [2005, 2025]

VALID_STATUS = {"frozen", "live"}
REQUIRED_FIELDS = ("status", "report_date", "coverage_month", "through_day", "baseline_years")

# --- block parsing ----------------------------------------------------------
_VINTAGE_FENCE_RE = re.compile(r"```vintage[ \t]*\n(.*?)\n```", re.DOTALL)


def parse_vintage_block(markdown: str) -> dict | None:
    """Return the parsed ``vintage`` block dict, or None if absent/not a mapping."""
    match = _VINTAGE_FENCE_RE.search(markdown)
    if not match:
        return None
    data = yaml.safe_load(match.group(1))
    return data if isinstance(data, dict) else None


def _strip_vintage_block(markdown: str) -> str:
    """Remove the vintage block so prose scans never read the block's own values."""
    return _VINTAGE_FENCE_RE.sub("", markdown)


def find_vintage_reports(root: Path) -> list[Path]:
    """All markdown files under root that carry a vintage block (opt-in by presence)."""
    found = []
    for path in sorted(Path(root).rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if parse_vintage_block(text) is not None:
            found.append(path)
    return found


# --- coverage-day extraction ------------------------------------------------
# Narrow, documented patterns. Each matches ONLY a phrase that denotes the
# report's own coverage window, never an event/forecast window or a
# generated/compiled/accessed/issued metadata date. Every captured day must
# equal the block's ``through_day``.
#
# Deliberately NOT matched (so they cannot cause false failures):
#   - metadata dates: "Compiled 2026-05-20", "Generated 2026-06-01",
#     "accessed 2026-05-20", "issued 20/05/2026", "re-pulled on 2026-06-01"
#   - event/forecast windows: "May 13-19 front", "May 21-28", "28th-29th",
#     "16th-17th", "1st-3rd", "days 29-31", "12 days still to run"
#   - "dry to day 27"  (uses "to day", not "through day")
#   - "19 days of May", "partial 19-day observation"
_COVERAGE_DAY_PATTERNS = (
    re.compile(r"through day (\d{1,2})\b"),                       # "through day 19"
    re.compile(r"\b(\d{1,2}) of 31 days\b"),                     # "19 of 31 days" / "31 of 31 days"
    re.compile(r"May 1[–\-](\d{1,2})\b"),                   # "May 1-19" / "May 1-31"
    re.compile(r"(?:Data|Coverage) through 2026-05-(\d{2})\b"),  # "Data through 2026-05-19"
)


def extract_coverage_days(prose: str) -> list[int]:
    """Return all coverage-context through-day claims found in prose."""
    days: list[int] = []
    for pattern in _COVERAGE_DAY_PATTERNS:
        days.extend(int(m.group(1)) for m in pattern.finditer(prose))
    return days


# --- current-input vintage --------------------------------------------------
def current_through_day(coverage_month: str, input_path: Path) -> int | None:
    """Max ``partial_month_through_day`` for coverage_month in an MTD/history CSV."""
    df = pd.read_csv(input_path)
    year, month = (int(x) for x in str(coverage_month).split("-"))
    sub = df[(df["year"] == year) & (df["month"] == month)]
    vals = sub["partial_month_through_day"].dropna()
    return int(vals.max()) if len(vals) else None


# --- checks -----------------------------------------------------------------
def check_schema(block: dict) -> list[str]:
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in block:
            errors.append(f"missing required field '{field}'")
    status = block.get("status")
    if status is not None and status not in VALID_STATUS:
        errors.append(f"status must be one of {sorted(VALID_STATUS)}, got {status!r}")
    method = block.get("decile_method")
    if method is not None and method not in DECILE_METHODS:
        errors.append(f"unknown decile_method {method!r}")
    if status == "live" and not block.get("inputs"):
        errors.append("live report must list 'inputs'")
    return errors


def check_internal_consistency(block: dict, markdown: str) -> list[str]:
    """Prose must agree with the block's own declared vintage (frozen + live)."""
    errors = []
    prose = _strip_vintage_block(markdown)

    through_day = block.get("through_day")
    if through_day is not None:
        for day in sorted(set(extract_coverage_days(prose))):
            if day != through_day:
                errors.append(
                    f"prose coverage-day {day} does not match through_day {through_day}"
                )

    method = block.get("decile_method")
    if method in DECILE_METHODS:
        for token in DECILE_METHODS[method]["forbidden_prose"]:
            if token in prose:
                errors.append(
                    f"prose contains '{token}' forbidden for decile_method '{method}'"
                )
    return errors


def check_live_against_inputs(block: dict, repo_root: Path) -> list[str]:
    """Live reports must match current input vintage + current method/baseline."""
    errors = []

    method = block.get("decile_method")
    if method is not None and method != DECILE_METHOD_ID:
        errors.append(
            f"live decile_method {method!r} differs from current {DECILE_METHOD_ID!r}"
        )

    if block.get("baseline_years") != BASELINE_YEARS:
        errors.append(
            f"live baseline_years {block.get('baseline_years')} "
            f"differs from current {BASELINE_YEARS}"
        )

    coverage_month = block.get("coverage_month")
    through_day = block.get("through_day")
    for rel in block.get("inputs", []) or []:
        path = Path(repo_root) / rel
        if not path.exists():
            errors.append(f"live input {rel} not found; cannot determine current through_day")
            continue
        current = current_through_day(coverage_month, path)
        if current is None:
            errors.append(
                f"cannot determine current through_day for coverage_month "
                f"{coverage_month} in {rel} (no rows or null partial_month_through_day)"
            )
        elif current != through_day:
            errors.append(
                f"live through_day {through_day} differs from current {current} in {rel}"
            )
    return errors


def validate_report(markdown: str, repo_root: Path) -> list[str]:
    """Validate one report's vintage pin. Returns a list of error strings ([] = ok)."""
    block = parse_vintage_block(markdown)
    if block is None:
        return ["missing vintage block"]

    errors = check_schema(block)
    if errors:
        return errors  # downstream checks assume a well-formed block

    errors += check_internal_consistency(block, markdown)
    if block.get("status") == "live":
        errors += check_live_against_inputs(block, repo_root)
    return errors
