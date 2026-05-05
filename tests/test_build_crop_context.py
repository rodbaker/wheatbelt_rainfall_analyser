"""Tests for build_crop_context.py logic."""
import csv as _csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_crop_context as bcc


def _make_db(financial_year="2020-21") -> sqlite3.Connection:
    """Build an in-memory ABS-shaped SQLite DB for testing."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE census_years (
            year_id INTEGER PRIMARY KEY,
            financial_year TEXT,
            release_date TEXT,
            evao_threshold REAL,
            asgs_edition TEXT,
            source_file TEXT
        );
        CREATE TABLE regions (
            region_code TEXT PRIMARY KEY,
            region_label TEXT,
            region_level INTEGER,
            asgs_edition TEXT,
            asgs_editions TEXT
        );
        CREATE TABLE observations (
            obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
            year_id INTEGER,
            region_code TEXT,
            commodity_code TEXT,
            estimate REAL,
            rse TEXT,
            n_businesses REAL,
            n_businesses_rse TEXT
        );
    """)
    conn.execute(
        "INSERT INTO census_years VALUES (3, ?, '2022-07-26', 40000, '3', 'test.csv')",
        (financial_year,),
    )
    conn.execute(
        "INSERT INTO regions VALUES ('501031017', 'Merredin', 9, '2016', '2016')"
    )
    conn.execute(
        "INSERT INTO regions VALUES ('502041050', 'Esperance', 9, '2016', '2016')"
    )
    # Wheat area for Merredin
    conn.execute(
        "INSERT INTO observations (year_id, region_code, commodity_code, estimate, rse, n_businesses, n_businesses_rse) "
        "VALUES (3, '501031017', 'AGCEREAL_AHAWHT_F', 50000.0, '^', 120.0, '')"
    )
    # Wheat production — suppressed (null)
    conn.execute(
        "INSERT INTO observations (year_id, region_code, commodity_code, estimate, rse, n_businesses, n_businesses_rse) "
        "VALUES (3, '501031017', 'AGCEREAL_ATOWHT_F', NULL, '', NULL, '')"
    )
    # Wheat yield
    conn.execute(
        "INSERT INTO observations (year_id, region_code, commodity_code, estimate, rse, n_businesses, n_businesses_rse) "
        "VALUES (3, '501031017', 'WHEAT_YIELD_F', 2.1, '', 120.0, '')"
    )
    # Barley area for Merredin
    conn.execute(
        "INSERT INTO observations (year_id, region_code, commodity_code, estimate, rse, n_businesses, n_businesses_rse) "
        "VALUES (3, '501031017', 'AGCEREAL_AHABAR_F', 10000.0, '', 50.0, '')"
    )
    conn.commit()
    return conn


_STATION_SA2S = {
    "51017": {"sa2_name": "Merredin", "state": "Western Australia"},
    "52050": {"sa2_name": "Esperance", "state": "Western Australia"},
    "21081": {"sa2_name": "Bairnsdale", "state": "Victoria"},  # not in GeoJSON or test DB → unmatched
}

_GEOJSON_MAP = {
    "51017": "501031017",
    "52050": "502041050",
    # '21081' deliberately absent — exercises unmatched path
}

_CROPS = {
    "wheat": {
        "label": "Wheat",
        "area_code": "AGCEREAL_AHAWHT_F",
        "production_code": "AGCEREAL_ATOWHT_F",
        "yield_code": "WHEAT_YIELD_F",
    },
    "barley": {
        "label": "Barley",
        "area_code": "AGCEREAL_AHABAR_F",
        "production_code": "AGCEREAL_ATOBAR_F",
        "yield_code": "BARLEY_YIELD_F",
    },
}

_CFG = {"baseline_year": "2020-21", "crops": _CROPS}


