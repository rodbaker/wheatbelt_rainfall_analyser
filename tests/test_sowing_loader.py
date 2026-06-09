"""Tests for the Sa2Break loader (R6 joins; Geraldton weight-0 + warning).

Assembles Sa2Break records from three files using the approved R6 keys:
  features <-> concordance : sa2_code_9dig <-> SA2_CODE21  (fail loud on miss)
  features <-> broadacre   : 5-digit sa2_code              (miss -> weight 0 + warn)
SA2->SD weight is allocation_ratio (one record per feature-SA2 x SD overlap).
"""

import csv
import tempfile
import unittest
from pathlib import Path

from src.sowing.crosswalk import Sa2Break
from src.sowing.loader import LoadResult, load_sa2_breaks

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_FEATURES = REPO_ROOT / "data" / "features" / "rainfall_features_sa2_season.csv"
REAL_CONC = REPO_ROOT / "data" / "meta" / "sa2_2021_to_sd_2011_concordance_wa.csv"
REAL_BROAD = REPO_ROOT / "data" / "meta" / "sa2_coverage_report.csv"

_FEAT_COLS = ["season_year", "state_name", "sa2_code", "sa2_code_9dig", "sa2_name",
              "autumn_break_date", "autumn_break_status"]
_CONC_COLS = ["SA2_CODE21", "SD_CODE11", "SD_STATE_CODE", "allocation_ratio"]
_BROAD_COLS = ["sa2_code", "sa2_name", "state", "broadacre_area_ha"]


def _write(path, cols, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _feat(**kw):
    base = dict(season_year="2026", state_name="Western Australia", sa2_code="51240",
                sa2_code_9dig="509021240", sa2_name="Merredin",
                autumn_break_date="2026-05-20", autumn_break_status="on_time")
    base.update(kw)
    return base


class TestLoadSa2Breaks(unittest.TestCase):
    def _run(self, feats, concs, broads, **kw):
        with tempfile.TemporaryDirectory() as d:
            fp, cp, bp = Path(d) / "f.csv", Path(d) / "c.csv", Path(d) / "b.csv"
            _write(fp, _FEAT_COLS, feats)
            _write(cp, _CONC_COLS, concs)
            _write(bp, _BROAD_COLS, broads)
            return load_sa2_breaks(fp, cp, bp, **kw)

    def test_happy_path_single_sd(self):
        res = self._run(
            [_feat()],
            [dict(SA2_CODE21="509021240", SD_CODE11="525", SD_STATE_CODE="5", allocation_ratio="1.0")],
            [dict(sa2_code="51240", sa2_name="Merredin", state="Western Australia", broadacre_area_ha="500.0")],
        )
        self.assertIsInstance(res, LoadResult)
        (rec,) = res.records
        self.assertIsInstance(rec, Sa2Break)
        self.assertEqual(rec.sd_code11, "525")
        self.assertEqual(rec.sd_state_code, "5")
        self.assertEqual(rec.allocation_ratio, 1.0)
        self.assertEqual(rec.broadacre_area_ha, 500.0)
        self.assertEqual(rec.break_doy, 140)        # 2026-05-20 -> DOY 140
        self.assertEqual(rec.status, "on_time")
        self.assertEqual(rec.season_year, 2026)
        self.assertEqual(res.missing_broadacre, [])

    def test_split_sa2_yields_one_record_per_overlap(self):
        res = self._run(
            [_feat(sa2_code_9dig="511011275", sa2_code="51275", sa2_name="Esperance Surrounds")],
            [
                dict(SA2_CODE21="511011275", SD_CODE11="530", SD_STATE_CODE="5", allocation_ratio="0.981"),
                dict(SA2_CODE21="511011275", SD_CODE11="515", SD_STATE_CODE="5", allocation_ratio="0.019"),
            ],
            [dict(sa2_code="51275", sa2_name="Esperance Surrounds", state="Western Australia", broadacre_area_ha="800.0")],
        )
        self.assertEqual({r.sd_code11 for r in res.records}, {"530", "515"})
        self.assertEqual({round(r.allocation_ratio, 3) for r in res.records}, {0.981, 0.019})

    def test_not_assessed_and_absent_give_none_break_doy(self):
        res = self._run(
            [_feat(autumn_break_date="", autumn_break_status="not_assessed"),
             _feat(sa2_code_9dig="509021241", sa2_code="51241", sa2_name="Moora",
                   autumn_break_date="", autumn_break_status="absent")],
            [dict(SA2_CODE21="509021240", SD_CODE11="525", SD_STATE_CODE="5", allocation_ratio="1.0"),
             dict(SA2_CODE21="509021241", SD_CODE11="525", SD_STATE_CODE="5", allocation_ratio="1.0")],
            [dict(sa2_code="51240", broadacre_area_ha="500.0"),
             dict(sa2_code="51241", broadacre_area_ha="500.0")],
        )
        self.assertTrue(all(r.break_doy is None for r in res.records))
        self.assertEqual({r.status for r in res.records}, {"not_assessed", "absent"})

    def test_missing_broadacre_is_weight_zero_named_and_warned(self):
        with self.assertLogs(level="WARNING") as cm:
            res = self._run(
                [_feat(sa2_code_9dig="511041287", sa2_code="51287", sa2_name="Geraldton - North")],
                [dict(SA2_CODE21="511041287", SD_CODE11="525", SD_STATE_CODE="5", allocation_ratio="1.0")],
                [],  # no broadacre rows
            )
        (rec,) = res.records
        self.assertEqual(rec.broadacre_area_ha, 0.0)            # not synthesized
        self.assertIn(("51287", "Geraldton - North"), res.missing_broadacre)
        self.assertTrue(any("51287" in m for m in cm.output))   # warning names it

    def test_unmatched_concordance_fails_loud(self):
        with self.assertRaises(ValueError):
            self._run(
                [_feat(sa2_code_9dig="999999999")],
                [dict(SA2_CODE21="509021240", SD_CODE11="525", SD_STATE_CODE="5", allocation_ratio="1.0")],
                [dict(sa2_code="51240", broadacre_area_ha="500.0")],
            )

    def test_non_wa_rows_ignored(self):
        res = self._run(
            [_feat(state_name="South Australia", sa2_code_9dig="404011099")],
            [dict(SA2_CODE21="509021240", SD_CODE11="525", SD_STATE_CODE="5", allocation_ratio="1.0")],
            [dict(sa2_code="51240", broadacre_area_ha="500.0")],
        )
        self.assertEqual(res.records, [])

    def test_multiple_seasons_loaded(self):
        res = self._run(
            [_feat(season_year="2024"), _feat(season_year="2025")],
            [dict(SA2_CODE21="509021240", SD_CODE11="525", SD_STATE_CODE="5", allocation_ratio="1.0")],
            [dict(sa2_code="51240", broadacre_area_ha="500.0")],
        )
        self.assertEqual({r.season_year for r in res.records}, {2024, 2025})


class TestLoadSa2BreaksRealFiles(unittest.TestCase):
    def test_loads_real_vendored_files_and_flags_geraldton(self):
        res = load_sa2_breaks(REAL_FEATURES, REAL_CONC, REAL_BROAD)
        self.assertTrue(res.records)
        missing5 = {c for c, _ in res.missing_broadacre}
        self.assertIn("51285", missing5)   # Geraldton
        self.assertIn("51287", missing5)   # Geraldton - North


if __name__ == "__main__":
    unittest.main()
