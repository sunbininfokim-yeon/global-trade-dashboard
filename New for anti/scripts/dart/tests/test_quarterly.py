"""Quarter-end EV series. Rows follow fnlttSinglAcntAll for an FY report and
quarterly reports (thstrm / thstrm_add / frmtrm_add)."""
import unittest

from dart_kfa.quarterly import dart_points, parse_fchart, series


def r(sj, aid, th=None, fr=None, add=None, fr_add=None):
    return {"sj_div": sj, "account_id": aid, "thstrm_amount": th, "frmtrm_amount": fr,
            "thstrm_add_amount": add, "frmtrm_add_amount": fr_add}


FY = [r("BS", "ifrs-full_CashAndCashEquivalents", "100", "80"), r("BS", "ifrs-full_LongtermBorrowings", "500", "450"),
      r("BS", "ifrs-full_Equity", "1000", "900"), r("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "800", "720"),
      r("IS", "dart_OperatingIncomeLoss", "120", "100"), r("IS", "ifrs-full_Revenue", "1200", "1000")]
Q1 = [r("BS", "ifrs-full_CashAndCashEquivalents", "90"), r("BS", "ifrs-full_LongtermBorrowings", "520"),
      r("BS", "ifrs-full_Equity", "1010"), r("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "810"),
      r("IS", "dart_OperatingIncomeLoss", "40", add="40", fr_add="25"), r("IS", "ifrs-full_Revenue", "330", add="330", fr_add="280")]


class Quarterly(unittest.TestCase):
    def test_points_and_ltm(self):
        pts = dart_points(2025, FY, None, {}, {"Q1": Q1})
        self.assertEqual([p["period_end"] for p in pts], ["2024-12-31", "2025-12-31", "2026-03-31"])
        q1 = pts[-1]
        self.assertEqual(q1["ltm"], {"revenue": 1200 + 330 - 280, "op": 120 + 40 - 25})

    def test_series_ev(self):
        pts = dart_points(2025, FY, None, {}, {"Q1": Q1})
        s = series(pts, closes={"202603": 10.0, "202512": 9.0}, shares=100)
        last = s["points"][-1]
        self.assertEqual((last["market_cap"], last["net_debt"], last["nci"]), (1000.0, 430.0, 200.0))
        self.assertEqual(last["ev"], 1630.0)
        self.assertAlmostEqual(last["ev_to_ebit"], 1630 / 135)
        self.assertIsNone(s["points"][0]["market_cap"])          # no close for 2024-12

    def test_fchart(self):
        xml = '<item data="20260331|1|2|0|62900|5" /><item data="20260430|1|2|0|61000.5|5" />'
        self.assertEqual(parse_fchart(xml), {"202603": 62900.0, "202604": 61000.5})


if __name__ == "__main__":
    unittest.main()
