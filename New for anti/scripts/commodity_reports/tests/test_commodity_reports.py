from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commodity_reports.build import GLOBAL_BUCKET, build_commodity_reports  # noqa: E402
from commodity_reports.feeds import RawReport, parse_feed, parse_html_list  # noqa: E402
from commodity_reports.score import ReportScorer, append_label, load_learned_multipliers  # noqa: E402
from commodity_reports.tag import CommodityTagger, CountryTagger, tag_report  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def cfg(name: str):
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


class CommodityTagTests(unittest.TestCase):
    def setUp(self):
        self.tagger = CommodityTagger.from_config(cfg("commodities.json"))

    def test_english_and_portuguese_aliases(self):
        self.assertIn("soybeans", self.tagger.tag("U.S. soybean production forecast raised"))
        self.assertIn("soybeans", self.tagger.tag("producao de soja estimada em 172 milhoes"))

    def test_bare_oil_is_not_crude(self):
        # Palm oil has its own window; it must not land on the crude board.
        hits = self.tagger.tag("Malaysia palm oil exports rise in July")
        self.assertIn("palm_oil", hits)
        self.assertNotIn("oil", hits)

    def test_lead_the_verb_is_not_lead_the_metal(self):
        self.assertNotIn("lead", self.tagger.tag("Ministers lead the grain corridor talks"))
        self.assertIn("lead", self.tagger.tag("Refined lead output at the smelter fell 4 percent"))

    def test_ambiguous_nouns_need_market_context(self):
        self.assertNotIn("gold", self.tagger.tag("The team took gold at the championship"))
        self.assertIn("gold", self.tagger.tag("Gold mine output rose to 118 tonnes"))

    def test_coking_coal_is_its_own_window(self):
        hits = self.tagger.tag("Coking coal exports from Queensland fell 3 percent")
        self.assertIn("met_coal", hits)


class CountryTagTests(unittest.TestCase):
    def setUp(self):
        self.tagger = CountryTagger.from_config(cfg("countries.json"))

    def test_longest_alias_wins(self):
        self.assertEqual(self.tagger.tag("North Korea grain imports"), ["PRK"])
        self.assertEqual(self.tagger.tag("Papua New Guinea LNG"), ["PNG"])

    def test_lowercase_us_is_a_pronoun(self):
        self.assertEqual(self.tagger.tag("The ministry told us the harvest is late"), [])
        self.assertIn("USA", self.tagger.tag("US wheat exports climbed"))

    def test_producing_region_implies_country(self):
        self.assertIn("BRA", self.tagger.tag("Dryness across Mato Grosso delayed planting"))
        self.assertIn("USA", self.tagger.tag("Corn Belt rainfall was below normal"))


class RoutingTests(unittest.TestCase):
    """The rule that defines this feature: the text picks the window."""

    def setUp(self):
        self.commodity = CommodityTagger.from_config(cfg("commodities.json"))
        self.country = CountryTagger.from_config(cfg("countries.json"))

    def route(self, title, summary="", **kw):
        return tag_report(
            title=title,
            summary=summary,
            commodity_tagger=self.commodity,
            country_tagger=self.country,
            **kw,
        )

    def test_usda_report_about_brazil_goes_to_brazil(self):
        t = self.route(
            "Brazil wheat production lowered on dry Parana weather",
            "USDA lowered Brazil wheat production to 8.9 million tonnes.",
            default_country="USA",
        )
        self.assertEqual(t.commodities, ["wheat"])
        self.assertEqual(t.countries, ["BRA"])
        self.assertEqual(t.country_source, "text")

    def test_publisher_country_is_only_a_fallback(self):
        t = self.route(
            "Acompanhamento da safra: producao de soja sobe 3,4 por cento",
            default_country="BRA",
        )
        self.assertEqual(t.countries, ["BRA"])
        self.assertEqual(t.country_source, "source_default")

    def test_headline_country_outranks_body_country(self):
        t = self.route(
            "US soybean exports climb",
            "Argentina's drought pushed buyers to Gulf Coast supplies.",
        )
        self.assertEqual(t.countries[0], "USA")
        self.assertIn("ARG", t.countries)

    def test_world_balance_sheet_has_no_country(self):
        t = self.route("World wheat production forecast at a record 812 million tonnes")
        self.assertEqual(t.scope, "global")
        self.assertEqual(t.countries, [])


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.scorer = ReportScorer(cfg("series_catalog.json"))
        self.commodity = CommodityTagger.from_config(cfg("commodities.json"))
        self.country = CountryTagger.from_config(cfg("countries.json"))

    def make(self, title, summary="", published_at="2026-08-13T12:00:00+00:00"):
        raw = RawReport(
            source_id="us_usda_newsroom", agency="USDA", agency_ko="미 농무부",
            url=f"https://example.test/{abs(hash(title))}", title=title, summary=summary,
            published_at=published_at,
        )
        tagged = tag_report(
            title=title, summary=summary,
            commodity_tagger=self.commodity, country_tagger=self.country,
            default_country="USA",
        )
        return self.scorer.score(raw, tagged, now=NOW)

    def test_named_series_outranks_a_bare_mention(self):
        wasde = self.make("WASDE raises US soybean production to 4.52 billion bushels")
        chat = self.make("US soybean growers visit the state fair")
        self.assertIsNotNone(wasde)
        self.assertIsNotNone(chat)
        self.assertEqual(wasde.series_id, "USDA_WASDE")
        self.assertGreater(wasde.importance, chat.importance)

    def test_recency_decays(self):
        fresh = self.make("WASDE raises US corn yield", published_at="2026-08-13T12:00:00+00:00")
        stale = self.make("WASDE raises US corn yield estimate", published_at="2026-02-13T12:00:00+00:00")
        self.assertGreater(fresh.importance, stale.importance)

    def test_off_topic_release_is_dropped(self):
        self.assertIsNone(self.make("National School Lunch Week photo gallery"))
        self.assertIsNone(self.make("Secretary announces staff appointments"))

    def test_label_history_reweights_a_series(self):
        path = ROOT / "cache" / "_test_labels.jsonl"
        path.unlink(missing_ok=True)
        append_label(path, series_id="USDA_WASDE", url="u", title="t", label="promote")
        self.assertGreater(load_learned_multipliers(path)["USDA_WASDE"], 1.0)
        path.unlink()


