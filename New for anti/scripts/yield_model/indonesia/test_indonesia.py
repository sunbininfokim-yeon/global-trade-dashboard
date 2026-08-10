import unittest

import numpy as np
import pandas as pd

from . import climate as C
from .model import predict_target, train_target
from .regions import ALL
from .run_forecast import palm_public_region


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


class PalmPublicForecastTests(unittest.TestCase):
    def test_2026_cpo_forecast_is_numeric(self):
        palm = palm_public_region(2026)
        self.assertTrue(palm["forecast_available"])
        self.assertGreater(palm["yield_kg_ha"]["point"], 0)
        self.assertGreater(palm["headline"]["production_tonnes"]["point"], 0)
        self.assertEqual(palm["provenance"]["target"],
                         "CPO, not fresh fruit bunches (FFB)")

    def test_only_validated_regions_publish_numbers(self):
        regions = palm_public_region(2026)["regional_outlook"]
        published = {r["province"] for r in regions
                     if r["forecast_2026"] is not None}
        self.assertEqual(published, {
            "Riau", "Sumatera Selatan", "Sumatera Barat",
        })
        for region in regions:
            if region["province"] not in published:
                self.assertEqual(region["status"], "reference_only")
                self.assertFalse(region["forecast_available"])
                self.assertIsNone(region["forecast_2026"])

    def test_oil_palm_calendar_is_perennial(self):
        calendar = palm_public_region(2026)["crop_calendar"]
        self.assertFalse(calendar["annual_sowing_season"])
        self.assertEqual(calendar["harvest"]["months"], list(range(1, 13)))
        self.assertEqual(calendar["harvest"]["ideal_round_days"], 7)


if __name__ == "__main__":
    unittest.main()
