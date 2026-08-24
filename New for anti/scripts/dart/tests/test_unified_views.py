"""Unified Basic / Finance Team / PE / IB contract tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.analyze import analyze_payload
from dart_kfa.fetch import load_fixture
from dart_kfa.view_engine import build_unified_views, get_view_definitions


FIXTURE = ROOT / "tests" / "fixtures" / "samsung_fnltt_sample.json"


def analyzed_industrial() -> dict:
    return analyze_payload(
        load_fixture(FIXTURE),
        corp={"name": "삼성전자", "industry": "C261", "source": "dart", "code": "005930"},
    )


def fully_supported_company() -> dict:
    company = analyzed_industrial()
    company["accounts"]["DEPRECIATION"] = {
        "value": 10.0,
        "match": "id:verified_depreciation",
        "reason": None,
    }
    company["accounts"]["CAPEX"] = {"value": 12.0, "match": "id:verified_capex", "reason": None}
    company["accounts"]["REVENUE"]["value"] = 500.0
    company["metrics"]["operating_margin"]["value"] = 15.0
    company["ma_metrics"].update({
        "fcf": {"value": 50.0, "unit": "currency", "reason": None},
        "fcf_margin": {"value": 10.0, "unit": "pct", "reason": None},
        "ebitda_proxy": {"value": 100.0, "unit": "currency", "reason": None},
        "net_debt": {"value": 200.0, "unit": "currency", "reason": None},
        "net_debt_to_ebitda": {"value": 2.0, "unit": "x", "reason": None},
    })
    company["assumption_defaults"]["seeded_from_statements"].update({
        "capex_to_sales": 0.024,
        "da_to_sales": 0.02,
        "operating_nwc_to_sales": 0.10,
        "tax_rate": 0.25,
    })
    return company


class DefinitionContractTest(unittest.TestCase):
    def test_exact_view_ids_and_beginner_explanations(self):
        definitions = get_view_definitions()
        self.assertEqual(list(definitions["views"]), ["basic", "finance_team", "pe", "ib"])
        self.assertEqual(definitions["default_view"], "basic")
        self.assertEqual(definitions["views"]["basic"]["audience"], "beginner")
        self.assertTrue(definitions["cards"]["revenue"]["explain_ko"])

    def test_sec_and_dart_consume_identical_definitions_and_cards(self):
        dart_company = analyzed_industrial()
        sec_company = deepcopy(dart_company)
        dart_company["source"] = "opendart"
        sec_company["source"] = "sec_companyfacts"
        dart = build_unified_views(dart_company)
        sec = build_unified_views(sec_company)
        self.assertEqual(dart["definitions_version"], sec["definitions_version"])
        self.assertEqual(dart["card_registry"], sec["card_registry"])
        self.assertEqual(dart["views"], sec["views"])
        self.assertEqual(dart["audit"]["source_adapter"], "opendart")
        self.assertEqual(sec["audit"]["source_adapter"], "sec_companyfacts")


class VisibilityContractTest(unittest.TestCase):
    def test_cards_exist_once_and_views_only_reference_ids(self):
        company = analyzed_industrial()
        contract = company["unified_views"]
        self.assertIn("revenue", contract["card_registry"])
        for view in contract["views"].values():
            self.assertNotIn("cards", view)
            self.assertTrue(all(ref in contract["card_registry"] for ref in view["card_refs"]))
            self.assertTrue(all(ref in contract["model_registry"] for ref in view["model_refs"]))

    def test_missing_cards_are_not_placeholders_but_are_audited(self):
        contract = build_unified_views(analyzed_industrial())
        self.assertNotIn("maintenance_capex_burden", contract["card_registry"])
        self.assertNotIn("segment", contract["card_registry"])
        self.assertNotIn("full_qoe", contract["card_registry"])
        omitted = {item["id"] for item in contract["audit"]["card_omissions"]}
        self.assertTrue({"maintenance_capex_burden", "segment", "full_qoe"}.issubset(omitted))

    def test_financial_entity_omits_fcf_and_all_industrial_models(self):
        company = analyze_payload(
            load_fixture(FIXTURE),
            corp={"name": "KB금융", "corp_code": "00688996", "industry": "K64"},
        )
        contract = build_unified_views(company, user_inputs={"market_cap": {"value": 1000.0, "currency": "KRW"}})
        self.assertEqual(set(contract["card_registry"]), {
            "operating_income", "net_income", "total_assets", "equity", "roe", "roa",
        })
        self.assertEqual(contract["model_registry"], {})
        self.assertTrue(all("fcf" not in view["card_refs"] for view in contract["views"].values()))
        self.assertTrue(any(item["id"] == "fcf" and item["status"] == "not_applicable" for item in contract["audit"]["card_omissions"]))

    def test_unverified_comps_segments_qoe_and_sotp_are_hidden(self):
        contract = build_unified_views(
            fully_supported_company(),
            user_inputs={
                "market_cap": {"value": 1000.0, "currency": "KRW"},
                "verified_peer_multiples": {"items": [{"pe": 10.0}]},
                "verified_segments": {"items": [{"enterprise_value": 500.0}]},
            },
        )
        for card_id in ("trading_comps", "segment", "full_qoe"):
            self.assertNotIn(card_id, contract["card_registry"])
        for model_id in ("trading_comps", "sotp"):
            self.assertNotIn(model_id, contract["model_registry"])


class SupportedModelsTest(unittest.TestCase):
    def test_display_fx_never_changes_model_calculation_currency(self):
        company = fully_supported_company()
        company["source"] = "sec_companyfacts"
        company["currency"] = "USD"
        for account in company["accounts"].values():
            account["currency"] = "USD"
        contract = build_unified_views(
            company,
            user_inputs={
                "display_currency": "KRW",
                "fx": {"rate": 1350, "source": "official_fx_snapshot", "as_of": "2026-08-20"},
                "market_cap": {"value": 1000.0, "currency": "USD", "source": "test_quote", "as_of": "2026-08-20"},
                "delever_assumptions": {"fcf_retention": 0.75, "horizon_years": 2},
            },
        )
        self.assertEqual(contract["currency"]["calculation_currency"], "USD")
        self.assertEqual(contract["card_registry"]["fcf"]["value"], 67500.0)
        self.assertEqual(contract["card_registry"]["ev_bridge"]["value"]["enterprise_value"], 1620000.0)
        model = contract["model_registry"]["delever_path"]
        self.assertEqual(model["calculation_currency"], "USD")
        self.assertEqual(model["components"]["path"][0]["net_debt"], 200.0)

    def test_unlabelled_market_cap_is_omitted_not_mixed_with_filing_amounts(self):
        contract = build_unified_views(
            fully_supported_company(),
            user_inputs={"market_cap": 1000.0},
        )
        model = contract["model_registry"]["fcf_yield_snapshot"]
        self.assertEqual(model["status"], "needs_input")
        self.assertEqual(model["reason"], "input:market_cap_required_for_fcf_yield")
        omission = next(item for item in contract["audit"]["card_omissions"] if item["id"] == "ev_bridge")
        self.assertEqual(omission["reason"], "missing:monetary_input_currency")

    def test_liquidity_delever_and_fcf_yield_are_computed(self):
        contract = build_unified_views(
            fully_supported_company(),
            user_inputs={
                "market_cap": {"value": 1000.0, "currency": "KRW"},
                "delever_assumptions": {"fcf_retention": 0.75, "horizon_years": 5},
            },
        )
        self.assertIn(contract["model_registry"]["liquidity_coverage"]["status"], {"computed", "partial"})
        self.assertEqual(contract["model_registry"]["delever_path"]["status"], "computed")
        self.assertEqual(contract["model_registry"]["fcf_yield_snapshot"]["status"], "computed")
        self.assertEqual(contract["card_registry"]["maintenance_capex_burden"]["estimate"]["kind"], "proxy")

    def test_delever_path_never_invents_retention_or_horizon(self):
        contract = build_unified_views(fully_supported_company())
        model = contract["model_registry"]["delever_path"]
        self.assertEqual(model["status"], "needs_input")
        self.assertEqual(set(model["required_inputs"]), {"fcf_retention", "horizon_years"})

    def test_only_actionable_dcf_gap_is_visible_as_needs_input(self):
        contract = build_unified_views(fully_supported_company())
        self.assertEqual(contract["model_registry"]["reverse_dcf"]["status"], "needs_input")
        self.assertEqual(contract["model_registry"]["fcf_yield_snapshot"]["status"], "needs_input")
        self.assertEqual(contract["model_registry"]["scenario_dcf_ev_bridge"]["status"], "needs_input")
        self.assertNotIn("trading_comps", contract["model_registry"])
        self.assertNotIn("sotp", contract["model_registry"])

    def test_reverse_dcf_and_scenario_dcf_ev_bridge_compute_with_explicit_inputs(self):
        inputs = {
            "market_cap": {"value": 1000.0, "currency": "KRW", "source": "test_quote", "as_of": "2026-08-20"},
            "valuation_assumptions": {
                "projection_years": 5,
                "revenue_cagr": 0.04,
                "ebit_margin": 0.15,
                "tax_rate": 0.25,
                "operating_nwc_to_sales": 0.10,
                "capex_to_sales": 0.024,
                "da_to_sales": 0.02,
                "wacc": 0.09,
                "terminal_growth": 0.02,
            },
        }
        contract = build_unified_views(fully_supported_company(), user_inputs=inputs)
        reverse = contract["model_registry"]["reverse_dcf"]
        scenario = contract["model_registry"]["scenario_dcf_ev_bridge"]
        self.assertIn(reverse["status"], {"computed", "partial"})
        self.assertIn(scenario["status"], {"computed", "partial"})
        self.assertEqual(reverse["estimate"]["kind"], "reverse_solve")
        self.assertEqual(scenario["estimate"]["kind"], "scenario_assumption")
        self.assertFalse(scenario["estimate"]["is_price_target"])

    def test_verified_comps_and_sotp_use_only_supplied_observations(self):
        inputs = {
            "verified_peer_multiples": {
                "status": "verified",
                "items": [
                    {"source": "exchange", "as_of": "2026-08-20", "pe": 10.0, "ev_ebitda": 7.0},
                    {"source": "exchange", "as_of": "2026-08-20", "pe": 14.0, "ev_ebitda": 9.0},
                ],
            },
            "verified_segments": {
                "status": "verified",
                "items": [
                    {"id": "a", "name": "A", "source": "filing", "as_of": "2025-12-31", "enterprise_value": 600.0, "currency": "KRW"},
                    {"id": "b", "name": "B", "source": "filing", "as_of": "2025-12-31", "metric_value": 50.0, "multiple": 8.0, "currency": "KRW"},
                ],
            },
        }
        contract = build_unified_views(fully_supported_company(), user_inputs=inputs)
        self.assertEqual(contract["model_registry"]["trading_comps"]["value"]["median"]["pe"], 12.0)
        self.assertEqual(contract["model_registry"]["sotp"]["value"]["gross_segment_ev"], 1000.0)
        self.assertFalse(contract["model_registry"]["sotp"]["estimate"]["assumptions"]["discount_applied"])

    def test_invalid_scenario_assumptions_are_audited_not_raised(self):
        contract = build_unified_views(
            fully_supported_company(),
            user_inputs={
                "valuation_assumptions": {
                    "projection_years": 5,
                    "revenue_cagr": 2.0,
                    "ebit_margin": 0.15,
                    "tax_rate": 0.25,
                    "operating_nwc_to_sales": 0.10,
                    "capex_to_sales": 0.024,
                    "da_to_sales": 0.02,
                    "wacc": 0.09,
                    "terminal_growth": 0.02,
                }
            },
        )
        self.assertNotIn("scenario_dcf_ev_bridge", contract["model_registry"])
        omission = next(
            item for item in contract["audit"]["model_omissions"]
            if item["id"] == "scenario_dcf_ev_bridge"
        )
        self.assertTrue(omission["reason"].startswith("invalid:scenario_assumptions:"))


if __name__ == "__main__":
    unittest.main()