class FeedParseTests(unittest.TestCase):
    def test_atom_and_rss_both_parse(self):
        source = {"id": "int_fao_newsroom", "agency": "FAO"}
        items = parse_feed((FIXTURES / "int_fao_newsroom.xml").read_text(encoding="utf-8"), source)
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].url.startswith("https://www.fao.org/"))
        self.assertTrue(items[0].published_at.startswith("2026-08-07"))

    def test_html_list_dedupes_and_absolutizes(self):
        source = {
            "id": "int_opec_press", "agency": "OPEC",
            "html": {"base": "https://www.opec.org", "item_href_re": "[^\"']*press_room[^\"']*"},
        }
        items = parse_html_list((FIXTURES / "int_opec_press.html").read_text(encoding="utf-8"), source)
        urls = [i.url for i in items]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertTrue(all(u.startswith("https://www.opec.org/") for u in urls))
        self.assertNotIn("about_us", " ".join(urls))


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.doc = build_commodity_reports(
            fetch_live=False, fixture_dir=FIXTURES, per_bucket=8, now=NOW
        )

    def test_schema_and_stats(self):
        self.assertEqual(self.doc["schema_version"], "commodity-reports-v1")
        self.assertGreaterEqual(self.doc["stats"]["published"], 4)
        # Feeds with no fixture must be reported, not silently counted as empty.
        self.assertTrue(any(s.get("error") == "fixture_missing" for s in self.doc["feed_status"]))

    def test_nass_ag_prices_routes_to_every_commodity_it_names(self):
        # Real-world case: NASS's "Agricultural Prices" is one report covering many
        # crops at once. It has to land on each commodity's USA window, not just one,
        # and be recognized as the named series rather than an unranked mention.
        index = self.doc["index"]
        by_id = {i["id"]: i for i in self.doc["items"]}
        for commodity in ("corn", "wheat", "soybeans"):
            ids = index[commodity]["USA"]
            matches = [rid for rid in ids if by_id[rid]["series_id"] == "USDA_AG_PRICES"]
            self.assertTrue(matches, f"Agricultural Prices missing from {commodity}·USA")

    def test_report_with_no_tracked_commodity_is_dropped(self):
        # "Egg Products" names no commodity this dashboard tracks (no egg window
        # exists). Dropped -- no review queue to land in, by design for now.
        titles = [it["title"]["original"] for it in self.doc["items"]]
        self.assertNotIn("Egg Products", titles)
        self.assertNotIn("pending_review", self.doc)

    def test_windows_are_addressable_by_commodity_and_iso3(self):
        # br_conab and int_fao_newsroom are disabled (config/sources.json,
        # 2026-09-02: confirmed dead on the first live Actions run) so their
        # fixtures are intentionally excluded here -- this asserts cross-cutting
        # indexing via sources that are actually enabled.
        index = self.doc["index"]
        self.assertIn("USA", index["soybeans"])
        self.assertIn("BRA", index["wheat"])
        self.assertIn(GLOBAL_BUCKET, index["oil"])

    def test_bucket_order_is_newest_first_even_over_a_less_important_report(self):
        # soybeans/USA holds two real fixture reports: the Aug-12 WASDE release
        # (importance 5.24, the higher of the two) and the Aug-31 Agricultural
        # Prices release (5.11). Display order must be by date -- the operator
        # was reading a live board where the day's actual top release sat below
        # an older, slightly higher-scored administrative one, and asked for
        # newest-first instead. Importance still decides which reports make the
        # per_bucket cut; only the order they're shown in changed.
        by_id = {i["id"]: i for i in self.doc["items"]}
        ids = self.doc["index"]["soybeans"]["USA"]
        dates = [by_id[rid]["published_at"] for rid in ids]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertTrue(dates[0].startswith("2026-08-31"))

    def test_every_indexed_id_resolves_to_an_item(self):
        ids = {i["id"] for i in self.doc["items"]}
        for buckets in self.doc["index"].values():
            for rows in buckets.values():
                self.assertTrue(set(rows) <= ids)

    def test_items_carry_what_the_card_renders(self):
        item = next(i for i in self.doc["items"] if "WASDE" in (i["summary"] or ""))
        self.assertTrue(item["url"].startswith("https://"))
        self.assertTrue(item["summary"])
        self.assertEqual(item["agency_ko"], "미 농무부")
        self.assertEqual(item["series_id"], "USDA_WASDE")

    def test_no_orphan_items(self):
        referenced = {r for b in self.doc["index"].values() for rows in b.values() for r in rows}
        self.assertEqual({i["id"] for i in self.doc["items"]}, referenced)


if __name__ == "__main__":
    unittest.main()
