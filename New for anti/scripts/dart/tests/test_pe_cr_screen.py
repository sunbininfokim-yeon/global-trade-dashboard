"""CR/PE screen: known synthetic scenarios and saved-API boundary tests."""
from copy import deepcopy
from datetime import date, timedelta
import unittest

from test_pe_cr import VALUES, bundle
from test_pe_cr_evidence import payload, reviewed, saved_report
from build_pe_cr import build
from dart_kfa.canonical_analysis import analyze_canonical_facts
from dart_kfa.pe_cr import build_pe_cr


END = "2025-12-31"
SOURCE = {"filing_id": "synthetic", "url": "https://example.com/synthetic", "locator": "synthetic note"}


def signals(screen):
    return {s["id"]: s for s in screen["signals"]}


def year(y):
    return bundle(y, {**VALUES, "op": 2 if y == 2023 else -10, "cfo": -30, "cogs": 600 + (y-2023)*50,
                      "equity": 160, "parent_equity": 80, "issued_capital": 100})


def cash_plan(b):
    base = date(2026, 1, 1)
    return {"schema_version": "kfa-cash-plan/1", "entity_id": b["entity_id"], "as_of": END, "currency": "KRW", "fs_div": "CFS",
            "scale": 1, "opening_unrestricted_cash": 100, "minimum_cash": 20, "scenario_label": "synthetic downside",
            "weeks": [{"week_start": (base + timedelta(weeks=i)).isoformat(), "operating_receipts": 5,
                       "committed_financing_draws": 0, "operating_payments": 10, "cash_taxes": 0,
                       "cash_capex": 0, "principal_payments": 85 if i == 0 else 0, "cash_interest": 0}
                      for i in range(13)]}


