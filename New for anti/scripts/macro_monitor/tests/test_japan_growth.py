"""Unit tests for the official Japan growth-monitor source adapters."""

from __future__ import annotations

import unittest

from macro_monitor.japan_growth import (  # type: ignore[import-not-found]
    GENERAL_GOVERNMENT_FFA,
    PRIVATE_NONFINANCIAL_FFA,
    _boj_api_url,
    build_net_funding_demand,
    parse_esri_nominal_calendar_year,
    parse_esri_nominal_quarterly_gdp,
)


class TestJapanGrowthAdapters(unittest.TestCase):
    def test_esri_nominal_parsers_keep_correct_columns_and_periods(self):
        annual = (
            ",GDP(Expenditure Approach),Private Non-Resi.Investment\n"
            "2024/1-12.,600,120\n"
            "2025/1-12.,650,130\n"
        ).encode()
        quarterly = (
            ",GDP(Expenditure Approach)\n"
            "2025/ 1- 3.,150\n"
            "4- 6.,160\n"
            "7- 9.,170\n"
            "10-12.,180\n"
        ).encode()
        capex = parse_esri_nominal_calendar_year(annual)
        gdp = parse_esri_nominal_quarterly_gdp(quarterly)
        self.assertEqual(capex[-1]["date"], "2025-12-31")
        self.assertAlmostEqual(capex[-1]["value"], 20.0)
        self.assertEqual(gdp["2025-03-31"], 150.0)
        self.assertEqual(gdp["2025-12-31"], 180.0)

    def test_net_funding_demand_uses_matching_four_quarter_gdp_sum(self):
        private = {
            "2025-03-31": 100.0,
            "2025-06-30": 100.0,
            "2025-09-30": 100.0,
            "2025-12-31": 100.0,
        }
        fiscal = {
            "2025-03-31": -200.0,
            "2025-06-30": -200.0,
            "2025-09-30": -200.0,
            "2025-12-31": -200.0,
        }
        gdp = {
            "2025-03-31": 100.0,
            "2025-06-30": 100.0,
            "2025-09-30": 100.0,
            "2025-12-31": 100.0,
        }
        row = build_net_funding_demand(private, fiscal, gdp)[-1]
        # FFA uses 100m JPY; 400 - 800 = -400 → -40 bn / 400 bn GDP = -10%.
        self.assertEqual(row["date"], "2025-12-31")
        self.assertAlmostEqual(row["value"], -10.0)
        self.assertAlmostEqual(row["private_nonfinancial_pct_gdp"], 10.0)
        self.assertAlmostEqual(row["general_government_pct_gdp"], -20.0)

    def test_boj_code_list_keeps_literal_comma(self):
        url = _boj_api_url(
            [PRIVATE_NONFINANCIAL_FFA, GENERAL_GOVERNMENT_FFA],
            start_date="199801",
        )
        self.assertIn("code=FOF_FFAF411L700,FOF_FFAF420L700", url)
        self.assertNotIn("%2C", url)


if __name__ == "__main__":
    unittest.main()


class Version2Additions(__import__("unittest").TestCase):
    def test_capex_ratio_over_four_quarters(self):
        from macro_monitor import japan_growth as jg
        gdp = {"2025-09-30": 160.0, "2025-12-31": 170.0, "2026-03-31": 165.0, "2026-06-30": 175.0}
        capex = {"2025-09-30": 30.0, "2025-12-31": 32.0, "2026-03-31": 31.0, "2026-06-30": 33.0}
        (row,) = jg.build_capex_ratio_4q(capex, gdp)
        self.assertEqual(row["date"], "2026-06-30")
        self.assertAlmostEqual(row["value"], 126 / 670 * 100, places=3)

    def test_release_discovery_follows_the_top_page(self):
        from macro_monitor import japan_growth as jg
        page = b'<a href="/en/sna/data/sokuhou/files/2026/qe262_2/gdemenuea.html">latest</a>'
        url = jg.discover_esri_release_page(lambda u: page)
        self.assertEqual(url, "https://www.esri.cao.go.jp/en/sna/data/sokuhou/files/2026/qe262_2/gdemenuea.html")
        gap = b'<a href="2622gap.xlsx">GDP gap</a>'
        self.assertEqual(jg.discover_cao_gap_xlsx(lambda u: gap), "https://www5.cao.go.jp/keizai3/getsurei/2622gap.xlsx")

    def test_cabinet_office_gap_rows(self):
        import io
        from openpyxl import Workbook
        from macro_monitor import japan_growth as jg
        wb = Workbook(); ws = wb.active
        ws.append(["title", None, "四半期"]); ws.append([2026, "Ⅰ", 0.5]); ws.append([None, "Ⅱ", 0.7]); ws.append([None, None, None])
        buf = io.BytesIO(); wb.save(buf)
        self.assertEqual(jg.parse_cao_gdp_gap(buf.getvalue()),
                         [{"date": "2026-03-31", "value": 0.5}, {"date": "2026-06-30", "value": 0.7}])
