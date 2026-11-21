from __future__ import annotations

import io
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_microstructure import nps_stocks as ns  # noqa: E402


def xlsx(header_stake: str, rows: list[tuple]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["※ 기금운용지침 …"])
    ws.append(["번호", "종목명", "평가액(억원)", "자산군 내 비중", header_stake])
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def filler(n: int, start: int = 10):
    return [(i, f"종목{i}", 1.0, 0.0001, 0.001) for i in range(start, start + n)]


class Holdings(unittest.TestCase):
    def test_fraction_columns_become_percent(self):
        rows = ns.parse_holdings_xlsx(xlsx("지분율", [(1, "삼성전자", 551094.5, 0.2106, 0.0776)] + filler(120)))
        self.assertEqual(rows[0]["stake_pct"], 7.76)
        self.assertAlmostEqual(rows[0]["weight_pct"], 21.06, places=2)

    def test_percent_numbers_and_strings_kept(self):
        rows = ns.parse_holdings_xlsx(xlsx("지분율(%)", [(1, "삼성전자", 398412.6, 0.22, 8.52)] + [
            (i, f"종목{i}", 1.0, "0.0%", 1.2) for i in range(2, 130)]))
        self.assertEqual(rows[0]["stake_pct"], 8.52)
        rows = ns.parse_holdings_xlsx(xlsx("지분율", [(1, "삼성전자", 1.0, "23.29%", "7.28%")] + [
            (i, f"종목{i}", 1.0, "0%", "1.11%") for i in range(2, 130)]))
        self.assertEqual(rows[0]["stake_pct"], 7.28)

    def test_links(self):
        html = '<a href="/fileDown.do?atchFileId=FL25002092&atchFileSn=2" class="btn-download" title="x">2025</a>'
        self.assertEqual(ns.parse_holdings_links(html),
                         {"2025": "https://fund.nps.or.kr/fileDown.do?atchFileId=FL25002092&atchFileSn=2"})


class Dart(unittest.TestCase):
    def test_only_nps_filings(self):
        got = ns.nps_reports([
            {"repror": "국민연금공단", "rcept_dt": "20261110", "stkrt": "8.01", "stkrt_irds": "-1.02", "stkqy": "1,000", "rcept_no": "2"},
            {"repror": "국민연금공단", "rcept_dt": "2026-03-10", "stkrt": "7.5", "rcept_no": "1"},
            {"repror": "블랙록", "rcept_dt": "20261111", "stkrt": "5.0", "rcept_no": "3"}])
        self.assertEqual([g["date"] for g in got], ["2026-03-10", "2026-11-10"])   # both date formats
        self.assertEqual(got[1]["stake_pct"], 8.01)
        self.assertEqual(got[1]["chg_pp"], -1.02)


class Build(unittest.TestCase):
    def test_year_end_and_reports_merge_and_old_years_are_not_refetched(self):
        top = [{"ticker": "005930", "label_ko": "삼성전자", "marcap": 1000e12, "rank": 1}]
        blob = xlsx("지분율", [(1, "삼성전자", 1.0, 0.2, 0.0776)] + filler(120))
        calls = []
        out = ns.build_nps_stocks(
            top=top, previous={"year_end": {"2024": {"tickers": {"005930": {"stake_pct": 7.26, "value_eok": 1}}}}},
            holdings_links={"2024": "u24", "2025": "u25"},
            fetch_file=lambda u: calls.append(u) or blob,
            corp_index={"005930": ["00126380", "삼성전자"]},
            fetch_dart=lambda c: [{"repror": "국민연금공단", "rcept_dt": "20260310", "stkrt": "8.0", "rcept_no": "1"}])
        self.assertEqual(calls, ["u25"])
        b = out["by_ticker"]["005930"]
        self.assertEqual([p["date"] for p in b["points"]], ["2024-12-31", "2025-12-31", "2026-03-10"])
        self.assertEqual(b["est_value_jo_now"], 80.0)

    def test_dart_failure_keeps_stored_reports(self):
        top = [{"ticker": "005930", "label_ko": "삼성전자", "marcap": 1e12}]
        prev = {"by_ticker": {"005930": {"reports": [{"date": "2026-03-10", "kind": "dart_5pct", "stake_pct": 8.0}]}}}

        def boom(_c):
            raise RuntimeError("down")
        out = ns.build_nps_stocks(top=top, previous=prev, holdings_links={}, fetch_file=None,
                                  corp_index={"005930": ["x"]}, fetch_dart=boom)
        self.assertEqual(out["by_ticker"]["005930"]["latest"]["stake_pct"], 8.0)
        self.assertTrue(out["errors"])


class Schedule(unittest.TestCase):
    def test_rules(self):
        cal = {x["id"]: x for x in ns.schedule(date(2026, 11, 20), nps_history=[{"month": "2026-08", "kind": "month_end"}],
                                               year_end_years=["2025"])}
        self.assertEqual(cal["foreign"]["next"], "2026-11-23")          # Friday -> Monday
        self.assertEqual(cal["dart_5pct"]["next"], "2026-12-10")
        self.assertIsNone(cal["nps_month"]["next"])
        self.assertEqual(cal["nps_year_end"]["next"], "2027-Q3")

    def test_month_estimate_from_seen_gaps(self):
        hist = [{"month": "2026-08", "kind": "month_end", "first_seen": "2026-11-10"},
                {"month": "2026-09", "kind": "month_end", "first_seen": "2026-12-10"}]
        cal = {x["id"]: x for x in ns.schedule(date(2026, 12, 11), nps_history=hist, year_end_years=[])}
        self.assertEqual(cal["nps_month"]["kind"], "estimate")
        self.assertTrue(cal["nps_month"]["next"].startswith("2027-01"))


if __name__ == "__main__":
    unittest.main()
