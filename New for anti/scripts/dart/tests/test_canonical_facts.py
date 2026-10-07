"""Offline synthetic tests for the canonical DART/SEC fact contract."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.canonical_facts import (  # noqa: E402
    CanonicalFactError,
    adapt_dart_filings,
    adapt_sec_companyfacts,
    default_dart_account_specs,
    make_labeled_proxy,
)


FLOW_SPEC = {
    "REVENUE": {
        "nature": "flow",
        "statement": "IS",
        "source_ids": ["ifrs-full_Revenue"],
        "sec_concepts": ["Revenues"],
    }
}
BALANCE_SPEC = {
    "CASH": {
        "nature": "balance",
        "statement": "BS",
        "source_ids": ["ifrs-full_CashAndCashEquivalents"],
        "sec_concepts": ["CashAndCashEquivalentsAtCarryingValue"],
    }
}


def dart_row(
    code: str,
    account_id: str,
    statement: str,
    amount: int,
    *,
    cumulative: int | None = None,
    period_value_kind: str | None = None,
):
    row = {
        "rcept_no": f"receipt-{code}",
        "reprt_code": code,
        "bsns_year": "2025",
        "corp_code": "001",
        "fs_div": "CFS",
        "sj_div": statement,
        "account_id": account_id,
        "account_nm": account_id,
        "thstrm_amount": str(amount),
        "currency": "KRW",
    }
    if cumulative is not None:
        row["thstrm_add_amount"] = str(cumulative)
    if period_value_kind is not None:
        row["period_value_kind"] = period_value_kind
    return row


class TestDartCanonicalAdapter(unittest.TestCase):
    def test_default_specs_preserve_reviewed_complete_aggregation_policy(self):
        specs = default_dart_account_specs()
        self.assertIn("ifrs-full_Revenue", specs["REVENUE"]["source_ids"])
        self.assertEqual(specs["LEASE_LIABILITIES"]["aggregation"]["required_components"], 2)

    def test_split_lease_components_are_summed_only_when_complete(self):
        specs = {"LEASE_LIABILITIES": default_dart_account_specs()["LEASE_LIABILITIES"]}
        current = dart_row("11011", "ifrs-full_CurrentLeaseLiabilities", "BS", 30)
        noncurrent = dart_row("11011", "ifrs-full_NoncurrentLeaseLiabilities", "BS", 70)
        complete = adapt_dart_filings(
            {"11011": [current, noncurrent]}, account_specs=specs, fiscal_year_end="2025-12-31"
        )["series"]["LEASE_LIABILITIES"]["annual"]
        self.assertEqual(complete["value"], 100)
        self.assertEqual(complete["provenance"]["aggregation"], "sum_complete_components")

        incomplete = adapt_dart_filings(
            {"11011": [current]}, account_specs=specs, fiscal_year_end="2025-12-31"
        )["series"]["LEASE_LIABILITIES"]["annual"]
        self.assertIsNone(incomplete["value"])
        self.assertEqual(incomplete["reason"], "missing:aggregation_components:1/2")

    def test_report_codes_non_december_periods_and_reconciliation(self):
        filings = {
            "11013": [dart_row("11013", "ifrs-full_Revenue", "IS", 10, cumulative=10)],
            "11012": [dart_row("11012", "ifrs-full_Revenue", "IS", 21, cumulative=31)],
            "11014": [dart_row("11014", "ifrs-full_Revenue", "IS", 17, cumulative=48)],
            "11011": [dart_row("11011", "ifrs-full_Revenue", "IS", 70)],
        }
        got = adapt_dart_filings(
            filings,
            account_specs=FLOW_SPEC,
            fiscal_year_end="2025-03-31",
            entity_id="001",
            scale=1000,
            source_unit_label="천원",
        )
        revenue = got["series"]["REVENUE"]
        self.assertEqual(got["fiscal_year_start"], "2024-04-01")
        self.assertEqual(revenue["quarters"]["Q1"]["period_end"], "2024-06-30")
        self.assertEqual(revenue["quarters"]["Q2"]["period_start"], "2024-07-01")
        self.assertEqual(
            [revenue["quarters"][q]["value"] for q in ("Q1", "Q2", "Q3", "Q4")],
            [10000, 21000, 17000, 22000],
        )
        self.assertEqual(revenue["quarters"]["Q2"]["quality"], "deterministic_derived")
        self.assertEqual(revenue["quarters"]["Q2"]["report_code"], "11012")
        self.assertEqual(revenue["quarters"]["Q2"]["report_type"], "half_year_report")
        self.assertEqual(revenue["quarters"]["Q2"]["unit"]["source_scale"], 1000)
        self.assertEqual(revenue["reconciliation"]["status"], "ok")

    def test_missing_predecessor_is_unavailable_not_an_estimate(self):
        filings = {
            "11012": [dart_row("11012", "ifrs-full_Revenue", "IS", 31, cumulative=31)],
            "11014": [dart_row("11014", "ifrs-full_Revenue", "IS", 17, cumulative=48)],
            "11011": [dart_row("11011", "ifrs-full_Revenue", "IS", 70)],
        }
        got = adapt_dart_filings(filings, account_specs=FLOW_SPEC, fiscal_year_end="2025-12-31")
        revenue = got["series"]["REVENUE"]
        self.assertIsNone(revenue["quarters"]["Q2"]["value"])
        self.assertEqual(revenue["quarters"]["Q2"]["availability"], "unavailable")
        self.assertEqual(revenue["quarters"]["Q2"]["confidence"], "none")
        self.assertEqual(revenue["quarters"]["Q2"]["reason"], "missing:predecessor_ytd_Q1")
        self.assertEqual(revenue["quarters"]["Q3"]["value"], 17)
        self.assertEqual(revenue["reconciliation"]["status"], "incomplete")

    def test_balance_is_point_in_time_and_scope_does_not_fallback(self):
        codes = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
        values = {"Q1": 100, "H1": 130, "Q3": 90, "FY": 120}
        filings = {
            code: [dart_row(code, "ifrs-full_CashAndCashEquivalents", "BS", values[bucket])]
            for bucket, code in codes.items()
        }
        got = adapt_dart_filings(filings, account_specs=BALANCE_SPEC, fiscal_year_end="2025-12-31")
        cash = got["series"]["CASH"]
        self.assertEqual([cash["quarters"][q]["value"] for q in ("Q1", "Q2", "Q3", "Q4")], [100, 130, 90, 120])
        self.assertEqual(cash["quarters"]["Q2"]["period_kind"], "balance_point_in_time")
        self.assertEqual(cash["reconciliation"]["method"], "fy_balance_equals_q4_endpoint")
        self.assertEqual(cash["reconciliation"]["status"], "ok")

        ofs = adapt_dart_filings(filings, account_specs=BALANCE_SPEC, fiscal_year_end="2025-12-31", fs_div="OFS")
        self.assertIsNone(ofs["series"]["CASH"]["quarters"]["Q1"]["value"])

    def test_interim_income_statement_requires_cumulative_field(self):
        filings = {
            "11013": [dart_row("11013", "ifrs-full_Revenue", "IS", 10)],
            "11012": [dart_row("11012", "ifrs-full_Revenue", "IS", 21)],
        }
        got = adapt_dart_filings(filings, account_specs=FLOW_SPEC, fiscal_year_end="2025-12-31")
        self.assertIsNone(got["series"]["REVENUE"]["quarters"]["Q2"]["value"])
        # H1's standalone-quarter amount is never treated as cumulative H1.
        source = got["series"]["REVENUE"]["quarters"]["Q2"]["provenance"]["source_facts"][-1]
        self.assertIsNone(source["source_field"])

    def test_explicit_direct_interim_value_is_preferred_and_audited(self):
        filings = {
            "11013": [dart_row("11013", "ifrs-full_Revenue", "IS", 10, cumulative=10)],
            # thstrm_amount is an explicitly identified Q2 value; add_amount
            # remains the independently reported H1 YTD observation.
            "11012": [dart_row(
                "11012", "ifrs-full_Revenue", "IS", 21,
                cumulative=31, period_value_kind="direct",
            )],
            "11014": [dart_row("11014", "ifrs-full_Revenue", "IS", 17, cumulative=48)],
            "11011": [dart_row("11011", "ifrs-full_Revenue", "IS", 70)],
        }
        got = adapt_dart_filings(filings, account_specs=FLOW_SPEC, fiscal_year_end="2025-12-31")
        q2 = got["series"]["REVENUE"]["quarters"]["Q2"]
        self.assertEqual(q2["value"], 21)
        self.assertEqual(q2["quality"], "reported")
        self.assertEqual(q2["provenance"]["derivation"], "reported_direct_quarter")
        self.assertEqual(
            q2["provenance"]["direct_quarter_source"]["source_facts"][0]["source_field"],
            "thstrm_amount",
        )

    def test_direct_interim_conflict_is_not_silently_preferred(self):
        filings = {
            "11013": [dart_row("11013", "ifrs-full_Revenue", "IS", 10, cumulative=10)],
            "11012": [dart_row(
                "11012", "ifrs-full_Revenue", "IS", 20,
                cumulative=31, period_value_kind="direct",
            )],
        }
        got = adapt_dart_filings(filings, account_specs=FLOW_SPEC, fiscal_year_end="2025-12-31")
        q2 = got["series"]["REVENUE"]["quarters"]["Q2"]
        self.assertIsNone(q2["value"])
        self.assertEqual(q2["reason"], "conflict:direct_quarter_vs_ytd_derivation")


def sec_fact(points):
    return {"facts": {"us-gaap": {"Revenues": {"units": {"USD": points}}}}, "entityName": "Synthetic Co"}


class TestSecCanonicalAdapter(unittest.TestCase):
    def test_sec_exact_ytd_periods_share_contract_and_reconcile(self):
        points = [
            {"start": "2024-04-01", "end": "2024-06-30", "val": 10, "form": "10-Q", "fp": "Q1", "filed": "2024-08-01", "accn": "q1"},
            {"start": "2024-04-01", "end": "2024-09-30", "val": 31, "form": "10-Q", "fp": "Q2", "filed": "2024-11-01", "accn": "q2"},
            {"start": "2024-04-01", "end": "2024-12-31", "val": 48, "form": "10-Q", "fp": "Q3", "filed": "2025-02-01", "accn": "q3"},
            {"start": "2024-04-01", "end": "2025-03-31", "val": 70, "form": "10-K", "fp": "FY", "filed": "2025-05-01", "accn": "fy"},
        ]
        got = adapt_sec_companyfacts(sec_fact(points), fiscal_year_end="2025-03-31", account_specs=FLOW_SPEC)
        revenue = got["series"]["REVENUE"]
        self.assertEqual(got["schema_version"], "canonical-financial-facts/1")
        self.assertEqual([revenue["quarters"][q]["value"] for q in ("Q1", "Q2", "Q3", "Q4")], [10, 21, 17, 22])
        self.assertEqual(revenue["quarters"]["Q2"]["report_code"], "10-Q")
        self.assertEqual(revenue["annual"]["report_code"], "10-K")
        self.assertEqual(revenue["reconciliation"]["status"], "ok")

    def test_sec_three_month_q2_is_not_mislabeled_as_half_year_ytd(self):
        points = [
            {"start": "2025-01-01", "end": "2025-03-31", "val": 10, "form": "10-Q", "fp": "Q1", "filed": "2025-05-01"},
            # Discrete Q2, not H1 YTD: adapter must reject it.
            {"start": "2025-04-01", "end": "2025-06-30", "val": 21, "form": "10-Q", "fp": "Q2", "filed": "2025-08-01"},
        ]
        got = adapt_sec_companyfacts(sec_fact(points), fiscal_year_end="2025-12-31", account_specs=FLOW_SPEC)
        q2 = got["series"]["REVENUE"]["quarters"]["Q2"]
        self.assertIsNone(q2["value"])
        self.assertEqual(q2["reason"], "missing:ytd_H1")

    def test_sec_52_week_fiscal_calendar_preserves_reported_dates(self):
        points = [
            {"start": "2024-09-29", "end": "2024-12-28", "val": 10, "form": "10-Q", "fp": "Q1", "filed": "2025-01-31"},
            {"start": "2024-09-29", "end": "2025-03-29", "val": 31, "form": "10-Q", "fp": "Q2", "filed": "2025-05-02"},
            {"start": "2024-09-29", "end": "2025-06-28", "val": 48, "form": "10-Q", "fp": "Q3", "filed": "2025-08-01"},
            {"start": "2024-09-29", "end": "2025-09-27", "val": 70, "form": "10-K", "fp": "FY", "filed": "2025-10-31"},
        ]
        report_periods = {
            "Q1": {"start": "2024-09-29", "end": "2024-12-28"},
            "H1": {"start": "2024-09-29", "end": "2025-03-29"},
            "Q3": {"start": "2024-09-29", "end": "2025-06-28"},
            "FY": {"start": "2024-09-29", "end": "2025-09-27"},
        }
        got = adapt_sec_companyfacts(
            sec_fact(points),
            fiscal_year_end="2025-09-27",
            account_specs=FLOW_SPEC,
            report_periods=report_periods,
        )
        revenue = got["series"]["REVENUE"]
        self.assertEqual(got["fiscal_year_start"], "2024-09-29")
        self.assertEqual(revenue["annual"]["period_start"], "2024-09-29")
        self.assertEqual(revenue["quarters"]["Q1"]["period_end"], "2024-12-28")
        self.assertEqual(revenue["quarters"]["Q4"]["period_start"], "2025-06-29")
        self.assertEqual(revenue["quarters"]["Q4"]["value"], 22)


class TestProxyContract(unittest.TestCase):
    def test_proxy_requires_auditable_metadata_and_is_never_high_confidence(self):
        got = adapt_dart_filings({}, account_specs=FLOW_SPEC, fiscal_year_end="2025-12-31")
        missing = got["series"]["REVENUE"]["quarters"]["Q1"]
        with self.assertRaisesRegex(CanonicalFactError, "source_references"):
            make_labeled_proxy(
                missing,
                value=5,
                metric_id="roe",
                entity_class="industrial",
                estimate_policy_id="ending_balance_denominator_v1",
                method="net_income_divided_by_ending_equity",
                reason="Average equity is unavailable",
                confidence="low",
                source_references=[],
            )
        proxy = make_labeled_proxy(
            missing,
            value=5,
            metric_id="roe",
            entity_class="industrial",
            estimate_policy_id="ending_balance_denominator_v1",
            method="net_income_divided_by_ending_equity",
            reason="Average equity is unavailable; ending balance used",
            confidence="low",
            source_references=[{"account_id": "NET_INCOME"}, {"account_id": "EQUITY"}],
        )
        self.assertEqual(proxy["quality"], "proxy")
        self.assertEqual(proxy["confidence"], "low")
        self.assertEqual(proxy["visibility"], "expert")
        self.assertEqual(proxy["estimate_policy_id"], "ending_balance_denominator_v1")
        self.assertTrue(proxy["provenance"]["proxy"])
        with self.assertRaisesRegex(CanonicalFactError, "low_or_medium"):
            make_labeled_proxy(
                missing,
                value=5,
                metric_id="roe",
                entity_class="industrial",
                estimate_policy_id="ending_balance_denominator_v1",
                method="method",
                reason="reason",
                confidence="high",
                source_references=[{"id": "source"}],
            )
        with self.assertRaisesRegex(CanonicalFactError, "approved_estimate_policy"):
            make_labeled_proxy(
                missing,
                value=5,
                metric_id="revenue",
                entity_class="industrial",
                estimate_policy_id="peer_revenue_guess",
                method="peer_margin_times_revenue",
                reason="unsupported estimate",
                confidence="low",
                source_references=[{"id": "source"}],
            )


if __name__ == "__main__":
    unittest.main()
