import json
import unittest
from copy import deepcopy
from pathlib import Path

from test_pe_cr import VALUES, bundle
from build_pe_cr import build
from dart_kfa.pe_cr import build_pe_cr, account_specs
from dart_kfa.pe_cr_evidence import BASES, BALANCES


def reviewed(bundle, values):
    pack = {k: bundle[k] for k in ("source", "entity_id", "currency", "fs_div", "fiscal_year_end")}
    return {**pack, "schema_version": "kfa-pe-cr-reviewed/1", "rows": [
        {"key": k, "basis": BASES[k], "amount": v, "scale": 1,
         "period_start": None if k in BALANCES else "2025-01-01", "period_end": "2025-12-31",
         "evidence": {"url": "https://example.com/synthetic", "document": "synthetic", "table": "test", "row": k}}
        for k, v in values.items()]}


def saved_report(values, *, code="11011", corp="00126380", scale=1):
    request = dict(corp_code=corp, bsns_year="2025", reprt_code=code, fs_div="CFS")
    return {"request": request, "response": {"status": "000", "list": [
        dict(corp_code=corp, bsns_year="2025", reprt_code=code, currency="KRW", rcept_no="synthetic",
             sj_div=spec["statement"], account_id=spec["source_ids"][0], thstrm_amount=str(value*scale))
        for k, value in values.items() for spec in [account_specs()["PECR_" + k]]
    ]}}


def payload(report):
    return dict(entity_id="00126380", fiscal_year_end="2025-12-31", fs_div="CFS", filings={"FY": report})


