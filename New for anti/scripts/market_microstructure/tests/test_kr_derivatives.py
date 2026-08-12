"""Contract tests for foreign futures/call/put daily flow inputs."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_derivatives_board import append_foreign_flow_history, foreign_flow_points  # noqa: E402
from fetch_kr_derivatives import fetch_kr_derivatives_bundle, load_investor_csv  # noqa: E402


class TestKrDerivatives(unittest.TestCase):
    def test_csv_keeps_buy_sell_and_calculates_net(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "foreign_call.csv"
            path.write_text("일자,외국인 매수,외국인 매도\n2026/08/11,12500,8000\n", encoding="utf-8-sig")
            rows = load_investor_csv(path)
        self.assertEqual(rows[0]["foreign_buy_mn_krw"], 12500.0)
        self.assertEqual(rows[0]["foreign_sell_mn_krw"], 8000.0)
        self.assertEqual(rows[0]["foreign_net_mn_krw"], 4500.0)

    def test_net_only_csv_does_not_invent_buy_sell(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "foreign_put.csv"
            path.write_text("일자,외국인 합계\n2026-08-11,-421\n", encoding="utf-8-sig")
            rows = load_investor_csv(path)
        self.assertIsNone(rows[0]["foreign_buy_mn_krw"])
        self.assertIsNone(rows[0]["foreign_sell_mn_krw"])
        self.assertEqual(rows[0]["foreign_net_mn_krw"], -421.0)

    def test_no_csv_stays_missing_not_demo(self):
        old = {k: os.environ.pop(k, None) for k in ("KRX_API", "KRX_OPENAPI_KEY")}
        try:
            bundle = fetch_kr_derivatives_bundle(bas_dd="20260811")
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v
        inv = bundle["investor_nets"]
        self.assertEqual(inv["quality"], "missing")
        self.assertIsNone(inv["latest"]["futures"])
        self.assertNotIn("fixture_seed", bundle["source_priority_used"])

    def test_history_merges_observed_products_by_date(self):
        investor = {
            "futures": [{"date": "2026-08-11", "foreign_buy_mn_krw": 1000, "foreign_sell_mn_krw": 900, "foreign_net_mn_krw": 100}],
            "options_call": [{"date": "2026-08-11", "foreign_buy_mn_krw": None, "foreign_sell_mn_krw": None, "foreign_net_mn_krw": -50}],
            "options_put": None,
        }
        self.assertEqual(len(foreign_flow_points(investor)), 1)
        with tempfile.TemporaryDirectory() as td:
            out = append_foreign_flow_history(Path(td) / "history.json", investor)
        point = out["points"][0]
        self.assertEqual(out["quality"], "observed")
        self.assertEqual(point["futures"]["foreign_net_mn_krw"], 100)
        self.assertEqual(point["options_call"]["foreign_net_mn_krw"], -50)


if __name__ == "__main__":
    unittest.main()
