import copy
import json
import unittest
from pathlib import Path

import refresh_mts as r

LIVE = json.loads((Path(__file__).resolve().parents[2] / "public/data/us_budget/mts_live_v1.json").read_text(encoding="utf-8"))
NAMES = ["October", "November", "December", "January", "February", "March", "April",
         "May", "June", "July", "August", "September"]


def report(blocks, record_date):
    """Synthetic Table 1 rows: {fy: [(receipts, outlays), ...]} in fiscal-month order."""
    rows = []
    for i, (fy, months) in enumerate(blocks.items()):
        pid = f"p{i}"
        rows.append({"classification_desc": f"FY {fy}", "classification_id": pid, "parent_id": "0", "record_type_cd": "T"})
        for name, (rec, out) in zip(NAMES, months):
            rows.append({"classification_desc": name, "classification_id": f"{pid}{name}", "parent_id": pid, "record_type_cd": "MTH",
                         r.RECEIPTS: str(rec), r.OUTLAYS: str(out), r.DEFICIT: str(rec - out), "record_date": record_date})
        rows.append({"classification_desc": "Year-to-Date", "classification_id": f"{pid}y", "parent_id": pid, "record_type_cd": "T",
                     r.RECEIPTS: str(sum(m[0] for m in months)), r.OUTLAYS: str(sum(m[1] for m in months)),
                     r.DEFICIT: str(sum(m[0] - m[1] for m in months))})
    return rows


def fy2026_from_live():
    return [(m["receipts"], m["outlays"]) for m in LIVE["months"] if m["month"] >= "2025-10"]


class RefreshTests(unittest.TestCase):
    def test_october_report_rolls_window_and_adds_partial_year(self):
        rows = report({2026: fy2026_from_live(), 2027: [(400e9, 690e9)]}, "2026-10-31")
        merged = r.merge(copy.deepcopy(LIVE), r.parse_report(rows, "2026-10-31"), "2026-10-31")
        months = [m["month"] for m in merged["months"]]
        self.assertEqual(len(months), 36)
        self.assertEqual(months[0], "2023-11")
        self.assertEqual(months[-1], "2026-10")
        self.assertEqual(merged["mts_record_date"], "2026-10-31")
        self.assertEqual(merged["fytd"], {"fy": 2027, "through": "2026-10", "receipts": 400e9, "outlays": 690e9,
                                          "deficit": 290e9, "complete": False})
        self.assertEqual(merged["months"][-1]["deficit"], 290e9)

    def test_ytd_row_is_never_counted_as_a_month(self):
        parsed = r.parse_report(report({2027: [(1, 2), (3, 5)]}, "2026-11-30"), "2026-11-30")
        self.assertEqual(sorted(parsed["months"]), ["2026-10", "2026-11"])

    def test_missing_field_fails_with_the_real_keys(self):
        rows = report({2027: [(1, 2)]}, "2026-10-31")
        del rows[1][r.OUTLAYS]
        with self.assertRaisesRegex(r.RefreshError, "row keys"):
            r.parse_report(rows, "2026-10-31")

    def test_large_jump_in_an_overlapping_month_is_rejected(self):
        months = fy2026_from_live()
        months[3] = (months[3][0], months[3][1] * 1.5)
        rows = report({2026: months, 2027: [(1e9, 2e9)]}, "2026-10-31")
        with self.assertRaisesRegex(r.RefreshError, ">2%"):
            r.merge(copy.deepcopy(LIVE), r.parse_report(rows, "2026-10-31"), "2026-10-31")

    def test_gap_in_series_is_rejected(self):
        # A November-only FY2027 report skipping October leaves a hole.
        rows = report({2027: [(1e9, 2e9), (1e9, 2e9)]}, "2026-11-30")
        rows = [x for x in rows if x.get("classification_desc") != "October"]
        with self.assertRaisesRegex(r.RefreshError, "gap"):
            r.merge(copy.deepcopy(LIVE), r.parse_report(rows, "2026-11-30"), "2026-11-30")

    def test_fetch_error_keeps_published_file(self):
        def blocked(_url):
            raise r.RefreshError("MTS HTTP 403")
        with self.assertRaises(r.RefreshError):
            r.latest_record_date(blocked)

    def test_omb_watch_reports_but_never_imports(self):
        annual = {"fy2027": {"year": {"fy": 2027}}}
        self.assertEqual(r.omb_watch(annual, head=lambda _u: 404)["available"], False)
        w = r.omb_watch(annual, head=lambda _u: 200)
        self.assertEqual((w["next_fy"], w["available"]), (2028, True))
        self.assertIn("hist01z1_fy2028.xlsx", w["url"])


if __name__ == "__main__":
    unittest.main()
