import copy
import json
import unittest
from decimal import Decimal as D
from pathlib import Path
from engine import calculate, defaults

ROOT = Path(__file__).parent
SNAP = {"as_of": "2026-11-01", "sources": {
    "eex_eua_auction": {"status": "observed", "unit": "EUR/EUA", "price_type": "auction_clearing", "latest_observations": [{"price": "80", "observation_date": "2026-10-30"}]},
    "ecb_eurkrw": {"status": "observed", "unit": "KRW/EUR", "price_type": "reference_fx", "latest_observations": [{"price": "1500", "observation_date": "2026-10-30"}]}}}


class EngineTest(unittest.TestCase):
    def run_case(self, **changes):
        return calculate({**defaults(SNAP), **changes}, SNAP)

    def test_acceptance_shipowner(self):
        expected = json.loads((ROOT / "acceptance_cases.json").read_text())["shipowner"]
        s = self.run_case(price_shock="10")["shipowner"]
        for key, target in [("obligation_eua", "expected_obligation_eua"), ("procurement_gap_eua", "expected_procurement_gap_eua"), ("budget_eur", "expected_new_purchase_cash_eur"), ("net_cost_change_eur", "expected_net_extra_economic_cost_eur")]:
            self.assertEqual(s[key], D(expected[target]))

    def test_double_scope_weight_avoided(self):
        self.assertEqual(self.run_case(emissions_tco2e="100000", emissions_basis="scope_adjusted")["shipowner"]["obligation_eua"], D(100000))

    def test_late_delivery_excluded(self):
        s = self.run_case(delivery_date="2027-10-01")["shipowner"]
        self.assertEqual(s["procurement_gap_eua"], D(80000))
        self.assertEqual(s["late_delivery_eua"], D(30000))

    def test_scope_or_gas_unknown_held(self):
        for key in ("scope_confirmed", "gases_complete"):
            self.assertIsNone(self.run_case(**{key: False})["shipowner"]["obligation_eua"])

    def test_hedge_does_not_supply_allowances(self):
        self.assertEqual(self.run_case(ship_hedge_delta="50000")["shipowner"]["procurement_gap_eua"], D(50000))

    def test_reference_not_futures_price(self):
        d = self.run_case(future_price=None)["dealer"]
        self.assertIsNone(d["future_price_input"])
        self.assertEqual(d["future_price_status"], "missing")

    def test_bundled_reference_stays_synthetic(self):
        snap = json.loads((ROOT / "synthetic_snapshot.json").read_text())
        r = calculate(defaults(snap), snap)
        self.assertEqual(r["references"]["auction"]["status"], "synthetic")
        self.assertEqual(r["shipowner"]["budget_eur"], D(4000000))

    def test_agency_has_no_own_initial_margin(self):
        self.assertEqual(self.run_case(dealer_role="agency", initial_margin="250000")["dealer"]["vm_and_im_peak_funding_gap_eur"], 0)

    def test_zero_delta_can_need_cash(self):
        d = self.run_case()["dealer"]
        self.assertEqual(d["net_pnl_eur"], 0)
        self.assertEqual(d["vm_outflow_at_shock_eur"], D(500000))
        self.assertEqual(d["vm_only_peak_funding_gap_eur"], D(400000))
        self.assertEqual(d["cash_path"][-1]["cumulative_vm_eur"], 0)
        self.assertIsNone(d["vm_and_im_peak_funding_gap_eur"])

    def test_margin_and_buffer(self):
        self.assertEqual(self.run_case(initial_margin="250000")["dealer"]["vm_and_im_peak_funding_gap_eur"], D(650000))

    def test_agency_no_principal_position(self):
        d = self.run_case(dealer_role="agency")["dealer"]
        self.assertEqual(d["hedge_eua"], 0)
        self.assertEqual(d["net_delta_eua"], 0)

    def test_mismatched_buckets_and_delivery(self):
        d = self.run_case(future_bucket="2027-12", future_delivery_date="2027-12-01")["dealer"]
        self.assertTrue(d["curve_risk"])
        self.assertEqual(d["delivery_gap_eua"], D(50000))

    def test_missing_price_keeps_quantity(self):
        s = self.run_case(price_mode="manual", manual_price=None)["shipowner"]
        self.assertEqual(s["procurement_gap_eua"], D(50000))
        self.assertIsNone(s["budget_eur"])

    def test_ambiguous_reference_unavailable(self):
        snap = copy.deepcopy(SNAP)
        snap["sources"]["eex_eua_auction"]["latest_observations"] *= 2
        r = calculate(defaults(snap), snap)
        self.assertIsNone(r["shipowner"]["budget_eur"])
        self.assertEqual(r["references"]["auction"]["status"], "ambiguous")

    def test_nonfinite_negative_and_fractional_lots_rejected(self):
        for changes in ({"emissions_tco2e": "NaN"}, {"available_eua": "-1"}, {"dealer_lots": "1.5"}):
            with self.assertRaises(ValueError):
                self.run_case(**changes)

    def test_fuel_balance_not_eua_or_penalty(self):
        f = self.run_case()["fueleu"]
        self.assertEqual(f["balance_tco2e"], D("-663.2"))
        self.assertEqual(f["pool_cost_eur"], D("132640"))
        self.assertIsNone(f["penalty_eur"])


if __name__ == "__main__":
    unittest.main()
