"""Offline checks for the redacted OpenDART P1 validation record."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "p1_live_dart_2025_evidence.json"
SCRIPT = ROOT / "tools" / "validate_p1_live_dart.py"


def load_script():
    spec = importlib.util.spec_from_file_location("p1_live_validation", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class P1LiveValidationTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_script()
        self.evidence = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_2025_cfs_evidence_records_two_indexed_industrial_issuers_and_no_promotion(self):
        self.assertEqual(self.evidence["schema_version"], "kfa-p1-live-dart-evidence/1")
        self.assertEqual(self.evidence["requested_fs_div"], "CFS")
        self.assertEqual(self.evidence["manifest_promotion"], "none_automatic")
        self.assertEqual([item["company_id"] for item in self.evidence["companies"]], ["samsung_electronics", "hd_korea_shipbuilding"])
        for company in self.evidence["companies"]:
            self.assertEqual(company["selected_year"], 2025)
            self.assertEqual(company["promotion_decision"], "no_promotion")
            self.assertEqual([endpoint["report_code"] for endpoint in company["endpoints"]], ["11011", "11014", "11012", "11013"])
            for endpoint in company["endpoints"]:
                self.assertEqual(endpoint["response_status"], "000")
                self.assertFalse(endpoint["strict_formula_available_at_endpoint"])
                self.assertEqual(endpoint["da_candidate_rows"], [])
                self.assertEqual(endpoint["strict_formula_reason"], "missing:separately_reported_ppe_depreciation_or_intangible_amortization")
                self.assertTrue(endpoint["receipt_ids"])
                self.assertEqual(endpoint["operating_income_rows"][0]["currency"], "KRW")

    def test_only_explicitly_labelled_components_are_separate(self):
        self.assertEqual(self.tool.classify_da_row({"account_nm": "유형자산감가상각비"}), ("ppe_depreciation", True))
        self.assertEqual(self.tool.classify_da_row({"account_nm": "무형자산상각비"}), ("intangible_amortization", True))
        self.assertEqual(self.tool.classify_da_row({"account_nm": "감가상각비"}), ("combined_or_ambiguous", False))
        self.assertEqual(self.tool.classify_da_row({"account_nm": "단기상각후원가금융자산"}), (None, False))

    def test_matching_endpoint_is_required_even_for_two_separate_candidate_labels(self):
        company = {"id": "fixture", "name_ko": "fixture", "stock_code": "000000", "corp_code": "00000000"}
        payload = {
            "status": "000",
            "list": [
                {"rcept_no": "r1", "reprt_code": "11014", "bsns_year": "2025", "sj_div": "IS", "account_id": "dart_OperatingIncomeLoss", "account_nm": "영업이익", "currency": "KRW"},
                {"rcept_no": "r1", "reprt_code": "11014", "bsns_year": "2025", "sj_div": "CF", "account_id": "ppe", "account_nm": "유형자산 감가상각비", "currency": "KRW"},
                {"rcept_no": "r1", "reprt_code": "11014", "bsns_year": "2025", "sj_div": "CF", "account_id": "intangible", "account_nm": "무형자산 상각비", "currency": "USD"},
            ],
        }
        evidence = self.tool.summarize_payload(payload, company=company, year=2025, report_code="11014")
        self.assertFalse(evidence["strict_formula_available_at_endpoint"])
        self.assertEqual(evidence["strict_formula_reason"], "incompatible:receipt_scope_currency_or_period")


if __name__ == "__main__":
    unittest.main()
