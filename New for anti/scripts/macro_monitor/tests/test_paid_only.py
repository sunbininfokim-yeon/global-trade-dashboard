"""Paid-only cards are removed. Public cards stay."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from macro_monitor.paid_only import strip_paid_only  # noqa: E402


class TestPaidOnly(unittest.TestCase):
    def test_drops_cds_and_pmi_keeps_cpi(self):
        doc = {
            "countries": [{
                "iso3": "ZAF",
                "indicators": [
                    {"id": "cpi_yoy", "value": 4.8},
                    {"id": "sovereign_cds_5y", "value": 220},
                    {"id": "absa_pmi", "value": 48.5},
                ],
                "categories": {
                    "growth": [{"id": "absa_pmi"}, {"id": "cpi_yoy"}],
                },
                "headlines": [{"id": "sovereign_cds_5y"}, {"id": "cpi_yoy"}],
            }],
        }
        removed = strip_paid_only(doc)
        country = doc["countries"][0]
        self.assertEqual([i["id"] for i in country["indicators"]], ["cpi_yoy"])
        self.assertEqual([c["id"] for c in country["categories"]["growth"]], ["cpi_yoy"])
        self.assertEqual([h["id"] for h in country["headlines"]], ["cpi_yoy"])
        self.assertIn("ZAF:sovereign_cds_5y", removed)
        self.assertIn("ZAF:absa_pmi", removed)


if __name__ == "__main__":
    unittest.main()
