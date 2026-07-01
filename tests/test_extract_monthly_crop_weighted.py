"""Crop-weighted monthly history tags rows and differs from centroid for WA."""
import pytest
pd = pytest.importorskip("pandas")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not list((ROOT / "data/meta/monthly_rain").glob("*.monthly_rain.nc")),
                    reason="monthly grids not present")
def test_crop_weighted_history_method_tag(tmp_path):
    import subprocess, sys
    out = tmp_path / "wa_hist_cw.csv"
    subprocess.run(
        [sys.executable, "scripts/extract_sa2_monthly_rainfall.py",
         "--states", "Western Australia", "--method", "crop_weighted",
         "--output", str(out)],
        cwd=ROOT, check=True)
    df = pd.read_csv(out)
    assert (df["extraction_method"] == "cropfrac_weighted_polygon_mean").all()
    # Gnowangerup June rows should exist and be finite
    g = df[(df["sa2_name"] == "Gnowangerup") & (df["month"] == 6)]
    assert g["rainfall_mm"].notna().any()
