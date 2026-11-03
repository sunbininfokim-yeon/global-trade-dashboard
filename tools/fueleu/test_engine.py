import unittest

import engine as e

NL = {"country": "NL", "name": "Rotterdam"}
ES_CANARY = {"country": "ES", "name": "Las Palmas", "outermost": True}
DE = {"country": "DE", "name": "Hamburg"}
CN = {"country": "CN", "name": "Shanghai"}
SG = {"country": "SG", "name": "Singapore"}


def one(fuel, tonnes=1000, scope="intra_eu"):
    return [{"fuel": fuel, "tonnes": tonnes, "scope": scope}]


class Intensity(unittest.TestCase):
    def test_fossil_defaults_match_published_wtw_values(self):
        # Commonly cited FuelEU WtW intensities for the Annex II fossil defaults.
        for fuel, expected in (("hfo", 91.744), ("lfo", 91.392), ("mdo_mgo", 90.767), ("lng_otto_ms", 89.203)):
            self.assertAlmostEqual(e.intensity(one(fuel), 2025)["ghg_intensity"], expected, places=2)

    def test_targets_follow_article_4(self):
        self.assertAlmostEqual(e.target(2025), 89.3368, places=4)
        self.assertAlmostEqual(e.target(2029), 89.3368, places=4)
        self.assertAlmostEqual(e.target(2030), 85.6904, places=4)
        self.assertAlmostEqual(e.target(2050), 18.232, places=3)
        with self.assertRaises(ValueError):
            e.target(2024)

    def test_extra_eu_counts_half(self):
        full = e.intensity(one("hfo", 1000, "intra_eu"), 2025)["energy_mj"]
        half = e.intensity(one("hfo", 1000, "extra_eu"), 2025)["energy_mj"]
        self.assertAlmostEqual(half, full / 2)

    def test_rfnbo_reward_only_until_2033(self):
        e_methanol = {"lcv": 0.0199, "wtt": 1.0, "cf_co2": 1.375, "cf_ch4": 0.0, "cf_n2o": 0.0, "slip": 0.0, "rfnbo": True}
        mix = [{"fuel": "hfo", "tonnes": 900, "scope": "intra_eu"}, {"fuel": e_methanol, "tonnes": 100, "scope": "intra_eu"}]
        self.assertLess(e.intensity(mix, 2033)["ghg_intensity"], e.intensity(mix, 2034)["ghg_intensity"])

    def test_wind_reward_steps(self):
        self.assertEqual([e.wind_factor(x) for x in (0, 0.05, 0.1, 0.2)], [1.0, 0.99, 0.97, 0.95])

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            e.intensity(one("unknown"), 2025)
        with self.assertRaises(ValueError):
            e.intensity(one("hfo", -1), 2025)
        with self.assertRaises(ValueError):
            e.intensity(one("hfo", 0), 2025)


class BalanceAndPenalty(unittest.TestCase):
    def test_hfo_ship_deficit_and_penalty(self):
        r = e.ship(one("hfo", 10_000), 2025)
        energy = 10_000e6 * 0.0405
        cb = (89.3368 - 91.744) * energy / 1e6
        self.assertAlmostEqual(r["compliance_balance_tco2e"], cb, delta=2)
        expected_pen = abs(r["compliance_balance_tco2e"] * 1e6) / (r["ghg_intensity"] * 41_000) * 2_400
        self.assertAlmostEqual(r["penalty_eur"], expected_pen, places=2)
        self.assertAlmostEqual(r["penalty_eur_per_tco2e"], 638.0, delta=0.5)

    def test_consecutive_multiplier(self):
        base = e.ship(one("hfo"), 2025)["penalty_eur"]
        third = e.ship(one("hfo"), 2025, consecutive_deficits=2)["penalty_eur"]
        self.assertAlmostEqual(third, base * 1.2)

    def test_surplus_has_no_penalty(self):
        r = e.ship(one("lng_diesel_ss"), 2025)
        self.assertGreater(r["compliance_balance_tco2e"], 0)
        self.assertEqual(r["penalty_eur"], 0.0)

    def test_borrow_limit_two_percent_and_not_consecutive(self):
        r = e.ship(one("hfo"), 2025)
        self.assertAlmostEqual(r["borrow_limit_tco2e"], 0.02 * 89.3368 * r["energy_mj"] / 1e6)
        self.assertEqual(e.ship(one("hfo"), 2025, borrowed_last_period=True)["borrow_limit_tco2e"], 0.0)


class Options(unittest.TestCase):
    def test_deficit_cheapest_and_borrow_needs_next_price(self):
        r = e.ship(one("hfo", 10_000), 2025)
        o = e.options(r, pool_price=100)
        self.assertEqual(o["position"], "deficit")
        self.assertEqual(o["cheapest"], "pool_buy")
        self.assertIsNone(next(x for x in o["rows"] if x["option"] == "borrow_then_pool")["cost_eur"])
        cheap_next = e.options(r, pool_price=100, next_pool_price=50)
        self.assertEqual(cheap_next["cheapest"], "borrow_then_pool")
        self.assertEqual(e.options(r, pool_price=900)["cheapest"], "penalty")

    def test_surplus_bank_vs_sell(self):
        r = e.ship(one("lng_diesel_ss"), 2025)
        self.assertEqual(e.options(r, 100)["best"], "pool_sell")
        self.assertEqual(e.options(r, 100, next_pool_price=150)["best"], "bank")


