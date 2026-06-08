"""Smoke tests: verify the three canonical CLI entrypoints respond to --help."""
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_help(module: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )


class TestCliHelp(unittest.TestCase):

    def test_silo_wrangler_help(self):
        result = _run_help("src.agents.silo_wrangler.run_ingest")
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, f"Non-zero exit\n{output}")
        self.assertTrue(
            any(m in output for m in ["Run daily SILO data ingestion", "--hybrid"]),
            f"No expected marker found:\n{output}",
        )

    def test_silo_wrangler_date_option(self):
        """--date option must be present so cron_schedule.sh --date passes work."""
        result = _run_help("src.agents.silo_wrangler.run_ingest")
        output = result.stdout + result.stderr
        self.assertIn("--date", output, "--date option missing from run_ingest help")

    def test_risk_engine_help(self):
        result = _run_help("src.agents.risk_engine.run_risk_engine")
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, f"Non-zero exit\n{output}")
        self.assertTrue(
            any(m in output for m in ["CropForecaster Risk Engine", "--date-range"]),
            f"No expected marker found:\n{output}",
        )

    def test_publisher_help(self):
        result = _run_help("src.agents.insight_publisher.run_publisher")
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, f"Non-zero exit\n{output}")
        self.assertTrue(
            any(m in output for m in ["CropForecaster Insight Publisher", "--season"]),
            f"No expected marker found:\n{output}",
        )


if __name__ == "__main__":
    unittest.main()