def _rows_for(rows, station_5dig, crop=None):
    """Filter rows by station_sa2_5dig16 and optional crop."""
    return [
        r for r in rows
        if r["station_sa2_5dig16"] == station_5dig
        and (crop is None or r["crop"] == crop)
    ]


class TestBuildCropContext(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()

    def tearDown(self):
        self.conn.close()

    def test_get_year_id(self):
        self.assertEqual(bcc.get_year_id(self.conn, "2020-21"), 3)

    def test_get_year_id_missing(self):
        with self.assertRaises(ValueError):
            bcc.get_year_id(self.conn, "1999-00")

    def test_batch_query_observations_returns_known_row(self):
        obs = bcc.batch_query_observations(
            self.conn, 3, ["501031017"], ["AGCEREAL_AHAWHT_F"]
        )
        self.assertIn(("501031017", "AGCEREAL_AHAWHT_F"), obs)
        estimate, rse = obs[("501031017", "AGCEREAL_AHAWHT_F")]
        self.assertAlmostEqual(estimate, 50000.0)
        self.assertEqual(rse, "^")

    def test_null_estimate_treated_as_missing(self):
        obs = bcc.batch_query_observations(
            self.conn, 3, ["501031017"], ["AGCEREAL_ATOWHT_F"]
        )
        estimate, _ = obs[("501031017", "AGCEREAL_ATOWHT_F")]
        self.assertIsNone(estimate)

    # --- sa2_code is the full 9-digit ABS code ---

    def test_sa2_code_is_9_digits_for_matched(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        matched = [r for r in rows if r["boundary_status"] == "matched"]
        self.assertTrue(len(matched) > 0)
        for r in matched:
            self.assertEqual(len(r["sa2_code"]), 9, f"Expected 9-digit sa2_code, got {r['sa2_code']!r}")

    def test_sa2_code_is_string(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        for r in rows:
            self.assertIsInstance(r["sa2_code"], str)

    def test_sa2_code_empty_for_unmatched(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        unmatched = _rows_for(rows, "21081")
        self.assertTrue(len(unmatched) > 0)
        for r in unmatched:
            self.assertEqual(r["sa2_code"], "")

    def test_sa2_code_matches_geojson_main16(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        merredin = _rows_for(rows, "51017", "wheat")[0]
        self.assertEqual(merredin["sa2_code"], "501031017")

    # --- station_sa2_5dig16 traceability ---

    def test_station_sa2_5dig16_preserved(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        for r in rows:
            self.assertIn("station_sa2_5dig16", r)
            self.assertIsInstance(r["station_sa2_5dig16"], str)
        five_digits = {r["station_sa2_5dig16"] for r in rows}
        self.assertIn("51017", five_digits)
        self.assertIn("52050", five_digits)
        self.assertIn("21081", five_digits)

    def test_station_sa2_5dig16_is_5_digits_for_matched(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        matched = [r for r in rows if r["boundary_status"] == "matched"]
        for r in matched:
            self.assertEqual(len(r["station_sa2_5dig16"]), 5)

    # --- area_share ---

    def test_build_rows_area_share(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        wheat_row = _rows_for(rows, "51017", "wheat")[0]
        # total non-null area for Merredin = 50000 (wheat) + 10000 (barley) = 60000
        self.assertAlmostEqual(wheat_row["area_share"], 50000 / 60000)

    def test_area_share_present_when_area_ha_not_null(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        wheat_row = _rows_for(rows, "51017", "wheat")[0]
        # area_ha is not null even though production is suppressed
        self.assertIsNotNone(wheat_row["area_share"])

    def test_area_share_null_when_no_area_data(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        # Esperance has no observations in the test DB
        esp_wheat = _rows_for(rows, "52050", "wheat")[0]
        self.assertIsNone(esp_wheat["area_share"])

    # --- boundary_status and unmatched ---

    def test_build_rows_unmatched_boundary(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        unmatched_rows = _rows_for(rows, "21081")
        self.assertTrue(len(unmatched_rows) > 0)
        self.assertEqual(unmatched_rows[0]["boundary_status"], "unmatched")
        for r in unmatched_rows:
            self.assertIsNone(r["area_ha"])

    # --- suppressed values ---

    def test_null_estimate_area_ha_is_none(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        # Merredin wheat production is suppressed (NULL in DB)
        wheat_row = _rows_for(rows, "51017", "wheat")[0]
        self.assertIsNone(wheat_row["production_t"])

    def test_build_rows_null_count_production(self):
        rows, stats = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        self.assertGreater(stats["null_counts"]["production_t"], 0)

    def test_rse_preserved_as_string(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        wheat_row = _rows_for(rows, "51017", "wheat")[0]
        self.assertIsInstance(wheat_row["area_rse"], str)
        self.assertEqual(wheat_row["area_rse"], "^")

    # --- output schema ---

    def test_output_has_all_columns(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        for row in rows:
            for col in bcc.OUTPUT_COLS:
                self.assertIn(col, row, f"Missing column {col!r}")

    def test_write_csv_roundtrip(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            tmp = Path(f.name)
        bcc.write_csv(rows, tmp)
        with open(tmp) as f:
            written = list(_csv.DictReader(f))
        tmp.unlink()
        self.assertEqual(len(written), len(rows))
        # 9-digit sa2_code must survive round-trip as string
        codes = {r["sa2_code"] for r in written}
        self.assertIn("501031017", codes)
        # 5-digit traceability field must also survive
        five_codes = {r["station_sa2_5dig16"] for r in written}
        self.assertIn("51017", five_codes)

    def test_top_crop_by_area_per_state(self):
        rows, _ = bcc.build_rows(_STATION_SA2S, _GEOJSON_MAP, self.conn, _CFG)
        top = bcc.top_crop_by_area_per_state(rows)
        # WA Merredin has wheat=50000 > barley=10000
        self.assertIn("Western Australia", top)
        self.assertEqual(top["Western Australia"][0], "wheat")


class TestGeojsonAsUniverse(unittest.TestCase):
    """Verify that GeoJSON — not station metadata — drives the SA2 universe."""

    def setUp(self):
        self.conn = _make_db()
        # geojson_sa2s includes Albany Region (51226) which has no station in metadata
        self.geojson_sa2s = {
            "51017": {"sa2_name": "Merredin", "state": "Western Australia"},
            "51226": {"sa2_name": "Albany Region", "state": "Western Australia"},
        }
        self.geojson_map = {
            "51017": "501031017",
            "51226": "509011226",
        }

    def tearDown(self):
        self.conn.close()

    def test_sa2_without_station_metadata_is_included(self):
        """An SA2 present in GeoJSON but absent from station metadata must appear in output."""
        rows, _ = bcc.build_rows(self.geojson_sa2s, self.geojson_map, self.conn, _CFG)
        five_digs = {r["station_sa2_5dig16"] for r in rows}
        self.assertIn("51226", five_digs, "Albany Region (GeoJSON-only) must appear in output")

    def test_albany_region_retained(self):
        """Albany Region (51226 / 509011226) is retained when GeoJSON is the universe."""
        rows, _ = bcc.build_rows(self.geojson_sa2s, self.geojson_map, self.conn, _CFG)
        albany_rows = [r for r in rows if r["station_sa2_5dig16"] == "51226"]
        self.assertTrue(len(albany_rows) > 0)
        self.assertEqual(albany_rows[0]["sa2_name"], "Albany Region")

    def test_station_metadata_not_universe_limiter(self):
        """Passing only station SA2s would miss Albany; GeoJSON-sourced universe includes it."""
        # Station metadata universe — missing Albany
        station_only_sa2s = {"51017": {"sa2_name": "Merredin", "state": "Western Australia"}}
        rows_station, _ = bcc.build_rows(station_only_sa2s, self.geojson_map, self.conn, _CFG)
        five_digs_station = {r["station_sa2_5dig16"] for r in rows_station}

        # GeoJSON universe — includes Albany
        rows_geojson, _ = bcc.build_rows(self.geojson_sa2s, self.geojson_map, self.conn, _CFG)
        five_digs_geojson = {r["station_sa2_5dig16"] for r in rows_geojson}

        self.assertNotIn("51226", five_digs_station, "station-only universe must miss Albany")
        self.assertIn("51226", five_digs_geojson, "GeoJSON universe must include Albany")

    def test_sa2_codes_are_strings(self):
        """sa2_code values must be strings, not integers, to preserve leading digits."""
        rows, _ = bcc.build_rows(self.geojson_sa2s, self.geojson_map, self.conn, _CFG)
        for r in rows:
            self.assertIsInstance(r["sa2_code"], str, f"sa2_code must be str, got {type(r['sa2_code'])}")


# ---------------------------------------------------------------------------
# WA QGIS universe loader
# ---------------------------------------------------------------------------

_WA_UNIVERSE_CSV = """\
SA2_CODE21,SA2_NAME21
501021007,Capel
501031017,Bridgetown - Boyup Brook
509011226,Albany Surrounds
509011229,Gnowangerup
509011230,Katanning
509011231,Kojonup
509011234,Plantagenet
509021236,Chittering
509021237,Cunderdin
509021238,Dowerin
509021239,Gingin - Dandaragan
509021240,Merredin
509021241,Moora
509021242,Mukinbudin
509021243,Northam
509021244,Toodyay
509021245,York - Beverley
509031246,Brookton
509031247,Kulin
509031249,Narrogin
509031250,Wagin
511011274,Esperance
511011275,Esperance Surrounds
511041285,Geraldton
511041287,Geraldton - North
511041289,Irwin
511041291,Morawa
511041292,Northampton - Mullewa - Greenough
"""

_EXCLUDED_FROM_QGIS = [
    "501011003",  # Busselton Region
    "501031018",  # Donnybrook - Balingup
    "509031248",  # Murray
    "511021276",  # Carnarvon
    "511021277",  # Exmouth
    "511041290",  # Meekatharra
]


def _write_wa_universe(tmp_path) -> Path:
    p = tmp_path / "wa_wheatbelt_sa2_universe_2021.csv"
    p.write_text(_WA_UNIVERSE_CSV)
    return p


class TestWaQgisUniverse(unittest.TestCase):
    """Tests for load_wa_wheatbelt_universe and QGIS-sourced WA crop context."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._universe_path = Path(self._tmp) / "wa_universe.csv"
        self._universe_path.write_text(_WA_UNIVERSE_CSV)
        self.conn = _make_db()

    def tearDown(self):
        self.conn.close()
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    # 1. Loader returns exactly 28 rows
    def test_loader_returns_28_sa2s(self):
        sa2s, sa2_map = bcc.load_wa_wheatbelt_universe(self._universe_path)
        self.assertEqual(len(sa2s), 28)
        self.assertEqual(len(sa2_map), 28)

    # 2. Capel, Esperance, Geraldton-North are included
    def test_capel_included(self):
        sa2s, sa2_map = bcc.load_wa_wheatbelt_universe(self._universe_path)
        self.assertIn("501021007", sa2_map.values())

    def test_esperance_included(self):
        sa2s, sa2_map = bcc.load_wa_wheatbelt_universe(self._universe_path)
        self.assertIn("511011274", sa2_map.values())

    def test_geraldton_north_included(self):
        sa2s, sa2_map = bcc.load_wa_wheatbelt_universe(self._universe_path)
        self.assertIn("511041287", sa2_map.values())

    # 3. ABS-excluded edge regions absent from QGIS universe
    def test_excluded_regions_not_in_universe(self):
        _, sa2_map = bcc.load_wa_wheatbelt_universe(self._universe_path)
        main_codes = set(sa2_map.values())
        for code in _EXCLUDED_FROM_QGIS:
            self.assertNotIn(code, main_codes, f"{code} must be excluded from WA universe")

    # 4. Null-area QGIS regions are retained in build output
    def test_null_area_qgis_regions_retained(self):
        """Esperance Surrounds, Geraldton-North, Morawa have null ABS area but must appear in output."""
        sa2s, sa2_map = bcc.load_wa_wheatbelt_universe(self._universe_path)
        rows, _ = bcc.build_rows(sa2s, sa2_map, self.conn, _CFG)
        present_main = {r["sa2_code"] for r in rows}
        for code in ("511011275", "511041287", "511041291"):
            self.assertIn(code, present_main, f"{code} must be retained even with null area")

    # 5. QGIS names override ABS/GeoJSON names where they differ
    def test_albany_surrounds_name_used(self):
        sa2s, sa2_map = bcc.load_wa_wheatbelt_universe(self._universe_path)
        rows, _ = bcc.build_rows(sa2s, sa2_map, self.conn, _CFG)
        albany = next((r for r in rows if r["sa2_code"] == "509011226"), None)
        if albany:
            self.assertEqual(albany["sa2_name"], "Albany Surrounds")

    def test_esperance_surrounds_name_used(self):
        sa2s, sa2_map = bcc.load_wa_wheatbelt_universe(self._universe_path)
        rows, _ = bcc.build_rows(sa2s, sa2_map, self.conn, _CFG)
        esp = next((r for r in rows if r["sa2_code"] == "511011275"), None)
        if esp:
            self.assertEqual(esp["sa2_name"], "Esperance Surrounds")

    # 6. SA2 codes remain strings
    def test_sa2_codes_are_strings(self):
        sa2s, sa2_map = bcc.load_wa_wheatbelt_universe(self._universe_path)
        for code_5, code_21 in sa2_map.items():
            self.assertIsInstance(code_5, str)
            self.assertIsInstance(code_21, str)
        rows, _ = bcc.build_rows(sa2s, sa2_map, self.conn, _CFG)
        for r in rows:
            self.assertIsInstance(r["sa2_code"], str)
            self.assertIsInstance(r["station_sa2_5dig16"], str)

    # 7. Crop context output has 28 WA SA2s × configured crops
    def test_crop_context_28_sa2s_times_crops(self):
        sa2s, sa2_map = bcc.load_wa_wheatbelt_universe(self._universe_path)
        rows, _ = bcc.build_rows(sa2s, sa2_map, self.conn, _CFG)
        n_crops = len(_CFG["crops"])
        self.assertEqual(len(rows), 28 * n_crops)

    # 8. Join output (via build_join) preserves all 28 WA SA2s
    def test_join_preserves_all_28_wa_sa2s(self):
        import sys
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from join_sa2_rainfall_crop_context import build_join
        import pandas as pd

        sa2s, sa2_map = bcc.load_wa_wheatbelt_universe(self._universe_path)
        rows, _ = bcc.build_rows(sa2s, sa2_map, self.conn, _CFG)

        # Build a crop-context DataFrame from the wheat rows only (one crop for simplicity)
        wheat_rows = [r for r in rows if r["crop"] == "wheat"]
        ctx_df = pd.DataFrame(wheat_rows).rename(columns={"sa2_code": "abs_sa2_code_raw"})
        # join_sa2_rainfall_crop_context expects columns: sa2_code, station_sa2_5dig16, ...
        ctx_df["sa2_code"] = ctx_df["abs_sa2_code_raw"]
        ctx_df["financial_year"] = "2020-21"

        # Empty features — all rows get no_data
        feat_df = pd.DataFrame(columns=["sa2_code", "season_year", "station_count",
                                         "aggregation_method", "feature_quality_flag"])

        result = build_join(feat_df, ctx_df)
        self.assertEqual(result["abs_sa2_code"].nunique(), 28)
