#!/usr/bin/env python3
"""No-network tests for the end-of-day LETF share history contract."""

from __future__ import annotations

import unittest

from market_microstructure.letf_history import append_point, point_from_krx_rows


class TestLetfHistory(unittest.TestCase):
    def test_krx_rows_produce_observed_daily_share(self):
        point = point_from_krx_rows(
            date="2026-08-12",
            stock_rows=[
                {"ACC_TRDVAL": "1000000000000", "MKTCAP": "10000000000000"},
                {"ACC_TRDVAL": "2000000000000", "MKTCAP": "20000000000000"},
            ],
            etf_rows=[
                {"ISU_NM": "KODEX 레버리지", "ACC_TRDVAL": "200000000000", "MKTCAP": "1000000000000"},
                {"ISU_NM": "KODEX 200선물인버스2X", "ACC_TRDVAL": "100000000000", "MKTCAP": "500000000000"},
            ],
        )
        self.assertEqual(point["quality"], "observed")
        self.assertAlmostEqual(point["levered_inverse_etf_tv_over_kospi_cash_tv_pct"], 10.0)
        self.assertAlmostEqual(point["gobus_tv_jo"], 0.1)
        self.assertAlmostEqual(point["levered_inverse_etf_aum_jo"], 1.5)
        self.assertAlmostEqual(point["levered_inverse_etf_aum_over_kospi_ff_pct"], 6.6667, places=3)

    def test_append_replaces_same_date_without_fabricating_history(self):
        first = {"date": "2026-08-12", "value": 1}
        second = {"date": "2026-08-12", "value": 2}
        got = append_point({"points": [first]}, second)
        self.assertEqual(got["n_points"], 1)
        self.assertEqual(got["points"][0]["value"], 2)


if __name__ == "__main__":
    unittest.main()
