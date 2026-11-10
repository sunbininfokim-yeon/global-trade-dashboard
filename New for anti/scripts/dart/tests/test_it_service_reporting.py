"""Audited filing values wrapped in offline OpenDART-response-shaped records."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from build_pe_cr import build, prepare_filings
from dart_kfa.canonical_facts import adapt_dart_filings, default_dart_account_specs
from dart_kfa.industry_note_mapping import build_industry_note_profile
from dart_kfa.it_service_reporting import _registry
from test_pe_cr_evidence import saved_report


GABIA = "00506294"
FY_REVENUE, FY_OP = 335_681_176_239, 40_485_754_868
Q1_REVENUE, Q1_OP = 84_969_270_674, 10_726_015_555
H1_REVENUE, H1_OP = 173_730_368_633, 23_203_307_141
Q2_REVENUE, Q2_OP = 88_761_097_959, 12_477_291_586


def report(year, code, revenue, op, receipt, ytd=None, *, scope="CFS"):
    rec = saved_report({"revenue": revenue, "op": op}, code=code, corp=GABIA)
    rec["request"].update(bsns_year=str(year), fs_div=scope)
    for row, ytd_value in zip(rec["response"]["list"], ytd or (None, None)):
        row.update(bsns_year=str(year), rcept_no=receipt)
        if ytd_value is not None:
            row["thstrm_add_amount"] = str(ytd_value)
    return rec


def gabia(*, annual=False, scope="CFS"):
    if annual:
        filings = {"FY": report(2025, "11011", FY_REVENUE, FY_OP, "20260318001522", scope=scope)}
    else:
        filings = {"Q1": report(2026, "11013", Q1_REVENUE, Q1_OP, "20260515001940", scope=scope),
                   "H1": report(2026, "11012", Q2_REVENUE, Q2_OP, "20260814002908", (H1_REVENUE, H1_OP), scope=scope)}
    return {"entity_id": GABIA, "fiscal_year_end": "2025-12-31" if annual else "2026-12-31",
            "filings": filings, "fs_div": scope}


def canonical(payload):
    return adapt_dart_filings(prepare_filings(payload), account_specs=default_dart_account_specs(),
                              entity_id=payload["entity_id"], fiscal_year_end=payload["fiscal_year_end"], fs_div=payload["fs_div"])


def get_rows(profile, table):
    return {row["id"]: row for row in profile[table]["rows"]}


class ITServiceReportingTests(unittest.TestCase):
    def test_gabia_fy_2025_separates_segment_profit_and_product_revenue(self):
        result = build(gabia(annual=True))
        profile = result["industry_note_metrics"]
        it = profile["it_service_reporting"]
        self.assertEqual(result["industry"], "it_services")
        self.assertEqual(profile["mapping_id"], "gabia-2025-12-31")
        self.assertEqual(it["status"], "reported")
        self.assertEqual(it["segment_profitability"]["evidence"][0]["source_window"], "annual")
        segments, products = get_rows(it, "segment_profitability"), get_rows(it, "product_mix")
        self.assertEqual(segments["total"]["revenue"], FY_REVENUE)
        self.assertEqual(segments["total"]["operating_income"], FY_OP)
        self.assertEqual(segments["kinx"]["operating_income"], 20_234_737_560)
        self.assertAlmostEqual(segments["kinx"]["operating_margin"], 20_234_737_560 / 105_556_074_125)
        self.assertEqual(segments["other"]["operating_income"], -1_149_102_864)
        self.assertEqual(segments["eliminations"]["revenue"], -12_304_414_785)
        self.assertIsNone(segments["eliminations"]["operating_margin"])
        self.assertEqual(segments["kinx"]["included_in"], "total")
        self.assertEqual(products["cloud_it"]["revenue"], 181_345_052_937)
        self.assertNotIn("operating_income", products["cloud_it"])
        self.assertAlmostEqual(sum(r["share_of_consolidated_revenue"] for k, r in products.items() if k != "total"), 1.0)
        self.assertEqual(json.loads(json.dumps(profile, allow_nan=False)), profile)

    def test_gabia_q1_as_reported_q2_h1_minus_q1_by_identity_not_column_position(self):
        data = gabia()
        first = build(data, "Q1")["industry_note_metrics"]["it_service_reporting"]
        self.assertEqual(first["status"], "reported")
        self.assertEqual(get_rows(first, "segment_profitability")["total"]["revenue"], Q1_REVENUE)
        second = build(data, "Q2")["industry_note_metrics"]["it_service_reporting"]
        self.assertEqual(second["status"], "deterministic_derived")
        self.assertEqual((second["period_start"], second["period_end"]), ("2026-04-01", "2026-06-30"))
        evidence = second["segment_profitability"]["evidence"]
        self.assertEqual([e["source_window"] for e in evidence], ["half_year_ytd", "first_quarter"])
        self.assertEqual([e["filing_id"] for e in evidence], ["20260814002908", "20260515001940"])
        segments, products = get_rows(second, "segment_profitability"), get_rows(second, "product_mix")
        self.assertEqual(segments["total"]["revenue"], Q2_REVENUE)
        self.assertEqual(segments["total"]["operating_income"], Q2_OP)
        self.assertEqual(segments["kinx"]["operating_income"], 7_968_814_912)
        self.assertEqual(segments["gabia_cns"]["operating_income"], 92_605_627)
        self.assertEqual(segments["other"]["source_locations"], ["기타부문", "기타"])
        self.assertEqual(products["ix_idc"]["revenue"], 27_847_098_914)
        self.assertEqual(products["total"]["revenue"], Q2_REVENUE)

    def test_no_open_long_term_orders_is_not_a_reported_zero_or_arr(self):
        profile = build(gabia(), "Q2")["industry_note_metrics"]
        orders = profile["it_service_reporting"]["long_term_orders"]
        self.assertIsNone(orders["value"])
        self.assertEqual(orders["status"], "not_applicable")
        self.assertEqual(orders["scope"], "open_long_term_sales_and_service_orders_only")
        self.assertEqual(orders["as_of"], "2026-06-30")
        self.assertIn("eleId=13", orders["evidence"]["url"])
        rows = {r["id"]: r for r in profile["rows"]}
        self.assertEqual(rows["firm_order_backlog"]["reason"], orders["reason"])
        self.assertIsNone(rows["arr"]["value"])

    def test_missing_or_conflicting_context_keeps_tables_unavailable(self):
        data = gabia()
        for variant, period in ((gabia(scope="OFS"), "Q2"), (data, "Q4"), (data, "annual")):
            it = build(variant, period)["industry_note_metrics"]["it_service_reporting"]
            self.assertIsNone(it["segment_profitability"])
        b = canonical(data)
        for edits in ({"entity_id": "99999999"}, {"source": "SEC"}):
            result = build_industry_note_profile({**b, **edits}, "it_services", "Q2")
            self.assertNotIn("it_service_reporting", result)
        before = build_industry_note_profile(b, "it_services", "Q2", publication_cutoff="2026-08-13")
        self.assertEqual(before["it_service_reporting"]["reason"], "unavailable:filing_after_publication_cutoff")
        b["series"]["PECR_op"]["quarters"]["Q2"]["value"] += 1
        conflict = build_industry_note_profile(b, "it_services", "Q2")["it_service_reporting"]
        self.assertEqual(conflict["reason"], "conflict_or_missing:canonical_it_service_revenue_or_operating_income")
        self.assertIsNone(conflict["product_mix"])

    def test_derived_controls_are_supported_but_different_receipts_are_not(self):
        data = gabia()
        for row in data["filings"]["H1"]["response"]["list"]:
            del row["thstrm_amount"]
        b = canonical(data)
        self.assertEqual(b["series"]["PECR_revenue"]["quarters"]["Q2"]["quality"], "deterministic_derived")
        self.assertEqual(build(data, "Q2")["industry_note_metrics"]["it_service_reporting"]["status"], "deterministic_derived")
        # A different filing can restate segment composition with no change in totals.
        for variant in (data, gabia()):
            for row in variant["filings"]["Q1"]["response"]["list"]:
                row["rcept_no"] = "20260814002909"
            it = build(variant, "Q2")["industry_note_metrics"]["it_service_reporting"]
            self.assertEqual(it["reason"], "conflict_or_missing:canonical_it_service_revenue_or_operating_income")
            self.assertIsNone(it["segment_profitability"])

    def test_quarter_requires_reviewed_q1_and_consistent_reporting_basis(self):
        data = gabia()
        original = deepcopy(_registry())
        q1, h1 = original[1:]
        with patch("dart_kfa.it_service_reporting._registry", return_value=[h1]):
            result = build(data, "Q2")["industry_note_metrics"]["it_service_reporting"]
            self.assertEqual(result["reason"], "missing:reviewed_q1_for_h1_difference")
        q1["reporting_basis_id"] = "different_partition"
        with patch("dart_kfa.it_service_reporting._registry", return_value=original):
            with self.assertRaisesRegex(ValueError, "quarter_reporting_basis"):
                build(data, "Q2")
        q1["reporting_basis_id"] = h1["reporting_basis_id"]
        h1["segments"]["rows"][0]["revenue"] += 1
        with patch("dart_kfa.it_service_reporting._registry", return_value=original):
            with self.assertRaisesRegex(ValueError, "segments_reconciliation"):
                build(data, "Q2")


if __name__ == "__main__":
    unittest.main()
