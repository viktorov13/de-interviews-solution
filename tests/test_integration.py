import unittest
from datetime import date
from pathlib import Path

import psycopg

from etl.load import load_core
from mart.refresh import refresh_corridor
from ml.features import AS_OF, TEST_START, read_candidates
from ml.score import MODEL_NAME


class IntegrationTest(unittest.TestCase):
    def test_etl_and_market_edge_cases(self):
        with psycopg.connect(autocommit=True) as conn, conn.transaction(force_rollback=True):
            conn.execute(Path(__file__).with_name("edge_cases.sql").read_text(encoding="utf-8"))
            stats = load_core(conn, date(2021, 1, 1), date(2022, 4, 1))
            self.assertEqual(stats["source_rows"], 17)
            self.assertEqual(stats["loaded_rows"], 7)
            self.assertEqual(stats["quarantined_rows"], 10)
            self.assertEqual(stats["quarantine_reasons"], {
                "INVALID_PRICE": 1,
                "RUB_PRICE_TOO_LOW": 1,
                "INVALID_DISTANCE": 2,
                "INVALID_WEIGHT": 1,
                "INVALID_VOLUME": 1,
                "UNKNOWN_CITY": 1,
                "UNSUPPORTED_CURRENCY": 1,
                "MISSING_FX_RATE": 2,
            })
            self.assertEqual(conn.execute("""
                SELECT price_rub, weight_category, volume_category FROM core.prices
                WHERE price_id = 90000001
            """).fetchone(), (1500, "FTL", "FTL"))
            self.assertEqual(conn.execute("""
                SELECT loading_city_gcid = unloading_city_gcid, primary_body_group_id, volume_category
                FROM core.prices WHERE price_id = 90000014
            """).fetchone(), (True, 0, "OTH"))
            self.assertEqual(conn.execute("""
                SELECT source_city_id, region FROM core.cities WHERE gc_id = 990001
            """).fetchone(), (900001, "Республика Татарстан"))
            self.assertEqual(conn.execute("""
                SELECT latitude, longitude FROM core.cities WHERE gc_id = 990002
            """).fetchone(), (None, None))
            self.assertEqual(conn.execute("""
                SELECT body_group_id FROM core.price_body_groups
                WHERE price_id = 90000001 ORDER BY body_group_id
            """).fetchall(), [(4,), (56,)])

            refresh_corridor(conn, AS_OF)
            months = conn.execute("""
                SELECT price_month, p25_trip, median_trip, p75_trip, avg_trip,
                    p25_km, median_km, p75_km, trips_count, carriers_count,
                    cv_rate, mom_pct, yoy_pct, reliability_level
                FROM mart.market_corridor
                WHERE loading_city_gcid = 990001 AND unloading_city_gcid = 990002
                    AND body_group_id = 56 AND weight_category = 'FTL'
                ORDER BY price_month
            """).fetchall()
            self.assertEqual([row[0] for row in months], [
                date(2021, 1, 1), date(2021, 12, 1), date(2022, 1, 1), date(2022, 3, 1)
            ])
            self.assertEqual(months[2][1:10], (2000, 2500, 3000, 2500, 20, 25, 30, 3, 1))
            self.assertAlmostEqual(months[2][10], 0.4)
            self.assertAlmostEqual(months[2][11], 25.0)
            self.assertAlmostEqual(months[2][12], 100.0)
            self.assertEqual(months[2][13], "LOW_DATA")
            self.assertEqual(months[3][10:13], (None, None, None))

            conn.execute("DELETE FROM raw.cities WHERE gc_id = 990001")
            self.assertEqual(conn.execute("""
                SELECT COUNT(*) FROM mart.route_card
                WHERE loading_city_gcid = 990001 AND unloading_city_gcid = 990002
                    AND body_group_id = 56 AND weight_category = 'FTL'
            """).fetchone(), (4,))

    def test_snapshot_scoring(self):
        with psycopg.connect() as conn:
            history, future, invalid = conn.execute("""
                SELECT COUNT(*) FILTER (WHERE loading_date BETWEEN %s AND %s),
                    COUNT(*) FILTER (WHERE loading_date > %s),
                    COUNT(*) FILTER (WHERE loading_date < %s OR predicted_price_rub <= 0)
                FROM mart.ml_price_predictions
            """, (TEST_START, AS_OF, AS_OF, TEST_START)).fetchone()
            expected_history, = conn.execute("""
                SELECT COUNT(*) FROM core.market_facts WHERE loading_date BETWEEN %s AND %s
                    AND (available_on IS NULL OR available_on <= %s)
            """, (TEST_START, AS_OF, AS_OF)).fetchone()
            expected_future, = conn.execute("""
                SELECT COUNT(*) FROM core.prices WHERE loading_date > %s AND NOT complex
                    AND (available_on IS NULL OR available_on <= %s)
            """, (AS_OF, AS_OF)).fetchone()
            self.assertEqual((history, future, invalid), (expected_history, expected_future, 0))
            self.assertGreater(history, 0)
            self.assertGreater(future, 0)
            self.assertEqual(conn.execute("""
                SELECT test_rows, future_rows FROM mart.ml_evaluation
                WHERE as_of = %s AND model_name = %s
            """, (AS_OF, MODEL_NAME)).fetchone(), (history, future))

    def test_ml_availability_at_temporal_boundaries(self):
        with psycopg.connect(autocommit=True) as conn, conn.transaction(force_rollback=True):
            conn.execute("""
                INSERT INTO raw.prices (
                    id, loading_date, created_at, updated_at, currency_code, nearest_rate_date,
                    loading_city_gcid, unloading_city_gcid, distance, total_weight, total_volume,
                    body_type, price, price_type
                )
                SELECT id, loading::date, created::timestamp, updated::timestamp, currency,
                    fx_date::date, 1001, 1002, 700, 10, 20, 56, 3000, 3
                FROM (VALUES
                    (91000001, '2026-10-04', '2026-10-04', '2026-10-04', '643', NULL),
                    (91000002, '2026-10-04', '2026-10-05', NULL, '643', NULL),
                    (91000003, '2026-10-04', '2026-10-03', '2026-10-05', '643', NULL),
                    (91000004, '2026-10-04', '2026-10-03', '2026-10-03', '840', '2026-10-06'),
                    (91000005, '2026-10-05', '2026-10-05', NULL, '643', NULL),
                    (91000006, '2026-10-26', '2026-10-26', '2026-10-27', '643', NULL),
                    (91000007, '2026-10-27', '2026-10-26', NULL, '643', NULL),
                    (91000008, '2026-10-27', '2026-10-27', NULL, '643', NULL),
                    (91000009, '2026-10-04', NULL, NULL, '643', NULL)
                ) AS fixture(id, loading, created, updated, currency, fx_date)
            """)
            load_core(conn, date(2026, 10, 4), date(2026, 10, 28))
            self.assertEqual(conn.execute("""
                SELECT COUNT(*) FROM core.prices WHERE price_id BETWEEN 91000001 AND 91000009
            """).fetchone(), (9,))

            rows = read_candidates(conn)
            fixture = rows.loc[rows["price_id"].between(91000001, 91000009)].set_index("price_id")
            self.assertEqual(set(fixture.index), {91000001, 91000005, 91000007, 91000009})
            self.assertTrue(fixture.loc[[91000007], "actual_price_rub"].isna().all())
