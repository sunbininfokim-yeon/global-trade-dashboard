import os
import tempfile
import unittest
from datetime import date

from . import ledger as L


def entry(crop, year, verdict, done=True, check=None):
    return {"crop": crop, "label_ko": crop, "season": str(year), "harvest_year": year,
            "stages": [{"state": "done"}, {"state": "done" if done else "in_progress"}],
            "overall": {"verdict": verdict, "verdict_ko": verdict, "score": -2, "history_check": check}}


class LedgerTest(unittest.TestCase):
    def test_freeze_once_score_when_yield_arrives(self):
        book = {"started": None, "entries": {}}
        regions = {"corn_belt": [entry("corn", 2026, "unfavorable"), entry("soybeans", 2026, "favorable", done=False)]}
        self.assertEqual(L.freeze(book, regions, date(2026, 11, 20)), ["corn_belt|corn|2026"])
        # A later run with a different call does not rewrite the frozen one.
        regions["corn_belt"][0]["overall"]["verdict"] = "neutral"
        self.assertEqual(L.freeze(book, regions, date(2026, 11, 27)), [])
        self.assertEqual(book["entries"]["corn_belt|corn|2026"]["verdict"], "unfavorable")
        # No yield yet: pending.
        self.assertEqual(L.score(book, lambda r, c: {2025: 0.01}), [])
        self.assertEqual(L.summary(book)["pending"], 1)
        # Yield in, below trend: a hit.
        L.score(book, lambda r, c: {2026: -0.042})
        s = L.summary(book)
        self.assertEqual((s["unfavorable"]["n"], s["unfavorable"]["hits"]), (1, 1))
        self.assertEqual(s["recent"][0]["residual_pct"], -4.2)
        self.assertEqual(L.entry_record(book, "corn_belt", "corn")[0]["hit"], True)

    def test_reference_only_calls_kept_apart(self):
        book = {"started": None, "entries": {}}
        L.freeze(book, {"a": [entry("wheat", 2026, "unfavorable", check="unmatched")]}, date(2026, 12, 1))
        L.score(book, lambda r, c: {2026: 0.03})
        s = L.summary(book)["unfavorable"]
        self.assertEqual((s["n"], s["hits"], s["firm_n"]), (1, 0, 0))

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.json")
            book = {"started": "2026-11-20", "entries": {}}
            L.save(book, p)
            self.assertEqual(L.load(p), book)

    def test_provisional_until_final(self):
        book = {"started": None, "entries": {}}
        L.freeze(book, {"corn_belt": [entry("soybeans", 2026, "favorable")]}, date(2026, 11, 1))
        info = {"country": "United States", "country_ko": "미국", "commodity": "x",
                "market_year": "2026/27", "yield_t_ha": 3.6}
        L.score_provisional(book, lambda r, c, y: (0.04, info), date(2026, 11, 23))
        row = book["entries"]["corn_belt|soybeans|2026"]
        self.assertEqual((row["provisional"]["residual_pct"], row["provisional"]["hit"]), (4.0, True))
        self.assertEqual(L.summary(book)["provisional"]["hits"], 1)
        L.score(book, lambda r, c: {2026: -0.01})
        L.score_provisional(book, lambda r, c, y: (0.04, info), date(2027, 2, 1))
        self.assertNotIn("provisional", row)
        self.assertEqual(L.summary(book)["provisional"]["n"], 0)

    def test_national_residual_offsets(self):
        import pandas as pd
        from stage_conditions import usda_yields as U
        years = list(range(2014, 2027))
        psd = pd.DataFrame({"country": "Brazil", "commodity": U.SOY, "year": years,
                            "yield": [3.0 * 1.01 ** (y - 2014) for y in years]})
        psd.loc[psd.year == 2026, "yield"] *= 0.9
        res, info = U.national_residual(psd, "mato_grosso_soja", "soy", 2027)
        self.assertAlmostEqual(res, float(__import__("numpy").log(0.9)), places=3)
        self.assertEqual(info["market_year"], "2026/27")
        self.assertEqual(U.national_residual(psd, "sp_cana", "coffee", 2027), (None, None))


if __name__ == "__main__":
    unittest.main()
