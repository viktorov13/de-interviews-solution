CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW core.market_facts AS
SELECT *
FROM core.prices
WHERE is_fact AND price_type IN (1, 2, 3, 4, 5, 9)
    AND NOT complex AND NOT outlier_mark;

CREATE TABLE IF NOT EXISTS mart.market_corridor (
    price_month          date NOT NULL,
    loading_city_gcid    integer NOT NULL,
    unloading_city_gcid  integer NOT NULL,
    body_group_id        smallint NOT NULL,
    weight_category      varchar(4) NOT NULL,
    p25_trip             double precision NOT NULL,
    median_trip          double precision NOT NULL,
    p75_trip             double precision NOT NULL,
    avg_trip             double precision NOT NULL,
    p25_km               double precision NOT NULL,
    median_km            double precision NOT NULL,
    p75_km               double precision NOT NULL,
    trips_count          bigint NOT NULL,
    carriers_count       bigint NOT NULL,
    cv_rate              double precision,
    mom_pct              double precision,
    yoy_pct              double precision,
    reliability_level    text NOT NULL CHECK (reliability_level IN ('HIGH', 'MEDIUM', 'LOW_DATA')),
    as_of                date NOT NULL,
    PRIMARY KEY (price_month, loading_city_gcid, unloading_city_gcid, body_group_id, weight_category)
);
CREATE INDEX IF NOT EXISTS market_corridor_route_idx
    ON mart.market_corridor (loading_city_gcid, unloading_city_gcid, price_month);

CREATE OR REPLACE VIEW mart.route_card AS
SELECT m.*, origin.name AS loading_city, destination.name AS unloading_city, b.body_group
FROM mart.market_corridor AS m
JOIN core.cities AS origin ON origin.gc_id = m.loading_city_gcid
JOIN core.cities AS destination ON destination.gc_id = m.unloading_city_gcid
JOIN core.body_groups AS b USING (body_group_id);
