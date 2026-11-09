INSERT INTO raw.cities (id, gc_id, name, full_name_local, full_name_gc, latitude, longitude)
VALUES
    (900001, 990001, 'Казань', 'Казань, Республика Татарстан', 'Казань', 55.8, 49.1),
    (900002, 990001, 'Дубликат', 'Казань, Татарстан', 'Казань', 55.8, 49.1),
    (900003, 990002, 'Москва', 'Москва, г. Москва', 'Москва', 'NaN'::float8, 181);

INSERT INTO raw.exchange_rates (num_code, value, setting_date)
VALUES ('840', 75, '2022-01-01'), ('840', 77, '2022-01-01'), ('840', 90, '2022-01-15');

INSERT INTO raw.prices (
    id, created_at, organization_id, loading_date, loading_city_gcid, unloading_city_gcid,
    distance, total_weight, total_volume, body_type, price, price_type
)
SELECT 90000000 + i, TIMESTAMP '2022-01-02', 101, DATE '2022-01-15', 990001, 990002,
    100, 9.95, 120, 57, 2500, 3
FROM generate_series(1, 17) AS i;

UPDATE raw.prices SET price = 20, currency_code = '840', nearest_rate_date = '2022-01-01'
WHERE id = 90000001;
UPDATE raw.prices SET price_type = 1, organization_id = 102 WHERE id = 90000002;
UPDATE raw.prices SET price_type = 9, price = 3500 WHERE id = 90000003;
UPDATE raw.prices SET loading_date = '2022-02-10', outlier_mark = true WHERE id = 90000004;
UPDATE raw.prices SET price = 0 WHERE id = 90000005;
UPDATE raw.prices SET price = 1000 WHERE id = 90000006;
UPDATE raw.prices SET distance = -1 WHERE id = 90000007;
UPDATE raw.prices SET total_weight = -1 WHERE id = 90000008;
UPDATE raw.prices SET total_volume = -1 WHERE id = 90000009;
UPDATE raw.prices SET unloading_city_gcid = 0 WHERE id = 90000010;
UPDATE raw.prices SET currency_code = '999' WHERE id = 90000011;
UPDATE raw.prices SET currency_code = '840', nearest_rate_date = '2022-01-03' WHERE id = 90000012;
UPDATE raw.prices SET distance = 'NaN'::float8 WHERE id = 90000013;
UPDATE raw.prices SET unloading_city_gcid = 990001, body_type = NULL, total_volume = 0
WHERE id = 90000014;
UPDATE raw.prices SET loading_date = '2021-01-15', price = 1250 WHERE id = 90000015;
UPDATE raw.prices SET loading_date = '2021-12-15', price = 2000 WHERE id = 90000016;
UPDATE raw.prices SET currency_code = '840', nearest_rate_date = NULL WHERE id = 90000017;

INSERT INTO raw.price_body_types (price_id, body_type_id)
VALUES (90000001, 57), (90000001, 61), (90000001, 4);

INSERT INTO raw.price_dates (price_id, price_date)
SELECT id, loading_date FROM raw.prices WHERE id BETWEEN 90000001 AND 90000017;
INSERT INTO raw.price_dates (price_id, price_date)
VALUES (90000001, '2022-01-25'), (90000001, '2022-03-01'), (90000001, '2026-10-27');
