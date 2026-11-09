import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg

from etl.load import load_core
from mart.refresh import refresh_corridor
from ml.features import AS_OF, TEST_START, build_features, read_candidates
from ml.score import MODEL_NAME
from pipeline import run


class IntegrationTest(unittest.TestCase):
    def test_etl_and_market_edge_cases(self):
        with psycopg.connect(autocommit=True) as conn, conn.transaction(force_rollback=True):
            conn.execute(Path(__file__).with_name("edge_cases.sql").read_text(encoding="utf-8"))
            stats = load_core(conn, date(2021, 1, 1), date(2022, 4, 1))
            self.assertEqual(stats["source_rows"], 18)
            self.assertEqual(stats["loaded_rows"], 8)
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

            load_core(conn, date(2026, 11, 1), date(2026, 11, 2))
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
                SELECT COUNT(*) FROM core.market_facts
                WHERE price_type IN (3, 9) AND loading_date BETWEEN %s AND %s
                    AND (available_on IS NULL OR available_on <= %s)
            """, (TEST_START, AS_OF, AS_OF)).fetchone()
            expected_future, = conn.execute("""
                SELECT COUNT(*) FROM core.forecast_requests WHERE loading_date > %s
            """, (AS_OF,)).fetchone()
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
                    fx_date::date, 1001, 1002, 700, 10, 20, 56, 3000, price_type
                FROM (VALUES
                    (91000001, '2026-10-04', '2026-10-04', '2026-10-04', '643', NULL, 3),
                    (91000002, '2026-10-04', '2026-10-05', NULL, '643', NULL, 3),
                    (91000003, '2026-10-04', '2026-10-03', '2026-10-05', '643', NULL, 3),
                    (91000004, '2026-10-04', '2026-10-03', '2026-10-03', '840', '2026-10-06', 3),
                    (91000005, '2026-10-05', '2026-10-05', NULL, '643', NULL, 3),
                    (91000006, '2026-10-26', '2026-10-26', '2026-10-27', '643', NULL, 3),
                    (91000007, '2026-10-27', '2026-10-26', NULL, '643', NULL, 3),
                    (91000008, '2026-10-27', '2026-10-27', NULL, '643', NULL, 3),
                    (91000009, '2026-10-04', NULL, NULL, '643', NULL, 3),
                    (91000010, '2026-10-05', '2026-10-05', NULL, '643', NULL, 2)
                ) AS fixture(id, loading, created, updated, currency, fx_date, price_type)
            """)
            load_core(conn, date(2026, 10, 4), date(2026, 10, 28))
            self.assertEqual(conn.execute("""
                SELECT COUNT(*) FROM core.prices WHERE price_id BETWEEN 91000001 AND 91000010
            """).fetchone(), (10,))

            rows = read_candidates(conn)
            fixture = rows.loc[rows["price_id"].between(91000001, 91000010)].set_index("price_id")
            self.assertEqual(set(fixture.index), {91000001, 91000005, 91000007, 91000009})
            self.assertTrue(fixture.loc[[91000007], "actual_price_rub"].isna().all())

    def test_backfill_handles_moves_deletions_and_repaired_prices(self):
        with psycopg.connect(autocommit=True) as conn, conn.transaction(force_rollback=True):
            conn.execute(Path(__file__).with_name("edge_cases.sql").read_text(encoding="utf-8"))
            start, end = date(2022, 1, 1), date(2022, 2, 1)
            load_core(conn, start, end)

            conn.execute("""
                UPDATE raw.prices SET loading_date = DATE '2022-04-01' WHERE id = 90000001;
                DELETE FROM raw.prices WHERE id = 90000002;
                UPDATE raw.prices SET price = 2300 WHERE id = 90000005;
            """)
            stats = load_core(conn, start, end)
            self.assertEqual(stats["deleted_source_rows"], 1)
            self.assertEqual(conn.execute("""
                SELECT price_id, loading_date, price_rub FROM core.prices
                WHERE price_id IN (90000001, 90000002, 90000005) ORDER BY price_id
            """).fetchall(), [(90000001, date(2022, 4, 1), 1500), (90000005, date(2022, 1, 15), 2300)])
            self.assertEqual(conn.execute("""
                SELECT COUNT(*) FROM core.dq_quarantine_prices WHERE price_id = 90000005
            """).fetchone(), (0,))

    def test_scoring_failure_rolls_back_core_and_quarantine(self):
        with psycopg.connect(autocommit=True) as observer:
            price_id, price_rub = observer.execute("""
                SELECT price_id, price_rub FROM core.market_facts
                WHERE loading_date = %s ORDER BY price_id LIMIT 1
            """, (TEST_START,)).fetchone()

            def change_source_then_load(conn, start, end):
                conn.execute("UPDATE raw.prices SET price = 0 WHERE id = %s", (price_id,))
                return load_core(conn, start, end)

            def fail_scoring(conn):
                self.assertEqual(conn.execute("""
                    SELECT reason FROM core.dq_quarantine_prices WHERE price_id = %s
                """, (price_id,)).fetchone(), ("INVALID_PRICE",))
                raise RuntimeError("injected scoring failure")

            with (
                patch("pipeline.load_core", side_effect=change_source_then_load),
                patch("pipeline.score_batch", side_effect=fail_scoring),
                self.assertRaisesRegex(RuntimeError, "injected scoring failure"),
            ):
                run(TEST_START, date(2026, 10, 6))

            self.assertEqual(observer.execute("""
                SELECT price_rub FROM core.prices WHERE price_id = %s
            """, (price_id,)).fetchone(), (price_rub,))
            self.assertEqual(observer.execute("""
                SELECT COUNT(*) FROM core.dq_quarantine_prices WHERE price_id = %s
            """, (price_id,)).fetchone(), (0,))

    def test_label_free_forecasts_and_malformed_values(self):
        with psycopg.connect(autocommit=True) as conn, conn.transaction(force_rollback=True):
            conn.execute("""
                INSERT INTO raw.prices (
                    id, loading_date, created_at, currency_code, nearest_rate_date,
                    loading_city_gcid, unloading_city_gcid, distance, total_weight, total_volume,
                    body_type, price, price_type
                )
                SELECT id, loading::date, DATE '2026-10-26', currency, fx_date::date,
                    1001, 1002, distance, 10, 20, 57, price, 3
                FROM (VALUES
                    (92000001, '2500-01-01', '643', NULL, 700, 0),
                    (92000002, '2026-11-01', '840', NULL, 700, 35),
                    (92000003, '2026-11-01', '643', NULL, 1e200, 3000),
                    (92000004, '2026-11-01', '840', '2026-10-06', 700, 1e308),
                    (92000005, 'infinity', '643', NULL, 700, 3000)
                ) AS fixture(id, loading, currency, fx_date, distance, price)
            """)
            conn.execute("""
                INSERT INTO raw.price_body_types (price_id, body_type_id)
                VALUES (92000001, 61), (92000001, 4)
            """)
            load_core(conn, date(2026, 11, 1), None)

            reasons = conn.execute("""
                SELECT reason FROM core.dq_quarantine_prices
                WHERE price_id BETWEEN 92000001 AND 92000005 ORDER BY price_id
            """).fetchall()
            self.assertEqual(reasons, [
                ("INVALID_PRICE",), ("MISSING_FX_RATE",), ("INVALID_DISTANCE",),
                ("INVALID_NORMALIZED_PRICE",), ("INVALID_LOADING_DATE",),
            ])
            candidates = read_candidates(conn)
            rows = candidates.loc[candidates["price_id"].between(92000001, 92000005)]
            self.assertEqual(set(rows["price_id"]), {92000001, 92000002, 92000004})
            self.assertTrue(rows["actual_price_rub"].isna().all())
            distant = build_features(rows.loc[rows["price_id"] == 92000001]).iloc[0]
            self.assertEqual(distant["year"], 2500)
            self.assertEqual(distant["body_group"], "Тент")

    def test_reliability_thresholds_and_freshness(self):
        with psycopg.connect(autocommit=True) as conn, conn.transaction(force_rollback=True):
            conn.execute(Path(__file__).with_name("edge_cases.sql").read_text(encoding="utf-8"))
            conn.execute("""
                INSERT INTO raw.prices (
                    id, organization_id, loading_date, loading_city_gcid, unloading_city_gcid,
                    distance, total_weight, total_volume, body_type, price, price_type
                )
                SELECT 93000000 + body * 100 + i, i % carriers, DATE '2026-10-01',
                    990002, 990001, 100, 10, 20, body, 2000 + i, 3
                FROM (VALUES (56, 30, 5), (4, 30, 4), (2, 10, 5), (15, 9, 5))
                    AS cases(body, trips, carriers)
                CROSS JOIN LATERAL generate_series(1, trips) AS i;
                INSERT INTO raw.price_dates (price_id, price_date)
                SELECT id, loading_date FROM raw.prices
                WHERE id BETWEEN 93000000 AND 93006000;
            """)
            load_core(conn, date(2026, 10, 1), date(2026, 10, 2))

            def levels():
                return dict(conn.execute("""
                    SELECT body_group_id, reliability_level
                    FROM mart.market_corridor
                    WHERE loading_city_gcid = 990002 AND unloading_city_gcid = 990001
                """).fetchall())

            refresh_corridor(conn, date(2026, 10, 31))
            self.assertEqual(levels(), {56: "HIGH", 4: "MEDIUM", 2: "MEDIUM", 15: "LOW_DATA"})
            refresh_corridor(conn, date(2026, 11, 1))
            self.assertEqual(levels()[56], "MEDIUM")
