"""Regression tests for the OpenDART adapter and the snapshot it builds.

No network access and no DART_API_KEY needed: fetch_xbrl_facts is monkeypatched
with a fixture shaped like real OpenDART fnlttSinglAcntAll.json rows (the same
account_id keys verified in dart_facts.py's XBRL_TAGS against live Samsung/SK
Hynix responses), so these tests check the mapping and derived-card math, not
the HTTP call itself.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from dart_kfa import dart_facts
from dart_kfa.derived_cards import basic_cards_from_pack
from dart_kfa.snapshot_builder import build_kfa_snapshot


def sample_facts() -> dict[str, str]:
    return {
        "ifrs-full_Revenue": "1000000",
        "ifrs-full_GrossProfit": "400000",
        "dart_OperatingIncomeLoss": "150000",
        "ifrs-full_ProfitLoss": "120000",
        "ifrs-full_ProfitLossBeforeTax": "160000",
        "ifrs-full_IncomeTaxExpenseContinuingOperations": "40000",
        "ifrs-full_FinanceCosts": "5000",
        "ifrs-full_BasicEarningsLossPerShare": "1200",
        "ifrs-full_CashFlowsFromUsedInOperatingActivities": "180000",
        "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": "-70000",
        "ifrs-full_CashAndCashEquivalents": "300000",
        "ifrs-full_CurrentAssets": "500000",
        "ifrs-full_CurrentLiabilities": "250000",
        "ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings": "60000",
        "ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived": "90000",
    }


class MapFactsToPackTest(unittest.TestCase):
    def test_populated_fields_get_a_single_point_series(self):
        pack = dart_facts.map_facts_to_pack(sample_facts(), 2025)
        self.assertEqual(pack["pnl"]["revenue"]["value"], 1000000.0)
        self.assertEqual(pack["pnl"]["revenue"]["series"], [{"year": 2025, "end": "2025-12-31", "value": 1000000.0}])
        self.assertEqual(pack["pnl"]["operating_income"]["value"], 150000.0)

    def test_interest_expense_is_flagged_as_approximation(self):
        pack = dart_facts.map_facts_to_pack(sample_facts(), 2025)
        self.assertEqual(pack["pnl"]["interest_expense"]["value"], 5000.0)
        self.assertEqual(pack["pnl"]["interest_expense"]["reason"], "approx:ifrs_finance_costs_not_pure_interest")

    def test_missing_field_is_null_with_reason(self):
        pack = dart_facts.map_facts_to_pack({}, 2025)
        self.assertIsNone(pack["pnl"]["revenue"]["value"])
        self.assertEqual(pack["pnl"]["revenue"]["reason"], "missing:not_in_opendart")
        self.assertEqual(pack["pnl"]["revenue"]["series"], [])

    def test_current_ratio_is_derived_from_current_assets_and_liabilities(self):
        pack = dart_facts.map_facts_to_pack(sample_facts(), 2025)
        self.assertAlmostEqual(pack["liquidity"]["current_ratio"]["value"], 2.0)

    def test_current_ratio_is_null_when_current_liabilities_missing(self):
        facts = sample_facts()
        del facts["ifrs-full_CurrentLiabilities"]
        pack = dart_facts.map_facts_to_pack(facts, 2025)
        self.assertIsNone(pack["liquidity"]["current_ratio"]["value"])
        self.assertEqual(pack["liquidity"]["current_ratio"]["reason"], "missing:current_assets_or_current_liabilities")

    def test_net_debt_sums_short_and_long_term_borrowings_minus_cash(self):
        pack = dart_facts.map_facts_to_pack(sample_facts(), 2025)
        # 60000 + 90000 - 300000 = -150000 (net cash position)
        self.assertAlmostEqual(pack["debt_structure"]["net_debt"]["value"], -150000.0)

    def test_net_debt_is_null_when_no_debt_and_no_cash_fetched(self):
        pack = dart_facts.map_facts_to_pack({}, 2025)
        self.assertIsNone(pack["debt_structure"]["net_debt"]["value"])
        self.assertEqual(pack["debt_structure"]["net_debt"]["reason"], "missing:interest_bearing_debt_or_cash")

    def test_debt_due_within_1y_stays_null_value_with_only_short_term_component(self):
        pack = dart_facts.map_facts_to_pack(sample_facts(), 2025)
        due = pack["liquidity"]["debt_due_within_1y"]
        self.assertIsNone(due["value"])
        self.assertEqual(due["components"]["short_term_borrowings"], 60000.0)
        self.assertIsNone(due["components"]["current_portion_lt_debt"])
        self.assertEqual(due["reason"], "missing:current_portion_lt_debt_and_lease_current_not_separately_tagged")

    def test_depreciation_and_amortization_always_missing(self):
        pack = dart_facts.map_facts_to_pack(sample_facts(), 2025)
        self.assertIsNone(pack["cash_flow"]["depreciation_and_amortization"]["value"])
        self.assertEqual(
            pack["cash_flow"]["depreciation_and_amortization"]["reason"], "missing:not_disclosed_separately"
        )


class BasicCardsFromPackTest(unittest.TestCase):
    def test_margins_and_fcf_are_derived_from_a_single_year_pack(self):
        pack = dart_facts.map_facts_to_pack(sample_facts(), 2025)
        cards = basic_cards_from_pack(pack)
        self.assertAlmostEqual(cards["operating_income"]["margin"], 0.15)
        self.assertAlmostEqual(cards["net_income"]["margin"], 0.12)
        # cfo 180000 - abs(capex -70000) = 110000
        self.assertAlmostEqual(cards["fcf"]["value"], 110000.0)
        self.assertEqual(cards["fcf"]["definition"], "cfo - abs(capex)")
        self.assertIsNone(cards["revenue"]["yoy"])

    def test_ccc_days_is_null_with_reason_no_receivables_inventory_payables_fetched(self):
        pack = dart_facts.map_facts_to_pack(sample_facts(), 2025)
        cards = basic_cards_from_pack(pack)
        self.assertIsNone(cards["ccc_days"]["value"])
        self.assertEqual(cards["ccc_days"]["reason"], "missing:dso_dio_dpo_inputs_not_fetched")

    def test_empty_pack_degrades_to_null_reasons_everywhere_no_crash(self):
        pack = dart_facts.map_facts_to_pack({}, 2025)
        cards = basic_cards_from_pack(pack)
        for key in ("revenue", "operating_income", "net_income", "cfo", "fcf", "cash", "net_debt", "current_ratio"):
            self.assertIsNone(cards[key]["value"], key)


class BuildKfaSnapshotTest(unittest.TestCase):
    @patch("dart_kfa.dart_facts.fetch_xbrl_facts")
    def test_snapshot_has_expected_schema_and_meta(self, mock_fetch):
        mock_fetch.return_value = sample_facts()
        snapshot = build_kfa_snapshot("00126380", "005930", "삼성전자(주)", "SAMSUNG ELECTRONICS CO,.LTD", 2025)

        self.assertEqual(snapshot["schema"], "kfa_engine_v1")
        self.assertEqual(snapshot["as_of"], "2025-12-31")
        self.assertEqual(snapshot["meta"]["corp_code"], "00126380")
        self.assertEqual(snapshot["meta"]["stock_code"], "005930")
        self.assertIn("basic", snapshot["view_presets"]["views"])
        self.assertEqual(snapshot["basic_cards"]["revenue"]["value"], 1000000.0)
        self.assertEqual(snapshot["data_quality"]["facts_fetched"], len(sample_facts()))
        # Non-Basic cards ran too (via run_kfa_analysis), even if most are null+reason for one FY.
        self.assertIn("owner_earnings", snapshot["basic_cards"])

    @patch("dart_kfa.dart_facts.fetch_xbrl_facts")
    def test_snapshot_degrades_cleanly_with_zero_facts(self, mock_fetch):
        mock_fetch.return_value = {}
        snapshot = build_kfa_snapshot("00000000", "000000", "테스트", "TEST", 2025)
        self.assertEqual(snapshot["data_quality"]["facts_fetched"], 0)
        self.assertIsNone(snapshot["basic_cards"]["revenue"]["value"])
        self.assertEqual(snapshot["basic_cards"]["revenue"]["reason"], "missing:not_in_opendart")


if __name__ == "__main__":
    unittest.main()
