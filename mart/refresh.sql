WITH snapshot AS (
    SELECT %(as_of)s::date AS as_of
),
stats AS (
    SELECT
        m.price_month, p.loading_city_gcid, p.unloading_city_gcid,
        b.body_group_id, p.weight_category,
        PERCENTILE_CONT(ARRAY[0.25, 0.5, 0.75]) WITHIN GROUP (
            ORDER BY p.price_rub::double precision
        ) AS trip,
        PERCENTILE_CONT(ARRAY[0.25, 0.5, 0.75]) WITHIN GROUP (
            ORDER BY (p.price_rub / NULLIF(p.distance, 0)::numeric)::double precision
        ) AS km,
        AVG(p.price_rub) AS avg_trip,
        -- Both bridge keys are unique, so each deal contributes once per cell.
        COUNT(*) AS trips_count,
        COUNT(DISTINCT p.organization_id) FILTER (WHERE p.price_type IN (3, 9)) AS carriers_count,
        STDDEV_SAMP(p.price_rub) / NULLIF(AVG(p.price_rub), 0) AS cv_rate
    FROM core.market_facts AS p
    JOIN core.price_months AS m USING (price_id)
    JOIN core.price_body_groups AS b USING (price_id)
    CROSS JOIN snapshot AS s
    WHERE m.first_price_date <= s.as_of
        AND p.loading_date <= s.as_of
        AND COALESCE(p.available_on, p.loading_date) <= s.as_of
    GROUP BY m.price_month, p.loading_city_gcid, p.unloading_city_gcid,
        b.body_group_id, p.weight_category
)
INSERT INTO mart.market_corridor (
    price_month, loading_city_gcid, unloading_city_gcid, body_group_id, weight_category,
    p25_trip, median_trip, p75_trip, avg_trip, p25_km, median_km, p75_km,
    trips_count, carriers_count, cv_rate, mom_pct, yoy_pct, reliability_level, as_of
)
SELECT
    current.price_month, current.loading_city_gcid, current.unloading_city_gcid,
    current.body_group_id, current.weight_category,
    current.trip[1], current.trip[2], current.trip[3], current.avg_trip,
    current.km[1], current.km[2], current.km[3],
    current.trips_count, current.carriers_count, current.cv_rate,
    100 * (current.trip[2] / NULLIF(previous.trip[2], 0) - 1),
    100 * (current.trip[2] / NULLIF(last_year.trip[2], 0) - 1),
    CASE
        WHEN current.trips_count >= 30 AND current.carriers_count >= 5
            AND s.as_of - current.price_month <= 30 THEN 'HIGH'
        WHEN current.trips_count >= 10 THEN 'MEDIUM'
        ELSE 'LOW_DATA'
    END,
    s.as_of
FROM stats AS current
LEFT JOIN stats AS previous ON
    (previous.loading_city_gcid, previous.unloading_city_gcid,
     previous.body_group_id, previous.weight_category) =
    (current.loading_city_gcid, current.unloading_city_gcid,
     current.body_group_id, current.weight_category)
    AND previous.price_month = (current.price_month - INTERVAL '1 month')::date
LEFT JOIN stats AS last_year ON
    (last_year.loading_city_gcid, last_year.unloading_city_gcid,
     last_year.body_group_id, last_year.weight_category) =
    (current.loading_city_gcid, current.unloading_city_gcid,
     current.body_group_id, current.weight_category)
    AND last_year.price_month = (current.price_month - INTERVAL '1 year')::date
CROSS JOIN snapshot AS s;
