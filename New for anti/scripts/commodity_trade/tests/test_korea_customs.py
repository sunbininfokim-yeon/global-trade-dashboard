from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sources"))

from sources.korea_customs import parse_itemtrade_xml  # noqa: E402


class KoreaCustomsTests(unittest.TestCase):
    def test_parses_exact_month_and_ignores_total_row(self) -> None:
        document = b"""
        <response><header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
        <body><items>
          <item><year>2026.06</year><hsCode>2709</hsCode><expWgt>1,200</expWgt><expDlr>3,400</expDlr><impWgt>5,600</impWgt><impDlr>7,800</impDlr></item>
          <item><year>\xec\xb4\x9d\xea\xb3\x84</year><hsCode>-</hsCode><expWgt>999</expWgt></item>
        </items></body></response>
        """
        result = parse_itemtrade_xml(document, period="202606", hs_code="2709")
        self.assertEqual(result["X"][0]["value"], 1200.0)
        self.assertEqual(result["X"][0]["primary_value_usd"], 3400.0)
        self.assertEqual(result["M"][0]["value"], 5600.0)
        self.assertEqual(result["M"][0]["primary_value_usd"], 7800.0)

    def test_api_error_is_actionable(self) -> None:
        with self.assertRaisesRegex(ValueError, "SERVICE_KEY_IS_NULL"):
            parse_itemtrade_xml(
                b"<response><header><resultCode>20</resultCode><resultMsg>SERVICE_KEY_IS_NULL</resultMsg></header></response>",
                period="202606",
                hs_code="2709",
            )
