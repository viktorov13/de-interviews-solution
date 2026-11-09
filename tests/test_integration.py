import unittest
from datetime import date
from pathlib import Path

import psycopg

from etl.load import load_core
from mart.refresh import refresh_corridor
from ml.features import AS_OF, TEST_START


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
            """, (TEST_START, AS_OF)).fetchone()
            expected_future, = conn.execute("""
                SELECT COUNT(*) FROM core.prices WHERE loading_date > %s AND NOT complex
            """, (AS_OF,)).fetchone()
            self.assertEqual((history, future, invalid), (expected_history, expected_future, 0))
            self.assertGreater(history, 0)
            self.assertGreater(future, 0)
            self.assertEqual(conn.execute("""
                SELECT test_rows, future_rows FROM mart.ml_evaluation WHERE as_of = %s
            """, (AS_OF,)).fetchone(), (history, future))
