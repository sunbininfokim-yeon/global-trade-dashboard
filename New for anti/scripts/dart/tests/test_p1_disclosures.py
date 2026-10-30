"""Offline contract tests for the P1 deterministic disclosure add-on."""

from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.p1_disclosures import (  # noqa: E402
    build_p1_disclosures,
    compute_strict_ebitda,
    resolve_latest_endpoint,
)


def fact(account, value, *, endpoint="Q3", nature="flow", currency="KRW", fs_div="CFS", year=2025, quality="reported"):
    quarter = {"Q1": "Q1", "Q2": "Q2", "Q3": "Q3", "annual": None}[endpoint]
    ends = {"Q1": "2025-03-31", "Q2": "2025-06-30", "Q3": "2025-09-30", "annual": "2025-12-31"}
    starts = {"Q1": "2025-01-01", "Q2": "2025-04-01", "Q3": "2025-07-01", "annual": "2025-01-01"}
    reports = {"Q1": ("11013", "quarter_report"), "Q2": ("11012", "half_year_report"), "Q3": ("11014", "quarter_report"), "annual": ("11011", "business_report")}
    code, report_type = reports[endpoint]
    return {
        "account_id": account,
        "value": value,
        "availability": "available" if value is not None else "unavailable",
        "quality": quality if value is not None else "unavailable",
        "reason": None if value is not None else "missing:fixture",
        "source": "DART",
        "source_concept": "reported_" + account.lower(),
        "statement": "BS" if nature == "balance" else "IS",
        "nature": nature,
        "fiscal_year": year,
        "fiscal_quarter": quarter,
        "period_kind": "balance_point_in_time" if nature == "balance" else ("flow_annual" if endpoint == "annual" else "flow_discrete_quarter"),
        "period_start": None if nature == "balance" else starts[endpoint],
        "period_end": ends[endpoint],
        "report_code": code,
        "report_type": report_type,
        "fs_div": fs_div,
        "unit": {"kind": "currency", "currency": currency, "scale": 1},
        "provenance": {"filing_id": "fixture-" + code, "source_field": "reported_amount"},
    }


def canonical(endpoint="Q3", *, year=2025):
    accounts = {
        "OPERATING_INCOME": fact("OPERATING_INCOME", 100, endpoint=endpoint, year=year),
        "PPE_DEPRECIATION": fact("PPE_DEPRECIATION", 10, endpoint=endpoint, year=year),
        "INTANGIBLE_AMORTIZATION": fact("INTANGIBLE_AMORTIZATION", 5, endpoint=endpoint, year=year),
        "TRADE_RECEIVABLES": fact("TRADE_RECEIVABLES", 20, endpoint=endpoint, nature="balance", year=year),
        "REVENUE": fact("REVENUE", 100, endpoint=endpoint, year=year),
    }
    series = {}
    for account, cell in accounts.items():
        series[account] = {"annual": cell if endpoint == "annual" else None, "quarters": {endpoint: cell} if endpoint != "annual" else {}}
    return {
        "schema_version": "canonical-financial-facts/1",
        "source": "DART",
        "entity_id": "fixture-001",
        "fiscal_year": year,
        "fs_div": "CFS",
        "currency": "KRW",
        "series": series,
    }


