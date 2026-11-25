from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import ust_projection as pj  # noqa: E402

TEXT = ("2-Year 3-Year 5-Year 7-Year 10-Year 20-Year 30-Year FRN Nov-26 69 58 70 44 42 16 25 28 "
        "Dec-26 69 58 70 44 39 13 22 28 Jan-27 69 58 70 44 39 13 22 30 Treasury plans ... "
        "the November 10-year TIPS reopening auction size at $19 billion, the December 5-year TIPS reopening auction "
        "size at $24 billion, and the January 10-year TIPS new issue auction size at $21 billion.")


def row(cls, mat, amt):
    return {"record_date": "2026-10-31", "security_class1_desc": cls, "maturity_date": mat, "outstanding_amt": amt}


class Projection(unittest.TestCase):
    def test_parse_table_and_tips(self):
        t = pj.parse_auction_table(TEXT)
        self.assertEqual(list(t), ["2026-11", "2026-12", "2027-01"])
        self.assertEqual(sum(t["2026-11"].values()), 352)
        self.assertEqual(pj.parse_tips(TEXT, "2026-11-04"), {"2026-11": (10.0, 19.0), "2026-12": (5.0, 24.0), "2027-01": (10.0, 21.0)})

    def test_sizes_held_beyond_the_table(self):
        t, tips = pj.parse_auction_table(TEXT), pj.parse_tips(TEXT, "2026-11-04")
        issues, src = pj.issuance_for("2027-02", t, tips)
        self.assertEqual((src, sum(s for _, s in issues)), ("repeat", 352 + 19))

    def test_quarter_estimates(self):
        ev = [{"id": "2026-Q4", "estimates": {"quarters": [
            {"period": "October–December 2026", "kind": "estimate", "net_borrowing_bn": 618.0},
            {"period": "July–September 2026", "kind": "actual", "net_borrowing_bn": 742.0}]}}]
        q = pj.quarter_estimates(ev)
        self.assertEqual(q, {"2026-10": {"estimate": 618.0}, "2026-07": {"actual": 742.0}})

    def test_bills_take_the_rest(self):
        rows = [row("Bills Maturity Value", "2027-01-31", "100000"), row("Notes", "2026-11-15", "50000"),
                row("Notes", "2030-10-31", "850000")]
        p = pj.project(rows, "2026-10-31", {"2026-10": {"estimate": 300.0}}, pj.parse_auction_table(TEXT), {}, 1)[0]
        # 100 of net borrowing this month; coupons 352 issued, 50 matured -> bills -202
        self.assertEqual((p["coupon_gross_bn"], p["coupon_maturing_bn"], p["bills_net_bn"]), (352.0, 50.0, -202.0))


if __name__ == "__main__":
    unittest.main()
