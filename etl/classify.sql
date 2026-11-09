CREATE TEMP TABLE etl_prices ON COMMIT DROP AS
WITH rates AS (
    SELECT DISTINCT ON (num_code, setting_date) num_code, setting_date, value
    FROM raw.exchange_rates
    WHERE num_code IN ('840', '978')
    ORDER BY num_code, setting_date, id
)
SELECT
    p.id AS price_id,
    p.loading_date,
    p.loading_city_gcid,
    p.unloading_city_gcid,
    p.organization_id,
    p.price_type,
    p.is_fact,
    p.complex,
    p.outlier_mark,
    p.distance,
    p.total_weight,
    p.total_volume,
    p.weight_category,
    p.volume_category,
    p.body_type,
    core.body_group_id(COALESCE(b.std_id, p.body_type)) AS primary_body_group_id,
    p.price,
    CASE WHEN p.currency_code = '643' THEN 1::double precision ELSE r.value END AS rate,
    CASE
        WHEN p.price <= 0 OR p.price >= 'Infinity'::float8 THEN 'INVALID_PRICE'
        WHEN p.currency_code = '643' AND p.price <= 1000 THEN 'RUB_PRICE_TOO_LOW'
        WHEN p.distance <= 0 OR p.distance >= 'Infinity'::float8 THEN 'INVALID_DISTANCE'
        WHEN p.total_weight < 0 OR p.total_weight >= 'Infinity'::float8 THEN 'INVALID_WEIGHT'
        WHEN p.total_volume < 0 OR p.total_volume >= 'Infinity'::float8 THEN 'INVALID_VOLUME'
        WHEN origin.gc_id IS NULL OR destination.gc_id IS NULL THEN 'UNKNOWN_CITY'
        WHEN p.currency_code NOT IN ('643', '840', '978') THEN 'UNSUPPORTED_CURRENCY'
        WHEN p.currency_code <> '643' AND r.value IS NULL THEN 'MISSING_FX_RATE'
        WHEN r.value <= 0 OR r.value >= 'Infinity'::float8 THEN 'INVALID_FX_RATE'
    END AS reason
FROM etl_candidates AS candidate
JOIN raw.prices AS p ON p.id = candidate.price_id
LEFT JOIN core.source_cities AS origin ON origin.gc_id = p.loading_city_gcid
LEFT JOIN core.source_cities AS destination ON destination.gc_id = p.unloading_city_gcid
LEFT JOIN raw.body_types AS b ON b.id = p.body_type
LEFT JOIN rates AS r ON r.num_code = p.currency_code AND r.setting_date = p.nearest_rate_date;
