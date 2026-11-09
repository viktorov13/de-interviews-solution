CREATE SCHEMA IF NOT EXISTS core;

CREATE OR REPLACE VIEW core.source_cities AS
SELECT DISTINCT ON (gc_id)
    gc_id,
    id AS source_city_id,
    name,
    full_name_local,
    CASE WHEN POSITION(',' IN full_name_local) > 0 THEN
        NULLIF(BTRIM(SUBSTRING(full_name_local FROM POSITION(',' IN full_name_local) + 1)), '')
    END AS region,
    CASE WHEN latitude BETWEEN -90 AND 90 THEN latitude END AS latitude,
    CASE WHEN longitude BETWEEN -180 AND 180 THEN longitude END AS longitude
FROM raw.cities
ORDER BY gc_id, id;

-- Initialize the snapshot once, including when upgrading an existing volume.
CREATE TABLE IF NOT EXISTS core.city_snapshot AS
SELECT * FROM core.source_cities;
CREATE UNIQUE INDEX IF NOT EXISTS core_city_snapshot_gc_id_idx
    ON core.city_snapshot (gc_id);

CREATE OR REPLACE VIEW core.cities AS
SELECT gc_id, source_city_id, name, full_name_local, region, latitude, longitude
FROM core.city_snapshot;

CREATE OR REPLACE FUNCTION core.body_group_id(body_type_id integer)
RETURNS smallint
LANGUAGE sql IMMUTABLE
RETURN (CASE
    WHEN body_type_id IN (56, 57, 58, 59, 60, 61) THEN 56
    WHEN body_type_id IN (4, 46, 47, 48) THEN 4
    WHEN body_type_id = 2 THEN 2
    WHEN body_type_id IN (1, 15) THEN 15
    WHEN body_type_id IS NULL THEN 0
    ELSE -1
END)::smallint;

CREATE OR REPLACE VIEW core.body_groups AS
SELECT *
FROM (VALUES
    (56::smallint, 'Тент'),
    (4, 'Рефрижератор'),
    (2, 'Изотерм'),
    (15, 'Борт'),
    (-1, 'Прочие'),
    (0, 'Не указан')
) AS groups(body_group_id, body_group);

CREATE TABLE IF NOT EXISTS core.prices (
    price_id               bigint PRIMARY KEY,
    loading_date           date NOT NULL,
    loading_city_gcid      integer NOT NULL,
    unloading_city_gcid    integer NOT NULL,
    organization_id        integer,
    price_type             smallint NOT NULL,
    is_fact                boolean NOT NULL,
    complex                boolean NOT NULL,
    outlier_mark           boolean NOT NULL,
    distance               double precision NOT NULL CHECK (distance > 0),
    total_weight           double precision NOT NULL CHECK (total_weight >= 0),
    total_volume           double precision NOT NULL CHECK (total_volume >= 0),
    weight_category        varchar(4) NOT NULL,
    volume_category        varchar(4) NOT NULL,
    primary_body_group_id  smallint NOT NULL,
    price_rub              numeric NOT NULL CHECK (price_rub > 0)
);
ALTER TABLE core.prices ADD COLUMN IF NOT EXISTS available_on date;
CREATE INDEX IF NOT EXISTS core_prices_loading_date_idx ON core.prices (loading_date);

CREATE TABLE IF NOT EXISTS core.dq_quarantine_prices (
    price_id      bigint PRIMARY KEY,
    loading_date  date NOT NULL,
    reason        text NOT NULL
);
CREATE INDEX IF NOT EXISTS quarantine_loading_date_idx
    ON core.dq_quarantine_prices (loading_date);

-- Future inputs contain route features only, including requests with no usable source price.
CREATE TABLE IF NOT EXISTS core.forecast_requests (
    price_id               bigint PRIMARY KEY,
    loading_date           date NOT NULL,
    loading_city_gcid      integer NOT NULL,
    unloading_city_gcid    integer NOT NULL,
    distance               double precision NOT NULL CHECK (distance > 0),
    total_weight           double precision NOT NULL CHECK (total_weight >= 0),
    total_volume           double precision NOT NULL CHECK (total_volume >= 0),
    weight_category        varchar(4) NOT NULL,
    volume_category        varchar(4) NOT NULL,
    body_group_id          smallint NOT NULL
);
CREATE INDEX IF NOT EXISTS forecast_requests_loading_date_idx
    ON core.forecast_requests (loading_date);

CREATE TABLE IF NOT EXISTS core.price_body_groups (
    price_id       bigint NOT NULL REFERENCES core.prices ON DELETE CASCADE,
    body_group_id  smallint NOT NULL,
    PRIMARY KEY (price_id, body_group_id)
);

CREATE TABLE IF NOT EXISTS core.price_months (
    price_id          bigint NOT NULL REFERENCES core.prices ON DELETE CASCADE,
    price_month       date NOT NULL,
    first_price_date  date NOT NULL,
    PRIMARY KEY (price_id, price_month)
);
