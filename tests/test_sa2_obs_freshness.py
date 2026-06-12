"""Tests for build_sa2_obs_freshness_report.freshness_rows."""

from datetime import date

import scripts.build_sa2_obs_freshness_report as mod


def test_freshness_statuses():
    sa2s = [
        {"sa2_code": "50901", "sa2_name": "Moora", "state": "Western Australia",
         "station_ids": "8091;8137"},
        {"sa2_code": "51001", "sa2_name": "Kulin", "state": "Western Australia",
         "station_ids": "10073"},
        {"sa2_code": "51102", "sa2_name": "NoStations", "state": "Western Australia",
         "station_ids": ""},
    ]
    max_dates = {
        "8091": date(2026, 6, 9),    # current
        "8137": date(2026, 5, 17),   # older sibling — newest station wins
        "10073": date(2026, 5, 17),  # stale
    }
    rows = mod.freshness_rows(sa2s, max_dates, cutoff=date(2026, 6, 8))
    by = {r["sa2_code"]: r for r in rows}
    assert by["50901"]["status"] == "current"
    assert by["51001"]["status"] == "stale"
    assert by["51001"]["days_behind_cutoff"] == 22
    assert by["51102"]["status"] == "no_data"
