import unittest

import numpy as np
import pandas as pd

from . import climate as C
from .model import predict_target, train_target
from .regions import ALL


class ClimateTests(unittest.TestCase):
    def test_trailing_anomaly_never_uses_current_or_future(self):
        frame = pd.DataFrame({"year": range(2000, 2023), "rain": range(23)})
        result = C.trailing_anomalies(frame, ["rain"], 20, 20)
        expected = (20 - np.mean(range(20))) / np.std(range(20), ddof=1)
        self.assertAlmostEqual(result.loc[result.year.eq(2020), "rain_anom"].iloc[0], expected)
        changed = frame.copy()
        changed.loc[changed.year > 2020, "rain"] = 1_000_000
        changed_result = C.trailing_anomalies(changed, ["rain"], 20, 20)
        self.assertAlmostEqual(
            changed_result.loc[changed_result.year.eq(2020), "rain_anom"].iloc[0], expected)

    def test_wet_season_delay(self):
        dates = pd.date_range("2024-10-01", "2025-01-31")
        frame = pd.DataFrame({"date": dates, "precip": 0.0})
        frame.loc[frame.date.between("2024-11-08", "2024-11-10"), "precip"] = 12.0
        self.assertEqual(C.wet_season_delay(frame, 2025), 9.0)

    def test_point_weights_are_normalized(self):
        for cfg in ALL:
            self.assertAlmostEqual(sum(point["weight"] for point in cfg.points), 1.0)


class ModelTests(unittest.TestCase):
    def test_weather_signal_beats_trend_on_synthetic_record(self):
        years = np.arange(1990, 2025)
        feature = np.sin(np.arange(len(years)) * 1.7)
        target = np.exp(6.0 + 0.01 * (years - 1990) + 0.18 * feature)
        frame = pd.DataFrame({"year": years, "signal_anom": feature,
                              "yield_kg_ha": target})
        model = train_target(frame, "yield_kg_ha", {"core": ["signal_anom"]}, 10)
        self.assertTrue(model["beats_trend"])
        self.assertGreater(
            model["validation"][model["configuration"]]["skill_vs_trend"], 0.5)
        forecast = predict_target(model, 2025, {"signal_anom": 0.5})
        self.assertGreater(forecast["point"], forecast["trend"])


class PalmConditionsTests(unittest.TestCase):
    def _dailies(self, dry_from=None):
        from datetime import date as _d
        from .regions import PALM
        dates = pd.date_range("1990-01-01", "2026-10-15")
        rng = np.random.default_rng(0)
        out = {}
        for point in PALM.points:
            frame = pd.DataFrame({"date": dates})
            for column in C.WEATHER_COLUMNS:
                frame[column] = 25.0
            frame["precip"] = rng.choice([0.0, 12.0], len(dates), p=[0.4, 0.6])
            frame["soil"] = 0.8
            frame["tdew"] = 22.0
            if dry_from is not None:
                frame.loc[frame.date.between(dry_from, "2026-10-15"), "precip"] = 0.0
            out[point["name"]] = C.add_vpd(frame)
        return out

    def _oni(self):
        rows = [{"year": y, "season": s, "anom": 0.0}
                for y in range(1985, 2027) for s in ("JJA", "JAS", "ASO", "SON", "OND")]
        return pd.DataFrame(rows)

    def test_partial_season_is_not_read_as_drought(self):
        from datetime import date
        from .palm_conditions import classify, current_frame
        frame, observed = current_frame(2027, self._dailies(), self._oni(), date(2026, 10, 15))
        self.assertLess(observed, 1.0)
        items, score, verdict = classify(frame[frame.year == 2027].iloc[0])
        self.assertEqual(verdict, "neutral")
        precip = next(i for i in items if i["key"] == "precip_dry_lag1")
        self.assertEqual(precip["status"], "neutral")

    def test_long_dry_spell_with_el_nino_is_unfavourable(self):
        from datetime import date
        from .palm_conditions import classify, current_frame
        oni = self._oni()
        oni.loc[oni.year.eq(2026), "anom"] = 1.9
        frame, _ = current_frame(2027, self._dailies("2026-08-01"), oni, date(2026, 10, 15))
        items, score, verdict = classify(frame[frame.year == 2027].iloc[0])
        self.assertEqual(verdict, "unfavorable")
        self.assertLessEqual(score, -2)


if __name__ == "__main__":
    unittest.main()
