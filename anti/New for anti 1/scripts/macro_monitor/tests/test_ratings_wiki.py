"""Offline smoke for Wikipedia ratings mapper (no network)."""

from __future__ import annotations

import unittest

from macro_monitor.ratings_wiki import WIKI_NAMES, _lookup
import pandas as pd


class TestRatingsWiki(unittest.TestCase):
    def test_lookup_sp(self):
        df = pd.DataFrame(
            {
                "Country/Territory": ["United States", "South Korea", "Israel"],
                "Rating": ["AA+", "AA", "A"],
                "Outlook": ["Stable", "Stable", "Stable"],
            }
        )
        df["_name"] = df["Country/Territory"]
        hit = _lookup(df, WIKI_NAMES["USA"])
        self.assertEqual(hit["rating"], "AA+")
        hit = _lookup(df, WIKI_NAMES["KOR"])
        self.assertEqual(hit["rating"], "AA")


if __name__ == "__main__":
    unittest.main()
