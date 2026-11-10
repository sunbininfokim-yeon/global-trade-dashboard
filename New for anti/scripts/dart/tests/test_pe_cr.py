"""Synthetic accounting fixtures, not live issuer observations."""
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dart_kfa.canonical_facts import adapt_dart_filings, default_dart_account_specs
from dart_kfa.canonical_analysis import analyze_canonical_facts
from dart_kfa.pe_cr import account_specs, build_pe_cr
from build_pe_cr import build


VALUES = dict(revenue=1000, op=100, interest=-20, finance_costs=50, cogs=-600,
              cfo=150, capex_ppe=-40, capex_intangible=10, cash=80,
              receivables=100, inventory=120, payables=60, current_assets=400,
              current_liabilities=200, debt_current_total=100,
              contract_assets=50, contract_liabilities=80)


def bundle(year=2025, values=None, scope="CFS"):
    rows = []
    for key, value in (VALUES if values is None else values).items():
        spec = account_specs()["PECR_" + key]
        rows.append(dict(sj_div=spec["statement"], account_id=spec["source_ids"][0],
                         account_nm=key, fs_div=scope, bsns_year=str(year),
                         thstrm_amount=str(value), currency="KRW", rcept_no="synthetic"))
    return adapt_dart_filings({"FY": rows}, account_specs=account_specs(),
                             fiscal_year_end=f"{year}-12-31", entity_id="test", fs_div=scope)


