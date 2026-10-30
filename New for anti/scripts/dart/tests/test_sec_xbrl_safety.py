"""Safety regressions for the legacy SEC-to-common-engine bridge."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.canonical_facts import adapt_sec_companyfacts, default_sec_account_specs  # noqa: E402
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


class SecLeaseSafetyTest(unittest.TestCase):
    def test_current_only_lease_fact_is_never_emitted_as_total_lease_debt(self):
        facts = {
            "entityName": "Lease Co",
            "facts": {"us-gaap": {
                "Assets": {"units": {"USD": [
                    {"end": "2025-12-31", "val": 500, "form": "10-K", "fp": "FY", "filed": "2026-02-01"},
                ]}},
                "OperatingLeaseLiabilityCurrent": {"units": {"USD": [
                    {"end": "2025-12-31", "val": 30, "form": "10-K", "fp": "FY", "filed": "2026-02-01"},
                ]}},
            }},
        }
        legacy = facts_to_fnltt_payload(facts, ticker="LEASE", asof_fy=2025)
        self.assertFalse(any(row["account_id"] == "us-gaap_OperatingLeaseLiabilityCurrent" for row in legacy["list"]))

        canonical = adapt_sec_companyfacts(
            facts,
            fiscal_year_end="2025-12-31",
            account_specs={"LEASE_LIABILITIES": default_sec_account_specs()["LEASE_LIABILITIES"]},
        )
        lease = canonical["series"]["LEASE_LIABILITIES"]["annual"]
        self.assertIsNone(lease["value"])
        self.assertTrue(lease["reason"].startswith("missing:sec_exact_period_fact"))

    def test_custom_lease_spec_cannot_restore_current_only_fallback(self):
        facts = {"facts": {"us-gaap": {
            "OperatingLeaseLiabilityCurrent": {"units": {"USD": [
                {"end": "2025-12-31", "val": 30, "form": "10-K", "fp": "FY", "filed": "2026-02-01"},
            ]}},
        }}}
        canonical = adapt_sec_companyfacts(
            facts,
            fiscal_year_end="2025-12-31",
            account_specs={"LEASE_LIABILITIES": {
                "nature": "balance", "statement": "BS",
                "sec_concepts": ["OperatingLeaseLiabilityCurrent"],
            }},
        )
        self.assertIsNone(canonical["series"]["LEASE_LIABILITIES"]["annual"]["value"])


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
