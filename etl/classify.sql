CREATE TEMP TABLE etl_prices ON COMMIT DROP AS
WITH rates AS (
    SELECT DISTINCT ON (num_code, setting_date) num_code, setting_date, value
    FROM raw.exchange_rates
    WHERE num_code IN ('840', '978')
    ORDER BY num_code, setting_date, id
), source AS (
    SELECT
        p.id AS price_id, p.loading_date, p.loading_city_gcid, p.unloading_city_gcid,
        p.organization_id, p.price_type, p.is_fact, p.complex, p.outlier_mark,
        p.distance, p.total_weight, p.total_volume, p.weight_category, p.volume_category,
        core.body_group_id(COALESCE(b.std_id, p.body_type)) AS primary_body_group_id,
        GREATEST(p.created_at::date, p.updated_at::date) AS source_available_on,
        r.setting_date AS fx_date, p.price, p.currency_code,
        CASE WHEN p.currency_code = '643' THEN 1::double precision ELSE r.value END AS rate,
        origin.gc_id IS NOT NULL AND destination.gc_id IS NOT NULL AS known_route
    FROM etl_candidates AS candidate
    JOIN raw.prices AS p ON p.id = candidate.price_id
    LEFT JOIN core.source_cities AS origin ON origin.gc_id = p.loading_city_gcid
    LEFT JOIN core.source_cities AS destination ON destination.gc_id = p.unloading_city_gcid
    LEFT JOIN raw.body_types AS b ON b.id = p.body_type
    LEFT JOIN rates AS r ON r.num_code = p.currency_code AND r.setting_date = p.nearest_rate_date
), validated AS (
    SELECT source.*,
        CASE
            WHEN loading_date NOT BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'
                THEN 'INVALID_LOADING_DATE'
            -- Bound values before conversion to CatBoost's float32 feature representation.
            WHEN distance NOT BETWEEN 1e-37 AND 1e37 THEN 'INVALID_DISTANCE'
            WHEN total_weight NOT BETWEEN 0 AND 1e37 THEN 'INVALID_WEIGHT'
            WHEN total_volume NOT BETWEEN 0 AND 1e37 THEN 'INVALID_VOLUME'
            WHEN NOT known_route THEN 'UNKNOWN_CITY'
        END AS feature_reason,
        CASE WHEN price > 0 AND price < 'Infinity'::float8
                   AND rate > 0 AND rate < 'Infinity'::float8
            THEN price::numeric * rate::numeric
        END AS price_rub
    FROM source
)
SELECT
    price_id, loading_date, loading_city_gcid, unloading_city_gcid,
    organization_id, price_type, is_fact, complex, outlier_mark,
    distance, total_weight, total_volume, primary_body_group_id, price_rub, source_available_on,
    GREATEST(source_available_on, fx_date) AS available_on,
    feature_reason,
    COALESCE(NULLIF(BTRIM(weight_category), ''), CASE
        WHEN weight.rounded >= 30 THEN 'G20T'
        WHEN weight.rounded >= 10 THEN 'FTL'
        WHEN weight.rounded >= 5 THEN '10T'
        WHEN weight.rounded >= 2.5 THEN '5T'
        WHEN weight.rounded >= 0.5 THEN 'L5T'
        ELSE 'OTH'
    END) AS weight_category,
    COALESCE(NULLIF(BTRIM(volume_category), ''), CASE
        WHEN total_volume > 0 AND total_volume <= 120 THEN 'FTL'
        ELSE 'OTH'
    END) AS volume_category,
    CASE
        WHEN price <= 0 OR price >= 'Infinity'::float8 THEN 'INVALID_PRICE'
        WHEN currency_code = '643' AND price <= 1000 THEN 'RUB_PRICE_TOO_LOW'
        WHEN feature_reason IS NOT NULL THEN feature_reason
        WHEN currency_code NOT IN ('643', '840', '978') THEN 'UNSUPPORTED_CURRENCY'
        WHEN rate IS NULL THEN 'MISSING_FX_RATE'
        WHEN rate <= 0 OR rate >= 'Infinity'::float8 THEN 'INVALID_FX_RATE'
        WHEN price_rub NOT BETWEEN 1e-37 AND 1e37 THEN 'INVALID_NORMALIZED_PRICE'
    END AS reason
FROM validated
CROSS JOIN LATERAL (
    SELECT CASE WHEN feature_reason IS NULL THEN ROUND(total_weight::numeric, 1) END AS rounded
) AS weight;
