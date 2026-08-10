"""Regression guards for the palm anti-overfit gate."""

import unittest

from .palm_backtest import forward_predictions, load_frames, summarize


class PalmBacktestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.national, _ = load_frames()
        cls.folds = forward_predictions(cls.national)
        cls.summary = summarize(cls.folds, len(cls.national))

    def test_forward_folds_never_train_on_future(self):
        for row in self.folds.itertuples(index=False):
            self.assertLess(row.train_seasons, len(self.national))
            self.assertGreaterEqual(row.year, 2015)

    def test_climate_gate_stays_stopped_with_nineteen_seasons(self):
        climate = self.summary[self.summary["model"].str.startswith("climate_")]
        self.assertEqual(set(climate["strict_climate_sample_gate"]),
                         {"stopped_insufficient_seasons"})
        self.assertEqual(set(climate["operational_status"]),
                         {"stopped_climate_adjustment"})


if __name__ == "__main__":
    unittest.main()
