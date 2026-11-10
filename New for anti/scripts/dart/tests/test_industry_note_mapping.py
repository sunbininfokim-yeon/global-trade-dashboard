"""Public filing values are transcribed; raw API shape and rejection cases are offline."""
import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from build_pe_cr import build
from dart_kfa.canonical_analysis import analyze_canonical_facts
from dart_kfa.canonical_facts import adapt_sec_companyfacts
from dart_kfa.industry_note_mapping import _catalog, build_industry_note_profile
from test_pe_cr import bundle
from test_pe_cr_evidence import payload, saved_report


def rows(profile):
    return {r["id"]: r for r in profile["rows"]}


def micron():
    start, end = "2024-08-30", "2025-08-28"
    return adapt_sec_companyfacts(
        {"facts": {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            {"start": start, "end": end, "val": 37_378_000_000, "form": "10-K", "fp": "FY",
             "accn": "0000723125-25-000028", "filed": "2025-10-03"}
        ]}}}}}, entity_id="0000723125", fiscal_year_end=end, report_periods={"FY": {"start": start, "end": end}},
    )


class IndustryNoteMappingTests(unittest.TestCase):
    def test_micron_same_52_week_scope_in_integrated_pe_cr_output(self):
        profile = analyze_canonical_facts(micron())["pe_cr"]["industry_note_metrics"]
        r = rows(profile)
        self.assertEqual(profile["mapping_id"], "micron-fy2025-product-revenue")
        self.assertEqual(r["dram_revenue"]["value"], 28_578_000_000)
        self.assertEqual(r["nand_revenue"]["unit"], "USD")
        self.assertAlmostEqual(r["nand_revenue"]["share_of_consolidated_revenue"], 8503 / 37378)
        self.assertIsNone(r["hbm_revenue"]["value"])
        self.assertIsNone(r["capacity_utilization"]["value"])
        self.assertEqual(json.loads(json.dumps(profile, allow_nan=False)), profile)

    def test_hynix_krw_cfs_dart_facts_plus_explicit_sec_filing_evidence(self):
        raw = saved_report({"revenue": 97_146_675_000_000}, corp="00164779")
        p = {**payload(raw), "entity_id": "00164779", "corp": {"induty_code": "26110"}}
        profile = build(p)["industry_note_metrics"]
        r = rows(profile)
        self.assertEqual(profile["mapping_id"], "sk-hynix-fy2025-product-revenue")
        self.assertEqual(r["nand_revenue"]["value"], 20_690_084_000_000)
        self.assertEqual(r["dram_revenue"]["evidence"]["provider"], "SEC")
        self.assertEqual(r["dram_revenue"]["unit"], "KRW")
        self.assertIsNone(rows(build(p, "Q4")["industry_note_metrics"])["nand_revenue"]["value"])
        raw["response"]["list"][0]["thstrm_amount"] = "0"
        self.assertEqual(build(p)["industry_note_metrics"]["reason"], "conflict_or_missing:canonical_consolidated_revenue_control")

    def test_unknown_identity_period_scope_currency_or_source_never_borrows_rows(self):
        b = micron()
        for edits in ({"entity_id": "0000320193"}, {"fs_div": "OFS"}, {"currency": "KRW"}, {"source": "DART"},
                      {"fiscal_year_start": "2024-09-01"}):
            with self.subTest(edits=edits):
                profile = build_industry_note_profile({**b, **edits}, "semiconductor", "annual")
                self.assertTrue(all(r["value"] is None for r in profile["rows"]))
        before = build_industry_note_profile(b, "semiconductor", "annual", publication_cutoff="2025-10-02")
        self.assertEqual(before["reason"], "unavailable:filing_after_publication_cutoff")
        on_filing = build_industry_note_profile(b, "semiconductor", "annual", publication_cutoff="2025-10-03")
        self.assertEqual(on_filing["mapping_id"], "micron-fy2025-product-revenue")
        financial = build_industry_note_profile(b, "financial", "annual")
        self.assertEqual(financial["rows"], [])

    def test_costco_keeps_comparable_sales_and_adjusted_variant_separate(self):
        start, end = "2024-09-02", "2025-08-31"
        b = adapt_sec_companyfacts({"facts": {}}, entity_id="0000909832", fiscal_year_end=end,
                                   report_periods={"FY": {"start": start, "end": end}})
        profile = analyze_canonical_facts(b)["pe_cr"]["industry_note_metrics"]
        r = rows(profile)
        self.assertEqual(profile["industry"], "retail_wholesale")
        self.assertEqual(r["same_store_sales_growth"]["value"], .06)
        self.assertEqual(r["same_store_sales_growth_ex_fx_fuel"]["value"], .08)
        self.assertNotEqual(r["same_store_sales_growth"]["basis"], r["same_store_sales_growth_ex_fx_fuel"]["basis"])
        self.assertNotIn("platform_gmv", r)

    def test_hii_backlog_has_one_total_two_children_and_one_scope(self):
        b = adapt_sec_companyfacts({"facts": {}}, entity_id="0001501585", fiscal_year_end="2025-12-31")
        r = rows(build_industry_note_profile(b, "general", "annual"))
        self.assertEqual(r["firm_order_backlog"]["value"], 53_139_000_000)
        self.assertEqual(r["funded_order_backlog"]["value"], 31_985_000_000)
        self.assertEqual(r["unfunded_order_backlog"]["value"], 21_154_000_000)
        self.assertEqual(r["unfunded_order_backlog"]["included_in"], "firm_order_backlog")
        self.assertIsNone(r["firm_order_backlog"]["period_start"])
        self.assertIsNone(r["vessels_on_orderbook"]["value"])
        cfg, packets = _catalog()
        p = deepcopy(next(p for p in packets if p["entity_id"] == b["entity_id"]))
        p["rows"][1]["scope"] = "shipbuilding_only"
        with patch("dart_kfa.industry_note_mapping._catalog", return_value=(cfg, [p])):
            with self.assertRaisesRegex(ValueError, "backlog_partition"):
                build_industry_note_profile(b, "shipbuilding", "annual")

    def test_partition_and_hbm_child_are_not_added_twice(self):
        cfg, packets = _catalog()
        p = deepcopy(packets[0])
        p["rows"].append({**p["rows"][0], "metric": "hbm_revenue", "basis": "explicit_hbm_subset_of_dram",
                          "amount": 1000, "row": "synthetic HBM test row"})
        with patch("dart_kfa.industry_note_mapping._catalog", return_value=(cfg, [p])):
            r = rows(build_industry_note_profile(micron(), "semiconductor", "annual"))
            self.assertEqual(r["hbm_revenue"]["included_in"], "dram_revenue")
            self.assertAlmostEqual(sum(r[k]["share_of_consolidated_revenue"] for k in
                                       ("dram_revenue", "nand_revenue", "other_product_revenue")), 1)
            p["rows"][0]["amount"] -= 1
            with self.assertRaisesRegex(ValueError, "product_partition"):
                build_industry_note_profile(micron(), "semiconductor", "annual")

    def test_other_kit_rules_do_not_confuse_backlog_count_flow_and_unit(self):
        cfg, _ = _catalog()
        b = {**bundle(), "entity_id": "00000001"}
        p = {"id": "synthetic-test", "entity_id": b["entity_id"], "financial_provider": "DART", "industry": "shipbuilding",
             "period": "annual", "period_start": "2025-01-01", "period_end": "2025-12-31", "fs_div": "CFS", "currency": "KRW",
             "source": {"provider": "DART", "entity_id": b["entity_id"], "filing_id": "20260301000000", "filed": "2026-03-01",
                        "form": "11011", "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260301000000"},
             "rows": [{"metric": key, "scope": "shipbuilding_business", "basis": cfg["metrics"][key][3],
                       "amount": a, "scale": s, "unit": u, "table": "synthetic table", "row": key}
                      for key, a, s, u in (("firm_order_backlog", 250, 1_000_000, "KRW"),
                                          ("vessels_on_orderbook", 8, 1, "vessels"),
                                          ("firm_new_orders", 110, 1_000_000, "KRW"),
                                          ("capacity_utilization", "91.2", 1, "percent"))]}
        with patch("dart_kfa.industry_note_mapping._catalog", return_value=(cfg, [p])):
            r = rows(build_industry_note_profile(b, "shipbuilding", "annual"))
            self.assertEqual(r["firm_order_backlog"]["value"], 250_000_000)
            self.assertIsNone(r["firm_order_backlog"]["period_start"])
            self.assertEqual(r["firm_new_orders"]["period_start"], "2025-01-01")
            self.assertEqual(r["vessels_on_orderbook"]["unit"], "vessels")
            self.assertEqual(r["capacity_utilization"]["value"], .912)
            p["rows"][0]["unit"] = "USD"
            with self.assertRaisesRegex(ValueError, "metric_basis"):
                build_industry_note_profile(b, "shipbuilding", "annual")
        for kit, metric in (("retail_wholesale", "same_store_sales_growth"), ("retail_platform", "platform_gmv"),
                            ("it_services", "arr"), ("shipping", "fleet_capacity_teu"), ("machinery", "firm_order_backlog")):
            self.assertEqual(rows(build_industry_note_profile(b, kit, "annual"))[metric]["reason"],
                             "missing:reviewed_issuer_period_mapping")


if __name__ == "__main__":
    unittest.main()