class CRScreenTests(unittest.TestCase):
    def test_profit_cash_and_balance_sheet_flags(self):
        b = year(2025)
        result = build_pe_cr(b, history=[year(2024), year(2023)], reviewed_disclosures=reviewed(b, {"PPE_DEPRECIATION": 30, "INTANGIBLE_AMORTIZATION": 10}))
        c, s = result["cards"], result["cr_pe_screen"]
        self.assertEqual(c["operating_margin"]["value"], -.01)
        self.assertEqual(c["ebitda_margin"]["value"], .03)
        self.assertEqual(c["cfo"]["value"], -30)
        self.assertEqual(c["capital_erosion_ratio"]["value"], .2)
        self.assertEqual(len(s["sections"]), 7)
        self.assertEqual(s["lens_order"]["cr"][0], "short_term_liquidity")
        self.assertEqual(s["lens_order"]["pe"][0], "profitability")
        lookup = signals(s)
        for k in ("operating_loss_2y", "negative_cfo_2y", "rising_cost_ratio_3y", "interest_coverage_under_1_3y", "equity_below_issued_capital"):
            self.assertEqual(lookup[k]["status"], "triggered")
        self.assertEqual(lookup["negative_equity"]["status"], "not_triggered")
        self.assertEqual(lookup["modified_audit_opinion"]["status"], "unavailable")

    def test_no_gap_scope_mix_duplicate_or_interim_lookahead(self):
        b = year(2025)
        for history in ([year(2023)], [{**year(2024), "fs_div": "OFS"}, year(2023)],
                        [year(2024), bundle(2024), year(2023)],
                        [year(2024), bundle(2024, {**VALUES, "op": -10, "cfo": -30, "revenue": 2000, "cogs": 1300}), year(2023)]):
            lookup = signals(build_pe_cr(b, history=history)["cr_pe_screen"])
            self.assertEqual(lookup["interest_coverage_under_1_3y"]["status"], "unavailable")
        s = build_pe_cr(b, selected_period="Q2", history=[year(2024), year(2023)])["cr_pe_screen"]
        self.assertEqual(s["annual_history"][0]["fiscal_year"], 2024)
        self.assertNotIn(2025, [p["fiscal_year"] for p in s["annual_history"]])

    def test_interest_coverage_does_not_use_total_finance_cost(self):
        prior = year(2024)
        del prior["series"]["PECR_interest"]
        b = year(2025)
        def assess(inputs=None):
            return signals(build_pe_cr(b, history=[prior, year(2023)], screen_inputs=inputs)["cr_pe_screen"])["interest_coverage_under_1_3y"]
        self.assertEqual(assess()["status"], "unavailable")
        verified = reviewed(prior, {"interest": 20})
        verified["rows"][0].update(period_start="2024-01-01", period_end="2024-12-31")
        self.assertEqual(assess({"annual_reviewed_disclosures": {"2024-12-31": verified}})["status"], "triggered")
        prior["series"]["PECR_interest"] = {"annual": {"reason": "conflict:duplicate_source_concept"}}
        self.assertEqual(assess({"annual_reviewed_disclosures": {"2024-12-31": verified}})["status"], "unavailable")

    def test_cash_plan_requires_13_weeks_and_never_infers_refinancing(self):
        b = year(2025)
        plan = cash_plan(b)
        s = build_pe_cr(b, screen_inputs={"cash_plan": plan})["cr_pe_screen"]
        c = s["cash_plan_13w"]
        self.assertEqual(c["classification"], "scenario")
        self.assertEqual(len(c["weeks"]), 13)
        self.assertEqual(c["weeks"][0]["closing_cash"], 10)
        self.assertEqual(c["weeks"][1]["opening_cash"], 10)
        self.assertEqual(c["first_week_below_minimum"], 1)
        self.assertEqual(c["lowest_closing_cash"], -50)
        self.assertEqual(signals(s)["cash_plan_below_minimum"]["observations"][0]["classification"], "scenario")
        plan["weeks"][0]["unconfirmed_refinancing"] = 200
        with self.assertRaisesRegex(ValueError, "invalid:cash_plan_week_calendar_or_fields"):
            build_pe_cr(b, screen_inputs={"cash_plan": plan})
        plan["weeks"].pop()
        with self.assertRaisesRegex(ValueError, "exactly_13_cash_plan_weeks"):
            build_pe_cr(b, screen_inputs={"cash_plan": plan})

    def test_industry_metrics_and_like_scope_declines(self):
        b = year(2025)
        def disclosed(y, amount, backlog):
            end, start = f"{y}-12-31", f"{y}-01-01"
            unit = {"scope": "synthetic shipyard capacity", "period_end": end, "source": SOURCE}
            return {"schema_version": "kfa-screen-industry/1", "entity_id": "test", "as_of": end, "fs_div": "CFS", "currency": "KRW", "scale": 1,
                    "rows": [{**unit, "metric": "capacity_utilization", "unit": "hours", "numerator": amount, "denominator": 100, "period_start": start},
                             {**unit, "metric": "order_backlog", "unit": "KRW", "numerator": backlog},
                             {**unit, "metric": "market_share", "unit": "units", "numerator": 20, "denominator": 500, "period_start": start}]}
        inputs = {"industry": disclosed(2025, 80, 200), "prior_industry": disclosed(2024, 90, 250)}
        screen = build_pe_cr(b, history=[year(2024)], screen_inputs=inputs)["cr_pe_screen"]
        self.assertEqual(screen["industry_observations"]["rows"][2]["value"], .04)
        self.assertEqual(signals(screen)["capacity_utilization_down"]["status"], "triggered")
        self.assertEqual(signals(screen)["order_backlog_down"]["status"], "triggered")
        inputs["prior_industry"]["rows"][0]["scope"] = "different shipyard"
        screen = build_pe_cr(b, history=[year(2024)], screen_inputs=inputs)["cr_pe_screen"]
        self.assertEqual(signals(screen)["capacity_utilization_down"]["status"], "unavailable")
        inputs["industry"]["scale"] = 1_000_000
        with self.assertRaisesRegex(ValueError, "invalid:industry_observation_scale"):
            build_pe_cr(b, history=[year(2024)], screen_inputs=inputs)

    def test_dart_governance_current_receipt_and_exact_opinion(self):
        b = {**year(2025), "entity_id": "00126380"}
        receipt = "20260310000001"
        row = {"corp_code": b["entity_id"], "rcept_no": receipt, "stlm_dt": END}
        audit = {"endpoint": "accnutAdtorNmNdAdtOpinion", "as_of": END, "receipt": receipt, "reprt_code": "11011", "fs_div": "CFS",
                 "scope_evidence": "synthetic annual consolidated audit",
                 "response": {"status": "000", "list": [{**row, "adtor": "Synthetic audit", "adt_opinion": "부적정"},
                                                            {**row, "adtor": "Old audit", "adt_opinion": "적정", "stlm_dt": "2024-12-31"}]}}
        ownership = {"endpoint": "hyslrChgSttus", "as_of": END, "receipt": receipt,
                     "response": {"status": "000", "list": [{**row, "change_on": "2025.05.01", "mxmm_shrholdr_nm": "Holder A"},
                                                            {**row, "change_on": "2024.12.01", "mxmm_shrholdr_nm": "Prior holder"}]}}
        s = build_pe_cr(b, screen_inputs={"dart_audit": audit, "dart_ownership": ownership})["cr_pe_screen"]
        self.assertEqual(s["governance"]["audit"]["opinion"], "adverse")
        self.assertEqual(signals(s)["modified_audit_opinion"]["status"], "triggered")
        self.assertEqual([row["holder"] for row in s["governance"]["ownership_events"]], ["Holder A"])
        self.assertNotIn("management_dispute", signals(s))
        audit["response"]["list"][0].update(adt_opinion="적정", emphs_matter="emphasis only")
        s = build_pe_cr(b, screen_inputs={"dart_audit": audit})["cr_pe_screen"]
        self.assertEqual(signals(s)["modified_audit_opinion"]["status"], "not_triggered")

    def test_dart_raw_api_history_uses_report_year_and_issuer(self):
        raw = saved_report(VALUES)
        p = payload(raw)
        prior = deepcopy(raw)
        prior["request"]["bsns_year"] = "2024"
        for row in prior["response"]["list"]:
            row["bsns_year"] = "2024"
        p["prior_reports"] = [{"fiscal_year_end": "2024-12-31", "filings": {"FY": prior}}]
        s = build(p)["cr_pe_screen"]
        self.assertEqual(signals(s)["operating_loss_2y"]["status"], "not_triggered")
        prior["response"]["list"][0]["corp_code"] = "99999999"
        with self.assertRaisesRegex(ValueError, "incompatible:dart_response_identity"):
            build(p)

    def test_sec_companyfacts_cli_and_verified_governance(self):
        start, end, cik = "2024-09-02", "2025-08-31", "0000909832"
        # Costco FY2025 reported amounts from SEC 10-K, in Companyfacts-shaped fixture.
        gaap = {tag: {"units": {"USD": [{"start": start, "end": end, "val": value*1000000, "fp": "FY", "form": "10-K",
                                        "accn": "0000909832-25-000101"}]}}
                for tag, value in {"RevenueFromContractWithCustomerExcludingAssessedTax": 275235,
                                   "OperatingIncomeLoss": 10383, "CostOfGoodsAndServicesSold": 239886}.items()}
        p = {"source": "SEC", "entity_id": cik, "fiscal_year_end": end, "companyfacts": {"cik": 909832, "facts": {"us-gaap": gaap}},
             "report_periods": {"FY": {"start": start, "end": end}}}
        p["screen_inputs"] = {"governance": {"schema_version": "kfa-screen-governance/1", "entity_id": cik,
                              "as_of": end, "period_start": start, "currency": "USD", "fs_div": "CFS", "scale": 1,
                              "related_party_transactions": [{"basis": "closing_balance", "category": "synthetic test category", "counterparty": "Synthetic",
                                                              "amount": 100, "source": SOURCE}]}}
        result = build(p)
        self.assertAlmostEqual(result["cards"]["operating_margin"]["value"], 10383/275235)
        self.assertIsNone(result["cards"]["ebitda_margin"]["value"])
        self.assertIsNone(result["cards"]["capital_erosion_ratio"]["value"])
        self.assertEqual(result["cr_pe_screen"]["governance"]["related_party_transactions"][0]["basis"], "closing_balance")
        with self.assertRaisesRegex(ValueError, "incompatible:sec_companyfacts_cik"):
            build({**p, "entity_id": "0000019617"})

    def test_financial_screen_keeps_funding_scope_not_industrial_flags(self):
        b = {**year(2025), "entity_id": "00688996"}
        analysis = analyze_canonical_facts(b)
        s = analysis["pe_cr"]["cr_pe_screen"]
        self.assertEqual(signals(s)["negative_cfo_2y"]["status"], "not_applicable")
        self.assertEqual(s["references"]["funding"], "disclosure_profile")
        binding = analysis["unified_views"]["expert_diagnostics"]
        self.assertEqual(binding["source_path"], "pe_cr.cr_pe_screen")
        self.assertEqual(binding["card_registry_path"], "pe_cr.cards")
        self.assertEqual(binding["lenses"]["cr"]["section_order"], s["lens_order"]["cr"])


if __name__ == "__main__":
    unittest.main()
