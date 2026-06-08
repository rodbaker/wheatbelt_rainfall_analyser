# src/agents/silo_wrangler/concurrent_ingest.py
"""Bounded-concurrency station ingest with serialized writes.

The network-bound worker (fetch -> process -> quality) runs across threads; the
writer (atomic CSV append + DuckDB upsert) is invoked only on the main thread,
from the as_completed loop, so shared-state writes are never concurrent.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class StationResult:
    station_id: str
    status: str                                  # success | no_data | error | excluded
    records: Optional[pd.DataFrame] = None
    detail: str = ""


def ingest_concurrently(
    items: List[Tuple[str, str]],
    worker: Callable[[str, str], StationResult],
    writer: Callable[[StationResult], bool],
    concurrency: int = 10,
) -> dict:
    """Run `worker` over (station_id, name) items with up to `concurrency`
    threads; call `writer` (main thread) for each success. Returns a summary.

    `worker` must be thread-safe and must NOT raise for ordinary failures — but
    if it does raise, the exception is caught and counted as a failure so one
    bad station never aborts the batch.
    """
    requested = len(items)
    succeeded = skipped = failed = 0
    records_processed = 0
    failed_ids: List[str] = []
    skipped_ids: List[str] = []
    start = time.time()

    def _run(item: Tuple[str, str]) -> StationResult:
        sid, name = item
        try:
            return worker(sid, name)
        except Exception as exc:                 # isolation: never abort the batch
            logger.error("Worker error for station %s: %s", sid, exc, exc_info=True)
            return StationResult(sid, "error", detail=str(exc))

    max_workers = max(1, int(concurrency))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run, it): it for it in items}
        for fut in as_completed(futures):
            result = fut.result()                # _run never raises
            if result.status == "success" and result.records is not None:
                try:
                    wrote = writer(result)       # serialized on main thread
                except Exception as exc:         # isolation: a write failure must not abort the batch
                    logger.error("Writer error for station %s: %s",
                                 result.station_id, exc, exc_info=True)
                    wrote = False
                if wrote:
                    succeeded += 1
                    records_processed += len(result.records)
                else:
                    failed += 1
                    failed_ids.append(result.station_id)
            elif result.status == "no_data":
                skipped += 1
                skipped_ids.append(result.station_id)
            else:
                failed += 1
                failed_ids.append(result.station_id)

    elapsed = round(time.time() - start, 2)
    summary = {
        "requested": requested,
        "succeeded": succeeded,
        "failed": failed,
        "skipped_no_data": skipped,
        "records_processed": records_processed,
        "elapsed_s": elapsed,
        "failed_ids": failed_ids,
        "skipped_ids": skipped_ids,
    }
    logger.info(
        "Concurrent ingest: requested=%d succeeded=%d failed=%d skipped_no_data=%d elapsed=%ss",
        requested, succeeded, failed, skipped, elapsed,
    )
    return summary
