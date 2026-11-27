from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import card_news as cn  # noqa: E402

BEA = """<rss><channel><item name="GDP"><title>GDP, (Second Estimate), 3rd Quarter 2026</title>
<link>https://www.bea.gov/news/2026/gdp</link><pubDate>Wed, 25 Nov 2026 08:30:00 EST</pubDate></item>
<item name="U.S. International Transactions"><title>Trade</title><link>https://www.bea.gov/t</link>
<pubDate>Tue, 24 Nov 2026 08:30:00 EST</pubDate></item></channel></rss>"""
GOOGLE = """<rss><channel><item><title>US CPI rises 0.4% - Reuters</title><link>https://n/1</link><source url="x">Reuters</source>
<pubDate>Tue, 24 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Australia CPI jumps to 4.9% - FXStreet</title><link>https://n/2</link><source url="x">FXStreet</source>
<pubDate>Tue, 24 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>US CPI was hot in 2025 - Old</title><link>https://n/3</link><source url="x">Old</source>
<pubDate>Tue, 01 Jul 2026 10:00:00 GMT</pubDate></item></channel></rss>"""


class CardNews(unittest.TestCase):
    def test_bea_items_keep_their_release_name(self):
        items = cn.parse_rss(BEA, "bea")
        self.assertEqual([x["name"] for x in items], ["GDP", "U.S. International Transactions"])
        self.assertEqual(items[0]["published_at"], "2026-11-25")

    def test_official_picks_by_source_and_puts_static_links_first(self):
        feeds = {"bea": cn.parse_rss(BEA, "bea"), "fed": []}
        gdp = cn.official_for("gdp", feeds, [])
        self.assertEqual([x["title"][:3] for x in gdp], ["GDP"])
        cpi = cn.official_for("cpi_yoy", feeds, [])
        self.assertEqual(cpi[0]["url"], "https://www.bls.gov/news.release/cpi.nr0.htm")
        tre = [{"title": "Quarterly Refunding Statement", "url": "u", "date": "2026-11-04", "kind": "refunding"},
               {"title": "Buyback", "url": "b", "date": "2026-11-05", "kind": "buyback"}]
        self.assertEqual([x["url"] for x in cn.official_for("qra_issuance", feeds, tre)], ["u"])

    def test_press_filters_country_topic_and_age(self):
        google = lambda lang, q: cn.parse_rss(GOOGLE, "google") if lang == "en" else []
        out = cn.press_for("cpi_yoy", google, date(2026, 11, 26))
        self.assertEqual([x["title"] for x in out], ["US CPI rises 0.4%"])      # source suffix dropped
        self.assertEqual(out[0]["source"], "Reuters")

    def test_apply_only_reports_changes(self):
        usa = {"indicators": [{"id": "gdp"}]}
        self.assertEqual(cn.apply(usa, {"gdp": [1]}, {"gdp": []}), ["gdp.news_official", "gdp.news_press"])
        self.assertEqual(cn.apply(usa, {"gdp": [1]}, {"gdp": []}), [])


if __name__ == "__main__":
    unittest.main()
