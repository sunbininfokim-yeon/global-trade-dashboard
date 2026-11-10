"""Verified public filing values in offline DART/SEC response shapes."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from build_pe_cr import build
from dart_kfa.canonical_analysis import analyze_canonical_facts
from dart_kfa.canonical_facts import adapt_sec_companyfacts
from dart_kfa.industry_note_mapping import _catalog, build_industry_note_profile
from dart_kfa.pe_cr import build_pe_cr
from test_industry_note_mapping import rows
from test_pe_cr import bundle
from test_pe_cr_evidence import payload, reviewed, saved_report


BGF = "01263022"
EBAY = "0001065088"
REVENUE = 9_061_216_107_616
COGS = 7_374_174_140_732
INVENTORY = 215_631_364_940
PRIOR_INVENTORY = 212_274_236_406


def bgf():
    report = saved_report({"revenue": REVENUE, "cogs": -COGS, "inventory": INVENTORY}, corp=BGF)
    rows_ = report["response"]["list"]
    for tag, amount in (("ifrs-full_TradeAndOtherCurrentReceivables", 191_576_822_047),
                        ("ifrs-full_TradeAndOtherCurrentPayables", 623_568_712_926)):
        rows_.append({**rows_[2], "account_id": tag, "thstrm_amount": str(amount)})
    for row in rows_:
        row["rcept_no"] = "20260318000829"
    return {**payload(report), "entity_id": BGF,
            "history": [{**bundle(2024, {"inventory": PRIOR_INVENTORY}), "entity_id": BGF}]}


def ebay():
    item = {"start": "2025-01-01", "end": "2025-12-31", "val": 11_100_000_000, "form": "10-K",
            "fp": "FY", "accn": "0001065088-26-000027", "filed": "2026-02-19"}
    facts = {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [item]}}}}
    return adapt_sec_companyfacts({"facts": facts}, entity_id=EBAY, fiscal_year_end="2025-12-31")


class RetailIndustryNoteTests(unittest.TestCase):
    def test_bgf_ccc_uses_only_net_trade_rows_and_current_prior_inventory(self):
        result = build(bgf())
        c = result["cards"]
        profile = result["industry_note_metrics"]
        self.assertEqual(result["industry"], "retail_wholesale")
        self.assertEqual(profile["mapping_id"], "bgf-retail-fy2025-trade-balances")
        self.assertAlmostEqual(c["receivables_to_sales"]["value"], 26_652_000_000 / REVENUE)
        self.assertAlmostEqual(c["dso_days"]["value"], (26_652_000_000 + 26_647_000_000) / 2 / REVENUE * 365)
        self.assertAlmostEqual(c["dio_days"]["value"], (INVENTORY + PRIOR_INVENTORY) / 2 / COGS * 365)
        self.assertAlmostEqual(c["dpo_days"]["value"], (544_989_000_000 + 536_408_000_000) / 2 / COGS * 365)
        self.assertAlmostEqual(c["ccc_days"]["value"], -15.09947048)
        self.assertEqual(c["inventory_less_trade_payables"]["value"], INVENTORY - 544_989_000_000)
        self.assertEqual(c["ccc_days_on_purchases"]["reason"], "missing:reviewed_merchandise_purchases")
        r = rows(profile)
        self.assertEqual(r["retail_inventory_purchases_reported"]["value"], 7_238_279_000_000)
        self.assertEqual(r["retail_franchise_settlement_payables"]["value"], 76_075_000_000)
        self.assertEqual(r["retail_supplier_finance"]["value"], 2_872_000_000)
        receivables = next(i for i in c["dso_days"]["inputs"] if i["input"] == "receivables" and not i["opening"])
        self.assertEqual(receivables["quality"], "deterministic_derived")
        self.assertEqual(receivables["provenance"]["source_allowance"], 53)
        self.assertEqual(receivables["provenance"]["source_scale"], 1_000_000)
        self.assertIn("eleId=37", receivables["provenance"]["url"])

    def test_bgf_rows_are_not_copied_across_scope_period_or_cutoff(self):
        data = bgf()
        b = {**bundle(), "entity_id": BGF}
        before = build_industry_note_profile(b, "retail_wholesale", "annual", publication_cutoff="2026-03-17")
        self.assertEqual(before["reason"], "unavailable:filing_after_publication_cutoff")
        self.assertNotIn("retail_trade_balances", before)
        on_filing = build_industry_note_profile(b, "retail_wholesale", "annual", publication_cutoff="2026-03-18")
        self.assertIn("retail_trade_balances", on_filing)
        self.assertNotIn("retail_trade_balances", build(data, "Q4")["industry_note_metrics"])
        self.assertEqual(build({**data, "history": []})["cards"]["ccc_days"]["reason"], "missing:opening_inventory")
        ofs = {**bundle(scope="OFS"), "entity_id": BGF}
        self.assertNotIn("retail_trade_balances", build_pe_cr(ofs)["industry_note_metrics"])

    def test_bgf_keeps_verified_api_or_explicit_values_and_rejects_conflicts(self):
        b = {**bundle(values={"revenue": REVENUE, "cogs": -COGS, "payables": 500_000_000_000}), "entity_id": BGF}
        c = build_pe_cr(b)["cards"]
        self.assertAlmostEqual(c["dpo_days"]["value"], (500_000_000_000 + 536_408_000_000) / 2 / COGS * 365)
        f = b["series"]["PECR_payables"]["annual"]
        f.update(value=None, availability="unavailable", reason="conflict:duplicate_reported_values")
        self.assertEqual(build_pe_cr(b)["cards"]["dpo_days"]["reason"], "conflict:duplicate_reported_values")
        data = bgf()
        override = reviewed({**bundle(), "entity_id": BGF}, {"receivables": 29_000_000_000})
        c = build({**data, "reviewed_disclosures": override})["cards"]
        self.assertEqual(c["dso_days"]["reason"], "missing:opening_receivables")
        self.assertAlmostEqual(c["receivables_to_sales"]["value"], 29_000_000_000 / REVENUE)
        self.assertIsNotNone(c["dpo_days"]["value"])

    def test_ebay_gmv_and_reported_monetization_are_not_canonical_revenue_or_ccc(self):
        b = ebay()
        result = analyze_canonical_facts(b, corp={"sic": "7389"})["pe_cr"]
        self.assertEqual(result["industry"], "retail_platform")
        self.assertEqual(result["industry_profile"]["selection_basis"], "reviewed_issuer_industry")
        self.assertEqual(b["series"]["PECR_revenue"]["annual"]["value"], 11_100_000_000)
        r = rows(result["industry_note_metrics"])
        self.assertEqual(r["platform_gmv"]["value"], 79_609_000_000)
        self.assertEqual(r["platform_gmv"]["unit"], "USD")
        self.assertEqual(r["platform_take_rate_reported"]["value"], .1394)
        self.assertEqual(r["platform_take_rate_reported"]["evidence"]["reported_net_revenue_control"]["source_amount"], 11100)
        self.assertEqual(result["cards"]["ccc_days"]["reason"], "not_applicable:industry_ccc")
        self.assertIsNone(result["cards"]["receivables_to_sales"]["value"])
        q = build_pe_cr(b, selected_period="Q4")
        self.assertEqual(q["industry_profile"]["ccc_policy"], "not_applicable")
        self.assertIsNone(rows(q["industry_note_metrics"])["platform_gmv"]["value"])
        newer = adapt_sec_companyfacts({"facts": {}}, entity_id=EBAY, fiscal_year_end="2026-12-31")
        self.assertEqual(build_pe_cr(newer)["industry"], "retail_platform")

    def test_scope_and_arithmetic_mutations_fail_validation(self):
        cfg, packets = _catalog()
        p = deepcopy(next(p for p in packets if p["entity_id"] == EBAY))
        p["rows"][1]["amount"] = "12.00"
        with patch("dart_kfa.industry_note_mapping._catalog", return_value=(cfg, [p])):
            with self.assertRaisesRegex(ValueError, "platform_take_rate"):
                build_industry_note_profile(ebay(), "retail_platform", "annual")
        p = deepcopy(next(p for p in packets if p["entity_id"] == BGF))
        with patch("dart_kfa.industry_note_mapping._catalog", return_value=(cfg, [p])):
            p["retail_trade_balances"][0]["url"] = p["retail_trade_balances"][0]["url"].replace("20260318000829", "20260318000828")
            with self.assertRaisesRegex(ValueError, "reviewed_dart_periodic_filing"):
                build(bgf())
            del p["retail_trade_balances"][0]
            with self.assertRaisesRegex(ValueError, "trade_balance_pair"):
                build(bgf())


if __name__ == "__main__":
    unittest.main()
