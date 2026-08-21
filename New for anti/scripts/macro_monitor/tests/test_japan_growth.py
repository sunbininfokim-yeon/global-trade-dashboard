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
