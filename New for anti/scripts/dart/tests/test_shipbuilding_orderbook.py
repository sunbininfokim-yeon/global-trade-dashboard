"""Approved contract-note tables and period/basis regression tests."""
import unittest
from copy import deepcopy
from unittest.mock import patch

from dart_kfa.canonical_analysis import analyze_canonical_facts
from dart_kfa.industry_note_mapping import build_industry_note_profile
from dart_kfa.shipbuilding_orderbook import _registry
from test_pe_cr import bundle


KSOE = "00164830"


def issuer(year=2025, scope="CFS"):
    return {**bundle(year, scope=scope), "entity_id": KSOE}


def profile(b, period, **kwargs):
    return build_industry_note_profile(b, "shipbuilding", period, **kwargs)["shipbuilding_orderbook"]


class ShipbuildingOrderbookTests(unittest.TestCase):
    def test_annual_connected_rows_and_recognition_reconcile(self):
        result = analyze_canonical_facts(issuer())
        b = result["pe_cr"]["industry_note_metrics"]["shipbuilding_orderbook"]
        self.assertEqual(b["source_window"], "annual")
        self.assertEqual(b["rows"][0]["closing"], 82_236_880_000_000)
        self.assertEqual(b["rows"][1]["closing"], 70_801_620_000_000)
        self.assertEqual(b["rows"][1]["included_in"], "total")
        self.assertEqual(sum(row["amount"] for row in b["expected_revenue_recognition"]), b["rows"][0]["closing"])
        self.assertIsNone(b["closing_vessels"])
        self.assertIsNone(result["pe_cr"]["industry_note_metrics"]["shipbuilding_rg"]["portfolios"][0]["rows"][0]["outstanding"])

    def test_h1_2026_is_ytd_in_a_quarter_view_and_same_report_as_rg(self):
        b = build_industry_note_profile(issuer(2026), "shipbuilding", "Q2")
        orderbook, rg = b["shipbuilding_orderbook"], b["shipbuilding_rg"]
        self.assertEqual(orderbook["source_window"], "half_year_ytd")
        self.assertEqual((orderbook["period_start"], orderbook["period_end"]), ("2026-01-01", "2026-06-30"))
        self.assertEqual(orderbook["rows"][0]["contract_movement"], 33_642_412_000_000)
        self.assertEqual(orderbook["rows"][0]["closing"], 98_808_720_000_000)
        self.assertEqual(orderbook["rows"][1]["closing"], 85_142_861_000_000)
        self.assertEqual(orderbook["expected_revenue_recognition"][0]["amount"], 19_959_957_000_000)
        self.assertTrue(orderbook["expected_revenue_recognition"][0]["remaining_in_current_year"])
        self.assertEqual(rg["portfolios"][0]["rows"][0]["limit"], 58_887_854_000_000)
        self.assertEqual(rg["portfolios"][0]["evidence"]["filing_id"], orderbook["evidence"]["filing_id"])

    def test_negative_movement_separate_scope_and_availability(self):
        self.assertEqual(profile(issuer(), "Q2")["rows"][2]["contract_movement"], -200_631_000_000)
        self.assertEqual(profile(issuer(scope="OFS"), "annual")["rows"][0]["closing"], 2_076_335_000_000)
        self.assertEqual(profile(issuer(scope="OFS"), "Q2")["status"], "unavailable")
        self.assertEqual(profile(issuer(), "Q4")["status"], "unavailable")
        self.assertEqual(profile({**issuer(), "currency": "USD"}, "annual")["status"], "unavailable")
        before = profile(issuer(2026), "Q2", publication_cutoff="2026-08-13")
        self.assertEqual(before["reason"], "unavailable:filing_after_publication_cutoff")

    def test_conflicting_movement_or_schedule_is_rejected(self):
        for field, reason in (("closing", "rollforward"), ("schedule", "recognition_schedule"), ("url", "reviewed_kind_periodic_filing")):
            with self.subTest(field=field):
                doc = deepcopy(_registry())
                if field == "closing":
                    doc["packets"][0]["rows"][1]["closing"] += 1
                elif field == "schedule":
                    doc["packets"][0]["revenue_schedule"][0]["amount"] += 1
                else:
                    doc["reports"]["20260320004889"]["url"] = "https://kind.krx.co.kr/report/invalid"
                with patch("dart_kfa.shipbuilding_orderbook._registry", return_value=doc):
                    with self.assertRaisesRegex(ValueError, reason):
                        profile(issuer(), "annual")

    def test_missing_schedule_keeps_verified_rollforward(self):
        doc = deepcopy(_registry())
        del doc["packets"][0]["revenue_schedule"]
        with patch("dart_kfa.shipbuilding_orderbook._registry", return_value=doc):
            orderbook = profile(issuer(), "annual")
            self.assertEqual(orderbook["status"], "reported")
            self.assertEqual(orderbook["expected_revenue_recognition"], [])
            self.assertIsNone(orderbook["schedule_evidence"])


if __name__ == "__main__":
    unittest.main()
