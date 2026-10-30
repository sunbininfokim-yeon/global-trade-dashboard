from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from series_quality import annotate_monthly_payload, annotate_point  # noqa: E402


class SeriesQualityTests(unittest.TestCase):
    def test_mass_point_is_exactly_normalized_to_kg(self) -> None:
        point = {"month": "2026-01", "value": 2, "unit": "metric_tons"}
        annotate_point(point)
        self.assertEqual(point["normalized"]["value"], 2000.0)
        self.assertEqual(point["normalized"]["unit"], "kg")
        self.assertTrue(point["normalized"]["comparable_across_reporters"])

    def test_volume_and_monetary_points_are_not_silently_converted(self) -> None:
        for unit in ("CONVBBL", "AUD_million_fob"):
            point = {"month": "2026-01", "value": 2, "unit": unit}
            annotate_point(point)
            self.assertIsNone(point["normalized"]["value"])
            self.assertFalse(point["normalized"]["comparable_across_reporters"])

    def test_country_and_commodity_flags_are_transparent(self) -> None:
        sectors = {
            "minerals": {
                "commodities": {
                    "iron_ore": {
                        "countries": {
                            "AUS": {
                                "points": [
                                    {
                                        "month": "2025-01",
                                        "value": 1,
                                        "unit": "AUD_million_fob",
                                        "hs_relation": "industry_proxy_not_hs_pure",
                                        "source": "abs",
                                    }
                                ]
                            },
                            "BRA": {
                                "points": [
                                    {"month": "2026-01", "value": 1000, "unit": "kg", "source": "comex"}
                                ]
                            },
                        }
                    }
                }
            }
        }
        contract = annotate_monthly_payload(sectors, "2026-08")
        commodity = sectors["minerals"]["commodities"]["iron_ore"]
        self.assertEqual(contract["schema_version"], "commodity-trade-quality-v1")
        self.assertEqual(commodity["comparison_policy"]["cross_reporter_numeric_comparison"], "not_allowed")
        self.assertIn("proxy_series_not_pure_hs_commodity", commodity["comparison_policy"]["country_quality_flags"])
        self.assertIn("stale_more_than_3_months", commodity["countries"]["AUS"]["series_quality"]["flags"])


if __name__ == "__main__":
    unittest.main()
