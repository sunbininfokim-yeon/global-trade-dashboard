"""T-bill auction rows for the QRA maturity tab (macro_monitor.qra.tbill)."""
from __future__ import annotations

import copy
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor.qra import tbill  # noqa: E402
import refresh_qra_quarters_in_pack as refresh_qra  # noqa: E402

WINDOW = {"start": "2026-08-01", "end": "2026-10-31"}
LABEL = "AUGUST 2026-OCTOBER 2026 QUARTER"


def _row(auction_date, term, offering_bn, accepted_bn=None, cmb="No"):
    return {
        "auction_date": auction_date,
        "security_term": term,
        "offering_amt": "null" if offering_bn is None else str(int(offering_bn * 1e9)),
        "total_accepted": "null" if accepted_bn is None else str(int(accepted_bn * 1e9)),
        "cash_management_bill_cmb": cmb,
    }


ROWS = [
    _row("2026-08-04", "4-Week", 80, 81),
    _row("2026-08-11", "4-Week", 85, 86),
    _row("2026-08-05", "13-Week", 92, 93),
    _row("2026-09-29", "13-Week", 90),          # announced, no result yet
    _row("2026-08-12", "52-Week", 50, 51),
    _row("2026-08-20", "35-Day", 40, 41, cmb="Yes"),
    _row("2026-09-30", "26-Week", None),        # no size published
]


class QuarterWindow(unittest.TestCase):
    def test_reads_tbac_label(self):
        self.assertEqual(tbill.quarter_window(LABEL), WINDOW)

    def test_crosses_year_end(self):
        self.assertEqual(
            tbill.quarter_window("NOVEMBER 2026-JANUARY 2027 QUARTER"),
            {"start": "2026-11-01", "end": "2027-01-31"},
        )

    def test_december_end(self):
        self.assertEqual(
            tbill.quarter_window("OCTOBER 2026-DECEMBER 2026 QUARTER")["end"], "2026-12-31")

    def test_unreadable_label_gives_none_not_a_guess(self):
        self.assertIsNone(tbill.quarter_window("Q3 2026"))
        self.assertIsNone(tbill.quarter_window(""))
        self.assertIsNone(tbill.quarter_window(None))


class Summarize(unittest.TestCase):
    def setUp(self):
        self.block = tbill.summarize(
            ROWS, quarter_label=LABEL, window=WINDOW, today=date(2026, 9, 25),
            outstanding=[{"date": "2026-08-31", "bn": 7248.1}, {"date": "2026-07-31", "bn": 6988.9}],
        )

    def test_terms_sorted_by_length_with_cmb_last(self):
        self.assertEqual([t["label"] for t in self.block["by_term"]], ["4W", "13W", "52W", "CMB"])

    def test_sizes_are_announced_offering_summed_per_term(self):
        by = {t["label"]: t for t in self.block["by_term"]}
        self.assertEqual(by["4W"]["offering_bn"], 165.0)
        self.assertEqual(by["13W"]["offering_bn"], 182.0)  # includes the not-yet-auctioned 90
        self.assertEqual(by["13W"]["n_auctioned"], 1)
        self.assertEqual(self.block["total_offering_bn"], 165 + 182 + 50 + 40)

    def test_counts_separate_results_announced_and_unsized(self):
        self.assertEqual(self.block["n_auctions"], 6)
        self.assertEqual(self.block["n_with_results"], 5)
        self.assertEqual(self.block["n_announced_only"], 1)
        self.assertEqual(self.block["n_without_size"], 1)

    def test_running_quarter_is_not_complete(self):
        self.assertFalse(self.block["complete"])
        self.assertEqual(self.block["through_auction_date"], "2026-09-29")
        self.assertEqual(self.block["through_result_date"], "2026-08-20")

    def test_complete_only_after_window_end_and_with_all_results(self):
        done = [r for r in ROWS if r["total_accepted"] != "null"]
        after = tbill.summarize(done, quarter_label=LABEL, window=WINDOW, today=date(2026, 11, 2))
        self.assertTrue(after["complete"])
        during = tbill.summarize(done, quarter_label=LABEL, window=WINDOW, today=date(2026, 10, 15))
        self.assertFalse(during["complete"])
        pending_after = tbill.summarize(ROWS, quarter_label=LABEL, window=WINDOW, today=date(2026, 11, 2))
        self.assertFalse(pending_after["complete"])

    def test_outstanding_change(self):
        self.assertEqual(self.block["outstanding"]["change_prev_month_bn"], 259.2)

    def test_no_rows_reports_reason_instead_of_zero(self):
        empty = tbill.summarize([], quarter_label=LABEL, window=WINDOW, today=date(2026, 9, 25))
        self.assertIsNone(empty["total_offering_bn"])
        self.assertTrue(empty["reason_missing"])
        self.assertFalse(empty["complete"])


class Note(unittest.TestCase):
    def test_running_quarter_says_it_is_not_the_quarter_total(self):
        block = tbill.summarize(ROWS, quarter_label=LABEL, window=WINDOW, today=date(2026, 9, 25),
                                outstanding=[{"date": "2026-08-31", "bn": 100.0}, {"date": "2026-07-31", "bn": 130.0}])
        note = tbill.note_ko(block)
        self.assertIn("분기 전체 합이 아닙니다", note)
        self.assertIn("순발행이 아니며", note)
        self.assertIn("전월말 대비 -$30B", note)

    def test_finished_quarter_says_so(self):
        done = [r for r in ROWS if r["total_accepted"] != "null"]
        block = tbill.summarize(done, quarter_label=LABEL, window=WINDOW, today=date(2026, 11, 2))
        note = tbill.note_ko(block)
        self.assertIn("(분기 전체)", note)
        self.assertNotIn("분기 전체 합이 아닙니다", note)


