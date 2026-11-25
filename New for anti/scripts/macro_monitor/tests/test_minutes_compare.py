from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor.cb_collect import minutes_compare as mc  # noqa: E402
from macro_monitor.fomc_collect.minutes import _sentence_quantifier  # noqa: E402


def side(date, sentences):
    return {"meeting_date": date, "released_on": None, "source_url": None,
            "body": {"sections": [{"text": " ".join(sentences)}]}}


FILL = "The Committee reviewed the data and the staff projections in detail at length today."


class Compare(unittest.TestCase):
    def test_counts_per_thousand_words_and_new_sentence(self):
        prev = side("2026-09-17", [FILL] * 40 + ["Inflation was discussed briefly here."])
        cur = side("2026-11-05", [FILL] * 40 + ["Inflation was discussed briefly here.",
                                                "Energy prices pushed inflation higher again this month."])
        r = mc.compare(prev, cur, lang="en", min_words=100)
        t = {x["id"]: x for x in r["topics"]}
        self.assertEqual((t["inflation"]["prev_count"], t["inflation"]["cur_count"]), (1, 3))   # 'prices' + 'inflation'
        self.assertTrue(t["inflation"]["change_per_1k"] > 0)
        self.assertIn("Energy prices", t["energy"]["new_sentence"] or t["inflation"]["new_sentence"])

    def test_korean_consumption_is_not_consumer_prices(self):
        r = mc.compare(side("a", ["소비자물가 상승률이 높았음. " * 200]), side("b", ["소비자물가 상승률이 높았음. " * 200]),
                       lang="ko", min_words=100)
        self.assertEqual({x["id"]: x["cur_count"] for x in r["topics"]}["consumption"], 0)

    def test_euro_area_is_not_fx(self):
        r = mc.compare(side("a", ["Euro area growth was solid. " * 60]), side("b", ["Euro area growth was solid. " * 60]),
                       lang="en", min_words=100)
        self.assertEqual({x["id"]: x["cur_count"] for x in r["topics"]}["fx"], 0)

    def test_too_short_gives_nothing(self):
        self.assertIsNone(mc.compare(side("a", [FILL]), side("b", [FILL]), lang="en"))


class FomcQuantifiers(unittest.TestCase):
    def test_bare_quantifiers_from_the_october_2026_minutes(self):
        self.assertEqual(_sentence_quantifier("Many pointed to elevated inflation."), ("many", "many"))
        self.assertEqual(_sentence_quantifier("A majority noted that risks were balanced."), ("a majority", "most"))
        self.assertEqual(_sentence_quantifier("The vast majority noted that energy prices rose.")[1], "most")
        self.assertEqual(_sentence_quantifier("A few, however, saw downside risks.")[1], "few")
        self.assertIsNone(_sentence_quantifier("Many firms reported higher costs."))
        self.assertEqual(_sentence_quantifier("Several participants noted that X.")[1], "several")


if __name__ == "__main__":
    unittest.main()
