from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sources"))

from sources.india_tradestat import (  # noqa: E402
    fetch_monthly_hs4_usd,
    fetch_monthly_specific_hs_usd,
    parse_hs4_usd_response,
)


HTML = """
<table id="example1"><thead><tr>
<th>S.No.</th><th>HSCode</th><th>Commodity</th><th>Jun-2025 (R)</th><th>Jun-2026 (F)</th>
</tr></thead><tbody><tr>
<td>1</td><td>2709</td><td>Crude oil</td><td>100.5</td><td>1,234.56</td>
</tr><tr><td>2</td><td>2710</td><td>Products</td><td>50</td><td>-</td></tr></tbody></table>
"""


class IndiaTradeStatTests(unittest.TestCase):
    def test_parser_keeps_official_value_unit_and_release_status(self) -> None:
        data = parse_hs4_usd_response(HTML, period="202606", hs_codes=["2709", "2710"], flow="M")
        point = data["2709"][0]
        self.assertEqual(point["month"], "2026-06")
        self.assertEqual(point["value"], 1234.56)
        self.assertEqual(point["unit"], "USD_million")
        self.assertEqual(point["quality"]["release_status"], "F")
        self.assertEqual(data["2710"], [])

    def test_cached_response_is_used_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "india_tradestat_hs4_usd_M_202606.html"
            path.write_text(HTML, encoding="utf-8")
            result = fetch_monthly_hs4_usd(
                period="202606", flow="M", hs_codes=["2709"], cache_dir=Path(directory), allow_fetch=False
            )
        self.assertTrue(result["available"])
        self.assertTrue(result["cache"]["hit"])
        self.assertEqual(result["series_by_hs"]["2709"][0]["value"], 1234.56)

    def test_specific_hs6_uses_exact_code_and_cached_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "india_tradestat_usd_M_202606_271111.html"
            path.write_text(HTML.replace("2709", "271111"), encoding="utf-8")
            result = fetch_monthly_specific_hs_usd(
                period="202606", flow="M", hs_code="271111", cache_dir=Path(directory), allow_fetch=False
            )
        self.assertTrue(result["available"])
        self.assertEqual(result["series_by_hs"]["271111"][0]["quality"]["commodity_level"], 6)

    def test_specific_code_missing_from_directory_is_not_treated_as_zero_trade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "india_tradestat_usd_M_202606_284410.html"
            path.write_text("<html><body>blank source form</body></html>", encoding="utf-8")
            result = fetch_monthly_specific_hs_usd(
                period="202606", flow="M", hs_code="284410", cache_dir=Path(directory), allow_fetch=False
            )
        self.assertTrue(result["available"])
        self.assertEqual(result["empty_status"], "source_hs_code_not_available")
        self.assertEqual(result["series_by_hs"]["284410"], [])

    def test_invalid_period_fails_without_fetch(self) -> None:
        result = fetch_monthly_hs4_usd(period="2026-06", flow="M", hs_codes=["2709"], cache_dir=Path("/tmp"))
        self.assertFalse(result["available"])
        self.assertIn("YYYYMM", result["reason"])


if __name__ == "__main__":
    unittest.main()
