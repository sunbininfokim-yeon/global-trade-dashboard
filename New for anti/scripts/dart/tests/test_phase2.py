"""Phase-2 tests: industry kits, M&A metrics, valuation presets."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.analyze import analyze_payload
from dart_kfa.fetch import load_fixture
from dart_kfa.valuation import fcff_dcf, run_valuation_bundle

FIX_SAMSUNG = ROOT / "tests" / "fixtures" / "samsung_fnltt_sample.json"
FIX_SHIP = ROOT / "tests" / "fixtures" / "shipping_fnltt_sample.json"
FIX_YARD = ROOT / "tests" / "fixtures" / "shipbuilding_fnltt_sample.json"


class TestIndustryKits(unittest.TestCase):
    def test_electronics_kit(self):
        c = analyze_payload(
            load_fixture(FIX_SAMSUNG),
            corp={
                "name": "삼성전자",
                "industry_kit": "semiconductor",
                "industry": "C261",
                "code": "005930",
            },
        )
        self.assertEqual(c["industry"]["industry_kit"], "semiconductor")
        self.assertIsNotNone(c["assumption_defaults"]["current_operating_margin_pct"])
        self.assertIn("fcf", c["ma_metrics"])
        self.assertIsNotNone(c["valuation"]["value_band"])
        self.assertTrue(c["industry"]["bok_peer"]["vs"]["available"])
        self.assertIn("current_ratio", c["industry"]["bok_peer"]["vs"]["metrics"])
        self.assertTrue(c["industry"]["background"].get("headline_ko"))

    def test_ksic_longest_prefix(self):
        from dart_kfa.industry import resolve_kit_id

        self.assertEqual(resolve_kit_id({"industry": "C261"}), "semiconductor")
        self.assertEqual(resolve_kit_id({"industry": "C26"}), "electronics_components")

    def test_shipping_lease_adjustment(self):
        c = analyze_payload(
            load_fixture(FIX_SHIP),
            corp={"name": "HMM", "industry_kit": "shipping"},
        )
        self.assertEqual(c["industry"]["industry_kit"], "shipping")
        flags = {f["id"] for f in c["industry"]["flags"]}
        self.assertIn("lease_inflates_leverage", flags)
        self.assertIn("debt_ratio_ex_lease", c["industry"]["adjusted_metrics"])
        self.assertIsNotNone(c["ma_metrics"]["lease_to_liabilities"]["value"])

    def test_shipbuilding_contract_liab(self):
        c = analyze_payload(
            load_fixture(FIX_YARD),
            corp={"name": "삼성중공업", "industry_kit": "shipbuilding"},
        )
        self.assertIn("debt_ratio_ex_contract_liab", c["industry"]["adjusted_metrics"])
        self.assertGreater(
            c["ma_metrics"]["contract_liab_to_liabilities"]["value"], 15
        )


class TestValuation(unittest.TestCase):
    def test_dcf_monotonic_wacc(self):
        low = fcff_dcf(
            revenue0=100.0,
            assumptions={
                "projection_years": 5,
                "revenue_cagr": 0.05,
                "ebit_margin": 0.1,
                "tax_rate": 0.25,
                "sales_to_nwc": 0.1,
                "capex_to_sales": 0.05,
                "da_to_sales": 0.03,
                "wacc": 0.08,
                "terminal_growth": 0.02,
                "net_debt": 0,
            },
        )
        high = fcff_dcf(
            revenue0=100.0,
            assumptions={
                "projection_years": 5,
                "revenue_cagr": 0.05,
                "ebit_margin": 0.1,
                "tax_rate": 0.25,
                "sales_to_nwc": 0.1,
                "capex_to_sales": 0.05,
                "da_to_sales": 0.03,
                "wacc": 0.12,
                "terminal_growth": 0.02,
                "net_debt": 0,
            },
        )
        self.assertTrue(low["ok"] and high["ok"])
        self.assertGreater(low["enterprise_value"], high["enterprise_value"])

    def test_bundle_has_three_scenarios(self):
        bundle = run_valuation_bundle(revenue0=1e14, ebitda0=1e13, net_debt=0.0)
        ids = {s["scenario_id"] for s in bundle["scenarios"]}
        self.assertTrue({"base", "bull", "bear"}.issubset(ids))
        self.assertIn("fcff_dcf", bundle["models"])
        self.assertIn("ev_ebitda", bundle["models"])

    def test_seed_asset_light_uses_quality_multiples(self):
        from dart_kfa.valuation import seed_from_statements, build_seeded_scenarios

        seed = seed_from_statements(
            {
                "REVENUE": 400e9,
                "CAPEX": 12e9,
                "DEPRECIATION": 11e9,
                "CURRENT_ASSETS": 140e9,
                "CURRENT_LIABILITIES": 160e9,
                "INCOME_TAX_EXPENSE": 20e9,
                "PROFIT_BEFORE_TAX": 130e9,
            },
            operating_margin_pct=32.0,
            fcf=120e9,
        )
        self.assertEqual(seed["quality_tier"], "asset_light_high_margin")
        self.assertLess(seed["capex_to_sales"], 0.05)
        sc = build_seeded_scenarios(operating_margin_pct=32.0, seed=seed)
        base = next(s for s in sc if s["id"] == "base")
        self.assertAlmostEqual(base["assumptions"]["capex_to_sales"], seed["capex_to_sales"])
        self.assertGreaterEqual(base["assumptions"]["ev_ebitda_multiple"], 20.0)


class TestFundamentalPack(unittest.TestCase):
    def test_pack_on_samsung_fixture(self):
        c = analyze_payload(
            load_fixture(FIX_SAMSUNG),
            corp={
                "name": "삼성전자",
                "industry_kit": "semiconductor",
                "industry": "C261",
                "code": "005930",
            },
        )
        pack = c["fundamental_pack"]
        self.assertEqual(pack["style"], "practitioner_desk")
        ids = {s["id"] for s in pack["scorecard"]}
        self.assertTrue({"growth", "profitability", "cash_conversion", "leverage", "returns"}.issubset(ids))
        self.assertTrue(pack["trend_3y"]["rows"])
        self.assertIn("fcf", pack["cash_bridge"])
        self.assertIn("net_debt_to_ebitda", pack["leverage_bridge"])

if __name__ == "__main__":
    unittest.main()
