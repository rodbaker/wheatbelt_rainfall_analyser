"""Guard: pinned reports must not silently diverge from inputs/method.

Frozen reports are checked for internal consistency (prose <-> their own
declared vintage). Live reports are additionally checked against current input
vintage + the current decile method. Live behaviour is fixture-tested only in
v1 (no real report is marked live).
"""
from pathlib import Path

import pandas as pd

from src.rainfall.vintage import (
    BASELINE_YEARS,
    DECILE_METHOD_ID,
    find_vintage_reports,
    parse_vintage_block,
    validate_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"

PINNED_REPORTS = [
    REPO_ROOT / "reports/weekly/2026-W21_outlook_v2.md",
    REPO_ROOT / "reports/monthly/2026-05_rainfall_monitor_sd.md",
]


def _block(status="frozen", through_day=19, decile_method=None, inputs=None,
           coverage="2026-05"):
    lines = [
        "```vintage",
        f"status: {status}",
        "report_date: 2026-05-20",
        f"coverage_month: {coverage}",
        f"through_day: {through_day}",
        f"baseline_years: {BASELINE_YEARS}",
    ]
    if decile_method:
        lines.append(f"decile_method: {decile_method}")
    if inputs:
        lines.append("inputs:")
        lines.extend(f"  - {i}" for i in inputs)
    lines.append("```")
    return "\n".join(lines)


def _doc(block, prose):
    return f"# Title\n\n{block}\n\n{prose}\n"


def _write_mtd(tmp_path, through_day=31):
    csv = tmp_path / "mtd.csv"
    pd.DataFrame(
        {"year": [2026], "month": [5], "partial_month_through_day": [through_day]}
    ).to_csv(csv, index=False)
    return csv


# --- real reports (opt-in by presence of a vintage block) -------------------

def test_all_reports_with_vintage_blocks_pass():
    pinned = find_vintage_reports(REPORTS_DIR)
    assert pinned, "no reports under reports/ carry a vintage block"
    for path in pinned:
        errors = validate_report(path.read_text(encoding="utf-8"), REPO_ROOT)
        assert errors == [], f"{path}: {errors}"


def test_v1_target_reports_are_pinned():
    pinned = set(find_vintage_reports(REPORTS_DIR))
    for target in PINNED_REPORTS:
        assert target in pinned, f"{target} lost its vintage block"


def test_scanner_opts_in_by_block_presence(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "plain.md").write_text("# Plain\n\nNo vintage block here.\n")
    csv = _write_mtd(tmp_path, through_day=31)
    bad_live = _doc(
        _block(status="live", through_day=19, decile_method=DECILE_METHOD_ID,
               inputs=[csv.name]),
        "Coverage through day 19.",
    )
    (reports / "bad_live.md").write_text(bad_live)

    found = find_vintage_reports(reports)
    assert reports / "bad_live.md" in found
    assert reports / "plain.md" not in found
    errors = validate_report((reports / "bad_live.md").read_text(), tmp_path)
    assert errors, "scanner-discovered bad live report should fail validation"


# --- frozen internal-consistency negatives ----------------------------------

def test_frozen_prose_day_mismatch_fails():
    md = _doc(
        _block(status="frozen", through_day=31),
        "Numbers reflect data through day 19 of the month.",
    )
    errors = validate_report(md, REPO_ROOT)
    assert any("through_day" in e for e in errors), errors


def test_canonical_method_with_div10_prose_fails():
    md = _doc(
        _block(status="frozen", through_day=31, decile_method="rank_ceil_v1"),
        "Decile = percentile rank ÷ 10, one decimal.",
    )
    errors = validate_report(md, REPO_ROOT)
    assert any("÷ 10" in e for e in errors), errors


# --- live negatives (fixture only) ------------------------------------------

def test_live_through_day_differs_from_current_mtd_fails(tmp_path):
    csv = _write_mtd(tmp_path, through_day=31)
    md = _doc(
        _block(status="live", through_day=19, decile_method=DECILE_METHOD_ID,
               inputs=[csv.name]),
        "Coverage through day 19.",
    )
    errors = validate_report(md, tmp_path)
    assert any("31" in e for e in errors), errors


def test_live_input_missing_coverage_month_fails(tmp_path):
    csv = tmp_path / "mtd.csv"
    # input has 2025-05 only; report covers 2026-05 -> cannot determine current
    pd.DataFrame(
        {"year": [2025], "month": [5], "partial_month_through_day": [31]}
    ).to_csv(csv, index=False)
    md = _doc(
        _block(status="live", through_day=31, decile_method=DECILE_METHOD_ID,
               inputs=[csv.name]),
        "Coverage: May 1–31, 31 of 31 days.",
    )
    errors = validate_report(md, tmp_path)
    assert any("determine" in e for e in errors), errors


def test_live_input_null_through_day_fails(tmp_path):
    csv = tmp_path / "mtd.csv"
    pd.DataFrame(
        {"year": [2026], "month": [5], "partial_month_through_day": [None]}
    ).to_csv(csv, index=False)
    md = _doc(
        _block(status="live", through_day=31, decile_method=DECILE_METHOD_ID,
               inputs=[csv.name]),
        "Coverage: May 1–31, 31 of 31 days.",
    )
    errors = validate_report(md, tmp_path)
    assert any("determine" in e for e in errors), errors


def test_live_input_file_missing_fails(tmp_path):
    md = _doc(
        _block(status="live", through_day=31, decile_method=DECILE_METHOD_ID,
               inputs=["does_not_exist.csv"]),
        "Coverage: May 1–31, 31 of 31 days.",
    )
    errors = validate_report(md, tmp_path)
    assert any("not found" in e for e in errors), errors


def test_live_method_differs_from_current_fails(tmp_path):
    csv = _write_mtd(tmp_path, through_day=31)
    md = _doc(
        _block(status="live", through_day=31, decile_method="ratio_div10_v0",
               inputs=[csv.name]),
        "Coverage: May 1–31, 31 of 31 days.",
    )
    errors = validate_report(md, tmp_path)
    assert any("decile_method" in e for e in errors), errors


# --- positive fixtures ------------------------------------------------------

def test_well_formed_live_report_passes(tmp_path):
    csv = _write_mtd(tmp_path, through_day=31)
    md = _doc(
        _block(status="live", through_day=31, decile_method=DECILE_METHOD_ID,
               inputs=[csv.name]),
        "Coverage: May 1–31, 31 of 31 days.",
    )
    errors = validate_report(md, tmp_path)
    assert errors == [], errors


def test_well_formed_frozen_report_passes():
    md = _doc(
        _block(status="frozen", through_day=19),
        "Observed May MTD through day 19 (May 1–19, 19 of 31 days).",
    )
    errors = validate_report(md, REPO_ROOT)
    assert errors == [], errors
