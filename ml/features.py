from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from psycopg import Connection
from psycopg.rows import dict_row

AS_OF = date(2026, 10, 26)
TRAIN_START = date(2026, 7, 26)
TEST_START = date(2026, 10, 5)
SQL = Path(__file__).resolve().with_suffix(".sql")

CATEGORICAL = (
    "origin_region", "destination_region", "body_group", "weight_category", "volume_category",
)
NUMERICAL = (
    "origin_latitude", "origin_longitude", "destination_latitude", "destination_longitude",
    "distance", "total_weight", "total_volume",
)
CALENDAR_FEATURES = ("month", "weekday", "day_of_year")


def read_candidates(conn: Connection) -> pd.DataFrame:
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            SQL.read_text(encoding="utf-8"),
            {"train_start": TRAIN_START, "test_start": TEST_START, "as_of": AS_OF},
        )
        return pd.DataFrame.from_records(
            cursor.fetchall(), columns=[column.name for column in cursor.description]
        )


def build_features(rows: pd.DataFrame) -> pd.DataFrame:
    features = rows.loc[:, [*NUMERICAL, *CATEGORICAL]].copy()
    for column in CATEGORICAL:
        features[column] = features[column].fillna("__unknown__").astype(str)
    for column in NUMERICAL:
        features[column] = pd.to_numeric(features[column])

    # Seconds preserve civil dates outside pandas' nanosecond range.
    loading_date = pd.Series(
        rows["loading_date"].to_numpy(dtype="datetime64[s]"), index=rows.index
    ).dt
    features["year"] = loading_date.year
    for name, offset, period in zip(
        CALENDAR_FEATURES, (loading_date.month - 1, loading_date.dayofweek, loading_date.dayofyear - 1),
        (12, 7, 365.25), strict=True,
    ):
        radians = 2 * np.pi * offset / period
        features[f"{name}_sin"] = np.sin(radians)
        features[f"{name}_cos"] = np.cos(radians)
    return features
