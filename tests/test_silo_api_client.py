"""Tests for SILOAPIClient.get_daily_data response parsing robustness.

Regression for the operational failure where `./ws refresh` requested a single
day SILO had not yet published (publishing lag). SILO returns a response with no
valid data rows, pandas infers the `YYYY-MM-DD` column as float NaN, and the
`.str` accessor raised `AttributeError: Can only use .str accessor with string
values!` — failing all stations with 0 records instead of degrading to "no data".

The sibling method `get_data_drill_data` already guards this with `.astype(str)`;
these tests pin the same contract on `get_daily_data`.
"""

from unittest.mock import patch

import pandas as pd

from src.agents.silo_wrangler.api_client import SILOAPIClient


def _client():
    config = {
        "api": {
            "base_url": "https://example.test/silo",
            "username": "test@example.com",
            "rate_limit_seconds": 0,
            "timeout_seconds": 5,
            "max_retries": 1,
        },
        "variables": {"R": "daily_rain", "X": "max_temp", "N": "min_temp"},
    }
    return SILOAPIClient(config)


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def test_no_valid_rows_returns_empty_not_crash():
    """A no-data response (blank date column → float NaN) must return empty, not raise."""
    # Mimics SILO returning a header but no published observation for the date.
    no_data_csv = "YYYY-MM-DD,daily_rain,max_temp,min_temp\n,,,\n"
    client = _client()
    with patch(
        "src.agents.silo_wrangler.api_client.requests.get",
        return_value=_FakeResponse(no_data_csv),
    ):
        df = client.get_daily_data("012320", "20260617", "20260617")
    assert df is not None
    assert df.empty


def test_request_sends_username_and_password():
    """SILO's public API requires both username and the 'apirequest' password
    constant; omitting the password yields 401. Pin both onto the request params."""
    csv = "YYYY-MM-DD,daily_rain,max_temp,min_temp\n2026-06-13,1.2,18.0,5.0\n"
    client = _client()  # fixture config has no password → must default to 'apirequest'
    with patch(
        "src.agents.silo_wrangler.api_client.requests.get",
        return_value=_FakeResponse(csv),
    ) as mock_get:
        client.get_daily_data("012320", "20260613", "20260613")
    params = mock_get.call_args.kwargs["params"]
    assert params["username"] == "test@example.com"
    assert params["password"] == "apirequest"


def test_valid_rows_are_kept_and_metadata_filtered():
    """Valid YYYY-MM-DD rows are retained; trailing non-date metadata rows dropped."""
    csv = (
        "YYYY-MM-DD,daily_rain,max_temp,min_temp\n"
        "2026-06-13,1.2,18.0,5.0\n"
        "2026-06-14,0.0,19.0,6.0\n"
        "metadata footer,,,\n"
    )
    client = _client()
    with patch(
        "src.agents.silo_wrangler.api_client.requests.get",
        return_value=_FakeResponse(csv),
    ):
        df = client.get_daily_data("012320", "20260613", "20260614")
    assert list(df["YYYY-MM-DD"]) == ["2026-06-13", "2026-06-14"]