class Voyages(unittest.TestCase):
    def test_leg_scope_by_ports(self):
        self.assertEqual(e.leg_share(NL, DE), (1.0, "intra_eu"))
        self.assertEqual(e.leg_share(CN, NL), (0.5, "extra_eu"))
        self.assertEqual(e.leg_share(NL, ES_CANARY), (0.5, "outermost_region"))
        self.assertEqual(e.leg_share(SG, CN), (0.0, "out_of_scope"))
        self.assertEqual(e.leg_share({"country": "NO"}, NL)[1], "extra_eu")
        self.assertEqual(e.leg_share({"country": "NO"}, NL, extra_member_codes=("NO",))[1], "intra_eu")

    def test_berth_counts_only_in_eu_port(self):
        legs = [{"id": "a", "origin": NL, "destination": CN, "at_sea": {"hfo": 100}, "at_berth": {"mdo_mgo": 50}}]
        rows = e.legs_to_consumption(legs)
        self.assertEqual([(r["scope"], r["share"]) for r in rows], [("extra_eu", 0.5)])

    def test_year_forecast_and_exact_leg_cost(self):
        legs = [
            {"id": "1", "status": "actual", "origin": CN, "destination": NL, "at_sea": {"hfo": 4000}, "at_berth": {"mdo_mgo": 80}},
            {"id": "2", "status": "actual", "origin": NL, "destination": DE, "at_sea": {"mdo_mgo": 300}},
            {"id": "3", "status": "planned", "origin": DE, "destination": SG, "at_sea": {"lng_diesel_ss": 3500}},
        ]
        y = e.ship_year(legs, 2026, pool_price=100)
        self.assertIsNotNone(y["actual_to_date"])
        self.assertNotAlmostEqual(y["actual_to_date"]["compliance_balance_tco2e"], y["full_year"]["compliance_balance_tco2e"])
        # Without RFNBO the balance is additive, so leg deltas sum to the year.
        self.assertAlmostEqual(sum(l["cb_delta_tco2e"] for l in y["legs"]), y["full_year"]["compliance_balance_tco2e"], places=6)
        hfo_leg = y["legs"][0]
        self.assertLess(hfo_leg["cb_delta_tco2e"], 0)
        self.assertAlmostEqual(hfo_leg["cost_at_pool_eur"], -hfo_leg["cb_delta_tco2e"] * 100)


class Pooling(unittest.TestCase):
    def test_article_21_checks(self):
        self.assertTrue(e.pool_valid({"a": 100, "b": -60}, {"a": 40, "b": 0})["valid"])
        self.assertFalse(e.pool_valid({"a": 50, "b": -60}, {"a": 0, "b": -10})["valid"])
        self.assertFalse(e.pool_valid({"a": 100, "b": -60}, {"a": -10, "b": 50})["valid"])

    def test_fleet_netting(self):
        f = e.fleet_pool({"a": 500, "b": -200, "c": -100})
        self.assertTrue(f["check"]["valid"])
        self.assertEqual(f["internal_netting_tco2e"], 300)
        self.assertEqual(f["external_surplus_tco2e"], 200)
        short = e.fleet_pool({"a": 50, "b": -200})
        self.assertFalse(short["check"]["valid"])
        self.assertEqual(short["external_need_tco2e"], 150)


if __name__ == "__main__":
    unittest.main()


class QuickCheck(unittest.TestCase):
    def test_sign_depends_on_fuel_not_size(self):
        small = e.quick_check(6_000, {"lng_otto_ms": 1_000})
        large = e.quick_check(150_000, {"lng_otto_ms": 30_000})
        self.assertEqual(small["position"], large["position"])
        self.assertAlmostEqual(small["margin_gco2e_per_mj"], large["margin_gco2e_per_mj"])
        self.assertAlmostEqual(large["compliance_balance_tco2e"], small["compliance_balance_tco2e"] * 30, places=6)

    def test_flip_years_by_fuel(self):
        self.assertEqual(e.quick_check(50_000, {"hfo": 10_000})["first_deficit_period"], 2025)
        self.assertEqual(e.quick_check(50_000, {"lng_otto_ms": 10_000})["first_deficit_period"], 2030)
        self.assertEqual(e.quick_check(50_000, {"lng_otto_ss": 10_000})["first_deficit_period"], 2035)
        self.assertEqual(e.quick_check(50_000, {"lng_diesel_ss": 10_000})["first_deficit_period"], 2040)

    def test_scope_and_shares(self):
        self.assertFalse(e.quick_check(4_999, {"hfo": 100})["in_scope"])
        half = e.quick_check(50_000, {"hfo": 1_000})
        full = e.quick_check(50_000, {"hfo": 1_000}, eu_share={"intra_eu": 1.0})
        self.assertAlmostEqual(full["compliance_balance_tco2e"], 2 * half["compliance_balance_tco2e"])
        with self.assertRaises(ValueError):
            e.quick_check(50_000, {"hfo": 1_000}, eu_share={"intra_eu": 0.5})
