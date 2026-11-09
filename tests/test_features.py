import unittest
from datetime import date

import pandas as pd

from ml.features import CATEGORICAL, NUMERICAL, build_features


class FeatureTest(unittest.TestCase):
    def test_calendar_and_allowlist(self):
        row = {name: None for name in CATEGORICAL}
        row.update({name: 10 for name in NUMERICAL})
        row.update(loading_date=date(2024, 1, 1), actual_price_rub=100, price_group_id=1)
        row["origin_latitude"] = None
        features = build_features(pd.DataFrame([row]))
        self.assertEqual(set(features.columns), {
            *NUMERICAL, *CATEGORICAL, "year", "month_sin", "month_cos",
            "weekday_sin", "weekday_cos", "day_of_year_sin", "day_of_year_cos",
        })
        values = features.iloc[0]
        self.assertEqual(values["year"], 2024)
        self.assertEqual(values["origin_region"], "__unknown__")
        self.assertTrue(pd.isna(values["origin_latitude"]))
        for name in ("month", "weekday", "day_of_year"):
            self.assertAlmostEqual(values[f"{name}_sin"], 0)
            self.assertAlmostEqual(values[f"{name}_cos"], 1)
