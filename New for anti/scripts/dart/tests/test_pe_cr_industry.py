"""Industry routing and ratios, with separate SEC filing spot checks."""
import json
import unittest
from pathlib import Path

from test_pe_cr import VALUES, bundle
from test_pe_cr_evidence import payload, reviewed, saved_report
from build_pe_cr import build
from dart_kfa.canonical_analysis import analyze_canonical_facts
from dart_kfa.canonical_facts import adapt_sec_companyfacts
from dart_kfa.pe_cr import build_pe_cr


class IndustryTests(unittest.TestCase):
    def test_dart_numeric_and_prefixed_ksic(self):
        for code, expected in (("31111", "shipbuilding"), ("C31111", "shipbuilding"), ("C312", "manufacturing"),
                               ("2929", "machinery"), ("C291", "machinery"), ("C261", "semiconductor"), ("C262", "it_hardware"),
                               ("465", "retail_wholesale"), ("4711", "retail_wholesale"), ("47912", "retail_wholesale"),
                               ("G47911", "retail_platform"), ("461", "retail_platform"), ("4791", "retail_mixed"),
                               ("G46", "retail_mixed"), ("582", "it_services"), ("J62010", "it_services"),
                               ("581", "general"), ("F411", "construction"), ("H501", "shipping")):
            with self.subTest(code=code):
                r = build_pe_cr(bundle(), corp={"induty_code": code})
                self.assertEqual(r["industry"], expected)
                self.assertEqual(r["industry_profile"]["selection_basis"], "dart_ksic")
                self.assertEqual(r["industry_profile"]["ksic"], code)
                self.assertTrue(set(r["focus"]) <= r["cards"].keys())

    def test_financial_code_cannot_be_overridden(self):
        r = build_pe_cr(bundle(), corp={"induty_code": "64201"}, industry="retail")
        self.assertEqual(r["industry"], "financial")
        self.assertEqual(r["cards"]["cfo"]["value"], 150)
        self.assertEqual(r["cards"]["fcf"]["reason"], "not_applicable:financial_entity")

    def test_cli_and_analysis_use_metadata(self):
        p = {**payload(saved_report(VALUES)), "corp": {"induty_code": "47912"}}
        self.assertEqual(build(p)["industry"], "retail_wholesale")
        r = analyze_canonical_facts(bundle(), corp={"induty_code": "J62"})["pe_cr"]
        self.assertEqual(r["industry"], "it_services")

    def test_sec_does_not_treat_sic_as_ksic(self):
        sec = {**bundle(), "source": "SEC"}
        r = build_pe_cr(sec, corp={"industry": "47912", "industry_kit": "software"})
        self.assertEqual(r["industry"], "it_services")
        self.assertIsNone(r["industry_profile"]["ksic"])
        self.assertEqual(build_pe_cr(sec, corp={"industry": "47912"})["industry"], "general")

    def test_retail_ccc_bases_and_negative_cycle(self):
        b = bundle(values={**VALUES, "receivables": 10, "inventory": 100, "payables": 180})
        prior = bundle(2024, {**VALUES, "receivables": 10, "inventory": 100, "payables": 180})
        base = build_pe_cr(b, industry="retail", history=[prior])
        self.assertEqual(base["focus"][0], "ccc_days")
        self.assertEqual(base["industry_profile"]["ccc_policy"], "primary")
        self.assertAlmostEqual(base["cards"]["ccc_days"]["value"], 365 * (.01 + 100/600 - 180/600))
        self.assertEqual(base["cards"]["ccc_days_on_purchases"]["reason"], "missing:reviewed_merchandise_purchases")
        pack = reviewed(b, {"merchandise_purchases": 500})
        c = build_pe_cr(b, industry="retail", history=iter([prior]), reviewed_disclosures=pack)["cards"]
        self.assertEqual(c["inventory_turns_period"]["value"], 6)
        self.assertEqual(c["inventory_less_trade_payables"]["value"], -80)
        self.assertAlmostEqual(c["dpo_days_on_purchases"]["value"], 365 * 180/500)
        self.assertAlmostEqual(c["ccc_days_on_purchases"]["value"], 365 * (.01 + 100/600 - 180/500))
        self.assertEqual(c["ccc_days"]["value"], base["cards"]["ccc_days"]["value"])

    def test_platform_and_mixed_do_not_consume_trade_balances(self):
        for code, reason in (("47911", "not_applicable:industry_ccc"), ("4791", "requires:confirmed_industry_ccc_scope")):
            r = build_pe_cr(bundle(), corp={"induty_code": code}, history=[bundle(2024)])
            self.assertEqual(r["cards"]["ccc_days"]["reason"], reason)
            self.assertIsNone(r["cards"]["dso_days"]["value"])
            self.assertIsNone(r["cards"]["nwc_change_to_sales"]["value"])
            self.assertEqual(r["cards"]["fcf"]["value"], 100)

    def test_exact_trade_receivables_note_can_supply_opening_and_closing(self):
        b = bundle(values={k: v for k, v in VALUES.items() if k != "receivables"})
        prior = bundle(2024, {k: v for k, v in VALUES.items() if k != "receivables"})
        pack = reviewed(b, {"receivables": 120})
        pack["rows"].append({**pack["rows"][0], "period_end": "2024-12-31", "amount": 80})
        card = build_pe_cr(b, industry="retail", history=[prior], reviewed_disclosures=pack)["cards"]["dso_days"]
        self.assertAlmostEqual(card["value"], 36.5)
        self.assertEqual([f["source"] for f in card["inputs"] if f["input"] == "receivables"], ["reviewed_disclosure"]*2)
        pack["rows"].pop()
        card = build_pe_cr(b, industry="retail", history=[prior], reviewed_disclosures=pack)["cards"]["dso_days"]
        self.assertEqual(card["reason"], "missing:opening_receivables")

    def test_shipbuilding_contract_position_and_note_backlog(self):
        b = bundle()
        r = build_pe_cr(b, industry="shipbuilding", reviewed_disclosures=reviewed(b, {"order_backlog": 700, "new_orders": 240}))
        self.assertEqual(r["industry_profile"]["ccc_policy"], "secondary")
        self.assertNotIn("ccc_days", r["focus"])
        self.assertEqual(r["cards"]["net_contract_position_to_sales"]["value"], -.03)
        self.assertEqual(r["cards"]["order_backlog"]["value"], 700)
        self.assertEqual(r["cards"]["new_orders"]["value"], 240)
        self.assertEqual(build_pe_cr(b, industry="shipbuilding")["cards"]["order_backlog"]["reason"], "missing:reviewed_order_backlog")

    def test_machinery_inventory_components_reconcile(self):
        b = bundle()
        for raw_material, expected in ((30, .5), (70, None)):
            pack = reviewed(b, {"wip_inventory": 60, "raw_material_inventory": raw_material, "inventory_note_total": 120})
            c = build_pe_cr(b, industry="machinery", reviewed_disclosures=pack)["cards"]
            self.assertEqual(c["wip_to_inventory"]["value"], expected)
            if expected is None:
                self.assertIn("exceed_total", c["raw_materials_to_inventory"]["reason"])
        pack = reviewed(b, {"wip_inventory": 60, "inventory_note_total": 121})
        c = build_pe_cr(b, industry="machinery", reviewed_disclosures=pack)["cards"]
        self.assertIn("does_not_match_balance_sheet", c["wip_to_inventory"]["reason"])

    def test_it_service_dso_and_development_costs_separate(self):
        b = bundle(values={**VALUES, "rd_expense": -120})
        pack = reviewed(b, {"capitalized_development": 25})
        c = build_pe_cr(b, industry="it", history=[bundle(2024)], reviewed_disclosures=pack)["cards"]
        self.assertAlmostEqual(c["dso_days"]["value"], 36.5)
        self.assertIsNone(c["ccc_days"]["value"])
        self.assertEqual(c["rd_expense_to_sales"]["value"], .12)
        self.assertEqual(c["capitalized_development_to_sales"]["value"], .025)
        self.assertEqual(c["contract_liabilities_to_sales"]["value"], .08)
        self.assertEqual(c["fcf"]["value"], 100)

    def test_costco_10k_inventory_and_payables_not_broad_receivables(self):
        # SEC EDGAR R3/R5 statements, 0000909832-25-000101; absolute USD
        # amounts transcribed into a Companyfacts-shaped fixture.
        prior_end, start, end = "2024-09-01", "2024-09-02", "2025-08-31"
        values = {"InventoryNet": [(prior_end, 18647), (end, 18116)],
                  "AccountsPayableCurrent": [(prior_end, 19421), (end, 19783)],
                  "ReceivablesNetCurrent": [(prior_end, 2721), (end, 3203)],
                  "RevenueFromContractWithCustomerExcludingAssessedTax": [(end, 275235)],
                  "CostOfGoodsAndServicesSold": [(end, 239886)]}
        gaap = {tag: {"units": {"USD": [
            {"end": d, "val": v*1000000, "fp": "FY", "form": "10-K", "accn": "0000909832-25-000101",
             **({"start": start} if tag in {"CostOfGoodsAndServicesSold", "RevenueFromContractWithCustomerExcludingAssessedTax"} else {})}
            for d, v in series]}} for tag, series in values.items()}
        data = {"facts": {"us-gaap": gaap}}
        b = adapt_sec_companyfacts(data, fiscal_year_end=end, entity_id="0000909832", report_periods={"FY": {"start": start, "end": end}})
        prior = adapt_sec_companyfacts(data, fiscal_year_end=prior_end, entity_id="0000909832")
        c = build_pe_cr(b, industry="retail", history=[prior])["cards"]
        self.assertAlmostEqual(c["dio_days"]["value"], 364*(18116+18647)/2/239886)
        self.assertAlmostEqual(c["dpo_days"]["value"], 364*(19783+19421)/2/239886)
        self.assertEqual(c["inventory_less_trade_payables"]["value"], -1667000000)
        self.assertIsNone(c["dso_days"]["value"])
        self.assertIsNone(c["ccc_days"]["value"])
        self.assertIsNone(c["dpo_days_on_purchases"]["value"])

    def test_itt_10k_machine_manufacturing_inventory_note(self):
        path = Path(__file__).resolve().parents[1] / "config/pe_cr_reviewed/itt_0000216228_2025_cfs.json"
        pack = json.loads(path.read_text())
        fact = {"end": "2025-12-31", "val": 671900000, "fp": "FY", "form": "10-K", "accn": "0000216228-26-000012"}
        b = adapt_sec_companyfacts({"facts": {"us-gaap": {"InventoryNet": {"units": {"USD": [fact]}}}}},
                                   fiscal_year_end="2025-12-31", entity_id="0000216228")
        c = build_pe_cr(b, industry="machinery", reviewed_disclosures=pack)["cards"]
        self.assertAlmostEqual(c["wip_to_inventory"]["value"], 125.2/671.9)
        self.assertAlmostEqual(c["raw_materials_to_inventory"]["value"], 411.8/671.9)
        self.assertIsNone(c["ccc_days"]["value"])


if __name__ == "__main__":
    unittest.main()
