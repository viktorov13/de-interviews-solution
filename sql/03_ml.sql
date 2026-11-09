CREATE TABLE IF NOT EXISTS mart.ml_price_predictions (
    price_id               bigint PRIMARY KEY,
    loading_date           date NOT NULL,
    loading_city_gcid      integer NOT NULL,
    unloading_city_gcid    integer NOT NULL,
    body_group             text NOT NULL,
    actual_price_rub       double precision CHECK (actual_price_rub > 0),
    predicted_price_rub    double precision NOT NULL CHECK (predicted_price_rub > 0),
    abs_error_rub          double precision,
    ape_pct                double precision,
    as_of                  date NOT NULL,
    model_name             text NOT NULL,
    scored_at              timestamptz NOT NULL DEFAULT statement_timestamp(),
    CHECK (
        (loading_date <= as_of AND actual_price_rub IS NOT NULL
            AND abs_error_rub IS NOT NULL AND ape_pct IS NOT NULL)
        OR (loading_date > as_of AND actual_price_rub IS NULL
            AND abs_error_rub IS NULL AND ape_pct IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS ml_predictions_loading_date_idx
    ON mart.ml_price_predictions (loading_date);

CREATE TABLE IF NOT EXISTS mart.ml_evaluation (
    as_of        date NOT NULL,
    model_name   text NOT NULL,
    train_rows   bigint NOT NULL,
    test_rows    bigint NOT NULL,
    future_rows  bigint NOT NULL,
    r2           double precision NOT NULL,
    mape_pct     double precision NOT NULL,
    rmse_rub     double precision NOT NULL,
    mae_rub      double precision NOT NULL,
    PRIMARY KEY (as_of, model_name)
);
