#!/usr/bin/env python3
"""Contract tests for publish_kr_us_semiconductor (frozen engine, history)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import kr_to_us_semiconductor as eng  # noqa: E402
import publish_kr_us_semiconductor as pub  # noqa: E402

MODEL = json.loads(eng.MODEL.read_text())  # frozen through 2026-11-20


def write_prices(folder: Path, end: str) -> None:
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2024-01-01", end)
    for key, sym in eng.SYMBOLS.items():
        tz = "Asia/Seoul" if sym.endswith(".KS") or sym == "^KS11" else "America/New_York"
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, len(days))))
        opn = close * np.exp(rng.normal(0, 0.006, len(days)))
        ts = [int(pd.Timestamp(d).tz_localize(tz).replace(hour=9).tz_convert("UTC").timestamp()) for d in days]
        doc = {"chart": {"result": [{"meta": {"symbol": sym, "dataGranularity": "1d", "exchangeTimezoneName": tz},
                                     "timestamp": ts, "indicators": {"quote": [{"open": opn.tolist(), "close": close.tolist()}]}}]}}
        (folder / f"{key}.json").write_text(json.dumps(doc))


class TestPublisher(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.px = Path(self.td.name)
        write_prices(self.px, "2026-11-27")

    def tearDown(self):
        self.td.cleanup()

    def run_at(self, now, prev=None):
        return pub.run(self.px, MODEL, pd.Timestamp(now), prev, False)

    def test_replays_after_freeze_are_settled(self):
        hist, disp = self.run_at("2026-11-27T03:00:00Z")
        self.assertEqual([r["date"] for r in hist["rows"]], ["2026-11-23", "2026-11-24", "2026-11-25"])
        self.assertTrue(all(r["kind"] == "replay" and r["actual"]["mu"] for r in hist["rows"]))
        self.assertEqual(disp["latest"]["status"], "retrospective_replay")
        self.assertEqual(disp["next"]["target_date_us"], "2026-11-27")  # 11/26 US holiday

    def test_live_issue_then_settle_and_never_replaced(self):
        hist, disp = self.run_at("2026-11-27T08:00:00Z")
        live = hist["rows"][-1]
        self.assertEqual((live["date"], live["kind"]), ("2026-11-27", "live"))
        self.assertNotIn("actual", live)  # US session not closed yet
        self.assertEqual(disp["latest"]["status"], "research_forecast")
        hist2, _ = self.run_at("2026-11-28T01:00:00Z", hist)
        row = hist2["rows"][-1]
        self.assertEqual(row["kind"], "live")
        self.assertEqual(row["p"], live["p"])  # the issued forecast is kept as issued
        self.assertIn("mu", row["actual"])

    def test_outside_window_issues_nothing(self):
        hist, _ = self.run_at("2026-11-27T05:00:00Z")  # 14:00 KST, KRX still open
        self.assertNotIn("2026-11-27", [r["date"] for r in hist["rows"]])

    def test_score_skips_flat_and_coin_flip(self):
        rows = [{"p": {"mu": {"opening": 0.7, "closing": 0.5}}, "actual": {"mu": {"open": 0.01, "close": 0.02}}},
                {"p": {"mu": {"opening": 0.3, "closing": 0.4}}, "actual": {"mu": {"open": 0.0, "close": 0.01}}}]
        s = pub.score(rows)["mu"]
        self.assertEqual(s["opening"], {"n": 1, "hit": 1})
        self.assertEqual(s["closing"], {"n": 1, "hit": 0})


if __name__ == "__main__":
    unittest.main()
