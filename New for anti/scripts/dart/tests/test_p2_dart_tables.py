"""P2 DART document-table adapter safety contracts."""

from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.p2_dart_tables import (  # noqa: E402
    P2DartTableError,
    build_verified_structured_disclosures,
    extract_table_candidates,
    fetch_dart_document,
)


REPORT_ID = "20260318001394"


def archive(table_value: str = "1,200") -> bytes:
    html = f"""
        <html><body><p>수주잔고는 별도 확인이 필요합니다.</p>
        <table><tr><th>사업부</th><th>수주잔고</th></tr>
        <tr><td>조선</td><td>{table_value}</td></tr></table></body></html>
    """.encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("report.xml", html)
    return stream.getvalue()


def verified_manifest() -> dict:
    return {
        "schema_version": "kfa-p2-dart-table-manifest/1",
        "verified_mappings": [{
            "id": "fixture-yard-backlog",
            "status": "verified",
            "provider": "OpenDART document",
            "disclosure_type": "backlog_order_book",
            "report_id": REPORT_ID,
            "source_table_id": f"{REPORT_ID}:report.xml:table:0",
            "fiscal_year": 2025,
            "period_end": "2025-12-31",
            "fs_div": "CFS",
            "currency": "KRW",
            "source_scale": 1000000,
            "report_type": "business_report",
            "report_code": "11011",
            "segment_id": "shipbuilding",
            "row_selector": {"row_index": 0, "value_column": 1, "segment_name_column": 0},
        }],
        "candidate_mappings": [],
    }


class P2DartTableTest(unittest.TestCase):
    def test_tables_are_candidates_until_an_exact_verified_mapping_exists(self):
        candidates = extract_table_candidates(archive(), report_id=REPORT_ID)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["classification"], "candidate_unverified")
        result = build_verified_structured_disclosures(
            archive(), report_id=REPORT_ID,
            manifest={"schema_version": "kfa-p2-dart-table-manifest/1", "verified_mappings": [], "candidate_mappings": []},
        )
        self.assertEqual(result["structured_disclosures"], [])
        self.assertEqual(result["reason"], "missing:verified_dart_document_table_mapping")

    def test_exact_mapping_preserves_report_table_row_unit_and_scale(self):
        result = build_verified_structured_disclosures(archive(), report_id=REPORT_ID, manifest=verified_manifest())
        row = result["structured_disclosures"][0]
        self.assertEqual(row["value"], 1_200_000_000)
        self.assertEqual(row["segment_name"], "조선")
        self.assertEqual(row["source_table"], f"{REPORT_ID}:report.xml:table:0")
        self.assertEqual(row["source_row_id"], f"{REPORT_ID}:report.xml:table:0:row:0")
        self.assertTrue(row["is_structured_reported"])

    def test_unparseable_or_footnoted_cell_is_not_coerced_to_a_number(self):
        result = build_verified_structured_disclosures(archive("1,200 주1"), report_id=REPORT_ID, manifest=verified_manifest())
        self.assertEqual(result["structured_disclosures"], [])

    def test_fetch_rejects_invalid_receipt_without_a_network_request(self):
        with self.assertRaisesRegex(P2DartTableError, "invalid_dart_report_id"):
            fetch_dart_document(api_key="not-stored-test-key", report_id="bad")


if __name__ == "__main__":
    unittest.main()
