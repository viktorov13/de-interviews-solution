-- Also reprocess IDs previously in the window, so corrections to loading_date
-- and source deletions do not leave old Core, forecast or quarantine rows behind.
CREATE TEMP TABLE etl_candidates ON COMMIT DROP AS
-- Inline bounds so PostgreSQL can simplify the predicates and use date indexes.
WITH bounds AS NOT MATERIALIZED (
    SELECT
        %(start_date)s::date AS start_date,
        %(end_date)s::date AS end_date
)
SELECT id AS price_id
FROM raw.prices CROSS JOIN bounds
WHERE (start_date IS NULL OR loading_date >= start_date)
    AND (end_date IS NULL OR loading_date < end_date)
UNION
SELECT price_id
FROM core.prices CROSS JOIN bounds
WHERE (start_date IS NULL OR loading_date >= start_date)
    AND (end_date IS NULL OR loading_date < end_date)
UNION
SELECT price_id
FROM core.dq_quarantine_prices CROSS JOIN bounds
WHERE (start_date IS NULL OR loading_date >= start_date)
    AND (end_date IS NULL OR loading_date < end_date)
UNION
SELECT price_id
FROM core.forecast_requests CROSS JOIN bounds
WHERE (start_date IS NULL OR loading_date >= start_date)
    AND (end_date IS NULL OR loading_date < end_date);
