WITH candidates AS (
    SELECT *
    FROM core.market_facts
    WHERE price_type IN (3, 9)
        AND loading_date BETWEEN %(train_start)s AND %(as_of)s
        AND (available_on IS NULL OR available_on <= %(as_of)s)
        AND (loading_date >= %(test_start)s
             OR COALESCE(available_on, loading_date) < %(test_start)s)
    UNION ALL
    SELECT *
    FROM core.prices
    WHERE loading_date > %(as_of)s AND NOT complex
        AND (available_on IS NULL OR available_on <= %(as_of)s)
)
SELECT
    p.price_id, p.loading_date, p.loading_city_gcid, p.unloading_city_gcid,
    origin.region AS origin_region,
    origin.latitude AS origin_latitude,
    origin.longitude AS origin_longitude,
    destination.region AS destination_region,
    destination.latitude AS destination_latitude,
    destination.longitude AS destination_longitude,
    b.body_group, p.distance, p.total_weight, p.total_volume, p.weight_category, p.volume_category,
    CASE WHEN p.loading_date <= %(as_of)s THEN p.price_rub::double precision END AS actual_price_rub
FROM candidates AS p
JOIN core.cities AS origin ON origin.gc_id = p.loading_city_gcid
JOIN core.cities AS destination ON destination.gc_id = p.unloading_city_gcid
JOIN LATERAL (
    SELECT body_group_id
    FROM core.price_body_groups
    WHERE price_id = p.price_id
    ORDER BY (body_group_id <> p.primary_body_group_id), body_group_id
    LIMIT 1
) AS primary_group ON TRUE
JOIN core.body_groups AS b USING (body_group_id)
ORDER BY p.loading_date, p.price_id;
