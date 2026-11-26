from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from localize_news_in_pack import COUNTRIES, PACK, SPEC, localize_pack  # noqa: E402
from macro_monitor.series import localize_news_fields, localize_news_query, localize_news_tags  # noqa: E402

US_WORDS = re.compile(r"\b(US|U\.S\.|BLS|BEA|Fed|FOMC)\b")


class LocalizeNewsQuery(unittest.TestCase):
    def test_us_default_becomes_the_countrys_own(self):
        self.assertEqual(localize_news_query("US CPI inflation consumer prices BLS", "KOR", "South Korea"),
                         "South Korea CPI inflation consumer prices")
        self.assertEqual(localize_news_query("US core CPI inflation", "GBR", "United Kingdom"), "United Kingdom core CPI inflation")

    def test_us_agency_becomes_the_countrys_statistics_agency(self):
        self.assertEqual(
            localize_news_query("US CPI inflation consumer prices BLS", "KOR", "South Korea", "Statistics Korea"),
            "South Korea CPI inflation consumer prices Statistics Korea")
        self.assertEqual(localize_news_query("US core PCE inflation Fed", "GBR", "United Kingdom", "ONS"),
                         "United Kingdom core PCE inflation")

    def test_us_card_and_country_specific_queries_are_kept(self):
        self.assertEqual(localize_news_query("US CPI inflation consumer prices BLS", "USA", "United States", "BLS"),
                         "US CPI inflation consumer prices BLS")
        self.assertEqual(localize_news_query("Bank Indonesia BI rate", "IDN", "Indonesia"), "Bank Indonesia BI rate")
        self.assertIsNone(localize_news_query(None, "KOR", "South Korea"))

    def test_tags(self):
        self.assertEqual(localize_news_tags(["cpi", "inflation", "BLS"], "KOR", "Statistics Korea"),
                         ["cpi", "inflation", "Statistics Korea"])
        self.assertEqual(localize_news_tags(["pce", "BEA", "fed"], "CAN", None), ["pce"])
        self.assertEqual(localize_news_tags(["cpi", "BLS"], "USA", "BLS"), ["cpi", "BLS"])


class LocalizeNewsFields(unittest.TestCase):
    SPEC_Q = "US CPI inflation consumer prices BLS"

    def test_engine_card_is_localized_once(self):
        ind = {"id": "cpi_yoy", "news_query": self.SPEC_Q, "news_tags": ["cpi", "inflation", "BLS"]}
        self.assertTrue(localize_news_fields(ind, "ZAF", "South Africa", "Stats SA"))
        self.assertEqual(ind["news_query"], "South Africa CPI inflation consumer prices Stats SA")
        self.assertEqual(ind["news_tags"], ["cpi", "inflation", "Stats SA"])
        before = copy.deepcopy(ind)
        self.assertFalse(localize_news_fields(ind, "ZAF", "South Africa", "Stats SA", self.SPEC_Q))
        self.assertEqual(ind, before)

    def test_earlier_agencyless_pack_card_is_upgraded(self):
        ind = {"news_query": "Russia CPI inflation consumer prices", "news_tags": ["cpi", "inflation", "BLS"]}
        self.assertTrue(localize_news_fields(ind, "RUS", "Russia", "Rosstat", self.SPEC_Q))
        self.assertEqual(ind["news_query"], "Russia CPI inflation consumer prices Rosstat")
        self.assertEqual(ind["news_tags"], ["cpi", "inflation", "Rosstat"])

    def test_country_configured_card_is_untouched(self):
        ind = {"news_query": "Bank of Korea base rate", "news_tags": ["bok", "fed"]}
        self.assertFalse(localize_news_fields(ind, "KOR", "South Korea", "Statistics Korea", self.SPEC_Q))
        self.assertEqual(ind, {"news_query": "Bank of Korea base rate", "news_tags": ["bok", "fed"]})


class ShippedPack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads(PACK.read_text(encoding="utf-8"))
        cls.spec = json.loads(SPEC.read_text(encoding="utf-8"))
        cls.countries = json.loads(COUNTRIES.read_text(encoding="utf-8"))

    def test_every_country_names_a_statistics_agency(self):
        for c in self.countries["countries"]:
            self.assertTrue(c.get("stats_agency"), c["iso3"])

    def test_no_non_us_card_searches_us_news(self):
        for country in self.pack["countries"]:
            if country["iso3"] == "USA":
                continue
            for ind in country.get("indicators") or []:
                where = f"{country['iso3']}:{ind.get('id')}"
                self.assertIsNone(US_WORDS.search(ind.get("news_query") or ""), where)
                self.assertFalse(set(ind.get("news_tags") or []) & {"BLS", "BEA"}, where)

    def test_patching_the_shipped_pack_is_a_no_op(self):
        pack = copy.deepcopy(self.pack)
        self.assertEqual(localize_pack(pack, self.spec, self.countries), [])
        self.assertEqual(pack, self.pack)


if __name__ == "__main__":
    unittest.main()
