"""Offline tests for BLS CPI contribution parsing and relationship guards."""

from __future__ import annotations

import unittest
from pathlib import Path

from macro_monitor.cpi.api import build_cpi_api_history
from macro_monitor.cpi.bls import build_cpi_structure, load_mapping, parse_analysis_table, parse_detail_table
from macro_monitor.cpi.official_sources import (
    build_official_inflation_sources,
    parse_cleveland_median,
    parse_cleveland_nowcast,
)


ROOT = Path(__file__).resolve().parents[1]
MAPPING = load_mapping(ROOT / "config" / "cpi_structure.map.json")

TABLE6 = """
<table>
  <tr><th>Expenditure category</th><th>Relative importance</th><th>One Month</th><th>Effect</th></tr>
  <tr><td>All items</td><td>100.000</td><td>0.3</td><td>-</td></tr>
  <tr><td>Food</td><td>13.447</td><td>0.2</td><td>0.028</td></tr>
  <tr><td>Food at home</td><td>8.188</td><td>0.2</td><td>0.016</td></tr>
  <tr><td>Food away from home</td><td>5.259</td><td>0.2</td><td>0.012</td></tr>
  <tr><td>Energy</td><td>7.791</td><td>-0.5</td><td>-0.037</td></tr>
  <tr><td>Energy commodities</td><td>4.551</td><td>-0.9</td><td>-0.041</td></tr>
  <tr><td>Commodities less food and energy commodities</td><td>18.737</td><td>0.1</td><td>0.016</td></tr>
  <tr><td>New vehicles</td><td>3.500</td><td>0.1</td><td>0.003</td></tr>
  <tr><td>Used cars and trucks</td><td>2.629</td><td>0.1</td><td>0.002</td></tr>
  <tr><td>Motor vehicle parts and equipment</td><td>0.500</td><td>0.2</td><td>0.001</td></tr>
  <tr><td>Services less energy services</td><td>60.025</td><td>0.4</td><td>0.240</td></tr>
  <tr><td>Shelter</td><td>35.149</td><td>0.3</td><td>0.105</td></tr>
  <tr><td>Rent of primary residence</td><td>7.680</td><td>0.3</td><td>0.023</td></tr>
  <tr><td>Owners' equivalent rent of residences</td><td>25.700</td><td>0.3</td><td>0.077</td></tr>
  <tr><td>Transportation services</td><td>5.000</td><td>0.3</td><td>0.015</td></tr>
  <tr><td>Motor vehicle insurance</td><td>2.754</td><td>0.2</td><td>0.006</td></tr>
  <tr><td>Motor vehicle maintenance and repair</td><td>1.000</td><td>0.2</td><td>0.002</td></tr>
  <tr><td>Airline fares</td><td>0.500</td><td>0.1</td><td>0.001</td></tr>
  <tr><td>Footnotes</td></tr>
</table>
"""

TABLE7 = TABLE6.replace("<td>0.3</td><td>-</td>", "<td>3.1</td><td>-</td>", 1)
TABLE2 = """
<table>
  <tr><th>Expenditure category</th><th>Relative importance</th><th>12-month</th><th>unadj</th><th>prior</th><th>current</th></tr>
  <tr><td>All items</td><td>100.000</td><td>3.1</td><td>0.2</td><td>0.3</td><td>0.3</td></tr>
  <tr><td>New vehicles</td><td>3.500</td><td>1.0</td><td>0.0</td><td>0.2</td><td>0.1</td></tr>
  <tr><td>Footnotes</td></tr>
</table>
"""

NOWCAST_PAGE = """
<table><tr><th>Month</th><th>CPI</th><th>Core CPI</th><th>PCE</th><th>Core PCE</th><th>Updated</th></tr>
<tr><td>August 2026</td><td>0.35</td><td>0.20</td><td>0.34</td><td>0.27</td><td>08/11</td></tr></table>
<table><tr><th>Month</th><th>CPI</th><th>Core CPI</th><th>PCE</th><th>Core PCE</th><th>Updated</th></tr>
<tr><td>August 2026</td><td>3.42</td><td>2.43</td><td>3.77</td><td>3.36</td><td>08/11</td></tr></table>
"""

MEDIAN_PAGE = """
<table><tr><th>Date</th><th>May-2026</th><th>Jun-2026</th></tr>
<tr><th>Median CPI</th><td>0.3</td><td>0.2</td></tr>
<tr><th>16% trimmed-mean CPI</th><td>0.3</td><td>0.0</td></tr></table>
<table><tr><th>Date</th><th>May-2026</th><th>Jun-2026</th></tr>
<tr><th>Median CPI</th><td>2.9</td><td>2.7</td></tr>
<tr><th>16% trimmed-mean CPI</th><td>2.9</td><td>2.6</td></tr></table>
"""


