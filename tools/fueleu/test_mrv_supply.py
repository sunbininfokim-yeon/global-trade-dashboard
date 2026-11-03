import unittest

import engine as e
import mrv_supply as m


def ship(fuel, co2, ch4, n2o, between=0.0, departed=0.0, arrived=0.0, in_port=0.0, ship_type="Container ship"):
    return {"imo": "1234567", "ship_type": ship_type, "fuel": fuel, "co2": co2, "ch4": ch4, "n2o": n2o,
            "between": between, "departed": departed, "arrived": arrived, "in_port": in_port}


def pure(fuel_key, tonnes=1000.0, **scope):
    f = e.FUELS[fuel_key]
    burnt = tonnes * (1 - f["slip"] / 100)
    co2 = burnt * f["cf_co2"]
    ch4 = burnt * f["cf_ch4"] + tonnes * f["slip"] / 100
    scope = scope or {"between": co2}
    return ship(tonnes, co2, ch4, burnt * f["cf_n2o"], **scope)


class Estimate(unittest.TestCase):
    def test_pure_hfo_ship_reproduces_engine_intensity(self):
        est = m.estimate_ship(pure("hfo"))
        self.assertEqual(est["propulsion"], "oil")
        self.assertAlmostEqual(est["intensity"], e.intensity([{"fuel": "hfo", "tonnes": 1, "scope": "intra_eu"}], 2025)["ghg_intensity"], places=2)

    def test_pure_mgo_ship(self):
        est = m.estimate_ship(pure("mdo_mgo"))
        self.assertAlmostEqual(est["intensity"], 90.767, places=1)

    def test_lng_detected_by_methane_and_uses_reported_slip(self):
        est = m.estimate_ship(pure("lng_otto_ms"))
        self.assertEqual(est["propulsion"], "lng")
        self.assertAlmostEqual(est["intensity"], 89.203, delta=0.6)
        diesel = m.estimate_ship(pure("lng_diesel_ss"))
        self.assertLess(diesel["intensity"], est["intensity"] - 10)

    def test_bio_blend_estimated_under_uco_assumption_and_other_not(self):
        # B30-like: 70 % LFO + 30 % FAME by mass.
        co2 = 700 * 3.151 + 300 * 2.834
        est = m.estimate_ship(ship(1000, co2, 0.05, 0.18, between=co2))
        self.assertEqual((est["status"], est["propulsion"]), ("estimated_assumed", "bio_blend"))
        mix = [{"fuel": "lfo", "tonnes": 700, "scope": "intra_eu"}, {"fuel": e.bio_fuel(), "tonnes": 300, "scope": "intra_eu"}]
        self.assertAlmostEqual(est["intensity"], e.intensity(mix, 2025)["ghg_intensity"], places=1)
        self.assertEqual(m.estimate_ship(ship(1000, 1375, 0.0, 0.0, between=1375))["propulsion"], "other")
        self.assertEqual(m.estimate_ship(ship(0, 0, 0, 0))["status"], "skipped")

    def test_fueleu_share_counts_half_of_third_country_voyages(self):
        co2 = 1000 * 3.114
        est = m.estimate_ship(ship(1000, co2, 0.05, 0.18, between=co2 * 0.2, departed=co2 * 0.3, arrived=co2 * 0.3, in_port=co2 * 0.2))
        self.assertAlmostEqual(est["fueleu_share"], 0.2 + 0.2 + 0.5 * 0.6)


class Aggregate(unittest.TestCase):
    def test_totals_and_split(self):
        bulk = pure("hfo", 2000)
        bulk["ship_type"] = "Bulk carrier"
        rows = [pure("hfo", 1000), bulk, pure("lng_diesel_ss", 1500), ship(1000, 3030, 0.05, 0.18, between=3030)]
        a = m.aggregate(rows)
        self.assertEqual(a["total"]["ships"], 3)
        self.assertEqual(a["total_with_bio_assumption"]["ships"], 4)
        self.assertEqual(a["by_propulsion"]["bio_blend"]["ships"], 1)
        self.assertEqual(a["unestimated"], {})
        self.assertEqual(a["by_propulsion"]["lng"]["surplus_ships_2025"], 1)
        self.assertGreater(a["by_propulsion"]["lng"]["net_2025"], 0)
        self.assertLess(a["by_propulsion"]["oil"]["net_2025"], 0)
        self.assertAlmostEqual(a["total"]["net_2025"], a["total"]["surplus_2025"] - a["total"]["deficit_2025"])
        self.assertLess(a["total"]["net_2030"], a["total"]["net_2025"])
        self.assertEqual(set(a["by_ship_type"]), {"Container ship", "Bulk carrier"})


if __name__ == "__main__":
    unittest.main()


class SizeFilter(unittest.TestCase):
    def test_offshore_dropped_and_general_cargo_count_matched(self):
        def gc(fuel, hours):
            r = pure("hfo", fuel)
            r.update(ship_type="General cargo ship", hours=hours)
            return r
        off = pure("hfo", 500)
        off.update(ship_type="Other ship types (Offshore)", hours=1000)
        big, small, mid = gc(5000, 5000), gc(300, 3000), gc(2000, 4000)
        kept, dropped = m.size_filter([big, small, mid, off, pure("hfo")], 2025, {"General cargo ship": 2})
        self.assertNotIn(off, kept)
        self.assertNotIn(small, kept)
        self.assertIn(big, kept)
        self.assertIn(mid, kept)
        self.assertEqual(dropped, {"Other ship types (Offshore)": 1, "General cargo ship": 1})
        self.assertEqual(len(m.size_filter([big, small, off], 2024, {})[0]), 3)
