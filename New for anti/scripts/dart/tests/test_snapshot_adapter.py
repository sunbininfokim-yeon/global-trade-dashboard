"""P0 static JSON output contract tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.snapshot_adapter import (  # noqa: E402
    SNAPSHOT_CONTRACT,
    build_kfa_snapshot,
    build_kfa_snapshot_from_dart_filings,
    enrich_legacy_snapshot,
)


def company(year: int, revenue: float, *, financial: bool = False) -> dict:
    policy = {
        "is_financial_entity": financial,
        "entity_class": "bank" if financial else "industrial_or_unknown",
    }
    return {
        "source": "opendart",
        "corp": {"corp_code": "00126380", "stock_code": "005930", "name": "테스트", "entity_policy": policy},
        "entity_policy": policy,
        "period": {"year": year, "selected": "annual", "start": f"{year}-01-01", "end": f"{year}-12-31", "fs_div": "CFS"},
        "canonical_audit": {"currency": "KRW"},
        "accounts": {
            "REVENUE": {"value": revenue, "reason": None, "quality": "reported", "provenance": {"rcept_no": f"r-{year}"}},
            "OPERATING_INCOME": {"value": revenue / 10, "reason": None, "quality": "reported", "provenance": {"rcept_no": f"r-{year}"}},
            "NET_INCOME": {"value": revenue / 20, "reason": None, "quality": "reported", "provenance": {"rcept_no": f"r-{year}"}},
            "CFO": {"value": revenue / 8, "reason": None, "quality": "reported", "provenance": {"rcept_no": f"r-{year}"}},
            "CASH": {"value": revenue / 4, "reason": None, "quality": "reported", "provenance": {"rcept_no": f"r-{year}"}},
        },
        "ma_metrics": {
            "fcf": {"value": revenue / 16, "reason": None},
            "net_debt": {"value": revenue / 5, "reason": None},
            "interest_coverage": {"value": 4.0, "reason": None},
        },
        "metrics": {
            "current_ratio": {"value": 2.0, "reason": None},
            "debt_ratio": {"value": 0.5, "reason": None},
        },
        "unified_views": {
            "model_registry": {
                "scenario_dcf_ev_bridge": {"status": "needs_input", "value": None, "assumptions": {}},
            }
        },
    }


class SnapshotAdapterTest(unittest.TestCase):
    def test_preserves_legacy_card_shape_and_adds_audit_contract(self):
        snapshot = build_kfa_snapshot([company(2023, 100), company(2024, 120), company(2025, 150)])
        self.assertEqual(snapshot["schema"], "kfa_engine_v1")
        self.assertEqual(snapshot["snapshot_contract"], SNAPSHOT_CONTRACT)
        self.assertEqual(snapshot["currency_contract"]["calculation_currency"], "KRW")
        self.assertEqual(snapshot["currency_contract"]["display_currency"], "KRW")
        card = snapshot["basic_cards"]["revenue"]
        self.assertEqual(card["value"], 150)
        self.assertEqual([row["year"] for row in card["series"]], [2023, 2024, 2025])
        self.assertIn("reason", card)
        self.assertEqual(card["value_kind"], "direct")
        self.assertEqual(card["period_lineage"][-1]["observation_kind"], "direct")
        self.assertEqual(snapshot["period_lineage"]["quarterly"]["status"], "not_materialized_in_annual_snapshot")

    def test_static_export_never_computes_a_model_without_explicit_inputs(self):
        item = company(2025, 150)
        item["unified_views"]["model_registry"]["scenario_dcf_ev_bridge"] = {
            "status": "computed", "value": 123.0, "assumptions": {},
        }
        snapshot = build_kfa_snapshot([item])
        model = snapshot["unified_views"]["model_registry"]["scenario_dcf_ev_bridge"]
        self.assertEqual(model["status"], "omitted")
        self.assertIsNone(model["value"])

    def test_history_is_not_interpolated(self):
        snapshot = build_kfa_snapshot([company(2025, 150)])
        card = snapshot["basic_cards"]["revenue"]
        self.assertEqual(len(card["series"]), 1)
        self.assertEqual(card["history_reason"], "insufficient:reported_annual_history:1_of_3")
        self.assertTrue(snapshot["data_quality"]["no_interpolation"])

    def test_financial_entity_gates_industrial_cards(self):
        snapshot = build_kfa_snapshot([company(2025, 150, financial=True)])
        for key in ("fcf", "net_debt", "interest_coverage"):
            self.assertIsNone(snapshot["basic_cards"][key]["value"])
            self.assertEqual(snapshot["basic_cards"][key]["value_kind"], "not_applicable")
        model = snapshot["unified_views"]["model_registry"]["scenario_dcf_ev_bridge"]
        self.assertEqual(model["status"], "not_applicable")

    def test_legacy_migration_does_not_keep_operating_income_as_ebitda(self):
        path = ROOT.parents[1] / "public" / "data" / "kfa_000660_v1.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        migrated = enrich_legacy_snapshot(original)
        self.assertEqual(migrated["snapshot_contract"], SNAPSHOT_CONTRACT)
        self.assertIsNone(migrated["basic_cards"]["ebitda"]["value"])
        self.assertEqual(
            migrated["basic_cards"]["ebitda"]["reason"],
            "missing:reported_ppe_depreciation_and_intangible_amortization",
        )
        self.assertEqual(len(migrated["basic_cards"]["revenue"]["series"]), 1)
        self.assertIn("history_reason", migrated["basic_cards"]["revenue"])
        self.assertEqual(migrated["pe"]["models"]["coverage_capacity"]["status"], "omitted")

    def test_raw_dart_bridge_uses_canonical_engine_without_network(self):
        specs = {
            "REVENUE": {"nature": "flow", "statement": "IS", "source_ids": ["revenue"]},
            "OPERATING_INCOME": {"nature": "flow", "statement": "IS", "source_ids": ["op"]},
            "NET_INCOME": {"nature": "flow", "statement": "IS", "source_ids": ["ni"]},
            "CFO": {"nature": "flow", "statement": "CF", "source_ids": ["cfo"]},
            "CAPEX": {"nature": "flow", "statement": "CF", "source_ids": ["capex"]},
        }

        def row(year, account_id, sj_div, amount):
            return {
                "reprt_code": "11011", "rcept_no": f"r-{year}-{account_id}", "bsns_year": str(year),
                "fs_div": "CFS", "sj_div": sj_div, "account_id": account_id,
                "account_nm": account_id, "thstrm_amount": str(amount), "currency": "KRW",
            }

        filings = {}
        for year, revenue in ((2023, 100), (2024, 120), (2025, 150)):
            filings[year] = {"11011": [
                row(year, "revenue", "IS", revenue), row(year, "op", "IS", revenue / 10),
                row(year, "ni", "IS", revenue / 20), row(year, "cfo", "CF", revenue / 8),
                row(year, "capex", "CF", -revenue / 16),
            ]}
        snapshot = build_kfa_snapshot_from_dart_filings(
            filings,
            account_specs=specs,
            fiscal_year_ends={year: f"{year}-12-31" for year in filings},
            corp={"corp_code": "00126380", "stock_code": "005930", "name": "테스트", "source": "opendart"},
        )
        self.assertEqual(snapshot["basic_cards"]["revenue"]["value"], 150)
        self.assertEqual(len(snapshot["basic_cards"]["revenue"]["series"]), 3)
        self.assertEqual(snapshot["basic_cards"]["fcf"]["value_kind"], "derived")


if __name__ == "__main__":
    unittest.main()
