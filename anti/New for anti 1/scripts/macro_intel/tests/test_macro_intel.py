from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro_intel.build import build_liquidity_intel
from macro_intel.qra import parse_qra_html
from macro_intel.reporters import (
    ReporterArticle,
    analyze_reporter_liquidity,
    extract_liquidity_indicators,
    scrape_economy21_priority,
)
from macro_intel.liquidity import compute_liquidity_bias


FIX = ROOT / "tests" / "fixtures"


class QraTests(unittest.TestCase):
    def test_parse_fixture(self):
        html = (FIX / "treasury_qra.html").read_text(encoding="utf-8")
        p = parse_qra_html(
            html,
            url="https://home.treasury.gov/news/press-releases/sb0584",
            title="Treasury Announces Marketable Borrowing Estimates",
        )
        self.assertGreaterEqual(len(p.quarters), 2)
        self.assertIn("qra_net_borrowing_up", p.signals)


class ReporterLiquidityTests(unittest.TestCase):
    def test_extract_fima_tga(self):
        cfg = json.loads((ROOT / "config" / "reporter_liquidity.json").read_text())
        hits = extract_liquidity_indicators(
            "미국 FIMA 레포와 TGA 잔고, RRP 역레포 논의",
            cfg,
        )
        ids = {h.indicator_id for h in hits}
        self.assertIn("fima", ids)
        self.assertIn("tga", ids)
        self.assertIn("rrp", ids)

    def test_scrape_and_analyze(self):
        html = (FIX / "economy21_list.html").read_text(encoding="utf-8")
        arts = scrape_economy21_priority(
            html,
            origin="http://www.economy21.co.kr",
            author_needles=["양영빈"],
        )
        self.assertGreaterEqual(len(arts), 2)
        cfg = json.loads((ROOT / "config" / "reporter_liquidity.json").read_text())
        analysis = analyze_reporter_liquidity(arts, cfg, author="양영빈")
        self.assertGreaterEqual(len(analysis["top_indicators"]), 1)
        self.assertTrue(analysis["finance_panel_fields"]["reporter_liquidity_primary"])
        # no per-article celebrity ticker objects in analysis
        self.assertNotIn("priority_reporter", json.dumps(analysis))


class BiasTests(unittest.TestCase):
    def test_tightening(self):
        rules = json.loads((ROOT / "config" / "liquidity_rules.json").read_text())
        b = compute_liquidity_bias(
            qra_signals=["qra_net_borrowing_up", "tga_cash_high"],
            beige_tone="firm",
            rules=rules,
        )
        self.assertEqual(b["bias"], "tightening")


class BuildTests(unittest.TestCase):
    def test_fixtures_build(self):
        doc = build_liquidity_intel(fetch_live=False, fixture_dir=FIX)
        self.assertEqual(doc["schema_version"], "liquidity-intel-v1")
        self.assertTrue(doc["stats"]["qra_parsed"])
        types = {t.get("event_type") for t in doc["ticker_items"]}
        self.assertNotIn("priority_reporter", types)
        # metrics line allowed
        self.assertTrue(
            "liquidity_indicator" in types or doc["stats"]["reporter_indicator_hits"] >= 1
        )
        fields = doc["liquidity"]["finance_panel_fields"]
        self.assertIn("reporter_liquidity_themes", fields)
        self.assertTrue(fields.get("reporter_liquidity_primary_ko") or fields.get("reporter_liquidity_themes"))


if __name__ == "__main__":
    unittest.main()
