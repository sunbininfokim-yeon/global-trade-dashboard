from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_microstructure import kospi_holders as kh  # noqa: E402

PORTFOLIO = """<div>포트폴리오 개요 ( 2026년 8월 말 기준) --> 전체자산 <b>1684.4</b> 조 원
금융부문 1683.4 조 원 99.9 % 국내주식 <span>433.8</span> 조 원 25.8 % 국내채권 282.2 조 원 16.8 %
해외주식 619.3 조 원 36.8 % 해외채권 98.5 조 원 5.8 % 대체투자 240.4 조 원 14.3 %
단기자금 4.3 조 원 0.3 % 복지 ·기타 부문 1.0 조 원 0.1 %</div>"""


def yearly(rows):
    return "".join(f"<tr><td>{y}</td><td>{v}</td><td>{p}</td></tr>" for y, v, p in rows)


class NpsPages(unittest.TestCase):
    def test_portfolio_month_end(self):
        got = kh.parse_nps_portfolio(PORTFOLIO)
        self.assertEqual(got["month"], "2026-08")
        self.assertEqual(got["total_jo"], 1684.4)
        self.assertEqual(got["assets"]["domestic_equity"], {"jo": 433.8, "pct": 25.8})
        self.assertEqual(got["assets"]["overseas_bond"]["jo"], 98.5)

    def test_portfolio_missing_piece_raises(self):
        with self.assertRaises(ValueError):
            kh.parse_nps_portfolio(PORTFOLIO.replace("해외채권", "해외 채권"))

    def test_year_ends_drop_the_current_year_and_average_the_total(self):
        pages = {
            "domestic_equity": kh.parse_nps_yearly(yearly([("2025", "263737", "18.1"), ("2026", "433786", "25.8")])),
            "domestic_bond": kh.parse_nps_yearly(yearly([("2025", "304763", "20.9"), ("2026", "282230", "16.8")])),
            "overseas_equity": kh.parse_nps_yearly(yearly([("2025", "550485", "37.8"), ("2026", "619318", "36.8")])),
            "overseas_bond": kh.parse_nps_yearly(yearly([("2025", "101303", "7.0"), ("2026", "98536", "5.8")])),
        }
        ye = kh.nps_year_ends(pages, current_year="2026")
        self.assertEqual([y["month"] for y in ye], ["2025-12"])
        self.assertAlmostEqual(ye[0]["total_jo"], 1455, delta=5)
        self.assertEqual(ye[0]["assets"]["domestic_equity"]["jo"], 263.7)


class NpsMath(unittest.TestCase):
    def series(self, vals, start="2026-08-28"):
        return pd.Series(vals, index=pd.bdate_range(start, periods=len(vals)))

    def snap(self):
        return kh.parse_nps_portfolio(PORTFOLIO)

    def test_flat_markets_keep_the_published_weight(self):
        now = kh.nps_now(self.snap(), kospi=self.series([100, 100, 100]),
                         acwi=self.series([50, 50, 50]), usdkrw=self.series([1300, 1300, 1300]))
        self.assertAlmostEqual(now["weight_pct"], 433.8 / 1684.4 * 100, places=1)

    def test_scenarios_cross_each_line_where_the_table_says(self):
        now = {"domestic_equity_jo": 300.0, "others_jo": 1200.0, "kospi_now": {"close": 5000.0}}
        sc = kh.nps_scenarios(now)
        self.assertAlmostEqual(sc["rows"][0]["weight_pct"], 20.0)
        self.assertAlmostEqual(sc["rows"][0]["to_line_jo"]["target"], 0.208 * 1500 - 300, places=1)
        for c in sc["crossings"]:
            x = c["kospi"] / 5000
            w = 300 * x / (300 * x + 1200) * 100
            self.assertAlmostEqual(w, c["pct"], places=1)

    def test_path_jumps_to_each_new_publication(self):
        idx = pd.bdate_range("2025-12-30", "2026-09-04")
        k = pd.Series(100.0, index=idx)
        k[k.index >= "2026-03-02"] = 150.0
        flat = pd.Series(1.0, index=idx)
        dec = {"month": "2025-12", "total_jo": 1000.0, "assets": {
            "domestic_equity": {"jo": 200.0}, "overseas_equity": {"jo": 300.0}, "overseas_bond": {"jo": 100.0}}}
        aug = {**self.snap()}
        path = kh.nps_path([dec, aug], kospi=k, acwi=flat, usdkrw=flat)
        by = {p["date"]: p for p in path}
        self.assertAlmostEqual(by["2025-12-31"]["weight_pct"], 20.0)
        self.assertAlmostEqual(by["2026-03-02"]["weight_pct"], 300 / 1100 * 100, places=1)
        self.assertEqual(by["2026-08-31"]["basis"], "2026-08")
        self.assertAlmostEqual(by["2026-08-31"]["weight_pct"], 433.8 / 1684.4 * 100, places=1)


class Foreign(unittest.TestCase):
    def test_cap_weighted_and_partial_days_skipped(self):
        per = {"A": {"2026-11-16": (50.0, 100.0), "2026-11-17": (40.0, 100.0)},
               "B": {"2026-11-16": (10.0, 100.0), "2026-11-17": (10.0, 100.0)},
               "C": {"2026-11-17": (0.0, 1.0)}}
        shares = {"A": 3.0, "B": 1.0, "C": 1.0}
        got = kh.aggregate_foreign(per, shares)
        self.assertEqual([g["date"] for g in got], ["2026-11-16", "2026-11-17"])
        self.assertAlmostEqual(got[0]["foreign_pct"], (300 * 50 + 100 * 10) / 400, places=2)

    def test_a_missing_big_name_drops_the_day(self):
        per = {"A": {"2026-11-17": (40.0, 100.0)}, "B": {"2026-11-16": (10.0, 100.0), "2026-11-17": (10.0, 100.0)}}
        got = kh.aggregate_foreign(per, {"A": 3.0, "B": 1.0})
        self.assertEqual([g["date"] for g in got], ["2026-11-17"])

    def test_naver_rows(self):
        rows = kh.foreign_rows([{"bizdate": "20261117", "foreignerHoldRatio": "46.00%", "closePrice": "195,000"},
                                {"bizdate": "20261116", "foreignerHoldRatio": "", "closePrice": "1"}])
        self.assertEqual(rows, {"2026-11-17": (46.0, 195000.0)})


if __name__ == "__main__":
    unittest.main()
