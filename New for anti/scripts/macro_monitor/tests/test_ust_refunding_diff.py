from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import ust_refunding_diff as rd  # noqa: E402

A = ("WASHINGTON -- The Treasury is offering $125 billion. NOMINAL COUPON AND FRN FINANCING Treasury anticipates "
     "maintaining nominal coupon and FRN auction sizes for at least the next several quarters. The table below presents "
     "2-Year 3-Year 5-Year 7-Year 10-Year 20-Year 30-Year FRN May-26 69 58 70 44 42 16 25 28 Jun-26 69 58 70 44 39 13 22 28 "
     "for the May to July 2026 quarter. BUYBACKS Treasury will purchase up to $38 billion.")
B = ("WASHINGTON -- The Treasury is offering $126 billion. NOMINAL COUPON AND FRN FINANCING Treasury anticipates "
     "maintaining nominal coupon and FRN auction sizes for the next several quarters. Treasury will engage with market "
     "participants. The table below presents 2-Year 3-Year 5-Year 7-Year 10-Year 20-Year 30-Year FRN Aug-26 69 58 70 44 42 16 25 28 "
     "for the August to October 2026 quarter. BUYBACKS Treasury will purchase up to $70 billion.")


class RefundingDiff(unittest.TestCase):
    def test_sections_drop_opening_and_table(self):
        s = rd.sections(B)
        self.assertEqual(list(s), ["NOMINAL COUPON AND FRN FINANCING", "BUYBACKS"])
        self.assertIn("[입찰 규모 표]", s["NOMINAL COUPON AND FRN FINANCING"])
        self.assertNotIn("$126", " ".join(s.values()))

    def test_compare_finds_wording_not_calendar(self):
        r = rd.compare({"date": "2026-08-05", "url": "a", "text": A}, {"date": "2026-11-04", "url": "b", "text": B})
        coupon = next(x for x in r["sections"] if x["header"] == "NOMINAL COUPON AND FRN FINANCING")
        dropped = "".join(seg.get("before", "") for seg in coupon["segments"] if seg["op"] in ("delete", "replace"))
        self.assertIn("at least", dropped)
        # 'at least' (2) + 'Treasury will engage with market participants.' (6); May->August, July->October not counted
        self.assertEqual(coupon["changed_word_count"], 8)
        bb = next(x for x in r["sections"] if x["header"] == "BUYBACKS")
        self.assertEqual(bb["changed_word_count"], 2)


if __name__ == "__main__":
    unittest.main()
