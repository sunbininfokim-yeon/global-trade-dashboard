"""KFA-Engine unit tests (fixture only — no API key required)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.accounts import amounts_only, normalize_name, resolve_accounts
from dart_kfa.analyze import analyze_payload
from dart_kfa.fetch import load_fixture, rows_from_payload
from dart_kfa.metrics import compute_metrics, eval_expr
from dart_kfa.validate import validate_accounts

FIXTURE = ROOT / "tests" / "fixtures" / "samsung_fnltt_sample.json"


class TestNormalize(unittest.TestCase):
    def test_spaces_and_parens(self):
        self.assertEqual(normalize_name("영업이익(손실)"), normalize_name("영업이익 손실"))


class TestAccounts(unittest.TestCase):
    def setUp(self):
        self.payload = load_fixture(FIXTURE)
        self.rows = rows_from_payload(self.payload)
        self.resolved = resolve_accounts(self.rows)

    def test_id_match_current_assets(self):
        ca = self.resolved["CURRENT_ASSETS"]
        self.assertEqual(ca["match"], "id:ifrs-full_CurrentAssets")
        self.assertEqual(ca["value"], 227_000_000_000_000)

    def test_balance_identity(self):
        amts = amounts_only(self.resolved)
        gate = validate_accounts(amts)
        self.assertEqual(gate["parse_status"], "verified")
        self.assertTrue(gate["identity_ok"])


class TestMetrics(unittest.TestCase):
    def setUp(self):
        rows = rows_from_payload(load_fixture(FIXTURE))
        self.amounts = amounts_only(resolve_accounts(rows))

    def test_current_ratio(self):
        m = compute_metrics(self.amounts)
        # 227 / 75 * 100 = 302.666...
        self.assertAlmostEqual(m["current_ratio"]["value"], 302.6667, places=3)
        self.assertIsNone(m["current_ratio"]["reason"])

    def test_roe(self):
        m = compute_metrics(self.amounts)
        # 25.5e12 / 355e12 * 100 ≈ 7.1831
        self.assertAlmostEqual(m["roe"]["value"], 7.1831, places=3)

    def test_missing_stays_null(self):
        amts = dict(self.amounts)
        amts["INVENTORIES"] = None
        m = compute_metrics(amts)
        self.assertIsNone(m["quick_ratio"]["value"])
        self.assertIn("missing:INVENTORIES", m["quick_ratio"]["reason"])
        # unrelated metric still works
        self.assertIsNotNone(m["current_ratio"]["value"])

    def test_div_by_zero(self):
        val, reason = eval_expr(["A", "/", "B"], {"A": 1.0, "B": 0.0})
        self.assertIsNone(val)
        self.assertEqual(reason, "div_by_zero")


class TestAnalyze(unittest.TestCase):
    def test_end_to_end(self):
        company = analyze_payload(
            load_fixture(FIXTURE),
            corp={"name": "삼성전자", "industry": "C26"},
        )
        self.assertEqual(company["schema_version"], "dart-company-v1")
        self.assertEqual(company["parse_status"], "verified")
        self.assertEqual(company["corp"]["code"], "005930")
        self.assertEqual(company["period"]["year"], 2024)
        self.assertTrue(any("유동비율" in line for line in company["narrative"]))
        self.assertTrue(company["metrics"]["current_ratio"]["trend_3y"])
        self.assertIn("ma_metrics", company)
        self.assertIn("valuation", company)

    def test_unverified_when_identity_breaks(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for row in payload["list"]:
            if row.get("account_id") == "ifrs-full_Assets":
                row["thstrm_amount"] = "1"
        company = analyze_payload(payload)
        self.assertEqual(company["parse_status"], "unverified")


if __name__ == "__main__":
    unittest.main()
