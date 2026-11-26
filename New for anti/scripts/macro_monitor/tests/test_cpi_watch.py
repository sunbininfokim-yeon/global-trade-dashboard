import unittest

from build_us_cpi_watch import build, parse_zori, rank_movers, zori_observation


class CpiWatchTests(unittest.TestCase):
    def test_true_declines_only_and_no_yoy_substitution(self):
        movers = {
            "up": [{"id": "a", "label_ko": "A", "mom_pct": 1.2}],
            "down": [{"id": "b", "label_ko": "B", "mom_pct": -0.7},
                     {"id": "c", "label_ko": "C", "mom_pct": 0.1}],
        }
        result = rank_movers(movers, "mom")
        self.assertEqual([row["item_id"] for row in result["bottom3"]], ["b"])
        self.assertEqual(result["max_abs_pct"], 1.2)
        self.assertEqual(rank_movers(movers, "yoy")["top3"], [])

    def test_zillow_national_row_and_calendar_month(self):
        text = ("RegionName,RegionType,2025-10-31,2026-08-31,2026-09-30,2026-10-31\n"
                "United States,country,100,105,,110\n"
                "Los Angeles,msa,200,210,215,220")
        observation = zori_observation(parse_zori(text.splitlines()))
        self.assertEqual(observation["reference_period"], "2026-10")
        self.assertIsNone(observation["mom_pct"])
        self.assertIsNone(observation["published_at"])
        self.assertAlmostEqual(observation["yoy_pct"], 10)

    def test_external_path_does_not_enter_internal_section(self):
        macro = {"countries": [{"iso3": "USA", "indicators": [{"id": "cpi_yoy", "movers": {
            "reference_period": "2026-10"
        }}]}]}
        mapping = {"relationships": [
            {"id": "same_sample", "type": "measurement_link", "source_ids": ["rent_primary"],
             "target_ids": ["owners_equivalent_rent"], "mechanism_ko": ""},
            {"id": "energy_to_airfares", "type": "external_input_required", "source_ids": [],
             "target_ids": ["airline_fares"], "mechanism_ko": ""},
        ]}
        report = build(macro, mapping, {}, {})
        self.assertFalse(report["forecast_active"])
        self.assertEqual([r["id"] for r in report["internal_pathways"]], ["same_sample"])
        self.assertEqual(report["external_prices"][0]["observation"]["status"], "unavailable")
        self.assertIn("airline_fares", next(r["item_ids"] for r in report["external_prices"] if r["id"] == "eia_jet"))


if __name__ == "__main__":
    unittest.main()
