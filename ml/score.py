import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from psycopg import Connection
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    r2_score,
    root_mean_squared_error,
)

from ml.features import AS_OF, CATEGORICAL, TEST_START, TRAIN_START, build_features, read_candidates

MODEL_NAME = "catboost-v2"
SEED = 20261026
PREDICTION_COLUMNS = (
    "price_id", "loading_date", "loading_city_gcid", "unloading_city_gcid", "body_group",
    "actual_price_rub", "predicted_price_rub", "abs_error_rub", "ape_pct", "as_of", "model_name",
)


def score_batch(conn: Connection) -> dict:
    rows = read_candidates(conn)
    dates = rows["loading_date"]
    train = rows.loc[(dates >= TRAIN_START) & (dates < TEST_START)]
    score = rows.loc[dates >= TEST_START].copy()
    test_mask = score["loading_date"] <= AS_OF
    test_count = int(test_mask.sum())
    if len(train) < 2 or test_count < 2:
        raise ValueError("Training and holdout each require at least two eligible observations")

    model = CatBoostRegressor(
        iterations=500,
        depth=7,
        learning_rate=0.08,
        loss_function="RMSE",
        cat_features=list(CATEGORICAL),
        random_seed=SEED,
        has_time=True,
        thread_count=2,
        allow_writing_files=False,
        verbose=False,
    )
    model.fit(build_features(train), train["actual_price_rub"])
    score["predicted_price_rub"] = np.maximum(model.predict(build_features(score)), 0.01)
    score["abs_error_rub"] = (score["predicted_price_rub"] - score["actual_price_rub"]).abs()
    score["ape_pct"] = 100 * score["abs_error_rub"] / score["actual_price_rub"]
    score["as_of"] = AS_OF
    score["model_name"] = MODEL_NAME

    actual = score.loc[test_mask, "actual_price_rub"]
    predicted = score.loc[test_mask, "predicted_price_rub"]
    metrics = {
        "as_of": AS_OF,
        "model_name": MODEL_NAME,
        "train_rows": len(train),
        "test_rows": test_count,
        "future_rows": len(score) - test_count,
        "r2": float(r2_score(actual, predicted)),
        "mape_pct": 100 * float(mean_absolute_percentage_error(actual, predicted)),
        "rmse_rub": float(root_mean_squared_error(actual, predicted)),
        "mae_rub": float(mean_absolute_error(actual, predicted)),
    }
    write_results(conn, score, metrics)
    return metrics


def write_results(conn: Connection, score: pd.DataFrame, metrics: dict) -> None:
    conn.execute("DELETE FROM mart.ml_price_predictions")
    rows = score.loc[:, list(PREDICTION_COLUMNS)].astype(object)
    rows = rows.where(rows.notna(), None)
    columns = ", ".join(PREDICTION_COLUMNS)
    with conn.cursor() as cursor, cursor.copy(f"""
        COPY mart.ml_price_predictions ({columns}) FROM STDIN
    """) as copy:
        for row in rows.itertuples(index=False, name=None):
            copy.write_row(row)

    conn.execute("""
        INSERT INTO mart.ml_evaluation (
            as_of, model_name, train_rows, test_rows, future_rows, r2, mape_pct, rmse_rub, mae_rub
        )
        VALUES (
            %(as_of)s, %(model_name)s, %(train_rows)s, %(test_rows)s, %(future_rows)s,
            %(r2)s, %(mape_pct)s, %(rmse_rub)s, %(mae_rub)s
        )
        ON CONFLICT (as_of, model_name) DO UPDATE SET
            train_rows = EXCLUDED.train_rows, test_rows = EXCLUDED.test_rows,
            future_rows = EXCLUDED.future_rows, r2 = EXCLUDED.r2, mape_pct = EXCLUDED.mape_pct,
            rmse_rub = EXCLUDED.rmse_rub, mae_rub = EXCLUDED.mae_rub
    """, metrics)
