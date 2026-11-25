from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import ust_maturity as um  # noqa: E402
import wire_ust_maturity as w  # noqa: E402


def row(cls, cusip, mat, amt, rec="2026-10-31"):
    return {"record_date": rec, "security_class1_desc": cls, "security_class2_desc": cusip, "maturity_date": mat,
            "outstanding_amt": amt}


class Summarize(unittest.TestCase):
    def test_outstanding_only_once_per_security(self):
        # A reopened bill: three issue rows, the outstanding amount on one of them.
        rows = [row("Bills Maturity Value", "B1", "2027-04-30", "null"),
                row("Bills Maturity Value", "B1", "2027-04-30", "300000"),
                row("Bills Maturity Value", "B1", "2027-04-30", "null"),
                row("Bonds", "N1", "2036-10-31", "100000"),
                row("Total Marketable", "", "null", "400000")]
        s = um.summarize(rows)
        self.assertEqual(s["by_class_bn"], {"bills": 300.0, "bonds": 100.0})
        self.assertEqual(s["bills_share_pct"], 75.0)
        # 0.5y * 300 + 10y * 100 over 400 = 2.875y = 34.5 months (365.25-day years)
        self.assertAlmostEqual(s["wam_months"], 34.5, delta=0.1)
        self.assertEqual(s["maturity_wall_bn"]["2027"], {"bills": 300.0})
        self.assertNotIn("2036", s["maturity_wall_bn"])          # beyond the ten-year window

    def test_card_panels(self):
        ms = um.monthly([row("Bills Maturity Value", "B1", "2027-04-30", "300000"),
                         row("Notes", "N1", "2029-10-31", "100000")])
        c = um.card(ms, "2026-11-25T00:00:00Z")
        self.assertEqual(c["id"], "ust_debt_wam")
        self.assertEqual([p["id"] for p in c["panels"]], ["bills_share", "maturity_wall"])
        self.assertEqual(c["panels"][1]["dates"], ["2027", "2029"])


class Duration(unittest.TestCase):
    def test_par_ten_year_and_bill(self):
        p, d = um.price_duration(10, 0.05, 0.05, "notes")
        self.assertAlmostEqual(p, 1.0, places=6)
        self.assertAlmostEqual(d, 7.79, delta=0.02)               # modified duration of a 5% par 10-year
        p, d = um.price_duration(0.5, 0, 0.04, "bills")
        self.assertAlmostEqual(d, 0.49, delta=0.01)

    def test_summary_takes_out_fed_holdings(self):
        curve = [(0.25, 0.04), (2, 0.04), (10, 0.05), (30, 0.05)]
        rows = [row("Bills Maturity Value", "B1", "2027-04-30", "300000"),
                {**row("Notes", "N1", "2036-10-31", "100000"), "interest_rate_pct": "5.0"}]
        s = um.summarize(rows, curve=curve, soma={"N1": 50.0}, soma_asof="2026-10-28")["duration"]
        self.assertAlmostEqual(s["teneq_bn"], 100 + 300 * (0.49 / 7.79), delta=2)   # bills add ~19bn of 10y risk
        self.assertAlmostEqual(s["fed_share_pct"], 50 * 7.79 / (s["dv01_mn"] / 0.1) * 100, delta=1)
        self.assertGreater(s["dv01_by_class_mn"]["notes"], 5 * s["dv01_by_class_mn"]["bills"])   # 100bn of 10y vs 300bn of bills


class Toolkit(unittest.TestCase):
    def test_change_after_each_action_from_the_close_before(self):
        dgs = [("2026-08-17", 5.30), ("2026-08-18", 5.28), ("2026-08-19", 5.19), ("2026-08-20", 5.20),
               ("2026-08-21", 5.15), ("2026-08-24", 5.16), ("2026-08-25", 5.17)]
        tk = w.toolkit(dgs, [{"date": "2026-08-19", "kind": "buyback", "title": "t", "url": "u"}], "2026-08-01")
        e = tk["events"][0]
        self.assertEqual((e["on"], e["before_pct"], e["d1_bp"], e["d5_bp"], e["d20_bp"]), ("2026-08-19", 5.28, -9, -11, None))


if __name__ == "__main__":
    unittest.main()