class TestCpiStructure(unittest.TestCase):
    def test_analysis_table_keeps_effect_and_footnote_cleaning(self):
        rows = parse_analysis_table(TABLE6, source_table="Table 6")
        by_label = {row.label: row for row in rows}
        self.assertEqual(by_label["energy"].effect, -0.037)
        self.assertIsNone(by_label["all items"].effect)

    def test_detail_table_never_invents_effect(self):
        rows = parse_detail_table(TABLE2)
        by_label = {row.label: row for row in rows}
        self.assertEqual(by_label["new vehicles"].pct_change, 0.1)
        self.assertIsNone(by_label["new vehicles"].effect)

    def test_structure_uses_non_overlapping_frontier_and_does_not_signal_hypotheses(self):
        doc = build_cpi_structure(one_month_html=TABLE6, twelve_month_html=TABLE7, detail_html=TABLE2, mapping=MAPPING)
        self.assertEqual(doc["headline"]["one_month_sa_pct"], 0.3)
        self.assertEqual([row["id"] for row in doc["drivers"]["one_month"]["top_positive"]], ["core_services", "food", "core_goods"])
        self.assertEqual([row["id"] for row in doc["drivers"]["one_month"]["top_negative"]], ["energy"])
        catalog = {row["id"]: row for row in doc["relationship_catalog"]}
        self.assertTrue(catalog["auto_cost_to_insurance"]["lag_validation_eligible"])
        self.assertFalse(catalog["auto_cost_to_insurance"]["signal_eligible"])
        self.assertFalse(catalog["rent_oer_measurement_link"]["lag_validation_eligible"])
        self.assertEqual(doc["active_pathways"], [])

    def test_every_relationship_references_a_configured_item(self):
        item_ids = {item["id"] for item in [*MAPPING["driver_frontier"], *MAPPING["items"]]}
        for relation in MAPPING["relationships"]:
            with self.subTest(relation=relation["id"]):
                self.assertTrue(set(relation["source_ids"]).issubset(item_ids))
                self.assertTrue(set(relation["target_ids"]).issubset(item_ids))

    def test_api_history_recalculates_changes_and_never_claims_contributions(self):
        config = {
            "source": {"publisher": "BLS"},
            "series": [{"id": "all_items", "series_id": "CUSRTEST", "label_ko": "전체", "label_en": "All items"}],
        }
        response = {
            "CUSRTEST": {
                "catalog": {"series_title": "All items"},
                "data": [
                    {"year": "2025", "period": "M01", "value": "100.0", "footnotes": [{}]},
                    {"year": "2026", "period": "M01", "value": "105.0", "footnotes": [{}]},
                    {"year": "2026", "period": "M02", "value": "106.05", "footnotes": [{}]},
                    {"year": "2026", "period": "M13", "value": "999.0", "footnotes": [{}]},
                ],
            }
        }
        doc = build_cpi_api_history(config, response, retrieved_at="2026-08-12T00:00:00Z")
        rows = doc["series"][0]["observations"]
        self.assertEqual([row["date"] for row in rows], ["2025-01", "2026-01", "2026-02"])
        self.assertEqual(rows[1]["yoy_pct"], 5.0)
        self.assertEqual(rows[2]["mom_pct"], 1.0)
        self.assertIn("기여도 순위를 만들지 않는다", doc["limitations"][1])

    def test_official_fed_values_keep_provider_and_source_separate_from_own_model(self):
        nowcast = parse_cleveland_nowcast(NOWCAST_PAGE)
        median = parse_cleveland_median(MEDIAN_PAGE)
        self.assertEqual(nowcast["monthly_pct"]["reference_period"], "2026-08")
        self.assertEqual(nowcast["monthly_pct"]["cpi_pct"], 0.35)
        self.assertEqual(median["year_over_year_pct"]["trimmed_mean_cpi_pct"], 2.6)
        doc = build_official_inflation_sources(nowcast, median, retrieved_at="2026-08-12T00:00:00Z")
        by_id = {row["id"]: row for row in doc["published_indicators"]}
        self.assertEqual(by_id["cleveland_fed_inflation_nowcast"]["provider"], "Federal Reserve Bank of Cleveland")
        self.assertIn("자체 CPI 전이 신호", by_id["cleveland_fed_inflation_nowcast"]["use_in_dashboard"])
        self.assertEqual(doc["research_and_source_cards"][0]["classification"], "official_research_methodology_not_live_dashboard_forecast")


if __name__ == "__main__":
    unittest.main()
