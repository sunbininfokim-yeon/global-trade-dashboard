from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import us_fiscal_soma as fs  # noqa: E402


class SomaInterest(unittest.TestCase):
    def test_soma_tga_two_charts_same_axis(self):
        bs = {"dates": ["2026-11-11", "2026-11-18"], "sides": [
            {"layers": [{"id": "treasuries", "values": [4.58, 4.5871]}]},
            {"layers": [{"id": "tga", "values": [0.90, 0.9166]}]}]}
        p = fs.soma_tga_panel(bs)
        self.assertEqual(p["type"], "charts")
        self.assertEqual([c["dates"] for c in p["charts"]], [["26.11.11", "26.11.18"]] * 2)
        self.assertEqual(p["charts"][0]["series"][0]["values"], [4580.0, 4587.1])     # billions

    def test_duration_rail(self):
        wam = {"panels": [
            {"id": "duration", "dates": [f"2025-{m:02d}-28" for m in range(1, 13)] + ["2026-01-31"],
             "series": [{"label": "시장성 국채 전체", "values": [14.0] * 12 + [15.0]},
                        {"label": "민간 보유(연준 제외)", "values": [11.5] * 12 + [12.0]}]},
            {"id": "duration_flow", "dates": ["2025-12-31", "2026-01-31"],
             "series": [{"label": "연준(매입·만기)", "values": [-5.0, 20.0]}]}]}
        r = fs.duration_rail(wam)
        vals = {x["label"]: x["value"] for x in r["rows"]}
        self.assertEqual(vals["연준(SOMA) 보유"], "3.0조$ · 20.0%")
        self.assertIn("(1년 +0.50)", vals["민간 보유"])
        self.assertEqual(vals["최근 12개월 합계"], "+15십억$")
        self.assertEqual(fs.duration_rail(None), None)

    def test_interest_gdp_uses_fiscal_year_quarters(self):
        mts = [{"fiscal_year": 2026, "interest_tn_usd": 1.2}]
        gdp = [("2025-10-01", 30000.0), ("2026-01-01", 30000.0), ("2026-04-01", 30000.0), ("2026-07-01", 30000.0)]
        p = fs.interest_gdp_panel(mts, gdp, [("2024-01-01", 3.8), ("2026-01-01", 3.9)])
        self.assertEqual(p["dates"], ["FY2026"])                      # OMB years before the first MTS year are left out
        self.assertEqual(p["series"][0]["values"], [4.0])              # 1.2T / 30T
        self.assertEqual(p["series"][1]["values"], [3.9])

    def test_avg_rate_panel(self):
        rows = [{"record_date": "2026-10-31", "security_desc": "Total Interest-bearing Debt", "avg_interest_rate_amt": "3.580"},
                {"record_date": "2026-10-31", "security_desc": "Treasury Bills", "avg_interest_rate_amt": "4.014"}]
        p = fs.avg_rate_panel(rows)
        self.assertEqual(p["dates"], ["26.10"])
        self.assertEqual([s["values"][0] for s in p["series"]], [3.58, 4.014, None, None])


if __name__ == "__main__":
    unittest.main()
