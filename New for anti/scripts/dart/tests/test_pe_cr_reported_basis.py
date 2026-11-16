"""Reported-basis fallback cards (Claude, 2026-11-12) and the live-data gaps
they answer (docs/ops/handoff/2026-11-11-claude-to-codex-pecr-live.md).
Synthetic statement values; the account ids are the ones seen live."""
import unittest

from test_pe_cr import VALUES, bundle
from dart_kfa.canonical_facts import adapt_dart_filings
from dart_kfa.entity_policy import classify_entity
from dart_kfa.pe_cr import account_specs, build_pe_cr
from dart_kfa.pe_cr_screen import _annual_history

BASE = dict(VALUES, cf_depreciation=70, cf_amortisation=-10, cf_rou_depreciation=5,
            borrowings_long=300, bonds_noncurrent=150, lease_current=20, lease_noncurrent=30,
            cash_interest_operating=-25, equity=900, parent_equity=850, parent_income=60, total_income=70,
            assets=2000, liabilities=1100)


class ReportedBasisCards(unittest.TestCase):
    def test_ebitda_cf_from_cash_flow_addbacks(self):
        c = build_pe_cr(bundle(values=BASE))["cards"]
        self.assertEqual(c["ebitda_cf"]["value"], 100 + 70 + 10 + 5)
        self.assertAlmostEqual(c["ebitda_cf_margin"]["value"], 185 / 1000)
        # strict card untouched: no reviewed D&A
        self.assertIsNone(c["ebitda"]["value"])

    def test_combined_da_line_wins_over_parts(self):
        c = build_pe_cr(bundle(values=dict(BASE, cf_dep_amort_total=60)))["cards"]
        self.assertEqual(c["ebitda_cf"]["value"], 100 + 60 + 5)

    def test_ebitda_cf_needs_depreciation_line(self):
        values = {k: v for k, v in BASE.items() if k not in ("cf_depreciation", "cf_dep_amort_total")}
        c = build_pe_cr(bundle(values=values))["cards"]
        self.assertIsNone(c["ebitda_cf"]["value"])
        self.assertEqual(c["ebitda_cf"]["reason"], "missing:cf_depreciation_addback")

    def test_net_debt_reported_uses_combined_current_line_not_parts(self):
        # debt_current_total=100 is present, so bonds_current must not be added on top.
        c = build_pe_cr(bundle(values=dict(BASE, bonds_current=999)))["cards"]
        self.assertEqual(c["gross_debt_reported"]["value"], 100 + 300 + 150 + 20 + 30)
        self.assertEqual(c["net_debt_reported"]["value"], 600 - 80)
        self.assertAlmostEqual(c["net_debt_reported_to_ebitda"]["value"], 520 / 185)
        self.assertIsNone(c["net_debt"]["value"])  # strict card still needs review

    def test_net_debt_reported_without_any_borrowing_tag_is_missing_not_zero(self):
        values = {k: v for k, v in BASE.items() if k not in ("debt_current_total", "borrowings_long", "bonds_noncurrent")}
        c = build_pe_cr(bundle(values=values))["cards"]
        self.assertEqual(c["net_debt_reported"]["reason"], "missing:tagged_borrowings")

    def test_cash_interest_coverage_kept_apart_from_pl_interest(self):
        values = {k: v for k, v in BASE.items() if k != "interest"}
        c = build_pe_cr(bundle(values=values))["cards"]
        self.assertIsNone(c["interest_coverage"]["value"])
        self.assertEqual(c["interest_coverage_cash"]["value"], 100 / 25)

    def test_holding_company_kit_is_not_financial(self):
        out = build_pe_cr(bundle(values=BASE), corp={"induty_code": "64992", "corp_name": "에이치디한국조선해양(주)"})
        self.assertNotEqual(out["industry"], "financial")
        self.assertEqual(out["cards"]["ebitda_cf"]["value"], 185)
        fin = build_pe_cr(bundle(values=BASE), corp={"induty_code": "64992", "corp_name": "한국금융지주"})
        self.assertEqual(fin["industry"], "financial")

    def test_financial_entities_get_none_of_them(self):
        c = build_pe_cr(bundle(values=BASE), entity_policy={"is_financial_entity": True})["cards"]
        for key in ("ebitda_cf", "net_debt_reported", "interest_coverage_cash", "ev_reported"):
            self.assertEqual(c[key]["reason"], "not_applicable:financial_entity", key)

    def test_three_year_cash_icr_history(self):
        years = [bundle(y, values=dict(BASE, op=10, cash_interest_operating=-20)) for y in (2023, 2024)]
        current = bundle(values=dict(BASE, op=10, cash_interest_operating=-20))
        points = _annual_history(current, years, "2025-12-31", {}, {})
        self.assertEqual([p["metrics"]["interest_coverage_cash"] for p in points], [0.5, 0.5, 0.5])
        screen = build_pe_cr(current, history=years)["cr_pe_screen"]
        signal = next(s for s in screen["signals"] if s["id"] == "interest_coverage_cash_under_1_3y")
        self.assertEqual(signal["status"], "triggered")

    def test_trade_payables_to_suppliers_tag_maps(self):
        spec = account_specs()["PECR_payables"]
        self.assertIn("ifrs-full_TradeAndOtherCurrentPayablesToTradeSuppliers", spec["source_ids"])
        row = dict(sj_div="BS", account_id="ifrs-full_TradeAndOtherCurrentPayablesToTradeSuppliers", account_nm="매입채무",
                   fs_div="CFS", bsns_year="2025", thstrm_amount="13039380000000", currency="KRW", rcept_no="x")
        b = adapt_dart_filings({"FY": [row]}, account_specs=account_specs(), fiscal_year_end="2025-12-31",
                               entity_id="00126380", fs_div="CFS")
        self.assertEqual(b["series"]["PECR_payables"]["annual"]["value"], 13039380000000)


class HoldingCompanyClassification(unittest.TestCase):
    def test_nonfinancial_holding_is_not_financial(self):
        p = classify_entity({"induty_code": "64992", "corp_name": "에이치디한국조선해양(주)"})
        self.assertFalse(p["is_financial_entity"])

    def test_financial_holdings_stay_financial(self):
        for name in ("한국금융지주", "메리츠금융지주", "BNK금융지주"):
            self.assertTrue(classify_entity({"induty_code": "64992", "corp_name": name})["is_financial_entity"], name)

    def test_other_649_codes_unchanged(self):
        self.assertTrue(classify_entity({"induty_code": "64999"})["is_financial_entity"])
        self.assertEqual(classify_entity({"induty_code": "64913"})["entity_class"], "specialized_credit_finance")


if __name__ == "__main__":
    unittest.main()
