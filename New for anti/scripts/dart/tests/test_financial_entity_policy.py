"""P0 regression tests: financial issuers must not enter industrial models."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.accounts import resolve_accounts
from dart_kfa.analyze import analyze_payload
from dart_kfa.entity_policy import classify_entity
from dart_kfa.fetch import load_fixture


FIXTURE = ROOT / "tests" / "fixtures" / "samsung_fnltt_sample.json"
INDUSTRIAL_METRICS = {
    "current_ratio", "quick_ratio", "cash_ratio", "debt_ratio", "operating_margin",
    "net_margin", "asset_turnover", "inventory_turnover", "receivables_turnover",
    "earnings_quality", "fcf", "roic", "interest_coverage",
}


class TestClassification(unittest.TestCase):
    def test_explicit_overrides_cover_kb_samsung_life_and_jpm(self):
        cases = [
            ({"corp_code": "00688996"}, "bank"),
            ({"corp_code": "00126256"}, "insurance"),
            ({"source": "sec", "corp_code": "19617"}, "bank"),
        ]
        for corp, expected in cases:
            with self.subTest(corp=corp):
                policy = classify_entity(corp)
                self.assertEqual(policy["entity_class"], expected)
                self.assertTrue(policy["is_financial_entity"])
                self.assertEqual(policy["classification_status"], "complete")

    def test_ksic_and_name_hints_fail_closed(self):
        self.assertEqual(classify_entity({"industry": "K65"})["entity_class"], "insurance")
        suspected = classify_entity({"name": "테스트금융"})
        self.assertEqual(suspected["entity_class"], "financial_suspected")
        self.assertTrue(suspected["is_financial_entity"])

    def test_existing_operating_income_fallback_maps_exact_ifrs_tag(self):
        rows = [{
            "sj_div": "IS",
            "account_id": "ifrs-full_ProfitLossFromOperatingActivities",
            "account_nm": "영업이익",
            "thstrm_amount": "123",
            "frmtrm_amount": "100",
            "bfefrmtrm_amount": "90",
        }]
        resolved = resolve_accounts(rows)
        self.assertEqual(resolved["OPERATING_INCOME"]["value"], 123.0)
        self.assertEqual(resolved["OPERATING_INCOME"]["match"], "id:ifrs-full_ProfitLossFromOperatingActivities")


class TestFinancialEngineGate(unittest.TestCase):
    def _assert_financial_output(self, corp: dict, expected_class: str) -> None:
        company = analyze_payload(load_fixture(FIXTURE), corp=corp)
        self.assertEqual(company["entity_policy"]["entity_class"], expected_class)
        self.assertFalse(company["entity_policy"]["industrial_metrics_allowed"])

        # The industrial fixture deliberately contains Revenue/CFO/debt inputs;
        # passing it as a bank/insurer verifies that the policy, rather than
        # missing facts, does the blocking.
        revenue = company["accounts"]["REVENUE"]
        self.assertIsNone(revenue["value"])
        self.assertEqual(revenue["reason"], "not_applicable:financial_entity_industrial_revenue")
        self.assertIsNotNone(company["accounts"]["OPERATING_INCOME"]["value"])

        for mid in INDUSTRIAL_METRICS:
            cell = company["metrics"][mid]
            self.assertIsNone(cell["value"], mid)
            self.assertEqual(cell["reason"], "not_applicable:financial_entity_industrial_metric", mid)

        for mid in ("fcf", "net_debt", "net_debt_to_ebitda", "ebitda_proxy", "interest_coverage"):
            cell = company["ma_metrics"][mid]
            self.assertIsNone(cell["value"], mid)
            self.assertEqual(cell["reason"], "not_applicable:financial_entity_ma_metric", mid)

        self.assertEqual(company["valuation"]["status"], "not_applicable")
        self.assertEqual(company["valuation"]["reason"], "not_applicable:financial_entity_industrial_valuation")
        self.assertEqual(company["fundamental_pack"]["style"], "financial_entity_safe")
        self.assertNotIn("cash_bridge", company["fundamental_pack"])

    def test_kb_bank_blocks_industrial_metrics(self):
        self._assert_financial_output(
            {"name": "KB금융", "corp_code": "00688996", "industry": "K64"}, "bank"
        )

    def test_samsung_life_insurance_blocks_industrial_metrics(self):
        self._assert_financial_output(
            {"name": "삼성생명", "corp_code": "00126256", "industry": "K65"}, "insurance"
        )

    def test_jpm_like_sec_policy_blocks_industrial_metrics(self):
        self._assert_financial_output(
            {"name": "JPMorgan Chase", "corp_code": "19617", "source": "sec", "code": "JPM"}, "bank"
        )


if __name__ == "__main__":
    unittest.main()
