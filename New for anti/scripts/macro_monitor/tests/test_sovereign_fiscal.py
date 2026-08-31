"""Tests for the actual-only cross-country debt / interest layer."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from macro_monitor.engine import build_universe, resolve_country  # noqa: E402
from macro_monitor.sovereign_fiscal import build_snapshot  # noqa: E402


class TestSovereignFiscalSnapshot(unittest.TestCase):
    def test_snapshot_keeps_common_actual_years_and_derives_usd_amounts(self):
        def imf(indicator: str):
            values = {
                "d": {"USA": {"2023": 120.0, "2024": 121.0}},
                "ie": {"USA": {"2023": 2.5, "2024": 2.7}},
                "NGDPD": {"USA": {"2023": 27000.0, "2024": 28000.0}},
            }
            return values[indicator]

        with patch("macro_monitor.sovereign_fiscal._imf_values", side_effect=imf), patch(
            "macro_monitor.sovereign_fiscal._completed_us_fiscal_years",
            return_value=[{
                "date": "2025-09-30", "fiscal_year": 2025,
                "interest_tn_usd": 1.2, "defense_tn_usd": 0.9,
                "interest_to_defense_pct": 133.3,
            }],
        ):
            snapshot = build_snapshot()

        usa = snapshot["countries"]["USA"]
        self.assertEqual(usa["asof"], "2024-12-31")
        self.assertAlmostEqual(usa["observations"][-1]["debt_tn_usd"], 33.88, places=2)
        self.assertAlmostEqual(usa["observations"][-1]["interest_tn_usd"], 0.756, places=3)
        self.assertEqual(snapshot["us_defense_ratio"]["asof"], "2025-09-30")
        self.assertIn("IMF 전망치는 제외", snapshot["refresh"]["actuals_policy_ko"])

    def test_engine_puts_fiscal_cards_in_rates_and_uses_us_treasury_ratio(self):
        countries = json.loads((ROOT / "config" / "countries.json").read_text(encoding="utf-8"))
        specs = json.loads((ROOT / "config" / "series.spec.json").read_text(encoding="utf-8"))
        snapshot = {
            "retrieved_at": "2026-08-30T00:00:00Z",
            "source": {
                "imf": {"publisher": "IMF Fiscal Policy Panel", "url": "https://example.test/imf"},
                "us_treasury": {"publisher": "U.S. Treasury MTS Table 5", "url": "https://example.test/mts"},
            },
            "countries": {
                "USA": {"observations": [
                    {"date": "2023-12-31", "debt_tn_usd": 32.0, "debt_gdp_pct": 120.0, "interest_tn_usd": 0.7, "interest_gdp_pct": 2.5},
                    {"date": "2024-12-31", "debt_tn_usd": 34.0, "debt_gdp_pct": 121.0, "interest_tn_usd": 0.8, "interest_gdp_pct": 2.7},
                ]},
                "GBR": {"observations": [
                    {"date": "2023-12-31", "debt_tn_usd": 2.9, "debt_gdp_pct": 101.0, "interest_tn_usd": 0.1, "interest_gdp_pct": 3.1},
                    {"date": "2024-12-31", "debt_tn_usd": 3.0, "debt_gdp_pct": 102.0, "interest_tn_usd": 0.1, "interest_gdp_pct": 3.0},
                ]},
            },
            "us_defense_ratio": {"observations": [
                {"date": "2023-09-30", "interest_tn_usd": 0.9, "interest_to_defense_pct": 110.0},
                {"date": "2024-09-30", "interest_tn_usd": 1.0, "interest_to_defense_pct": 120.0},
            ]},
        }
        with patch("macro_monitor.engine._load_sovereign_fiscal_snapshot", return_value=snapshot):
            doc = build_universe(countries, specs, asof=date(2026, 8, 1), generated_at="2026-08-01T00:00:00Z")

        usa = resolve_country(doc, "USA")
        assert usa is not None
        by_id = {row["id"]: row for row in usa["indicators"]}
        self.assertEqual(by_id["sovereign_debt"]["category"], "rates")
        self.assertEqual(by_id["sovereign_debt"]["fiscal_compare"]["secondary_label_ko"], "국가부채/GDP")
        self.assertEqual(by_id["sovereign_interest"]["source"], "U.S. Treasury MTS Table 5")
        self.assertEqual(by_id["sovereign_interest"]["fiscal_compare"]["secondary_label_ko"], "국방비 대비 국채이자")
        self.assertIn("sovereign_debt", [row["id"] for row in usa["categories"]["rates"]])

        gbr = resolve_country(doc, "GBR")
        assert gbr is not None
        gbr_by_id = {row["id"]: row for row in gbr["indicators"]}
        self.assertEqual(gbr_by_id["sovereign_interest"]["fiscal_compare"]["secondary_label_ko"], "부채이자/GDP")


if __name__ == "__main__":
    unittest.main()
