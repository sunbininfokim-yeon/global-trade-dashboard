from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor.series import localize_news_query  # noqa: E402


class LocalizeNewsQuery(unittest.TestCase):
    def test_us_default_becomes_the_countrys_own(self):
        self.assertEqual(localize_news_query("US CPI inflation consumer prices BLS", "KOR", "South Korea"),
                         "South Korea CPI inflation consumer prices")
        self.assertEqual(localize_news_query("US core CPI inflation", "GBR", "United Kingdom"), "United Kingdom core CPI inflation")

    def test_us_card_and_country_specific_queries_are_kept(self):
        self.assertEqual(localize_news_query("US CPI inflation consumer prices BLS", "USA", "United States"),
                         "US CPI inflation consumer prices BLS")
        self.assertEqual(localize_news_query("Bank Indonesia BI rate", "IDN", "Indonesia"), "Bank Indonesia BI rate")
        self.assertIsNone(localize_news_query(None, "KOR", "South Korea"))


if __name__ == "__main__":
    unittest.main()
