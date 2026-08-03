import unittest

from .data import parse_cocobod_purchases
from .features import _vpd
from .ghana_forecast import decide
from .regions import POINTS, points_for


class WestAfricaTests(unittest.TestCase):
    def test_vpd_increases_when_dewpoint_falls(self):
        self.assertGreater(_vpd(32, 18), _vpd(32, 25))

    def test_recent_weights_are_positive(self):
        for country in {point["country"] for point in POINTS}:
            self.assertGreater(sum(point["weight"] for point in points_for(country)), 0)

    def test_cocobod_html_parser(self):
        html = """
        <table><tr><th>No.</th><th>Crop Year</th><th>Ashanti</th><th>Total</th></tr>
        <tr><td>1</td><td>2019/20</td><td>165,830</td><td>165,830</td></tr></table>
        """
        rows = parse_cocobod_purchases(html)
        self.assertEqual(rows[0]["year"], 2020)
        self.assertEqual(rows[0]["region"], "Ashanti")
        self.assertEqual(rows[0]["value_tonnes"], 165830)

    def test_forecast_gate_rejects_weak_purchase_signal(self):
        screens = [{
            "country": "Ghana",
            "target": "purchases_tonnes",
            "runs": {"small_gain": {
                "skill_vs_trend": 0.09,
                "recent_skill_vs_trend": 0.20,
                "fold_years": [2019, 2020],
            }},
        }, {
            "country": "Ghana",
            "target": "production_tonnes",
            "runs": {"wrong_label": {
                "skill_vs_trend": 0.50,
                "recent_skill_vs_trend": 0.50,
            }},
        }]
        result = decide(screens)
        self.assertFalse(result["forecast_enabled"])
        self.assertEqual(result["status"], "abandoned_with_current_data")

    def test_forecast_gate_accepts_only_cocobod_label(self):
        screens = [{
            "country": "Ghana",
            "target": "regional_purchases_tonnes",
            "runs": {"passing": {
                "skill_vs_trend": 0.12,
                "recent_skill_vs_trend": 0.11,
                "fold_years": [2019, 2020],
            }},
        }]
        result = decide(screens)
        self.assertTrue(result["forecast_enabled"])
        self.assertEqual(result["selected_candidate"]["feature_set"], "passing")


if __name__ == "__main__":
    unittest.main()
