"""Safety regressions for the legacy SEC-to-common-engine bridge."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.sec_xbrl import facts_to_fnltt_payload, shares_outstanding_fact  # noqa: E402


class SecAnnualSelectionTest(unittest.TestCase):
    def test_same_end_quarter_fact_never_wins_over_annual_duration(self):
        facts = {
            "entityName": "AAPL-like",
            "facts": {"us-gaap": {
                "Assets": {"units": {"USD": [
                    {"end": "2025-09-27", "val": 500, "form": "10-K", "fp": "FY", "filed": "2025-10-31"},
                ]}},
                "Revenues": {"units": {"USD": [
                    {"start": "2025-06-29", "end": "2025-09-27", "val": 30, "form": "10-K", "fp": "FY", "filed": "2025-10-31"},
                    {"start": "2024-09-29", "end": "2025-09-27", "val": 120, "form": "10-K", "fp": "FY", "filed": "2025-10-31"},
                ]}},
            }},
        }
        payload = facts_to_fnltt_payload(facts, ticker="AAPL", asof_fy=2025)
        revenue = next(row for row in payload["list"] if row["account_nm"] == "Revenues")
        self.assertEqual(revenue["thstrm_amount"], "120")


class SecShareSafetyTest(unittest.TestCase):
    def test_weighted_average_shares_are_never_a_point_in_time_fallback(self):
        facts = {"facts": {"us-gaap": {
            "WeightedAverageNumberOfSharesOutstandingBasic": {"units": {"shares": [
                {"start": "2025-01-01", "end": "2025-12-31", "val": 100, "form": "10-K", "fp": "FY", "fy": 2025},
            ]}},
        }}}
        self.assertIsNone(shares_outstanding_fact(facts, fy=2025))

    def test_point_in_time_share_fact_keeps_identity_and_date(self):
        facts = {"facts": {"dei": {
            "EntityCommonStockSharesOutstanding": {"units": {"shares": [
                {"end": "2025-09-27", "val": 100, "form": "10-K", "fp": "FY", "fy": 2025, "accn": "0001", "filed": "2025-10-31"},
            ]}},
        }}}
        got = shares_outstanding_fact(facts, fy=2025)
        self.assertEqual(got["value"], 100.0)
        self.assertEqual(got["share_basis"], "point_in_time_basic")
        self.assertEqual(got["share_as_of"], "2025-09-27")
        self.assertEqual(got["share_source_ref"], "SEC:0001")


if __name__ == "__main__":
    unittest.main()
