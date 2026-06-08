# tests/test_concurrent_ingest.py
import pandas as pd

from src.agents.silo_wrangler.concurrent_ingest import StationResult, ingest_concurrently


def test_failure_isolation_and_summary():
    items = [("001", "A"), ("002", "B"), ("003", "C"), ("004", "D")]

    def worker(sid, name):
        if sid == "002":
            raise RuntimeError("boom")          # exception must be isolated
        if sid == "003":
            return StationResult(sid, "no_data")
        return StationResult(sid, "success", records=pd.DataFrame({"x": [1, 2]}))  # 2 rows each

    written = []

    def writer(result):
        written.append(result.station_id)
        return True

    summary = ingest_concurrently(items, worker, writer, concurrency=3)

    assert summary["requested"] == 4
    assert summary["succeeded"] == 2
    assert summary["failed"] == 1                # 002 raised
    assert summary["skipped_no_data"] == 1       # 003
    assert summary["records_processed"] == 4     # 2 successful writes x 2 rows
    assert sorted(written) == ["001", "004"]     # only successes written
    assert "elapsed_s" in summary
    assert sorted(summary["failed_ids"]) == ["002"]


def test_concurrency_one_matches_concurrency_n():
    items = [(f"{i:03d}", "x") for i in range(10)]

    def worker(sid, name):
        return StationResult(sid, "success", records=pd.DataFrame({"x": [1]}))

    def writer(result):
        return True

    s1 = ingest_concurrently(items, worker, writer, concurrency=1)
    sn = ingest_concurrently(items, worker, writer, concurrency=5)
    assert s1["succeeded"] == sn["succeeded"] == 10


def test_writer_failure_counts_as_failed():
    items = [("001", "A")]

    def worker(sid, name):
        return StationResult(sid, "success", records=pd.DataFrame({"x": [1]}))

    def writer(result):
        return False        # write failed

    summary = ingest_concurrently(items, worker, writer, concurrency=2)
    assert summary["succeeded"] == 0
    assert summary["failed"] == 1


def test_writer_exception_is_isolated():
    items = [("001", "A"), ("002", "B")]

    def worker(sid, name):
        return StationResult(sid, "success", records=pd.DataFrame({"x": [1]}))

    def writer(result):
        if result.station_id == "001":
            raise RuntimeError("disk full")     # must be caught, not abort the batch
        return True

    summary = ingest_concurrently(items, worker, writer, concurrency=2)
    assert summary["succeeded"] == 1            # 002 still written
    assert summary["failed"] == 1              # 001 write failed but isolated
    assert summary["failed_ids"] == ["001"]
