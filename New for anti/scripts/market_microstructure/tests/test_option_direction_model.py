import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from option_direction_model import (calendar, dataset, fit, next_day, option_features,
    predict, probability, train_artifact, latest_source_day, evaluate)


@unittest.skipUnless(importlib.util.find_spec("exchange_calendars") and importlib.util.find_spec("sklearn"),
                     "install requirements-direction-research.txt for optional model tests")
class DirectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cal = calendar()
        cls.days = cls.cal.sessions_in_range("2025-01-02", "2026-10-30").strftime("%Y-%m-%d").tolist()

    def board(self, count=100):
        products = {}
        for k, product in enumerate(("options_call", "options_put")):
            products[product] = {"series": [{"date": d, "quality": "observed", "foreign": {"net_krw": i+k},
                "market_total": {"buy_krw": 1000}} for i,d in enumerate(self.days[:count])]}
        return {"kr": {"investor_nets": {"detailed_15007": {"products": products}}}}

    def test_calendar_skips_weekend_and_holiday(self):
        self.assertEqual(next_day(self.cal, "2026-10-30"), "2026-11-02")
        self.assertEqual(next_day(self.cal, "2026-10-08"), "2026-10-12")

    def test_future_rows_do_not_change_past_features(self):
        short, long = self.board(90), self.board(100)
        day = self.days[85]
        self.assertEqual(option_features(short,self.cal)[day], option_features(long,self.cal)[day])

    def test_missing_or_carried_forward_is_not_used(self):
        board = self.board()
        board["kr"]["investor_nets"]["detailed_15007"]["products"]["options_put"]["series"][85]["quality"] = "carried_forward"
        self.assertNotIn(self.days[90],option_features(board,self.cal))

    def test_duplicate_dates_fail(self):
        board = self.board()
        rows = board["kr"]["investor_nets"]["detailed_15007"]["products"]["options_call"]["series"]
        rows.append(rows[-1].copy())
        with self.assertRaises(ValueError): option_features(board,self.cal)

    def test_gap_in_prices_never_bridges_target(self):
        board = self.board()
        prices = {"candidates": [{"ticker": "069500", "rows": [{"date":d,"open":100,"close":101} for d in self.days[:100] if d != self.days[90]]}]}
        data = dataset(board,prices,self.cal)
        self.assertNotIn(self.days[89], {r["date"] for r in data})

    def training_rows(self, count=300):
        return [{"date":d,"target_date":next_day(self.cal,d), "y":i%2,"option_only":[i%7,i%3,.1,.2]}
                for i,d in enumerate(self.days[:count])]

    def test_freeze_cutoff_and_predict_never_refits(self):
        rows = self.training_rows(); cutoff = rows[-2]["target_date"]
        artifact = train_artifact(rows,cutoff,{})
        self.assertEqual(artifact["n_train"],299)
        original = copy.deepcopy(artifact)
        board = self.board(len(self.days))
        with patch("option_direction_model.fit", side_effect=AssertionError("must not train")):
            output = predict(artifact,board,self.cal,"2026-10-30")
        self.assertEqual(output["target_date"],"2026-11-02")
        self.assertIn(output["direction"],("UP","DOWN"))
        self.assertEqual(artifact,original)
        with self.assertRaises(ValueError): predict(artifact,board,self.cal,"2025-01-02")
        artifact["model"]["intercept"] += 1
        with self.assertRaises(ValueError): predict(artifact,board,self.cal,"2026-10-30")

    def test_missing_asof_has_no_direction(self):
        artifact = train_artifact(self.training_rows(),self.training_rows()[-1]["target_date"],{})
        output = predict(artifact,self.board(80),self.cal,"2026-10-30")
        self.assertEqual(output["status"],"unavailable")
        self.assertIsNone(output["direction"])

    def test_serialized_probability_matches_estimator(self):
        rows = self.training_rows(); model = fit(rows,"option_only")
        from sklearn.linear_model import LogisticRegression
        x = np.array([r["option_only"] for r in rows]); y = [r["y"] for r in rows]
        z = (x-np.array(model["mean"]))/np.array(model["scale"])
        est = LogisticRegression(C=1,max_iter=2000,random_state=0).fit(z,y)
        self.assertAlmostEqual(probability(model,x[-1]),est.predict_proba(z[-1:])[0,1])

    def test_latest_incomplete_date_is_not_silently_replaced(self):
        board = self.board()
        rows = board["kr"]["investor_nets"]["detailed_15007"]["products"]["options_put"]["series"]
        rows.pop()
        self.assertEqual(latest_source_day(board),self.days[99])
        self.assertNotIn(latest_source_day(board),option_features(board,self.cal))

    def test_fold_training_never_contains_evaluation_outcome(self):
        rows = self.training_rows(400)
        for row in rows:
            row.update(price_only=[.1,.2],combined=[.1,.2]+row["option_only"], **{"return": .01 if row["y"] else -.01})
        # Move fold boundary to 2026 by using these 2025+ sessions.
        result = evaluate(rows)
        self.assertTrue(result["folds"])
        for fold in result["folds"]:
            year, quarter = map(int,fold["quarter"].split("-"))
            self.assertLess(fold["train_last_target"],f"{year:04d}-{3*quarter-2:02d}-01")


if __name__ == "__main__": unittest.main()
