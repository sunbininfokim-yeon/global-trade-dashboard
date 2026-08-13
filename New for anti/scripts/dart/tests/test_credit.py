"""Free credit panel: interest coverage + SEC filing index (no CDS/ratings)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.credit import (
    build_credit_panel,
    classify_debt_filing,
    list_debt_filings,
    parse_offering_terms,
)
from dart_kfa.ma_metrics import compute_ma_metrics


class TestInterestCoverage(unittest.TestCase):
    def test_coverage_and_eir(self):
        amounts = {
            "OPERATING_INCOME": 100.0,
            "INTEREST_EXPENSE": 10.0,
            "LONG_TERM_DEBT_NONCURRENT": 200.0,
            "CASH": 50.0,
            "CFO": 80.0,
            "CAPEX": 20.0,
            "REVENUE": 500.0,
        }
        ma = compute_ma_metrics(amounts)
        self.assertAlmostEqual(ma["interest_coverage"]["value"], 10.0)
        self.assertAlmostEqual(ma["interest_burden"]["value"], 0.1)
        self.assertAlmostEqual(ma["effective_interest_rate_pct"]["value"], 5.0)

    def test_null_without_interest(self):
        ma = compute_ma_metrics({"OPERATING_INCOME": 100.0, "LONG_TERM_DEBT": 50.0})
        self.assertIsNone(ma["interest_coverage"]["value"])
        self.assertIn("interest", ma["interest_coverage"]["reason"])


class TestDebtFilingIndex(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify_debt_filing("424B2", ""), "prospectus_or_fwp")
        self.assertEqual(classify_debt_filing("FWP", None), "prospectus_or_fwp")
        self.assertEqual(classify_debt_filing("8-K", "2.02,2.03"), "eight_k_debt_item")
        self.assertEqual(classify_debt_filing("8-K", "2.02"), None)
        self.assertEqual(classify_debt_filing("S-3ASR", ""), "shelf_registration")

    def test_list_from_fixture(self):
        subs = {
            "cik": "789019",
            "filings": {
                "recent": {
                    "form": ["10-K", "424B2", "8-K", "8-K"],
                    "filingDate": ["2025-01-01", "2024-06-01", "2024-05-01", "2024-04-01"],
                    "accessionNumber": [
                        "0000789019-25-000001",
                        "0000789019-24-000010",
                        "0000789019-24-000009",
                        "0000789019-24-000008",
                    ],
                    "primaryDocument": [
                        "msft-10k.htm",
                        "d424b2.htm",
                        "d8k.htm",
                        "earnings.htm",
                    ],
                    "items": ["", "", "1.01,2.03", "2.02,9.01"],
                }
            },
        }
        rows = list_debt_filings(subs)
        kinds = {r["kind"] for r in rows}
        self.assertIn("prospectus_or_fwp", kinds)
        self.assertIn("eight_k_debt_item", kinds)
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["url"].startswith("https://www.sec.gov/Archives/edgar/data/"))


class TestParseTerms(unittest.TestCase):
    def test_coupon_and_principal(self):
        text = (
            "The Company is offering $1,500,000,000 aggregate principal amount of "
            "3.750% Notes due May 15, 2034. The notes will bear interest at 3.750%."
        )
        t = parse_offering_terms(text)
        self.assertIsNotNone(t)
        assert t is not None
        self.assertIn(3.75, t["coupons_pct"])
        self.assertEqual(t["principal_usd"][0], 1_500_000_000.0)

    def test_reject_noise(self):
        self.assertIsNone(parse_offering_terms("hello world " * 50))


class TestPanelOmitPaid(unittest.TestCase):
    def test_ratings_cds_omitted(self):
        ma = compute_ma_metrics(
            {
                "OPERATING_INCOME": 50.0,
                "INTEREST_EXPENSE": 5.0,
                "LONG_TERM_DEBT": 100.0,
                "CASH": 10.0,
            }
        )
        panel = build_credit_panel(ma=ma, amounts={"INTEREST_EXPENSE": 5.0}, debt_filings=[])
        self.assertEqual(panel["ratings"]["status"], "omitted")
        self.assertEqual(panel["cds"]["status"], "omitted")
        self.assertEqual(panel["coverage"]["interest_coverage"]["value"], 10.0)


if __name__ == "__main__":
    unittest.main()
