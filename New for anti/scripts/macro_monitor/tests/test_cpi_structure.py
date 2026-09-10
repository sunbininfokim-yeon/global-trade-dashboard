"""Contracts for the CPI relationship catalog used by the dashboard drawer."""

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from macro_monitor.cpi.bls import build_cpi_structure, load_mapping
from publish_cpi_structure import publish


ROOT = Path(__file__).resolve().parents[1]
MAPPING = load_mapping(ROOT / "config" / "cpi_structure.map.json")

TABLE6 = """
<table>
  <tr><th>Expenditure category</th><th>Relative importance</th><th>One Month</th><th>Effect</th></tr>
  <tr><td>All items</td><td>100.000</td><td>0.3</td><td>-</td></tr>
  <tr><td>Energy</td><td>7.791</td><td>-0.5</td><td>-0.037</td></tr>
  <tr><td>New vehicles</td><td>3.500</td><td>0.1</td><td>0.003</td></tr>
  <tr><td>Used cars and trucks</td><td>2.629</td><td>0.1</td><td>0.002</td></tr>
  <tr><td>Rent of primary residence</td><td>7.680</td><td>0.3</td><td>0.023</td></tr>
  <tr><td>Owners' equivalent rent of residences</td><td>25.700</td><td>0.3</td><td>0.077</td></tr>
  <tr><td>Footnotes</td></tr>
</table>
"""


class TestCpiStructure(unittest.TestCase):
    def test_relationships_reference_configured_items(self):
        item_ids = {item["id"] for item in [*MAPPING["driver_frontier"], *MAPPING["items"]]}
        for relation in MAPPING["relationships"]:
            with self.subTest(relation=relation["id"]):
                self.assertTrue(set(relation["source_ids"]).issubset(item_ids))
                self.assertTrue(set(relation["target_ids"]).issubset(item_ids))

    def test_catalog_preserves_ids_and_marks_unvalidated_hypotheses(self):
        doc = build_cpi_structure(
            one_month_html=TABLE6,
            twelve_month_html=TABLE6,
            detail_html=None,
            mapping=MAPPING,
        )
        catalog = {row["id"]: row for row in doc["relationship_catalog"]}
        measurement = catalog["rent_oer_measurement_link"]
        hypothesis = catalog["auto_cost_to_insurance"]
        self.assertEqual(measurement["type"], "measurement_link")
        self.assertEqual(measurement["source_ids"], ["rent_primary"])
        self.assertEqual(measurement["target_ids"], ["owners_equivalent_rent"])
        self.assertFalse(hypothesis["signal_eligible"])
        self.assertEqual(hypothesis["interpretation"], "candidate_structure_not_causal_finding_or_forecast")

    def test_publisher_attaches_small_evidence_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "map.json"
            evidence = root / "evidence.json"
            out = root / "out.json"
            source.write_text('{"relationships":[{"id":"x","type":"market_hypothesis","evidence_status":"old"}]}', encoding="utf-8")
            evidence.write_text(
                '{"schema_version":"v1","generated_at":"2026-01-01T00:00:00Z","reference_period":"2025-12",'
                '"relationships":[{"relationship_id":"x","evidence_tier":"relationship_candidate",'
                '"evidence_label_ko":"관계 후보","phase":{"summary_ko":"관찰 시작"},"tests":[]}]}',
                encoding="utf-8",
            )
            result = publish(source=source, out=out, evidence_path=evidence)
            relation = result["document"]["relationships"][0]
            self.assertEqual(relation["evidence_tier"], "relationship_candidate")
            self.assertEqual(relation["current_watch_ko"], "관찰 시작")
            self.assertIn("현재 관찰", relation["mechanism_ko"])


if __name__ == "__main__":
    unittest.main()
