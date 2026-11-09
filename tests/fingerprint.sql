-- Exclude the time of the run. Data and metrics must otherwise be unchanged.
SELECT 'core.city_snapshot', COUNT(*),
    MD5(STRING_AGG(MD5(TO_JSONB(c)::text), '' ORDER BY gc_id))
FROM core.city_snapshot AS c
UNION ALL
SELECT 'core.prices', COUNT(*),
    MD5(STRING_AGG(MD5(TO_JSONB(p)::text), '' ORDER BY price_id))
FROM core.prices AS p
UNION ALL
SELECT 'core.dq_quarantine_prices', COUNT(*),
    MD5(STRING_AGG(MD5(TO_JSONB(q)::text), '' ORDER BY price_id))
FROM core.dq_quarantine_prices AS q
UNION ALL
SELECT 'core.price_body_groups', COUNT(*),
    MD5(STRING_AGG(MD5(TO_JSONB(b)::text), '' ORDER BY price_id, body_group_id))
FROM core.price_body_groups AS b
UNION ALL
SELECT 'core.price_months', COUNT(*),
    MD5(STRING_AGG(MD5(TO_JSONB(m)::text), '' ORDER BY price_id, price_month))
FROM core.price_months AS m
UNION ALL
SELECT 'mart.market_corridor', COUNT(*),
    MD5(STRING_AGG(MD5(TO_JSONB(m)::text), ''
        ORDER BY price_month, loading_city_gcid, unloading_city_gcid, body_group_id, weight_category))
FROM mart.market_corridor AS m
UNION ALL
SELECT 'mart.ml_price_predictions', COUNT(*),
    MD5(STRING_AGG(MD5((TO_JSONB(p) - 'scored_at')::text), '' ORDER BY price_id))
FROM mart.ml_price_predictions AS p
UNION ALL
SELECT 'mart.ml_evaluation', COUNT(*),
    MD5(STRING_AGG(MD5(TO_JSONB(e)::text), '' ORDER BY as_of, model_name))
FROM mart.ml_evaluation AS e
ORDER BY 1;
