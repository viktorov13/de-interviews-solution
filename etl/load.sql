DELETE FROM core.prices AS p USING etl_candidates AS candidate
WHERE p.price_id = candidate.price_id;

DELETE FROM core.dq_quarantine_prices AS p USING etl_candidates AS candidate
WHERE p.price_id = candidate.price_id;

DELETE FROM core.forecast_requests AS p USING etl_candidates AS candidate
WHERE p.price_id = candidate.price_id;

INSERT INTO core.dq_quarantine_prices (price_id, loading_date, reason)
SELECT price_id, loading_date, reason
FROM etl_prices
WHERE reason IS NOT NULL;

INSERT INTO core.prices (
    price_id, loading_date, loading_city_gcid, unloading_city_gcid, organization_id,
    price_type, is_fact, complex, outlier_mark, distance, total_weight, total_volume,
    weight_category, volume_category, primary_body_group_id, price_rub, available_on
)
SELECT
    price_id, loading_date, loading_city_gcid, unloading_city_gcid, organization_id,
    price_type, is_fact, complex, outlier_mark, distance, total_weight, total_volume,
    weight_category, volume_category, primary_body_group_id, price_rub, available_on
FROM etl_prices
WHERE reason IS NULL;

CREATE TEMP TABLE etl_forecast ON COMMIT DROP AS
SELECT p.*
FROM etl_prices AS p
CROSS JOIN (SELECT MAX(as_of) AS as_of FROM raw.snapshot) AS snapshot
WHERE p.feature_reason IS NULL AND NOT p.complex AND p.loading_date > snapshot.as_of
    AND (p.source_available_on IS NULL OR p.source_available_on <= snapshot.as_of);

CREATE TEMP TABLE etl_body_groups ON COMMIT DROP AS
SELECT DISTINCT
    p.price_id,
    CASE WHEN link.body_type_id IS NULL THEN p.primary_body_group_id
         ELSE core.body_group_id(COALESCE(b.std_id, link.body_type_id))
    END AS body_group_id
FROM etl_prices AS p
LEFT JOIN raw.price_body_types AS link USING (price_id)
LEFT JOIN raw.body_types AS b ON b.id = link.body_type_id
WHERE p.reason IS NULL OR p.price_id IN (SELECT price_id FROM etl_forecast);

INSERT INTO core.price_body_groups (price_id, body_group_id)
SELECT b.price_id, b.body_group_id
FROM etl_body_groups AS b
JOIN core.prices AS p USING (price_id);

INSERT INTO core.forecast_requests (
    price_id, loading_date, loading_city_gcid, unloading_city_gcid, distance,
    total_weight, total_volume, weight_category, volume_category, body_group_id
)
SELECT DISTINCT ON (p.price_id)
    p.price_id, p.loading_date, p.loading_city_gcid, p.unloading_city_gcid, p.distance,
    p.total_weight, p.total_volume, p.weight_category, p.volume_category, b.body_group_id
FROM etl_forecast AS p
JOIN etl_body_groups AS b USING (price_id)
ORDER BY p.price_id, (b.body_group_id <> p.primary_body_group_id), b.body_group_id;

INSERT INTO core.price_months (price_id, price_month, first_price_date)
SELECT p.price_id, DATE_TRUNC('month', d.price_date)::date, MIN(d.price_date)
FROM etl_prices AS p
JOIN raw.price_dates AS d USING (price_id)
WHERE p.reason IS NULL AND d.price_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'
GROUP BY p.price_id, DATE_TRUNC('month', d.price_date)::date;

INSERT INTO core.city_snapshot (
    gc_id, source_city_id, name, full_name_local, region, latitude, longitude
)
SELECT gc_id, source_city_id, name, full_name_local, region, latitude, longitude
FROM core.source_cities
ON CONFLICT (gc_id) DO UPDATE SET
    source_city_id = EXCLUDED.source_city_id,
    name = EXCLUDED.name,
    full_name_local = EXCLUDED.full_name_local,
    region = EXCLUDED.region,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude;

-- Keep the last known city for facts outside the refreshed date window.
DELETE FROM core.city_snapshot AS city
WHERE NOT EXISTS (SELECT 1 FROM core.source_cities WHERE gc_id = city.gc_id)
    AND NOT EXISTS (
        SELECT 1 FROM core.prices AS p
        WHERE city.gc_id IN (p.loading_city_gcid, p.unloading_city_gcid)
    )
    AND NOT EXISTS (
        SELECT 1 FROM core.forecast_requests AS p
        WHERE city.gc_id IN (p.loading_city_gcid, p.unloading_city_gcid)
    );
