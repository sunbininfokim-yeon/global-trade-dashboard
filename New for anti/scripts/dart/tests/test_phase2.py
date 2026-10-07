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
        self.assertEqual(c["valuation"]["status"], "inputs_required")
        self.assertIsNone(c["valuation"]["value_band"])
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

    def test_shipping_split_lease_liabilities_require_both_and_are_summed(self):
        from dart_kfa.accounts import load_accounts_map, resolve_accounts

        def row(account_id, amount):
            return {
                "account_id": account_id,
                "account_nm": account_id,
                "sj_div": "BS",
                "thstrm_amount": str(amount),
                "frmtrm_amount": str(amount - 1),
                "bfefrmtrm_amount": str(amount - 2),
                "currency": "KRW",
            }

        current = row("ifrs-full_CurrentLeaseLiabilities", 30)
        noncurrent = row("ifrs-full_NoncurrentLeaseLiabilities", 70)
        complete = resolve_accounts([current, noncurrent], load_accounts_map())["LEASE_LIABILITIES"]
        self.assertEqual(complete["value"], 100)
        self.assertTrue(complete["match"].startswith("sum:"))

        incomplete = resolve_accounts([current], load_accounts_map())["LEASE_LIABILITIES"]
        self.assertIsNone(incomplete["value"])
        self.assertEqual(incomplete["reason"], "missing:aggregation_components:1/2")

    def test_high_debt_without_reported_lease_does_not_claim_ifrs16_explains_leverage(self):
        from dart_kfa.industry import apply_industry_layer

        industry = apply_industry_layer(
            corp={"industry_kit": "shipping"},
            metrics={"debt_ratio": {"value": 500}},
            amounts={"LEASE_LIABILITIES": None},
        )
        self.assertNotIn("lease_inflates_leverage", {flag["id"] for flag in industry["flags"]})
        self.assertIn("LEASE_LIABILITIES", industry["adjustment_status"][0]["reason"])

    def test_non_lease_kit_does_not_emit_lease_adjustment_merely_because_a_value_exists(self):
        from dart_kfa.industry import apply_industry_layer

        industry = apply_industry_layer(
            corp={"industry_kit": "semiconductor"},
            metrics={},
            amounts={"TOTAL_LIABILITIES": 300, "EQUITY": 100, "LEASE_LIABILITIES": 80},
        )
        self.assertEqual(industry["adjusted_metrics"], {})
        self.assertEqual(industry["adjustment_status"], [])

    def test_shipbuilding_contract_liab(self):
        c = analyze_payload(
            load_fixture(FIX_YARD),
            corp={"name": "삼성중공업", "industry_kit": "shipbuilding"},
        )
        # The fixture reports only the current component.  It is not safe to
        # present that as total contract liabilities, so the adjustment stays
        # hidden until current and non-current components (or a total) exist.
        self.assertNotIn("debt_ratio_ex_contract_liab", c["industry"]["adjusted_metrics"])
        self.assertIsNone(c["ma_metrics"]["contract_liab_to_liabilities"]["value"])
        self.assertEqual(
            c["accounts"]["CONTRACT_LIABILITIES"]["reason"],
            "missing:aggregation_components:1/2",
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
                "operating_nwc_to_sales": 0.1,
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
                "operating_nwc_to_sales": 0.1,
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
        common = {
            "projection_years": 5,
            "revenue_cagr": 0.04,
            "ebit_margin": 0.12,
            "tax_rate": 0.25,
            "operating_nwc_to_sales": 0.10,
            "capex_to_sales": 0.08,
            "da_to_sales": 0.05,
            "wacc": 0.09,
            "terminal_growth": 0.02,
        }
        scenarios = [
            {"id": sid, "name_ko": sid, "assumptions": {**common, "revenue_cagr": growth}}
            for sid, growth in (("bear", 0.0), ("base", 0.04), ("bull", 0.08))
        ]
        bundle = run_valuation_bundle(
            revenue0=1e14, ebitda0=1e13, net_debt=0.0, scenarios=scenarios
        )
        ids = {s["scenario_id"] for s in bundle["scenarios"]}
        self.assertTrue({"base", "bull", "bear"}.issubset(ids))
        self.assertIn("fcff_dcf", bundle["models"])
        self.assertIn("ev_ebitda", bundle["models"])
        self.assertEqual(bundle["status"], "scenario")

    def test_seed_uses_only_filing_ratios_and_requires_explicit_forecast(self):
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
        self.assertIsNone(seed["quality_tier"])
        self.assertIsNone(seed["ev_ebitda_multiples"])
        self.assertLess(seed["capex_to_sales"], 0.05)
        self.assertEqual(build_seeded_scenarios(operating_margin_pct=32.0, seed=seed), [])
        sc = build_seeded_scenarios(
            operating_margin_pct=32.0,
            seed=seed,
            explicit_assumptions={
                "projection_years": 5,
                "revenue_cagr": 0.03,
                "ebit_margin": 0.32,
                "tax_rate": seed["tax_rate"],
                "operating_nwc_to_sales": 0.05,
                "capex_to_sales": seed["capex_to_sales"],
                "da_to_sales": seed["da_to_sales"],
                "wacc": 0.09,
                "terminal_growth": 0.02,
            },
        )
        base = next(s for s in sc if s["id"] == "base")
        self.assertAlmostEqual(base["assumptions"]["capex_to_sales"], seed["capex_to_sales"])
        self.assertEqual(base["assumptions"]["wacc"], 0.09)

    def test_default_bundle_does_not_invent_valuation(self):
        bundle = run_valuation_bundle(revenue0=1e14, ebitda0=1e13, net_debt=None)
        self.assertEqual(bundle["status"], "inputs_required")
        self.assertEqual(bundle["scenarios"], [])
        self.assertIsNone(bundle["value_band"])

    def test_per_share_requires_auditable_point_in_time_share_identity(self):
        assumptions = {
            "projection_years": 5,
            "revenue_cagr": 0.04,
            "ebit_margin": 0.12,
            "tax_rate": 0.25,
            "operating_nwc_to_sales": 0.10,
            "capex_to_sales": 0.08,
            "da_to_sales": 0.05,
            "wacc": 0.09,
            "terminal_growth": 0.02,
            "net_debt": 0,
            "shares_out": 100,
            "share_basis": "point_in_time_basic",
        }
        unverified = fcff_dcf(revenue0=1000, assumptions=assumptions)
        self.assertIsNone(unverified["value_per_share"])
        self.assertIn("missing:share_source_ref", unverified["reasons"])

        verified = fcff_dcf(
            revenue0=1000,
            assumptions={
                **assumptions,
                "share_source_ref": "SEC:10-K:0001",
                "share_as_of": "2025-09-27",
                "share_class": "common_stock",
                "dilution_policy": "basic_outstanding_at_period_end",
            },
        )
        self.assertIsNotNone(verified["value_per_share"])

    def test_invalid_explicit_scenario_never_reports_scenario_status(self):
        bundle = run_valuation_bundle(
            revenue0=100,
            ebitda0=10,
            net_debt=None,
            scenarios=[{"id": "bad", "assumptions": {"projection_years": 5}}],
        )
        self.assertEqual(bundle["status"], "blocked_quality")
        self.assertIsNone(bundle["value_band"])


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
