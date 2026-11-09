-- Also reprocess IDs previously in the window, so corrections to loading_date
-- and source deletions do not leave old Core or quarantine rows behind.
CREATE TEMP TABLE etl_candidates ON COMMIT DROP AS
WITH bounds AS (
    SELECT
        COALESCE(%(start_date)s, '-infinity'::date) AS start_date,
        COALESCE(%(end_date)s, 'infinity'::date) AS end_date
)
SELECT id AS price_id
FROM raw.prices CROSS JOIN bounds
WHERE loading_date >= start_date AND loading_date < end_date
UNION
SELECT price_id
FROM core.prices CROSS JOIN bounds
WHERE loading_date >= start_date AND loading_date < end_date
UNION
SELECT price_id
FROM core.dq_quarantine_prices CROSS JOIN bounds
WHERE loading_date >= start_date AND loading_date < end_date;
