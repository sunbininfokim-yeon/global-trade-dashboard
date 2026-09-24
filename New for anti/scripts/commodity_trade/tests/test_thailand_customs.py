from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sources"))

from sources.thailand_customs import parse_monthly_sum  # noqa: E402


class ThailandCustomsTests(unittest.TestCase):
    def test_parses_export_direct_month_and_ytd_sum(self) -> None:
        document = """
        <table><thead><tr><th>Jun 2026</th><th>Jan - Jun 2026</th></tr>
        <tr><th>FOB (Baht)</th><th>FOB (Baht)</th></tr></thead><tbody>
        <tr><th colspan='2'>SUM</th><th>2,428</th><th>3,783,872,116</th></tr>
        </tbody></table>
        """
        self.assertEqual(parse_monthly_sum(document, period="202606", flow="X"), {
            "value": 2428.0,
            "source_ytd_value": 3783872116.0,
        })

    def test_rejects_wrong_measure(self) -> None:
        document = "<table><th>Jun 2026</th><th>FOB (Baht)</th><tr><th>SUM</th><th>1</th></tr></table>"
        self.assertIsNone(parse_monthly_sum(document, period="202606", flow="M"))