class TestP1Disclosures(unittest.TestCase):
    def test_valid_strict_ebitda_has_all_reported_source_facts(self):
        result = compute_strict_ebitda(canonical(), endpoint="Q3")
        self.assertEqual(result["status"], "derived_deterministic")
        self.assertEqual(result["value"], 115)
        self.assertEqual(set(result["provenance"]["input_facts"]), {"OPERATING_INCOME", "PPE_DEPRECIATION", "INTANGIBLE_AMORTIZATION"})
        self.assertEqual(result["period"]["report_code"], "11014")
        self.assertEqual(result["period"]["report_id"], "fixture-11014")

    def test_missing_amortization_never_becomes_operating_income_proxy(self):
        source = canonical()
        source["series"].pop("INTANGIBLE_AMORTIZATION")
        result = compute_strict_ebitda(source, endpoint="Q3")
        self.assertIsNone(result["value"])
        self.assertIn("INTANGIBLE_AMORTIZATION:missing:account", result["reason"])

    def test_ebitda_rejects_scope_currency_or_period_mismatch(self):
        source = canonical()
        bad = source["series"]["PPE_DEPRECIATION"]["quarters"]["Q3"]
        bad["fs_div"] = "OFS"
        self.assertEqual(
            compute_strict_ebitda(source, endpoint="Q3")["reason"],
            "incompatible:strict_ebitda_period_scope_currency_or_unit",
        )
        bad["fs_div"] = "CFS"
        bad["unit"]["currency"] = "USD"
        self.assertEqual(
            compute_strict_ebitda(source, endpoint="Q3")["reason"],
            "incompatible:strict_ebitda_period_scope_currency_or_unit",
        )

    def test_endpoint_resolution_uses_h1_then_q1_then_fy_when_later_reports_absent(self):
        h1 = canonical("Q2")
        resolved_h1 = resolve_latest_endpoint(h1)
        self.assertEqual(resolved_h1["selected"], "Q2")
        self.assertEqual(build_p1_disclosures(h1, requested_endpoint="H1")["period_selection"]["selected"], "Q2")

        q1 = canonical("Q1")
        self.assertEqual(resolve_latest_endpoint(q1)["selected"], "Q1")
        fy = canonical("annual")
        self.assertEqual(resolve_latest_endpoint(fy)["selected"], "annual")
        self.assertEqual(build_p1_disclosures(fy, requested_endpoint="FY")["period_selection"]["selected"], "annual")

    def test_receivables_to_sales_requires_matched_balance_flow_scope_currency(self):
        output = build_p1_disclosures(canonical())
        ratio = output["current"]["receivables_to_sales_pct"]
        self.assertEqual(ratio["value"], 20)
        self.assertEqual(ratio["unit"]["kind"], "pct")
        source = canonical()
        source["series"]["TRADE_RECEIVABLES"]["quarters"]["Q3"]["unit"]["currency"] = "USD"
        self.assertEqual(
            build_p1_disclosures(source)["current"]["receivables_to_sales_pct"]["reason"],
            "incompatible:receivables_sales_period_scope_currency_or_unit",
        )

    def test_structured_reported_segment_and_backlog_are_accepted_with_provenance(self):
        rows = [
            {
                "disclosure_type": "segment_profit", "is_structured_reported": True,
                "segment_id": "shipbuilding", "segment_name": "Shipbuilding", "value": 30,
                "unit": {"kind": "currency", "currency": "KRW", "scale": 1},
                "fiscal_year": 2025, "period_end": "2025-09-30", "fs_div": "CFS",
                "report_id": "receipt-11014", "report_type": "quarter_report", "source_table": "segment-table", "source_row_id": "r1",
            },
            {
                "disclosure_type": "backlog_order_book", "is_structured_reported": True,
                "segment_id": "shipbuilding", "segment_name": "Shipbuilding", "value": 900,
                "unit": {"kind": "currency", "currency": "KRW", "scale": 1},
                "fiscal_year": 2025, "period_end": "2025-09-30", "fs_div": "CFS",
                "report_id": "receipt-11014", "report_type": "quarter_report", "source_table": "order-table", "source_row_id": "r3",
            },
        ]
        current = build_p1_disclosures(canonical(), structured_disclosures=rows)["current"]
        self.assertEqual(current["segment_profit"]["status"], "reported")
        self.assertEqual(current["segment_profit"]["value"][0]["provenance"]["source_row_id"], "r1")
        self.assertEqual(current["backlog_order_book"]["value"][0]["value"], 900)

    def test_unstructured_note_text_is_rejected_not_parsed(self):
        rows = [{
            "disclosure_type": "backlog_order_book", "is_structured_reported": False,
            "note_text": "수주잔고는 900입니다.", "fiscal_year": 2025,
        }]
        result = build_p1_disclosures(canonical(), structured_disclosures=rows)["current"]["backlog_order_book"]
        self.assertIsNone(result["value"])
        self.assertEqual(result["reason"], "rejected:unstructured_note_evidence")

    def test_annual_history_stays_separate_from_current_endpoint(self):
        current = canonical("Q3", year=2026)
        prior = canonical("annual", year=2025)
        output = build_p1_disclosures(current, annual_history=[prior])
        self.assertEqual(output["current"]["period"]["fiscal_quarter"], "Q3")
        self.assertEqual(output["annual_history"][0]["period"]["fiscal_quarter"], None)
        self.assertEqual(output["annual_history"][0]["ebitda"]["value"], 115)


if __name__ == "__main__":
    unittest.main()
