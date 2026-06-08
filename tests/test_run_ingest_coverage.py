import json

from src.agents.silo_wrangler.run_ingest import _gap_date_range, log_run_results


def test_gap_date_range_explicit_date():
    assert _gap_date_range("2026-06-01", None, {}) == ("20260601", "20260601")


def test_gap_date_range_days_window():
    start, finish = _gap_date_range(None, 5, {})
    assert len(start) == 8 and len(finish) == 8 and start <= finish


def test_gap_date_range_rolling_window():
    cfg = {"collection": {"mode": "rolling_window", "rolling_days": 40}}
    start, finish = _gap_date_range(None, None, cfg)
    assert len(start) == 8 and len(finish) == 8 and start <= finish


def test_gap_date_range_yesterday_default():
    cfg = {"collection": {"mode": "single"}}
    start, finish = _gap_date_range(None, None, cfg)
    assert start == finish and len(start) == 8


def test_log_run_results_writes_real_newlines(tmp_path):
    p = tmp_path / "runs.jsonl"
    log_run_results({"a": 1}, str(p))
    log_run_results({"b": 2}, str(p))
    lines = p.read_text().splitlines()
    assert len(lines) == 2                      # real newlines, not a literal "\n"
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": 2}