class ReviewedEvidenceTests(unittest.TestCase):
    def test_conditional_debt_metrics_and_negative_cfads(self):
        b = bundle()
        pack = reviewed(b, dict(PPE_DEPRECIATION=10, INTANGIBLE_AMORTIZATION=5, financing_debt=200,
                                unrestricted_cash=60, principal_due_1y=100, cfads=-45,
                                principal_paid=30, interest_paid=15, maintenance_capex=11))
        cards = build_pe_cr(b, reviewed_disclosures=pack)["cards"]
        self.assertEqual(cards["ebitda"]["value"], 115)
        self.assertEqual(cards["net_debt_to_ebitda"]["value"], 140/115)
        self.assertEqual(cards["debt_due_within_1y"]["value"], 100)
        self.assertEqual(cards["liquidity_coverage_1y"]["value"], .6)
        self.assertEqual(cards["dscr"]["value"], -1)
        self.assertEqual(cards["maintenance_capex"]["value"], 11)
        self.assertNotIn("PPE_DEPRECIATION", b["series"])

    def test_do_not_use_total_cash_for_restricted_cash_or_ccc(self):
        b = bundle()
        cards = build_pe_cr(b, reviewed_disclosures=reviewed(b, {"principal_due_1y": 50}))["cards"]
        self.assertEqual(cards["debt_due_within_1y"]["value"], 50)
        self.assertEqual(cards["liquidity_coverage_1y"]["reason"], "missing:reviewed_unrestricted_cash")
        self.assertIsNone(cards["ccc_days"]["value"])

    def test_scope_version_duplicate_and_gross_amount_rejected(self):
        b = bundle()
        pack = reviewed(b, {"principal_due_1y": 50})
        for k, value in (("entity_id", "other"), ("fs_div", "OFS"), ("currency", "USD"), ("fiscal_year_end", "2024-12-31")):
            with self.assertRaisesRegex(ValueError, "incompatible:reviewed_" + k):
                build_pe_cr(b, reviewed_disclosures={**pack, k: value})
        with self.assertRaisesRegex(ValueError, "conflict:duplicate_reviewed_fact"):
            build_pe_cr(b, reviewed_disclosures={**pack, "rows": pack["rows"] * 2})
        pack["rows"][0]["basis"] = "undiscounted_financial_liabilities"
        with self.assertRaisesRegex(ValueError, "invalid:reviewed_basis"):
            build_pe_cr(b, reviewed_disclosures=pack)

    def test_reported_interest_wins_and_conflict_does_not_fallback(self):
        b = bundle()
        pack = reviewed(b, {"interest": 25})
        self.assertEqual(build_pe_cr(b, reviewed_disclosures=pack)["cards"]["interest_coverage"]["value"], 5)
        f = b["series"]["PECR_interest"]["annual"]
        f.update(value=None, reason="conflict:duplicate_source_concept", availability="unavailable")
        self.assertIsNone(build_pe_cr(b, reviewed_disclosures=pack)["cards"]["interest_coverage"]["value"])
        f["reason"] = "missing:dart_fact_FY"
        self.assertEqual(build_pe_cr(b, reviewed_disclosures=pack)["cards"]["interest_coverage"]["value"], 4)

    def test_fy_disclosure_never_fills_q4(self):
        b = bundle()
        for s in b["series"].values():
            s["quarters"]["Q4"] = {**s["annual"], "period_start": "2025-10-01", "period_kind": "flow_discrete_quarter"}
        pack = reviewed(b, dict(PPE_DEPRECIATION=10, INTANGIBLE_AMORTIZATION=5, maintenance_capex=50))
        cards = build_pe_cr(b, selected_period="Q4", reviewed_disclosures=pack)["cards"]
        self.assertIsNone(cards["ebitda"]["value"])
        self.assertIsNone(cards["maintenance_capex"]["value"])
        self.assertIn("annual", cards["net_debt_to_ebitda"]["reason"])

    def test_official_request_scope_and_identity(self):
        raw = saved_report(VALUES)
        cards = build(payload(raw))["cards"]
        self.assertEqual(cards["fcf"]["value"], 100)
        self.assertEqual(cards["fcf"]["inputs"][0]["provenance"]["scope_source"], "opendart_request")
        self.assertNotIn("fs_div", raw["response"]["list"][0])
        for field, value in (("fs_div", "OFS"), ("corp_code", "another"), ("bsns_year", "2024"), ("reprt_code", "11012")):
            bad = deepcopy(raw)
            bad["response"]["list"][0][field] = value
            with self.assertRaisesRegex(ValueError, "incompatible:dart_response_identity"):
                build(payload(bad))

    def test_known_financial_identity_cannot_opt_into_industrial_metrics(self):
        b = {**bundle(), "entity_id": "00688996"}
        result = build_pe_cr(b, entity_policy={"is_financial_entity": False})
        self.assertEqual(result["visible_cards"], [])
        self.assertEqual(result["cards"]["fcf"]["reason"], "not_applicable:financial_entity")

    def test_h1_direct_income_not_confused_with_ytd_cash_flow(self):
        q1 = saved_report({"cfo": 20, "capex_ppe": 3, "capex_intangible": 1}, code="11013")
        h1 = saved_report({"op": 30, "interest": 6, "cfo": 60, "capex_ppe": 9, "capex_intangible": 3}, code="11012")
        data = {**payload(q1), "filings": {"Q1": q1, "H1": h1}}
        cards = build(data, period="Q2")["cards"]
        self.assertEqual(cards["interest_coverage"]["value"], 5)
        self.assertEqual(cards["fcf"]["value"], 32)

    def test_samsung_official_document_amounts_offline_not_live_api(self):
        # Main statement amounts are transcribed from the issuer's audited
        # report in KRW million, then wrapped as API-shaped test rows. This
        # does not claim the live API emits these exact concept IDs.
        raw = saved_report(dict(op=43601051, cfo=85315148, capex_ppe=-47522179, capex_intangible=-4630970,
                                revenue=333605938, cogs=202235513, receivables=51127642,
                                inventory=52636828, payables=13039380), scale=1000000)
        path = Path(__file__).resolve().parents[1] / "config/pe_cr_reviewed/samsung_00126380_2025_cfs.json"
        pack = json.loads(path.read_text())
        prior = bundle(2024, {"receivables": 43623073000000, "inventory": 51754865000000, "payables": 12370177000000})
        prior["entity_id"] = "00126380"
        data = {**payload(raw), "reviewed_disclosures": pack, "history": [prior]}
        cards = build(data)["cards"]
        self.assertEqual(cards["ebitda"]["value"], 90527643000000)
        self.assertAlmostEqual(cards["interest_coverage"]["value"], 43601051/605783)
        self.assertEqual(cards["fcf"]["value"], 33161999000000)
        self.assertAlmostEqual(cards["ccc_days"]["value"], 365/2 * (
            (51127642+43623073)/333605938 + (52636828+51754865-13039380-12370177)/202235513))
        self.assertIsNone(cards["debt_due_within_1y"]["value"])
        raw["response"]["list"][0]["thstrm_amount"] = "43600000000000"
        with self.assertRaisesRegex(ValueError, "incompatible:reviewed_annual_operating_income_control"):
            build(data)


if __name__ == "__main__":
    unittest.main()