class PECRTests(unittest.TestCase):
    def test_cash_flow_and_expense_signs(self):
        c = build_pe_cr(bundle())["cards"]
        self.assertEqual(c["fcf"]["value"], 100)
        self.assertEqual(c["fcf_ppe_only"]["value"], 110)
        self.assertEqual(c["interest_coverage"]["value"], 5)
        self.assertEqual(c["finance_cost_coverage"]["value"], 2)
        self.assertEqual(c["cash_to_current_borrowings"]["value"], .8)

    def test_ccc_uses_opening_average(self):
        c = build_pe_cr(bundle(), history=[bundle(2024, {**VALUES, "receivables": 80, "inventory": 100, "payables": 40})])["cards"]
        self.assertAlmostEqual(c["ccc_days"]["value"], 90/1000*365 + 110/600*365 - 50/600*365)
        self.assertAlmostEqual(c["nwc_change_to_sales"]["value"], .02)
        self.assertEqual(len(c["ccc_days"]["inputs"]), 9)

    def test_missing_opening_never_uses_closing_only(self):
        self.assertIsNone(build_pe_cr(bundle())["cards"]["ccc_days"]["value"])

    def test_missing_capex_not_zero(self):
        b = bundle(); del b["series"]["PECR_capex_intangible"]
        c = build_pe_cr(b)["cards"]
        self.assertIsNone(c["fcf"]["value"])
        self.assertEqual(c["fcf_ppe_only"]["value"], 110)

    def test_finance_costs_and_cash_interest_not_substituted(self):
        b = bundle(); del b["series"]["PECR_interest"]
        c = build_pe_cr(b)["cards"]
        self.assertIsNone(c["interest_coverage"]["value"])
        self.assertEqual(c["finance_cost_coverage"]["value"], 2)

    def test_missing_latest_stays_missing(self):
        b = bundle(); b["series"]["PECR_op"]["annual"]["value"] = None
        self.assertIsNone(build_pe_cr(b, history=[bundle(2024)])["cards"]["interest_coverage"]["value"])

    def test_financial_suppression(self):
        r = build_pe_cr(bundle(), entity_policy={"is_financial_entity": True})
        self.assertEqual(r["visible_cards"], ["cfo", "cash_flow_capex_ppe", "cash_flow_capex_intangible"])
        self.assertIsNone(r["cards"]["fcf"]["value"])
        self.assertIsNone(r["cards"]["ccc_days"]["value"])

    def test_currency_scope_scale_and_proxies_rejected(self):
        for field, value in [("fs_div", "OFS"), ("quality", "proxy"), ("unit", {"currency": "USD", "scale": 1}), ("unit", {"currency": "KRW", "scale": 1000})]:
            b = bundle(); b["series"]["PECR_interest"]["annual"][field] = value
            self.assertIsNone(build_pe_cr(b)["cards"]["interest_coverage"]["value"])

    def test_opening_other_scope_or_company_rejected(self):
        for k, v in [("entity_id", "other"), ("fs_div", "OFS")]:
            prior = bundle(2024); prior[k] = v
            self.assertIsNone(build_pe_cr(bundle(), history=[prior])["cards"]["ccc_days"]["value"])

    def test_conflicting_opening_rejected(self):
        a = bundle(2024); b = deepcopy(a); b["series"]["PECR_receivables"]["annual"]["value"] += 1
        self.assertIn("conflict", build_pe_cr(bundle(), history=[a, b])["cards"]["dso_days"]["reason"])

    def test_loss_and_zero_denominator(self):
        c = build_pe_cr(bundle(values={**VALUES, "op": -100}))["cards"]
        self.assertEqual(c["interest_coverage"]["value"], -5)
        c = build_pe_cr(bundle(values={**VALUES, "interest": 0}))["cards"]
        self.assertIsNone(c["interest_coverage"]["value"])

    def test_shipping_ccc_disabled(self):
        c = build_pe_cr(bundle(), history=[bundle(2024)], industry="shipping")["cards"]
        self.assertEqual(c["ccc_days"]["reason"], "not_applicable:industry_ccc")

    def test_statement_qualified_mapping_and_broad_ar_excluded(self):
        rows = [dict(sj_div="CF", account_id="ifrs-full_InterestExpense", thstrm_amount="20", fs_div="CFS"),
                dict(sj_div="BS", account_id="ifrs-full_TradeAndOtherCurrentReceivables", thstrm_amount="100", fs_div="CFS")]
        b = adapt_dart_filings({"FY": rows}, account_specs=default_dart_account_specs(), fiscal_year_end="2025-12-31")
        self.assertIsNone(b["series"]["PECR_interest"]["annual"]["value"])
        self.assertIsNone(b["series"]["PECR_receivables"]["annual"]["value"])

    def test_cis_allowed_but_conflicting_duplicates_blocked(self):
        row = dict(sj_div="CIS", account_id="ifrs-full_InterestExpense", thstrm_amount="20", fs_div="CFS", rcept_no="synthetic")
        def adapt(rows):
            return adapt_dart_filings({"FY": rows}, account_specs=account_specs(), fiscal_year_end="2025-12-31")["series"]["PECR_interest"]["annual"]
        self.assertEqual(adapt([row])["value"], 20)
        self.assertEqual(adapt([row])["provenance"]["source_statement"], "CIS")
        self.assertIsNone(adapt([row, {**row, "sj_div": "IS", "thstrm_amount": "30"}])["value"])

    def test_additive_integration(self):
        self.assertIn("pe_cr", analyze_canonical_facts(bundle()))

    def test_strict_ebitda_and_conversion(self):
        b = bundle()
        for key, value in [("OPERATING_INCOME", 100), ("PPE_DEPRECIATION", 10), ("INTANGIBLE_AMORTIZATION", 5)]:
            f = deepcopy(b["series"]["PECR_op"]["annual"])
            f.update(account_id=key, value=value)
            b["series"][key] = {"annual": f, "quarters": {}}
        c = build_pe_cr(b)["cards"]
        self.assertEqual(c["ebitda"]["value"], 115)
        self.assertAlmostEqual(c["fcf_to_ebitda"]["value"], 100/115)
        for key in ("OPERATING_INCOME", "PPE_DEPRECIATION", "INTANGIBLE_AMORTIZATION"):
            b["series"][key]["annual"]["unit"]["scale"] = 1000
        self.assertIsNone(build_pe_cr(b)["cards"]["ebitda"]["value"])

    def test_q4_and_null_cells_do_not_crash(self):
        b = bundle()
        for s in b["series"].values():
            f = deepcopy(s["annual"])
            if f["nature"] == "flow":
                f["period_start"] = "2025-10-01"
            f["period_kind"] = "flow_discrete_quarter" if f["nature"] == "flow" else "balance_point_in_time"
            f["fiscal_quarter"] = "Q4"
            s["quarters"]["Q4"] = f
            s["annual"] = None
        c = build_pe_cr(b, selected_period="Q4")["cards"]
        self.assertEqual(c["fcf"]["value"], 100)
        self.assertIsNone(c["ebitda"]["value"])
        self.assertIsNone(build_pe_cr(b)["cards"]["fcf"]["value"])

    def test_industry_focus_keys_exist(self):
        for industry in ("manufacturing", "semiconductor", "construction", "shipbuilding", "shipping", "financial"):
            r = build_pe_cr(bundle(), industry=industry)
            self.assertTrue(set(r["focus"]).issubset(r["cards"]))

    def test_offline_entrypoint(self):
        out = build(dict(entity_id="00688996", fiscal_year_end="2025-12-31", fs_div="CFS", filings={}))
        self.assertEqual(out["industry"], "financial")

    def test_quarter_actual_days_and_no_ytd_mix(self):
        specs = account_specs(); reports = {}
        for code, multiple in [("Q1", 1), ("H1", 3)]:
            reports[code] = [dict(sj_div=s["statement"], account_id=s["source_ids"][0], fs_div="CFS",
                                 thstrm_amount=str(VALUES[k[5:]]*multiple),
                                 thstrm_add_amount=str(VALUES[k[5:]]*multiple), rcept_no="synthetic")
                             for k, s in specs.items() if k[5:] in VALUES]
        b = adapt_dart_filings(reports, account_specs=specs, fiscal_year_end="2025-12-31", entity_id="test")
        c = build_pe_cr(b, selected_period="Q2")["cards"]
        self.assertEqual(c["fcf"]["value"], 200)
        self.assertAlmostEqual(c["dso_days"]["value"], 200/2000*91)


if __name__ == "__main__":
    unittest.main()
