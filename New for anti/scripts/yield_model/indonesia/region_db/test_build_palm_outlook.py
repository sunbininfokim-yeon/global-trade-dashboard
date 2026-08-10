"""Contract tests for forecast/reference separation."""

import unittest

from .build_palm_outlook import build_payload


class PalmOutlookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = build_payload()

    def test_only_predeclared_regions_receive_forecasts(self):
        forecast = {item["province"] for item in self.payload["regions"]
                    if item["forecast_2025"] is not None}
        self.assertEqual(forecast, {
            "Riau", "Sumatera Selatan", "Sumatera Barat"})
        forecast_2026 = {item["province"] for item in self.payload["regions"]
                         if item["forecast_2026"] is not None}
        self.assertEqual(forecast_2026, forecast)

    def test_reference_regions_never_receive_point_forecasts(self):
        for item in self.payload["regions"]:
            if item["status"] == "reference_only":
                self.assertFalse(item["forecast_available"])
                self.assertIsNone(item["forecast_2025"])
                self.assertIsNone(item["forecast_2026"])

    def test_climate_is_not_applied(self):
        self.assertFalse(self.payload["climate_adjustment"]["applied"])
        for item in self.payload["regions"]:
            self.assertFalse(item["climate_adjustment_applied"])
        self.assertEqual(
            set(self.payload["climate_reference"]), {"2025", "2026"})
        for year in self.payload["climate_reference"].values():
            self.assertEqual(
                year["status"], "reference_only_not_applied_to_point")

    def test_ranges_contain_points(self):
        for forecast in self.payload["national"].values():
            for key in ["range_68", "range_95"]:
                self.assertLessEqual(forecast[key][0], forecast["point"])
                self.assertGreaterEqual(forecast[key][1], forecast["point"])

    def test_perennial_calendar_is_explicit(self):
        calendar = self.payload["crop_calendar"]
        self.assertFalse(calendar["annual_sowing_season"])
        self.assertEqual(calendar["harvest"]["months"], list(range(1, 13)))
        self.assertEqual(calendar["harvest"]["ideal_round_days"], 7)


if __name__ == "__main__":
    unittest.main()
