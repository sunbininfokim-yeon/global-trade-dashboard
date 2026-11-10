"""Source-qualified cash-flow totals: raw API-shaped fixtures and one 10-K check."""

import unittest

from build_pe_cr import build
from dart_kfa.canonical_analysis import analyze_canonical_facts
from dart_kfa.pe_cr import build_pe_cr
from test_pe_cr import bundle
from test_pe_cr_evidence import payload, saved_report


TOTALS = ("cfo", "cfi", "cff", "cash_flow_net_activities", "cash_flow_fx_effect")
TAGS = {
    "cfo": "NetCashProvidedByUsedInOperatingActivities",
    "cfi": "NetCashProvidedByUsedInInvestingActivities",
    "cff": "NetCashProvidedByUsedInFinancingActivities",
    "fx": "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "capex": "PaymentsToAcquirePropertyPlantAndEquipment",
}


def amounts(result):
    return tuple(result["cards"][key]["value"] for key in TOTALS)


class CashFlowActivityTests(unittest.TestCase):
    def test_dart_discrete_quarters_use_prior_ytd_not_annualized_figures(self):
        def report(code, op, inv, fin, fx):
            return saved_report(dict(cfo=op, cfi=inv, cff=fin, cash_fx=fx), code=code)
        fy = report("11011", 180, -90, -10, -2)
        p = payload(fy)
        p["filings"].update(Q1=report("11013", 50, -25, 30, 1),
                            H1=report("11012", 85, -30, 15, 2),
                            Q3=report("11014", 110, -65, 15, -2))
        expected = {"Q1": (50, -25, 30, 55, 1), "Q2": (35, -5, -15, 15, 1),
                    "Q3": (25, -35, 0, -10, -4), "Q4": (70, -25, -25, 20, 0),
                    "annual": (180, -90, -10, 80, -2)}
        for period, want in expected.items():
            with self.subTest(period=period):
                result = build(p, period)
                self.assertEqual(amounts(result), want)
                self.assertEqual(result["cards"]["cfi"]["currency"], "KRW")
                self.assertEqual(len(result["cards"]["cash_flow_net_activities"]["inputs"]), 3)
        result = build(p, "Q2")
        self.assertEqual(result["cards"]["cfi"]["inputs"][0]["provenance"]["source_reports"], ["Q1", "H1"])
        del p["filings"]["H1"]
        self.assertEqual(amounts(build(p, "Q3")), (None, None, None, None, None))
        self.assertEqual(amounts(build(p, "annual")), expected["annual"])

    def test_dart_missing_is_not_zero_wrong_statement_ignored(self):
        report = saved_report(dict(cfo=80, cfi=-60, cff=0))
        rows = report["response"]["list"]
        rows[1]["sj_div"] = "BS"
        rows.append({**rows[1], "sj_div": "CF", "account_id": "issuer_untested", "account_nm": "투자활동현금흐름"})
        r = build(payload(report))
        self.assertEqual(amounts(r), (80, None, 0, None, None))
        self.assertEqual(r["cards"]["cash_flow_net_activities"]["reason"], "requires:cash_flow_activity_totals:cfi")

    def test_cash_flow_keeps_financial_source_data_but_not_fcf(self):
        data = bundle(values=dict(cfo=-100, cfi=40, cff=100, cash_fx=9, cash_interest_operating=-6,
                                  cash_interest_financing=-4, capex_ppe=-1, capex_intangible=-2))
        result = analyze_canonical_facts(data, corp={"induty_code": "64201"})["pe_cr"]
        self.assertEqual(amounts(result), (-100, 40, 100, 40, 9))
        self.assertIsNone(result["cards"]["fcf"]["value"])
        cash = result["cash_flow_statement"]
        self.assertFalse(cash["details_are_exhaustive"])
        self.assertEqual([a["card_id"] for a in cash["activities"]], ["cfo", "cfi", "cff"])
        self.assertEqual(cash["activities"][2]["details"][0]["card_id"], "cash_flow_cash_interest_financing")
        self.assertEqual(result["cards"]["cash_flow_cash_interest_financing"]["value"], -4)
        screen = result["cr_pe_screen"]
        self.assertEqual(screen["references"]["cash_flow"], "cash_flow_statement")
        self.assertTrue(set(TOTALS) <= set(next(s for s in screen["sections"] if s["id"] == "cash_flow")["card_ids"]))

    def test_currency_scope_and_period_mismatch_block_total(self):
        for patch in ({"fs_div": "OFS"}, {"unit": {"kind": "currency", "currency": "USD", "scale": 1}},
                      {"period_kind": "flow_discrete_quarter"}, {"source": "SEC"}, {"statement": "BS"}):
            with self.subTest(patch=patch):
                data = bundle(values=dict(cfo=10, cfi=-3, cff=-2))
                data["series"]["PECR_cff"]["annual"].update(patch)
                self.assertEqual(amounts(build_pe_cr(data)), (10, -3, None, None, None))

    def test_sec_companyfacts_q2_excludes_ytd_and_currency_mismatch(self):
        def entry(end, fp, val):
            return dict(start="2025-01-01", end=end, form="10-Q", fp=fp, val=val, accn="synthetic")
        gaap = {tag: {"units": {"USD": [entry("2025-03-31", "Q1", q1), entry("2025-06-30", "Q2", h1)]}}
                for k, q1, h1 in [("cfo", 25, 65), ("cfi", -10, -35), ("cff", 15, 30), ("fx", 3, 1)]
                for tag in [TAGS[k]]}
        gaap[TAGS["cff"]]["units"]["KRW"] = [entry("2025-06-30", "Q2", 10**10)]
        p = dict(source="SEC", entity_id="0000000001", fiscal_year_end="2025-12-31",
                 companyfacts={"cik": 1, "facts": {"us-gaap": gaap}})
        self.assertEqual(amounts(build(p, "Q2")), (40, -25, 15, 30, -2))
        gaap[TAGS["cff"]]["units"]["USD"][1]["accn"] = "different-vintage"
        result = build(p, "Q2")
        self.assertEqual(amounts(result), (40, -25, 15, None, -2))
        self.assertEqual(result["cards"]["cash_flow_net_activities"]["reason"], "conflict:cash_flow_filing_versions")
        del gaap[TAGS["cff"]]["units"]["USD"]
        gaap[TAGS["cff"] + "ContinuingOperations"] = {"units": {"USD": [entry("2025-06-30", "Q2", 40)]}}
        self.assertEqual(amounts(build(p, "Q2")), (40, -25, None, None, -2))

    def test_apple_fy2025_consolidated_cash_flow_report_amounts(self):
        # Transcribed from the consolidated cash-flow statement, not a live API test:
        # https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm
        start, end, m = "2024-09-29", "2025-09-27", 1_000_000
        gaap = {TAGS[k]: {"units": {"USD": [dict(start=start, end=end, form="10-K", fp="FY", val=v*m,
                                                  accn="0000320193-25-000079")]}}
                for k, v in (("cfo", 111482), ("cfi", 15195), ("cff", -120686), ("capex", 12715))}
        p = dict(source="SEC", entity_id="0000320193", fiscal_year_end=end, report_periods={"FY": {"start": start, "end": end}},
                 companyfacts={"cik": 320193, "facts": {"us-gaap": gaap}})
        r = build(p)
        self.assertEqual(amounts(r), (111482*m, 15195*m, -120686*m, 5991*m, None))
        self.assertEqual(r["cards"]["cfi"]["currency"], "USD")
        self.assertEqual(r["cards"]["cash_flow_capex_ppe"]["value"], 12715*m)
        self.assertIsNone(r["cards"]["fcf"]["value"])