def _pack():
    return {
        "qra_issuance": {
            "components": [{"id": "c2y", "label_ko": "2Y", "tenor": "2y", "value": 207.0}],
            "components_note_ko": f"TBAC 권고 쿠폰 경매 규모의 분기 합계입니다. {tbill.BILL_NOTE_MARK}",
        },
        "tga": {
            "maturity_components": [{"id": "c2y", "label_ko": "2Y", "tenor": "2y", "value": 207.0}],
            "maturity_table": [{"kind": "coupon", "label_ko": "2Y", "tenor": "2y", "value_bn": 207.0}],
        },
    }


class Graft(unittest.TestCase):
    def setUp(self):
        self.block = tbill.summarize(ROWS, quarter_label=LABEL, window=WINDOW, today=date(2026, 9, 25))

    def test_adds_bill_rows_after_coupons_and_keeps_coupons(self):
        by_id = _pack()
        self.assertTrue(tbill.graft(by_id, self.block))
        comps = by_id["qra_issuance"]["components"]
        self.assertEqual(comps[0]["id"], "c2y")
        bills = [c for c in comps if c.get("kind") == "bill"]
        self.assertEqual([b["label_ko"] for b in bills], ["T-bill 4W", "T-bill 13W", "T-bill 52W", "T-bill CMB"])
        self.assertEqual(bills[1]["n_auctions"], 2)

    def test_idempotent(self):
        once = _pack()
        tbill.graft(once, self.block)
        twice = copy.deepcopy(once)
        tbill.graft(twice, self.block)
        self.assertEqual(once, twice)

    def test_tga_mirror_and_note(self):
        by_id = _pack()
        tbill.graft(by_id, self.block)
        self.assertEqual(len(by_id["tga"]["maturity_components"]), 5)
        self.assertEqual(by_id["tga"]["maturity_table"][-1]["kind"], "bill")
        self.assertNotIn(tbill.BILL_NOTE_MARK, by_id["qra_issuance"]["components_note_ko"])
        self.assertIn("따로 표시", by_id["qra_issuance"]["components_note_ko"])

    def test_no_auctions_leaves_pack_untouched(self):
        by_id = _pack()
        before = copy.deepcopy(by_id)
        empty = tbill.summarize([], quarter_label=LABEL, window=WINDOW, today=date(2026, 9, 25))
        self.assertFalse(tbill.graft(by_id, empty))
        self.assertEqual(by_id, before)


class Fetch(unittest.TestCase):
    def test_truncated_page_raises(self):
        page = {"meta": {"total-count": 900}, "data": [{"auction_date": "2026-08-04"}] * 500}
        with mock.patch.object(tbill, "_get", return_value=page):
            with self.assertRaises(RuntimeError):
                tbill.fetch_bill_auctions("2026-08-01", "2026-10-31")

    def test_retries_then_raises(self):
        with mock.patch.object(tbill, "_get", side_effect=ValueError("bad json")), \
                mock.patch.object(tbill.time, "sleep"):
            with self.assertRaises(RuntimeError):
                tbill.fetch_bill_auctions("2026-08-01", "2026-10-31")


class RegraftAfterQraRefresh(unittest.TestCase):
    """refresh_qra_quarters_in_pack resets components to coupons, then puts the stored bills back."""

    def _stored(self, tmp, label):
        block = tbill.summarize(ROWS, quarter_label=label, window=WINDOW, today=date(2026, 9, 25))
        path = Path(tmp) / "tbill_issuance_v1.json"
        import json
        path.write_text(json.dumps(block), encoding="utf-8")
        return path

    def test_same_quarter_regrafts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            by_id = _pack()
            with mock.patch.object(refresh_qra, "TBILL", self._stored(tmp, LABEL)):
                refresh_qra._regraft_tbill(by_id, LABEL)
        self.assertTrue(any(c.get("kind") == "bill" for c in by_id["qra_issuance"]["components"]))
        self.assertIn("tbill", by_id["qra_issuance"])

    def test_other_quarter_drops_bills_instead_of_mixing_quarters(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            by_id = _pack()
            by_id["qra_issuance"]["tbill"] = {"stale": True}
            with mock.patch.object(refresh_qra, "TBILL", self._stored(tmp, "MAY 2026-JULY 2026 QUARTER")):
                refresh_qra._regraft_tbill(by_id, LABEL)
        self.assertFalse(any(c.get("kind") == "bill" for c in by_id["qra_issuance"]["components"]))
        self.assertNotIn("tbill", by_id["qra_issuance"])

    def test_missing_file_is_a_no_op(self):
        by_id = _pack()
        before = copy.deepcopy(by_id)
        with mock.patch.object(refresh_qra, "TBILL", Path("/nonexistent/tbill.json")):
            refresh_qra._regraft_tbill(by_id, LABEL)
        self.assertEqual(by_id, before)


if __name__ == "__main__":
    unittest.main()
