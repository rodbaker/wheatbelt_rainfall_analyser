"""Crop-weighted MTD must reproduce the confirmed WA June 1-28 2026 anchors."""
import pytest
pd = pytest.importorskip("pandas")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MTD = ROOT / "data/features/sa2_2026_06_mtd_cropwtd.csv"

ANCHORS = {"Gnowangerup": 38.1, "Wagin": 47.9, "Katanning": 35.7}


@pytest.mark.skipif(not (ROOT / "data/meta/daily_rain/2026.daily_rain.nc").exists(),
                    reason="2026 daily grid not present")
def test_wa_anchors(tmp_path):
    import subprocess, sys
    out = ROOT / "data/features/sa2_2026_06_mtd_cropwtd.csv"
    subprocess.run(
        [sys.executable, "scripts/extract_sa2_partial_month_rainfall.py",
         "--year", "2026", "--month", "6", "--method", "crop_weighted"],
        cwd=ROOT, check=True)
    df = pd.read_csv(out)
    for name, expected in ANCHORS.items():
        got = float(df.loc[df["sa2_name"] == name, "rainfall_mm"].iloc[0])
        assert abs(got - expected) <= 0.3, f"{name}: {got} vs {expected}"
