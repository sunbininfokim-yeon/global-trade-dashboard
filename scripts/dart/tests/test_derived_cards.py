"""Regression tests for KFA expert cards and model contracts.

The fixture is deliberately self-contained: it is a normalised, annual,
consolidated industrial issuer and contains no live API dependency.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from dart_kfa.derived_cards import derive_interest_coverage, enrich_snapshot, run_kfa_analysis


def _cell(value, series):
    return {"value": value, "series": series}


def _annual(values):
    return [
        {"year": year, "end": f"{year}-12-31", "value": value}
        for year, value in values
    ]


def full_pack():
    return {
        "as_of": "2025-12-31",
        "currency": "USD",
        "pnl": {
            "revenue": _cell(1210.0, _annual([(2023, 1000.0), (2024, 1100.0), (2025, 1210.0)])),
            "operating_income": _cell(205.0, _annual([(2023, 150.0), (2024, 176.0), (2025, 205.0)])),
            "ebitda": _cell(265.0, _annual([(2023, 205.0), (2024, 235.0), (2025, 265.0)])),
            "net_income": _cell(140.0, _annual([(2023, 100.0), (2024, 120.0), (2025, 140.0)])),
            "profit_before_tax": _cell(175.0, _annual([(2023, 125.0), (2024, 150.0), (2025, 175.0)])),
            "income_tax_expense": _cell(35.0, _annual([(2023, 25.0), (2024, 30.0), (2025, 35.0)])),
            "effective_tax_rate": _cell(0.20, _annual([(2023, 0.20), (2024, 0.20), (2025, 0.20)])),
        },
        "cash_flow": {
            "cfo": _cell(190.0, _annual([(2023, 135.0), (2024, 165.0), (2025, 190.0)])),
            "fcf": _cell(110.0, _annual([(2023, 60.0), (2024, 85.0), (2025, 110.0)])),
            "capex": _cell(80.0, _annual([(2023, 75.0), (2024, 80.0), (2025, 80.0)])),
            "depreciation_and_amortization": _cell(60.0, _annual([(2023, 55.0), (2024, 58.0), (2025, 60.0)])),
        },
        "liquidity": {"interest_coverage": _cell(8.0, _annual([(2023, 6.0), (2024, 7.0), (2025, 8.0)]))},
        "debt_structure": {"net_debt": _cell(400.0, _annual([(2023, 500.0), (2024, 450.0), (2025, 400.0)]))},
        "working_capital": {
            "net_working_capital": _cell(120.0, _annual([(2023, 100.0), (2024, 110.0), (2025, 120.0)])),
            "nwc_to_sales": _cell(None, []),
        },
    }


class DerivedCardsTest(unittest.TestCase):
    def test_all_expert_cards_and_models_use_reported_normalised_inputs(self):
        analysis = run_kfa_analysis(
            full_pack(),
            {"market_cap": 2200.0},
            [
                {"id": "a", "name": "Segment A", "enterprise_value": 1500.0},
                {"id": "b", "name": "Segment B", "enterprise_value": 900.0},
            ],
        )
        cards = analysis["cards"]
        expected = {
            "owner_earnings", "earnings_quality", "margins_trend", "capex_to_da", "net_debt_to_oe",
            "ebitda_or_op", "net_debt_to_ebitda", "fcf_to_ebitda", "maint_capex_burden", "nwc_change_to_sales",
            "ebitda", "trading_multiples", "ev_bridge", "qoe_flags", "segment", "nwc_to_sales",
        }
        self.assertEqual(set(cards), expected)
        # OE = NI + D&A − min(D&A, Capex) = NI where Capex exceeds D&A.
        self.assertAlmostEqual(cards["owner_earnings"]["value"], 140.0)
        self.assertAlmostEqual(cards["earnings_quality"]["value"], 190.0 / 140.0)
        self.assertAlmostEqual(cards["net_debt_to_ebitda"]["value"], 400.0 / 265.0)
        self.assertAlmostEqual(cards["nwc_change_to_sales"]["value"], 10.0 / 1210.0)

        models = analysis["models"]
        self.assertEqual(set(models["investor"]), {"oe_hurdle", "reverse_dcf", "oe_yield"})
        self.assertEqual(set(models["pe"]), {"delever_path", "coverage_capacity", "fcf_yield_entry"})
        self.assertEqual(set(models["deal"]), {"fcff_dcf", "trading_comps", "sotp_or_ev_bridge"})
        self.assertEqual(models["deal"]["fcff_dcf"]["status"], "ok")
        self.assertEqual(len(models["deal"]["fcff_dcf"]["components"]["scenarios"]), 3)
        self.assertEqual(len(models["deal"]["fcff_dcf"]["components"]["wacc_sensitivity"]), 5)
        self.assertEqual(models["deal"]["sotp_or_ev_bridge"]["status"], "ok")
        self.assertNotIn("not_computed", json.dumps(models))
        self.assertNotIn("value_per_share", json.dumps(models))
        self.assertNotIn("target_price", json.dumps(models))

    def test_misaligned_periods_are_not_ratioed_together(self):
        pack = full_pack()
        pack["cash_flow"]["cfo"]["series"][-1]["end"] = "2025-09-30"
        cards = run_kfa_analysis(pack, {"market_cap": 2200.0})["cards"]
        years = [row["year"] for row in cards["earnings_quality"]["series"]]
        self.assertNotIn(2025, years)
        self.assertEqual(cards["earnings_quality"]["reason"], "period_mismatch_rows_excluded")

    def test_interest_coverage_needs_reported_interest_expense_and_aligned_periods(self):
        pack = full_pack()
        pack["liquidity"]["interest_coverage"] = _cell(None, [])
        pack["pnl"]["interest_expense"] = _cell(25.0, _annual([(2023, 25.0), (2024, 25.0), (2025, 25.0)]))
        result = derive_interest_coverage(pack)
        self.assertAlmostEqual(result["value"], 205.0 / 25.0)
        self.assertEqual(len(result["series"]), 3)
        self.assertIsNone(result["reason"])

        pack["pnl"]["interest_expense"]["series"][-1]["end"] = "2025-09-30"
        result = derive_interest_coverage(pack)
        self.assertEqual([row["year"] for row in result["series"]], [2023, 2024])

    def test_sample_snapshot_is_marked_as_snapshot_derived_not_live_filing_facts(self):
        root = Path(__file__).resolve().parents[3]
        sample_path = root / "New for anti" / "public" / "data" / "kfa_005930_v1.json"
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        enriched = enrich_snapshot(payload)
        self.assertEqual(enriched["as_of"], "2025-12-31")
        self.assertEqual(enriched["data_quality"]["input_kind"], "snapshot_derived")
        self.assertFalse(enriched["data_quality"]["raw_filing_facts_embedded"])
        self.assertEqual(
            enriched["basic_cards"]["interest_coverage"]["reason"],
            "missing:interest_expense_unmapped_from_snapshot",
        )
        self.assertAlmostEqual(enriched["basic_cards"]["earnings_quality"]["value"], 1.8872191476482356)
        self.assertIsNone(enriched["basic_cards"]["owner_earnings"]["value"])
        self.assertEqual(enriched["basic_cards"]["owner_earnings"]["reason"], "missing:depreciation_and_amortization")


if __name__ == "__main__":
    unittest.main()
