import unittest
from decimal import Decimal as D
from engine import calculate, defaults


class FundingTest(unittest.TestCase):
    def result(self, **changes):
        p = {**defaults({}), "initial_margin": "250000", "funding_rate_pct": "0",
             "future_delivery_date": "2026-11-04", "customer_delivery_date": "2026-11-04",
             "customer_payment_date": "2026-11-10", **changes}
        return calculate(p, {})

    def test_matched_supply_cash_reconciles_without_double_counting_vm(self):
        f = self.result()["dealer"]["funding"]
        self.assertEqual(f["peak_funding_gap_eur"], D(3901000))
        self.assertEqual(f["closing_cash_eur"], D(349000))
        self.assertEqual(f["net_contribution_eur"], D(249000))
        self.assertEqual(sum((e["cash_eur"] for e in f["events"] if e["kind"] == "variation_margin"), D(0)), 0)

    def test_persistent_shock_changes_invoice_and_vm_not_acquisition_cost(self):
        d = self.result(price_path="persistent")["dealer"]
        f = d["funding"]
        self.assertEqual(d["cash_path"][-1]["cumulative_vm_eur"], D(-500000))
        self.assertEqual(f["closing_cash_eur"], D(349000))
        self.assertEqual(next(e["cash_eur"] for e in f["events"] if e["kind"] == "physical_future_payment"), D(-3500000))

    def test_prepayment_removes_external_funding_in_example(self):
        f = self.result(customer_payment_date="2026-11-01")["dealer"]["funding"]
        self.assertEqual(f["peak_funding_gap_eur"], 0)

    def test_unknown_margin_never_becomes_complete_funding(self):
        f = self.result(initial_margin=None)["dealer"]["funding"]
        self.assertEqual(f["status"], "partial")
        self.assertIsNone(f["peak_funding_gap_eur"])
        self.assertIsNone(f["net_contribution_eur"])

    def test_late_futures_require_replacement_and_leave_inventory(self):
        f = self.result(future_delivery_date="2026-12-01")["dealer"]["funding"]
        self.assertEqual(f["replacement_eua"], D(50000))
        self.assertEqual(f["residual_inventory_eua"], D(50000))
        self.assertIsNone(f["peak_funding_gap_eur"])
        f = self.result(future_delivery_date="2026-12-01", replacement_price="82")["dealer"]["funding"]
        self.assertEqual(f["status"], "scenario")
        self.assertIsNone(f["net_contribution_eur"])

    def test_no_hedge_needs_spot_price_not_margin(self):
        f = self.result(dealer_lots="0", initial_margin=None, replacement_price="82")["dealer"]["funding"]
        self.assertEqual(f["status"], "scenario")
        self.assertEqual(f["closing_cash_eur"], D(249000))

    def test_financing_calendar_day_interest(self):
        f = self.result(cash_buffer="0", initial_margin="0", trade_fees="0", funding_rate_pct="36.5")["dealer"]["funding"]
        # 500k borrowed for one day, 500.0 for one day, then 4,000,500.5 for six days.
        self.assertEqual(f["financing_cost_eur"], D("24503.503"))
        self.assertEqual(f["net_contribution_eur"], D("225496.497"))

    def test_unknown_customer_price_holds_contribution(self):
        f = self.result(customer_price=None)["dealer"]["funding"]
        self.assertIn("customer_receipt", f["missing_inputs"])
        self.assertIsNone(f["net_contribution_eur"])

    def test_agency_has_no_own_funding_ledger(self):
        f = self.result(dealer_role="agency")["dealer"]["funding"]
        self.assertEqual(f["status"], "not_applicable")
        self.assertEqual(f["events"], [])

    def test_basis_move_leaves_pnl_with_zero_aggregate_delta(self):
        d = self.result(hedge_basis_shock="2")["dealer"]
        self.assertEqual(d["net_delta_eua"], 0)
        self.assertEqual(d["net_pnl_eur"], D(100000))

    def test_hedge_comparison_preserves_lot_residual(self):
        d = self.result(available_eua="20001")["dealer"]
        last = d["hedge_comparison"][-1]
        self.assertEqual(last["lots"], D(50))
        self.assertEqual(last["residual_delta_eua"], D(1))

    def test_invalid_dates_and_price_path(self):
        for p in ({"customer_payment_date": "2026-01-01"}, {"future_delivery_date": "2026-11-02"}, {"price_path": "unknown"}):
            with self.assertRaises(ValueError):
                self.result(**p)


if __name__ == "__main__":
    unittest.main()
