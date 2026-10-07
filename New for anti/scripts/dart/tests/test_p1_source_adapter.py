"""Offline source-adapter contracts for strict P1 evidence only."""

from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.canonical_facts import adapt_dart_filings, adapt_sec_companyfacts  # noqa: E402
from dart_kfa.p1_disclosures import build_p1_disclosures, compute_strict_ebitda, resolve_latest_endpoint  # noqa: E402
from dart_kfa.p1_source_adapter import (  # noqa: E402
    P1SourceAdapterError,
    adapt_verified_dart_p1_accounts,
    adapt_verified_sec_p1_accounts,
    adapt_verified_structured_disclosures,
    build_verified_p1_account_specs,
    load_validation_manifest,
    merge_verified_p1_accounts,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


OP_DART_SPEC = {"OPERATING_INCOME": {"nature": "flow", "statement": "IS", "source_ids": ["op"]}}
OP_SEC_SPEC = {"OPERATING_INCOME": {"nature": "flow", "statement": "IS", "sec_concepts": ["OperatingIncomeLoss"]}}


class P1SourceAdapterTest(unittest.TestCase):
    def setUp(self):
        self.manifest = fixture("p1_verified_manifest.json")
        self.dart_rows = fixture("p1_dart_verified_rows.json")
        self.sec_facts = fixture("p1_sec_companyfacts.json")

    def _dart_base(self):
        return adapt_dart_filings(
            self.dart_rows, account_specs=OP_DART_SPEC, fiscal_year_end="2025-12-31", entity_id="fixture-dart"
        )

    def _sec_base(self):
        return adapt_sec_companyfacts(
            self.sec_facts, account_specs=OP_SEC_SPEC, fiscal_year_end="2025-12-31", entity_id="fixture-sec"
        )

    def test_dart_verified_separate_components_enter_canonical_and_compute_strict_ebitda(self):
        fragment = adapt_verified_dart_p1_accounts(
            self.dart_rows, manifest=self.manifest, fiscal_year_end="2025-12-31", entity_id="fixture-dart"
        )
        canonical = merge_verified_p1_accounts(self._dart_base(), fragment)
        result = compute_strict_ebitda(canonical, endpoint="Q3")
        self.assertEqual(result["value"], 22)  # Q3: 17 operating income + 4 PPE + 1 intangible.
        self.assertEqual(result["status"], "derived_deterministic")
        source_facts = json.dumps(result["provenance"])
        self.assertIn("fixture-q3", source_facts)
        self.assertIn("ppe-q3", source_facts)
        self.assertIn("cashflow-note", source_facts)

    def test_sec_verified_separate_components_enter_same_canonical_contract(self):
        fragment = adapt_verified_sec_p1_accounts(
            self.sec_facts, manifest=self.manifest, fiscal_year_end="2025-12-31", entity_id="fixture-sec"
        )
        canonical = merge_verified_p1_accounts(self._sec_base(), fragment)
        result = compute_strict_ebitda(canonical, endpoint="Q3")
        self.assertEqual(result["value"], 22)
        self.assertIn("sec-q3", json.dumps(result["provenance"]))
        self.assertIn("ppe-q3", json.dumps(result["provenance"]))

    def test_combined_da_and_candidate_mapping_never_build_an_executable_spec(self):
        manifest = deepcopy(self.manifest)
        manifest["verified_mappings"] = [
            item for item in manifest["verified_mappings"] if item.get("kind") != "account"
        ]
        specs = build_verified_p1_account_specs(manifest, provider="DART")
        self.assertEqual(specs, {})

        combined = deepcopy(self.dart_rows)
        for rows in combined.values():
            rows[:] = [row for row in rows if row.get("account_id") not in {"fixture_PpeDepreciation", "fixture_IntangibleAmortization"}]
            rows.append({
                "reprt_code": rows[0]["reprt_code"], "rcept_no": rows[0]["rcept_no"], "bsns_year": "2025",
                "fs_div": "CFS", "sj_div": "IS", "account_id": "fixture_CombinedDepreciationAndAmortization",
                "thstrm_amount": "99", "currency": "KRW",
            })
        fragment = adapt_verified_dart_p1_accounts(
            combined, manifest=manifest, fiscal_year_end="2025-12-31", entity_id="fixture-dart"
        )
        canonical = merge_verified_p1_accounts(self._dart_base(), fragment)
        result = compute_strict_ebitda(canonical, endpoint="Q3")
        self.assertIsNone(result["value"])
        self.assertIn("PPE_DEPRECIATION:missing:account", result["reason"])
        self.assertIn("INTANGIBLE_AMORTIZATION:missing:account", result["reason"])

    def test_bridge_and_compute_reject_scope_currency_and_period_mismatch(self):
        fragment = adapt_verified_dart_p1_accounts(
            self.dart_rows, manifest=self.manifest, fiscal_year_end="2025-12-31", entity_id="fixture-dart"
        )
        wrong_currency = deepcopy(fragment)
        wrong_currency["currency"] = "USD"
        with self.assertRaisesRegex(P1SourceAdapterError, "incompatible_fragment_currency"):
            merge_verified_p1_accounts(self._dart_base(), wrong_currency)

        canonical = merge_verified_p1_accounts(self._dart_base(), fragment)
        canonical["series"]["PPE_DEPRECIATION"]["quarters"]["Q3"]["period_end"] = "2025-08-31"
        self.assertEqual(
            compute_strict_ebitda(canonical, endpoint="Q3")["reason"],
            "incompatible:strict_ebitda_period_scope_currency_or_unit",
        )

    def test_structured_table_rows_preserve_provenance_and_prose_is_not_promoted(self):
        records = [
            {
                "provider": "DART", "structure": "table", "source_table_id": "fixture-segment-table",
                "source_row_type": "segment-profit", "source_row_id": "seg-row-1", "source_concept": "dart_SegmentProfit",
                "segment_id": "shipbuilding", "segment_name": "Shipbuilding", "value": 30,
                "currency": "KRW", "scale": 1, "fiscal_year": 2025, "period_end": "2025-09-30", "fs_div": "CFS",
                "report_id": "fixture-q3", "report_code": "11014", "report_type": "quarter_report",
            },
            {
                "provider": "DART", "structure": "table", "source_table_id": "fixture-order-table",
                "source_row_type": "backlog", "source_row_id": "backlog-row-1", "source_concept": "dart_OrderBacklog",
                "segment_id": "shipbuilding", "segment_name": "Shipbuilding", "value": 900,
                "currency": "KRW", "scale": 1, "fiscal_year": 2025, "period_end": "2025-09-30", "fs_div": "CFS",
                "report_id": "fixture-q3", "report_code": "11014", "report_type": "quarter_report",
            },
            {
                "provider": "DART", "structure": "prose", "source_table_id": "fixture-order-table",
                "source_row_type": "backlog", "source_row_id": "prose-row", "note_text": "수주잔고 999",
            },
        ]
        accepted = adapt_verified_structured_disclosures(records, manifest=self.manifest, provider="DART")
        self.assertEqual(len(accepted), 2)
        canonical = merge_verified_p1_accounts(
            self._dart_base(),
            adapt_verified_dart_p1_accounts(self.dart_rows, manifest=self.manifest, fiscal_year_end="2025-12-31", entity_id="fixture-dart"),
        )
        output = build_p1_disclosures(canonical, structured_disclosures=accepted)
        segment = output["current"]["segment_profit"]["value"][0]
        backlog = output["current"]["backlog_order_book"]["value"][0]
        self.assertEqual(segment["provenance"]["provider"], "DART")
        self.assertEqual(segment["provenance"]["source_row_id"], "seg-row-1")
        self.assertEqual(backlog["provenance"]["mapping_id"], "fixture-dart-backlog-v1")

    def test_priority_is_explicit_q3_q2_q1_fy_and_production_manifest_has_no_promotions(self):
        canonical = merge_verified_p1_accounts(
            self._dart_base(),
            adapt_verified_dart_p1_accounts(self.dart_rows, manifest=self.manifest, fiscal_year_end="2025-12-31", entity_id="fixture-dart"),
        )
        self.assertEqual(resolve_latest_endpoint(canonical)["priority"], ["Q3", "Q2", "Q1", "annual"])
        production = load_validation_manifest()
        self.assertEqual(production["verified_mappings"], [])
        self.assertEqual(production["candidate_mappings"], [])


if __name__ == "__main__":
    unittest.main()
