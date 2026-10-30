"""P1 role-model safety and computation contracts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.p1_disclosures import build_p1_disclosures  # noqa: E402
from dart_kfa.p1_models import build_p1_models  # noqa: E402


def fact(account: str, value: float, *, nature: str = "flow", currency: str = "KRW") -> dict:
    return {
        "account_id": account,
        "value": value,
        "availability": "available",
        "quality": "reported",
        "reason": None,
        "source": "DART",
        "source_concept": "fixture_" + account.lower(),
        "statement": "BS" if nature == "balance" else "IS",
        "nature": nature,
        "fiscal_year": 2025,
        "fiscal_quarter": None,
        "period_kind": "balance_point_in_time" if nature == "balance" else "flow_annual",
        "period_start": None if nature == "balance" else "2025-01-01",
        "period_end": "2025-12-31",
        "report_code": "11011",
        "report_type": "business_report",
        "fs_div": "CFS",
        "unit": {"kind": "currency", "currency": currency, "scale": 1},
        "provenance": {"filing_id": "fixture-11011"},
    }


def canonical(*, include_components: bool = True) -> dict:
    flow = {
        "REVENUE": 1_000,
        "OPERATING_INCOME": 100,
        "CFO": 150,
        "CAPEX": -60,
        "INTEREST_EXPENSE": -10,
    }
    if include_components:
        flow.update({"PPE_DEPRECIATION": 40, "INTANGIBLE_AMORTIZATION": 20})
    balance = {
        "CASH": 50,
        "MARKETABLE_SECURITIES_CURRENT": 10,
        "MARKETABLE_SECURITIES_NONCURRENT": 5,
        "SHORT_TERM_DEBT": 100,
        "LONG_TERM_DEBT_CURRENT": 20,
        "LONG_TERM_DEBT_NONCURRENT": 80,
    }
    series = {
        account: {"annual": fact(account, value), "quarters": {}}
        for account, value in flow.items()
    }
    series.update({
        account: {"annual": fact(account, value, nature="balance"), "quarters": {}}
        for account, value in balance.items()
    })
    return {
        "schema_version": "canonical-financial-facts/1",
        "source": "DART",
        "entity_id": "fixture",
        "fiscal_year": 2025,
        "fs_div": "CFS",
        "currency": "KRW",
        "series": series,
    }


def inputs() -> dict:
    return {
        "assumptions": {
            "maintenance_capex": 30,
            "owner_earnings_hurdle": 0.10,
            "fcf_retention": 0.7,
            "horizon_years": 3,
            "projection_years": 5,
            "revenue_cagr": 0.03,
            "ebit_margin": 0.10,
            "tax_rate": 0.25,
            "operating_nwc_to_sales": 0.10,
            "capex_to_sales": 0.06,
            "da_to_sales": 0.04,
            "wacc": 0.09,
            "terminal_growth": 0.02,
        },
        "market": {"market_cap": 1_000, "currency": "KRW", "as_of": "2026-08-27", "source": "fixture"},
        "verified_peer_multiples": [
            {"id": "a", "pe": 10, "ev_ebitda": 7, "as_of": "2026-08-27", "source": "fixture"},
            {"id": "b", "pe": 14, "ev_ebitda": 9, "as_of": "2026-08-27", "source": "fixture"},
        ],
        "verified_segments": [
            {"id": "core", "enterprise_value": 900, "currency": "KRW", "as_of": "2026-08-27", "source": "fixture"},
        ],
    }


class P1RoleModelsTest(unittest.TestCase):
    def test_all_nine_models_compute_only_with_explicit_inputs_and_strict_ebitda(self):
        source = canonical()
        result = build_p1_models(source, p1_disclosures=build_p1_disclosures(source), inputs=inputs())
        models = result["models"]
        self.assertEqual(models["oe_hurdle"]["value"], 1200)
        self.assertAlmostEqual(models["oe_yield"]["value"], 0.12)
        self.assertEqual(models["reverse_dcf"]["status"], "computed")
        self.assertEqual(models["delever_path"]["status"], "computed")
        self.assertEqual(models["coverage_capacity"]["value"], 16)
        self.assertEqual(models["fcf_yield_entry"]["status"], "computed")
        self.assertEqual(models["fcff_dcf"]["status"], "computed")
        self.assertEqual(models["trading_comps"]["value"]["pe"], 12)
        self.assertEqual(models["sotp_or_ev_bridge"]["value"]["equity_value"], 765)
        self.assertEqual(models["delever_path"]["components"]["strict_ebitda"], 160)
        self.assertEqual(models["delever_path"]["currency_policy"], "filing_currency_only")

    def test_pe_models_refuse_combined_or_missing_da_even_if_legacy_proxy_could_exist(self):
        source = canonical(include_components=False)
        result = build_p1_models(source, p1_disclosures=build_p1_disclosures(source), inputs=inputs())
        self.assertEqual(result["models"]["delever_path"]["status"], "omitted")
        self.assertIn("strict_ebitda_inputs", result["models"]["delever_path"]["reason"])
        self.assertEqual(result["models"]["coverage_capacity"]["status"], "omitted")

    def test_market_currency_mismatch_is_not_converted_inside_the_model(self):
        source = canonical()
        supplied = inputs()
        supplied["market"]["currency"] = "USD"
        result = build_p1_models(source, p1_disclosures=build_p1_disclosures(source), inputs=supplied)
        self.assertEqual(result["models"]["oe_yield"]["status"], "omitted")
        self.assertEqual(result["models"]["oe_yield"]["reason"], "incompatible:market_cap_currency_requires_explicit_fx_contract")

    def test_financial_entities_are_not_given_industrial_models(self):
        source = canonical()
        result = build_p1_models(
            source,
            p1_disclosures=build_p1_disclosures(source),
            entity_policy={"is_financial_entity": True},
            inputs=inputs(),
        )
        self.assertTrue(all(model["status"] == "not_applicable" for model in result["models"].values()))


if __name__ == "__main__":
    unittest.main()
