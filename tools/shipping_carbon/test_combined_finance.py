import copy
import unittest
from datetime import date
from decimal import Decimal
from combined_finance import cash_ledger, observed_reference
from fueleu_adapter import call_fueleu


def inputs():
    return dict(year=2026, base_fuel="lfo", baseline_tonnes=1000, bio_energy_pct=20,
        base_price_eur_t=500, bio_price_eur_t=700, pool_buy_eur_tco2e=100, pool_compliance_year=2026,
        bio_e_value=14.9, fees_eur=1000, ets_fossil_tco2e_t=3.2, ets_bio_tco2e_t=.05,
        ets_scope_share=.5, ets_phase_factor=1, fueleu_scope_share=.5,
        ets_factor_basis="test assumptions, not verified fuel factors", scope_confirmed=True,
        technical_feasibility_confirmed=True, fueleu_bio_certified=True)


def run(p):
    return call_fueleu({"mode": "combined", "inputs": p,
        "reference": {"price_eur_eua": "90", "observation_date": "2026-11-03", "as_of": "2026-11-04", "status": "observed"}})


class CombinedTests(unittest.TestCase):
    def test_equal_energy_not_equal_mass(self):
        r = run(inputs()); a, b = r["options"]
        self.assertAlmostEqual(a["energy_mj"], 41_000_000)
        self.assertAlmostEqual(a["energy_mj"], b["energy_mj"])
        self.assertAlmostEqual(b["fossil_tonnes"], 800)
        self.assertAlmostEqual(b["bio_tonnes"], 8_200_000 / 37000)
        self.assertNotEqual(b["fossil_tonnes"] + b["bio_tonnes"], 1000)
        self.assertGreater(b["fueleu"]["compliance_balance_tco2e"], 0)
        self.assertEqual(b["recognized_surplus_sale_eur"], 0)
        self.assertGreater(b["uncontracted_surplus_tco2e"], 0)
        self.assertEqual(a["funding"]["status"], "held")
        self.assertIsNone(a["cost_including_financing_eur"])

    def test_delivered_breakeven_reprices_to_equal_cost(self):
        p = inputs(); r = run(p)
        p["bio_price_eur_t"] = r["bio_delivered_breakeven_eur_t"]
        self.assertLess(abs(run(p)["saving_before_financing_eur"]), 2)

    def test_no_automatic_zero_rating_or_sales(self):
        p = inputs(); p["ets_bio_tco2e_t"] = 0
        with self.assertRaisesRegex(ValueError, "zero ETS"):
            run(p)
        p["ets_bio_zero_confirmed"] = True
        self.assertEqual(run(p)["options"][1]["ets_eua"], 1280)
        p = inputs(); p["pool_sell_eur_tco2e"] = 150
        self.assertEqual(run(p)["options"][1]["recognized_surplus_sale_eur"], 0)
        p["surplus_sale_confirmed"] = True
        self.assertGreater(run(p)["options"][1]["recognized_surplus_sale_eur"], 0)

    def test_invalid_scope_gases_quote_year_and_certification_hold(self):
        for key, value in [("ets_scope_share", 2), ("ets_bio_tco2e_t", None),
                ("pool_compliance_year", 2025), ("fueleu_bio_certified", False),
                ("technical_feasibility_confirmed", False), ("ets_factor_basis", "")]:
            p = inputs(); p[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                run(p)

    def test_zero_blend_has_no_fake_breakeven(self):
        p = inputs(); p["bio_energy_pct"] = 0
        r = run(p)
        self.assertIsNone(r["bio_delivered_breakeven_eur_t"])
        self.assertEqual(r["saving_before_financing_eur"], 0)

    def test_financing_is_added_once_and_receipt_changes_funding(self):
        p = inputs(); p.update(fuel_payment_date="2026-11-05", eua_payment_date="2026-11-20",
            pool_payment_date="2026-12-05", fee_payment_date="2026-11-05",
            customer_receipt_date="2026-12-20", customer_receipt_eur=750000,
            cash_buffer_eur=100000, funding_rate_pct=5, horizon_date="2026-12-31")
        r = run(p)
        for o in r["options"]:
            self.assertAlmostEqual(o["cost_including_financing_eur"], o["total_reference_cost_eur"] + o["funding"]["interest_eur"], places=2)
            self.assertGreater(o["funding"]["peak_extra_funding_eur"], 0)
        p["customer_receipt_date"] = "2026-11-05"
        earlier = run(p)
        self.assertEqual(earlier["options"][0]["funding"]["peak_extra_funding_eur"], 0)
        self.assertEqual(earlier["options"][0]["funding"]["interest_eur"], 0)


class LedgerTests(unittest.TestCase):
    def test_calendar_interest_and_same_day_netting(self):
        r = cash_ledger([(date(2026, 1, 1), "pay", Decimal(-1000)),
                         (date(2026, 1, 11), "receive", Decimal(1000))], Decimal(0), Decimal("36.5"), date(2026, 1, 11))
        self.assertEqual(r["interest_eur"], 10)
        self.assertEqual(r["peak_extra_funding_eur"], 1000)
        self.assertEqual(r["ending_cash_eur"], -10)
        same = cash_ledger([(date(2026, 1, 1), "pay", Decimal(-1000)),
                            (date(2026, 1, 1), "receive", Decimal(1000))], Decimal(0), Decimal(5), date(2026, 1, 1))
        self.assertEqual(same["peak_extra_funding_eur"], 0)

    def test_snapshot_is_observed_weighted_and_rejects_synthetic(self):
        s = {"as_of": "2026-11-04", "sources": {"eex_eua_auction": {"status": "observed",
            "unit": "EUR/EUA", "price_type": "auction_clearing", "source_url": "https://www.eex.com",
            "observations": [{"observation_date": "2026-11-03", "price": 80, "auction_volume_tco2": 100},
                             {"observation_date": "2026-11-03", "price": 100, "auction_volume_tco2": 300},
                             {"observation_date": "2026-11-05", "price": 200, "auction_volume_tco2": 100}]}}}
        self.assertEqual(observed_reference(s)["price_eur_eua"], "95")
        s["sources"]["eex_eua_auction"]["status"] = "synthetic"
        with self.assertRaises(ValueError):
            observed_reference(s)


class IndependentAuditTests(unittest.TestCase):
    def test_missing_route_is_held_even_if_source_estimates_zero_energy(self):
        row = dict(fuel=1000, co2=3151, ch4=.05, n2o=.18, between=None,
                   departed=None, arrived=None, in_port=None)
        r = call_fueleu({"mode": "validate_row", "row": row})
        self.assertEqual(r["source"]["status"], "estimated")
        self.assertEqual(r["source"]["fueleu_energy_mj"], 0)
        self.assertEqual(set(r["held_fields"]), {"between", "departed", "arrived", "in_port"})

    def test_missing_n2o_is_not_observed_zero(self):
        row = dict(fuel=1000, co2=3151, ch4=.05, n2o=None, between=0,
                   departed=3151, arrived=0, in_port=0)
        missing = call_fueleu({"mode": "validate_row", "row": row})
        self.assertEqual(missing["held_fields"], ["n2o"])
        row["n2o"] = 0
        zero = call_fueleu({"mode": "validate_row", "row": row})
        self.assertEqual(zero["held_fields"], [])


if __name__ == "__main__":
    unittest.main()
