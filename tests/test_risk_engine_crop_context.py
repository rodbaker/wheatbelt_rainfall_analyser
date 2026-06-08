"""Tests for Phase 4: optional crop context boundary in RiskEngineRunner.

Verifies:
- disabled (default) → no CSV access, _crop_context_lookup is None
- enabled + valid CSV → lookup loads successfully
- enabled + required=True + missing CSV → FileNotFoundError
- enabled + required=False + missing CSV → None, no crash
"""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.common.crop_context_loader import REQUIRED_COLUMNS


def _minimal_crop_context_csv() -> Path:
    """Write a minimal valid crop_context_sa2.csv to a temp file."""
    row = {
        "sa2_code": "012345678",
        "station_sa2_5dig16": "01234",
        "sa2_name": "Test SA2",
        "state": "Western Australia",
        "financial_year": "2020-21",
        "crop": "wheat",
        "area_ha": "100.5",
        "production_t": "",
        "yield_t_ha": "2.2",
        "area_share": "0.75",
        "area_rse": "^",
        "production_rse": "np",
        "yield_rse": "",
        "source_dataset": "ABS Agricultural Census 2020-21",
        "source_commodity_area": "AGCEREAL_AHAWHT_F",
        "source_commodity_production": "AGCEREAL_ATOWHT_F",
        "source_commodity_yield": "WHEAT_YIELD_F",
        "boundary_status": "matched",
        "notes": "",
    }
    tmp = tempfile.NamedTemporaryFile(
        suffix=".csv", delete=False, mode="w", newline=""
    )
    path = Path(tmp.name)
    with tmp:
        writer = csv.DictWriter(tmp, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerow(row)
    return path


def _base_crop_config(crop_context_override=None):
    """Minimal crop config dict for RiskEngineRunner construction."""
    config = {
        "wheat": {
            "stages": {
                "planting": {"months": [4, 5, 6]},
                "tillering": {"months": [6, 7, 8], "frost_critical": True},
                "flowering": {"months": [9, 10], "frost_critical": True},
                "grain_fill": {
                    "months": [10, 11],
                    "frost_critical": True,
                    "heat_critical": True,
                },
                "harvest": {"months": [11, 12, 1], "rain_critical": True},
            }
        },
        "crop_context": crop_context_override or {"enabled": False},
    }
    return config


def _make_engine(crop_config):
    """Instantiate RiskEngineRunner with all heavy I/O mocked out."""
    from src.agents.risk_engine.run_risk_engine import RiskEngineRunner

    with (
        patch.object(
            RiskEngineRunner, "_load_crop_calendars", return_value=crop_config
        ),
        patch.object(
            RiskEngineRunner, "_load_region_lookup", return_value=MagicMock()
        ),
        patch("src.agents.risk_engine.run_risk_engine.DuckDBStorage"),
        patch("src.agents.risk_engine.run_risk_engine.WeatherEventDetector"),
    ):
        engine = RiskEngineRunner.__new__(RiskEngineRunner)
        engine.config_path = Path("config")
        engine.output_dir = Path(tempfile.mkdtemp())
        engine.crop_config = crop_config
        engine.storage = MagicMock()
        engine.detector = MagicMock()
        engine._region_lookup = MagicMock()
        engine._crop_context_lookup = engine._load_crop_context()
    return engine


class TestRiskEngineCropContextBoundary(unittest.TestCase):

    def tearDown(self):
        for path in getattr(self, "_tmp_paths", []):
            if path.exists():
                path.unlink()

    def _track(self, path):
        self._tmp_paths = getattr(self, "_tmp_paths", [])
        self._tmp_paths.append(path)
        return path

    # ------------------------------------------------------------------ #
    # 1. disabled (default) — no CSV access, lookup is None               #
    # ------------------------------------------------------------------ #
    def test_disabled_lookup_is_none(self):
        engine = _make_engine(_base_crop_config({"enabled": False}))
        self.assertIsNone(engine._crop_context_lookup)

    def test_missing_crop_context_key_treated_as_disabled(self):
        config = _base_crop_config()
        del config["crop_context"]
        engine = _make_engine(config)
        self.assertIsNone(engine._crop_context_lookup)

    # ------------------------------------------------------------------ #
    # 2. enabled + valid CSV → lookup loads                               #
    # ------------------------------------------------------------------ #
    def test_enabled_valid_csv_loads_lookup(self):
        csv_path = self._track(_minimal_crop_context_csv())
        engine = _make_engine(_base_crop_config({
            "enabled": True,
            "path": str(csv_path),
            "required": False,
        }))
        self.assertIsNotNone(engine._crop_context_lookup)
        self.assertEqual(len(engine._crop_context_lookup.records), 1)

    # ------------------------------------------------------------------ #
    # 3. enabled + required=True + missing file → FileNotFoundError       #
    # ------------------------------------------------------------------ #
    def test_enabled_required_missing_raises(self):
        missing = (
            Path(tempfile.gettempdir()) / "definitely_missing_crop_ctx.csv"
        )
        if missing.exists():
            missing.unlink()

        from src.agents.risk_engine.run_risk_engine import RiskEngineRunner

        config = _base_crop_config({
            "enabled": True,
            "path": str(missing),
            "required": True,
        })

        with (
            patch.object(
                RiskEngineRunner,
                "_load_crop_calendars",
                return_value=config,
            ),
            patch.object(
                RiskEngineRunner,
                "_load_region_lookup",
                return_value=MagicMock(),
            ),
            patch("src.agents.risk_engine.run_risk_engine.DuckDBStorage"),
            patch(
                "src.agents.risk_engine.run_risk_engine.WeatherEventDetector"
            ),
        ):

            engine = RiskEngineRunner.__new__(RiskEngineRunner)
            engine.config_path = Path("config")
            engine.output_dir = Path(tempfile.mkdtemp())
            engine.crop_config = config
            engine.storage = MagicMock()
            engine.detector = MagicMock()
            engine._region_lookup = MagicMock()

            with self.assertRaises(FileNotFoundError):
                engine._crop_context_lookup = engine._load_crop_context()

    # ------------------------------------------------------------------ #
    # 4. enabled + required=False + missing file → None, no crash         #
    # ------------------------------------------------------------------ #
    def test_enabled_not_required_missing_returns_none(self):
        missing = Path(tempfile.gettempdir()) / "also_missing_crop_ctx.csv"
        if missing.exists():
            missing.unlink()

        engine = _make_engine(_base_crop_config({
            "enabled": True,
            "path": str(missing),
            "required": False,
        }))
        self.assertIsNone(engine._crop_context_lookup)

    # ------------------------------------------------------------------ #
    # 5. disabled run does not attempt file access at all                 #
    # ------------------------------------------------------------------ #
    def test_disabled_does_not_call_load_crop_context_lookup(self):
        with patch(
            "src.agents.risk_engine.run_risk_engine.load_crop_context_lookup"
        ) as mock_loader:
            _make_engine(_base_crop_config({"enabled": False}))
            mock_loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
