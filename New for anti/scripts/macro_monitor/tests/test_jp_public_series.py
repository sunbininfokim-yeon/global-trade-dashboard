"""Japan public series (macro_monitor.jp_public_series). Fixtures are excerpts of the real answers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import jp_public_series as jps  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

BOJ_OK = """STATUS,200
MESSAGEID,M181000I
MESSAGE,Successfully completed
DATE,2026-09-26T13:35:33.459+09:00
PARAMETER,FORMAT,CSV
NEXTPOSITION,
SERIES_CODE,NAME_OF_TIME_SERIES,UNIT,FREQUENCY,CATEGORY,LAST_UPDATE,SURVEY_DATES,VALUES
MABJMTA,"Bank of Japan Accounts/Assets/Total (Assets, or Liabilities and Net Assets) (s)",100 million yen,MONTHLY,Bank of Japan Accounts,20260901,202607,6497120
MABJMTA,"Bank of Japan Accounts/Assets/Total (Assets, or Liabilities and Net Assets) (s)",100 million yen,MONTHLY,Bank of Japan Accounts,20260901,202608,6446620
MABJMTA,"x",100 million yen,MONTHLY,Bank of Japan Accounts,20260901,202609,
"""

MOF = """Interest Rate (September 2026),,,,,,,,,,,,,,,(Unit : %)
Date,1Y,2Y,3Y,4Y,5Y,6Y,7Y,8Y,9Y,10Y,15Y,20Y,25Y,30Y,40Y
2026/8/31,1.20,1.743,1.9,2.0,2.2,2.4,2.6,2.7,2.8,2.943,3.4,3.9,4.0,4.092,4.1
2026/9/1,1.21,1.75,1.9,2.0,2.2,2.4,2.6,2.7,2.8,2.95,3.4,3.9,4.0,4.10,4.1
2026/9/24,1.30,1.912,2.0,2.1,2.3,2.5,2.7,2.8,2.9,3.073,3.5,4.0,4.1,-,4.2
"""

CFTC_ROWS = [
    {"report_date_as_yyyy_mm_dd": "2026-09-22T00:00:00.000", "noncomm_positions_long_all": "192274", "noncomm_positions_short_all": "120292"},
    {"report_date_as_yyyy_mm_dd": "2026-09-15T00:00:00.000", "noncomm_positions_long_all": "237951", "noncomm_positions_short_all": "117592"},
]


class Parsers(unittest.TestCase):
    def test_boj_rows_become_first_of_month_points_and_blank_values_are_skipped(self):
        self.assertEqual(jps.parse_boj_csv(BOJ_OK), [("2026-07-01", 6497120.0), ("2026-08-01", 6446620.0)])

    def test_boj_answer_that_is_not_ok_raises(self):
        with self.assertRaises(ValueError):
            jps.parse_boj_csv("STATUS,400\nMESSAGE,Invalid\n")

    def test_mof_yields_by_tenor_with_missing_marked_by_dash(self):
        y = jps.parse_mof_jgb(MOF)
        self.assertEqual(y["10Y"][-1], ("2026-09-24", 3.073))
        self.assertEqual([d for d, _ in y["30Y"]], ["2026-08-31", "2026-09-01"])          # 9/24 had no 30Y quote

    def test_month_last_keeps_the_latest_day_of_each_month(self):
        y = jps.parse_mof_jgb(MOF)
        self.assertEqual(jps.month_last(y["10Y"]), [("2026-08-31", 2.943), ("2026-09-24", 3.073)])

    def test_cftc_net_is_long_minus_short_ascending(self):
        self.assertEqual(jps.parse_cftc_yen(CFTC_ROWS), [("2026-09-15", 237951 - 117592.0), ("2026-09-22", 192274 - 120292.0)])


class Transforms(unittest.TestCase):
    def test_ratio_uses_the_months_quarter_and_the_latest_quarter_after_it(self):
        monthly = [("2026-03-01", 600.0), ("2026-04-01", 640.0), ("2026-07-01", 650.0), ("2026-08-01", 660.0)]
        gdp = [("2026-01-01", 600.0), ("2026-04-01", 640.0)]                       # Q1, Q2; Q3 is not out
        out = jps.ratio_to_quarterly(monthly, gdp)
        self.assertEqual([round(v, 1) for _, v in out], [100.0, 100.0, 101.6, 103.1])

    def test_months_before_the_first_quarter_are_left_out(self):
        self.assertEqual(jps.ratio_to_quarterly([("2025-12-01", 1.0)], [("2026-01-01", 2.0)]), [])

    def test_spread_is_in_bp_and_only_on_shared_dates(self):
        self.assertEqual(jps.spread_bp([("a", 3.0), ("b", 3.1)], [("a", 1.8)]), [("a", 120.0)])

    def test_last_point_of_an_unfinished_month_keeps_its_own_date(self):
        patch = {"history": {"5y": {"dates": ["2026-08-31", "2026-09-30"], "values": [1.0, 2.0]}}}
        jps.pin_last_date(patch, "2026-09-24")
        self.assertEqual(patch["history"]["5y"]["dates"], ["2026-08-31", "2026-09-24"])
        done = {"history": {"5y": {"dates": ["2026-08-31"], "values": [1.0]}}}
        jps.pin_last_date(done, "2026-08-31")
        self.assertEqual(done["history"]["5y"]["dates"], ["2026-08-31"])


def stub_sources(**series):
    return jps.Sources(boj=lambda db, code: series[f"{db}/{code}"], fred=lambda sid: series[sid],
                       mof=lambda: series["jgb"], cftc=lambda: series["yen"])


class Series(unittest.TestCase):
    def test_units_are_converted_to_what_the_card_says(self):
        s = stub_sources(**{"BS01/MABJMTA": [("2026-08-01", 6446620.0)], "BS01/MABJMA004": [("2026-08-01", 6510.0)],
                            "TRESEGJPM052N": [("2026-08-01", 1083420.49)], "yen": [("2026-09-22", 71982.0)]})
        self.assertAlmostEqual(jps.series_for("boj_total_assets", s)[-1][1], 644.662)      # 100 million yen -> trillion yen
        self.assertAlmostEqual(jps.series_for("boj_jreit", s)[-1][1], 651.0)               # -> billion yen
        self.assertAlmostEqual(jps.series_for("fx_reserves", s)[-1][1], 1083.42049, places=4)   # million USD -> billion USD
        self.assertAlmostEqual(jps.series_for("yen_imm_net", s)[-1][1], 71.982)            # contracts -> thousand

    def test_patch_shows_the_observation_date_for_daily_sourced_series(self):
        y = jps.parse_mof_jgb(MOF)
        s = stub_sources(jgb=y)
        pts = jps.series_for("bond_10y", s)
        p = jps.build_patch("bond_10y", pts, retrieved_at="t")
        self.assertEqual((p["display"], p["asof"], p["data_status"]), ("3.07%", "2026-09-24", "live"))
        self.assertEqual(p["history"]["5y"]["dates"][-1], "2026-09-24")

    def test_every_spec_has_a_series_definition(self):
        for spec_id in jps.SPECS:
            self.assertIn(spec_id, {"boj_total_assets", "boj_assets_yoy", "boj_assets_gdp", "boj_etf", "boj_jreit", "call_rate", "m2_vs_2019",
                                    "cgpi", "current_account", "gdp_yoy", "gdp_qoq", "fx_reserves", "bond_2y", "bond_10y", "bond_30y",
                                    "spread_10y2y", "spread_30y10y", "yen_imm_net"})


class Apply(unittest.TestCase):
    def pack(self):
        def ind(i, status="demo", **kw):
            return {"id": i, "label_ko": i, "data_status": status, "quality": "demo", **kw}
        return {"indicators": [ind("gdp_yoy", "official_snapshot"), ind("gdp_qoq"), ind("gdp"), ind("boj_etf"),
                               ind("boj_etf_holdings", components=[{"id": "boj_etf"}, {"id": "boj_etf_share"}])],
                "categories": {"growth": [{"id": "gdp"}]}, "headlines": [{"id": "gdp_yoy"}], "data_status_summary": {"demo": 9}}

    def test_gdp_composite_and_etf_holdings_follow_the_real_series(self):
        jpn = self.pack()
        pts = [("2025-04-01", 100.0), ("2025-07-01", 100.5), ("2025-10-01", 101.0), ("2026-01-01", 101.5), ("2026-04-01", 102.0)]
        s = stub_sources(JPNRGDPEXP=pts, **{"BS01/MABJMA003": [("2026-08-01", 369835.0)]})
        patches = {k: jps.build_patch(k, jps.series_for(k, s), retrieved_at="t") for k in ("gdp_yoy", "gdp_qoq", "boj_etf")}
        r = jps.apply_all(jpn, patches, retrieved_at="t")
        by = {i["id"]: i for i in jpn["indicators"]}
        self.assertEqual({"gdp_yoy", "gdp_qoq", "boj_etf", "gdp", "boj_etf_holdings"}, set(r["changed"]))
        self.assertEqual(by["gdp"]["display"], "2.0% | 0.5%")
        self.assertEqual(by["boj_etf_holdings"]["display"], "37.0T")
        self.assertEqual([c["id"] for c in by["boj_etf_holdings"]["components"]], ["boj_etf"])            # no invented market share
        self.assertEqual(jpn["data_status_summary"], {"live": 5})
        self.assertTrue(r["summary_changed"])
        again = jps.apply_all(jpn, patches, retrieved_at="later")
        self.assertEqual(again["changed"], [])                                                          # idempotent


if __name__ == "__main__":
    unittest.main()
