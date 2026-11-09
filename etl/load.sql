DELETE FROM core.prices AS p USING etl_candidates AS candidate
WHERE p.price_id = candidate.price_id;

DELETE FROM core.dq_quarantine_prices AS p USING etl_candidates AS candidate
WHERE p.price_id = candidate.price_id;

INSERT INTO core.dq_quarantine_prices (price_id, loading_date, reason)
SELECT price_id, loading_date, reason
FROM etl_prices
WHERE reason IS NOT NULL;

INSERT INTO core.prices (
    price_id, loading_date, loading_city_gcid, unloading_city_gcid, organization_id,
    price_type, is_fact, complex, outlier_mark, distance, total_weight, total_volume,
    weight_category, volume_category, primary_body_group_id, price_rub
)
SELECT
    p.price_id, p.loading_date, p.loading_city_gcid, p.unloading_city_gcid, p.organization_id,
    p.price_type, p.is_fact, p.complex, p.outlier_mark, p.distance, p.total_weight, p.total_volume,
    COALESCE(NULLIF(BTRIM(p.weight_category), ''), CASE
        WHEN weight.rounded >= 30 THEN 'G20T'
        WHEN weight.rounded >= 10 THEN 'FTL'
        WHEN weight.rounded >= 5 THEN '10T'
        WHEN weight.rounded >= 2.5 THEN '5T'
        WHEN weight.rounded >= 0.5 THEN 'L5T'
        ELSE 'OTH'
    END),
    COALESCE(NULLIF(BTRIM(p.volume_category), ''), CASE
        WHEN p.total_volume > 0 AND p.total_volume <= 120 THEN 'FTL'
        ELSE 'OTH'
    END),
    p.primary_body_group_id,
    p.price::numeric * p.rate::numeric
FROM etl_prices AS p
CROSS JOIN LATERAL (SELECT ROUND(p.total_weight::numeric, 1) AS rounded) AS weight
WHERE p.reason IS NULL;

INSERT INTO core.price_body_groups (price_id, body_group_id)
SELECT DISTINCT
    p.price_id,
    CASE WHEN link.body_type_id IS NULL THEN p.primary_body_group_id
         ELSE core.body_group_id(COALESCE(b.std_id, link.body_type_id))
    END
FROM etl_prices AS p
LEFT JOIN raw.price_body_types AS link USING (price_id)
LEFT JOIN raw.body_types AS b ON b.id = link.body_type_id
WHERE p.reason IS NULL;

INSERT INTO core.price_months (price_id, price_month, first_price_date)
SELECT p.price_id, DATE_TRUNC('month', d.price_date)::date, MIN(d.price_date)
FROM etl_prices AS p
JOIN raw.price_dates AS d USING (price_id)
WHERE p.reason IS NULL
GROUP BY p.price_id, DATE_TRUNC('month', d.price_date)::date;
