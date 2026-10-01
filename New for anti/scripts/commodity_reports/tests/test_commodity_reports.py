from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commodity_reports.build import (  # noqa: E402
    GLOBAL_BUCKET,
    apply_series_commodity_fallback,
    build_commodity_reports,
)
from commodity_reports.feeds import (  # noqa: E402
    RawReport,
    add_pdf_summaries,
    fetch_fas_gain_pages,
    gain_links,
    parse_fas_gain_cards,
    parse_fas_gain_page,
    parse_feed,
    parse_html_list,
)
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

    def test_natural_rubber_has_its_own_window(self):
        self.assertIn("rubber", self.tagger.tag("Thailand natural rubber exports fell 6 percent in August"))
        self.assertIn("rubber", self.tagger.tag("ANRPC: global NR production forecast at 14.9 million tonnes; rubber demand"))
        self.assertIn("rubber", self.tagger.tag("Harga karet alam naik, ekspor meningkat"))

    def test_crude_steel_and_crude_palm_oil_are_not_crude_oil(self):
        # worldsteel's monthly release and MPOB's CPO notices landed on the
        # crude oil board on the first live build (2026-09-26).
        self.assertNotIn("oil", self.tagger.tag("August 2026 crude steel production"))
        hits = self.tagger.tag("Crude palm oil exports rose 5% in August")
        self.assertIn("palm_oil", hits)
        self.assertNotIn("oil", hits)
        self.assertIn("oil", self.tagger.tag("Crude oil stocks fell 3 million barrels"))

    def test_unambiguous_rubber_names_need_no_market_term(self):
        # VRA headlines name the crop ("cao su") without an English market word.
        self.assertIn("rubber", self.tagger.tag("VRA mời tham gia hội nghị doanh nhân cao su Việt Nam"))
        self.assertNotIn("rubber", self.tagger.tag("Kinh tế Việt Nam giữ đà tích cực trước biến động lãi suất"))

    def test_rss_the_feed_is_not_rss_the_rubber_grade(self):
        # Every feed calls itself RSS; only the numbered grade means rubber.
        self.assertNotIn("rubber", self.tagger.tag("Subscribe to our RSS feed for market prices"))
        self.assertIn("rubber", self.tagger.tag("RSS3 prices at the Bangkok market rose"))

    def test_rubber_stamp_is_not_rubber(self):
        self.assertNotIn("rubber", self.tagger.tag("Parliament gives rubber-stamp approval to the budget"))

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

    def test_british_thermal_units_is_not_the_uk(self):
        # Real miscount, live EIA data: a purely domestic US gas report
        # quoting a price in "million British thermal units (MMBtu)" landed
        # on GBR's window because "British" alone reads as the country.
        t = self.route(
            "EIA raises natural gas price forecast following increased heating demand",
            "Natural gas prices rose sharply, averaging $7.72 per million British "
            "thermal units (MMBtu), as cold weather increased heating demand.",
            default_country="USA",
        )
        self.assertNotIn("GBR", t.countries)
        self.assertEqual(t.countries, ["USA"])

    def test_british_still_means_the_uk_outside_that_one_phrase(self):
        t = self.route("British wheat exports climb on strong harvest")
        self.assertIn("GBR", t.countries)

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
        apply_series_commodity_fallback(tagged, self.scorer, title, summary)
        return self.scorer.score(raw, tagged, now=NOW)

    def test_series_wrapper_headline_with_no_crop_name_still_tags(self):
        # Real-world case: USDA's own WASDE announcement headline often names
        # no crop at all ("USDA Releases September World Agricultural Supply
        # and Demand Estimates") even though the report revises corn, wheat,
        # soybeans and more. Without the series fallback this is dropped
        # outright by the "no commodity, no window" gate, and the dashboard
        # is left showing whatever older report happened to name a crop.
        wasde = self.make(
            "USDA Releases September World Agricultural Supply and Demand Estimates",
            "The monthly report updates supply and demand forecasts.",
        )
        self.assertIsNotNone(wasde)
        self.assertEqual(wasde.series_id, "USDA_WASDE")
        self.assertIn("corn", wasde.commodities)
        self.assertIn("wheat", wasde.commodities)

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

    def test_rss_link_is_absolutized_against_the_feed_url(self):
        # Real bug, found in live EIA output: <link> came back as
        # "/pressroom/releases/press589.php" -- a relative path that resolved
        # against our own domain instead of eia.gov, 404ing the card's link.
        source = {"id": "us_eia_press", "agency": "EIA", "url": "https://www.eia.gov/rss/press_rss.xml"}
        body = """<?xml version="1.0"?><rss version="2.0"><channel>
            <item>
                <title>EIA press release</title>
                <link>/pressroom/releases/press589.php</link>
                <description>Body text.</description>
            </item>
        </channel></rss>"""
        items = parse_feed(body, source)
        self.assertEqual(items[0].url, "https://www.eia.gov/pressroom/releases/press589.php")

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

    def test_fas_gain_cards_extracts_date_title_link_and_summary(self):
        # fas.usda.gov/data/search (report_type:10251) replaced gain.fas.usda.gov
        # in 2026: a Drupal Views listing that server-renders each result as a
        # .c-card block, confirmed from a real page source pasted by the operator.
        source = {
            "id": "us_fas_gain_reports", "agency": "USDA FAS GAIN",
            "html": {"base": "https://www.fas.usda.gov"},
        }
        body = (FIXTURES / "us_fas_gain_reports.html").read_text(encoding="utf-8")
        items = parse_fas_gain_cards(body, source)
        # Four cards in the fixture, one a duplicate (tracking query string) of
        # another -- three distinct reports.
        self.assertEqual(len(items), 3)

        brazil = next(i for i in items if i.title.startswith("Brazil"))
        self.assertEqual(brazil.url, "https://www.fas.usda.gov/data/gain/2026/08/brazil-oilseeds-and-products-update")
        self.assertEqual(brazil.published_at, "2026-08-31T15:00:00+00:00")
        self.assertIn("soybean production", brazil.summary)

    def test_fas_gain_cards_dedupes_the_tracking_query_string(self):
        source = {"id": "us_fas_gain_reports", "html": {"base": "https://www.fas.usda.gov"}}
        body = (FIXTURES / "us_fas_gain_reports.html").read_text(encoding="utf-8")
        items = parse_fas_gain_cards(body, source)
        urls = [i.url for i in items]
        self.assertEqual(len(urls), len(set(u.split("?", 1)[0] for u in urls)))
        self.assertEqual(sum(1 for u in urls if "saudi-arabia" in u), 1)


class NonLatinCaseTests(unittest.TestCase):
    def test_capitalized_vietnamese_country_names_match(self):
        tagger = CountryTagger.from_config(cfg("countries.json"))
        self.assertEqual(tagger.tag("Xuất khẩu cao su của Thái Lan tăng"), ["THA"])
        self.assertIn("VNM", tagger.tag("Ngành cao su Việt Nam"))


class HtmlListTitleTests(unittest.TestCase):
    def test_slug_title_is_decoded_and_capitalized(self):
        source = {"id": "int_anrpc", "html": {"base": "https://www.anrpc.org",
                                               "item_href_re": "/newsla/[^\"'#?]+"}}
        body = '<a href="/newsla/anrpc-releases-monthly-nr-statistical-report%2C-june-2026"><img/></a>'
        items = parse_html_list(body, source)
        self.assertEqual(items[0].title, "Anrpc releases monthly nr statistical report, june 2026")


class LongAnchorTests(unittest.TestCase):
    def test_a_card_wrapped_in_its_link_is_still_found(self):
        source = {"id": "int_wgc_press", "html": {"base": "https://www.gold.org",
                  "item_href_re": "(?:https://www\\.gold\\.org)?/news-and-events/press-releases/[a-z0-9-]{10,}"}}
        teaser = "<div class='card'><img src='x.jpg'/><p>" + ("lorem ipsum " * 60) + "</p></div>"
        body = f'<a href="/news-and-events/press-releases/world-gold-council-launches-standard">{teaser}</a>'
        items = parse_html_list(body, source)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "World gold council launches standard")


class PdfSummaryTests(unittest.TestCase):
    def test_pdf_items_get_their_opening_text_and_known_ones_are_skipped(self):
        source = {"id": "int_ilzsg", "html": {"base": "https://www.ilzsg.org",
                                                "item_href_re": "[^\"']+\\.pdf"}}
        body = ('<a href="/wp-content/uploads/3.PRESS%20RELEASES/ILZSG%20Press%20Release%20August%202026.pdf">x</a>'
                '<a href="/wp-content/uploads/3.PRESS%20RELEASES/ILZSG%20Press%20Release%20July%202026.pdf">x</a>')
        items = parse_html_list(body, source)
        self.assertEqual(items[0].title, "ILZSG Press Release August 2026")
        fetched = []

        def fetch(url):
            fetched.append(url)
            return b"%PDF"

        n = add_pdf_summaries(items, fetch_pdf=fetch, extract=lambda b: "World  refined zinc\nsurplus of 45kt",
                              skip_urls={items[1].url})
        self.assertEqual(n, 1)
        self.assertEqual(items[0].summary, "World refined zinc surplus of 45kt")
        self.assertEqual(items[1].summary, "")
        self.assertEqual(len(fetched), 1)


class FasGainPagesTests(unittest.TestCase):
    """GAIN via FAS commodity/country pages, since /data/search is blocked."""

    def setUp(self):
        import json as _json

        self.store = _json.loads((FIXTURES / "us_fas_gain_reports.pages.json").read_text(encoding="utf-8"))
        self.source = {
            "id": "us_fas_gain_reports", "agency": "USDA FAS GAIN", "kind": "fas_gain_pages",
            "scope_hint": "global",
            "html": {
                "base": "https://www.fas.usda.gov",
                "list_urls": ["/data/commodities/coffee", "/regions/brazil", "/regions/nowhere"],
                "max_age_days": 150,
                "exclude_slug_re": "(exporter-guide|fairs-)",
                "slug_commodities": {"grain-and-feed": ["wheat", "corn", "rice"]},
            },
        }

    def fetch(self, url):
        if url not in self.store:
            raise FileNotFoundError(url)
        return self.store[url]

    def test_links_carry_year_and_month_and_drop_query_strings(self):
        links = gain_links(self.store["https://www.fas.usda.gov/data/commodities/coffee"])
        self.assertIn(("/data/gain/2026/08/vietnam-coffee-annual", 2026, 8), links)
        self.assertIn(("/data/gain/2026/08/brazil-oilseeds-and-products-update", 2026, 8), links)

    def test_reads_reports_skips_marketing_and_old_and_survives_a_dead_list_page(self):
        now = datetime(2026, 9, 26, tzinfo=timezone.utc)
        res = fetch_fas_gain_pages(self.source, fetch=self.fetch, max_items=40, now=now)
        self.assertTrue(res["ok"])
        urls = [i.url for i in res["items"]]
        # Same report linked from two list pages is read once.
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(len(urls), 3)
        self.assertFalse(any("exporter-guide" in u for u in urls))
        self.assertFalse(any("2025/01" in u for u in urls))

    def test_page_date_used_when_inside_the_url_month_else_month_precision(self):
        now = datetime(2026, 9, 26, tzinfo=timezone.utc)
        items = {i.title: i for i in fetch_fas_gain_pages(self.source, fetch=self.fetch, max_items=40, now=now)["items"]}
        brazil = items["Brazil: Oilseeds and Products Update"]
        self.assertEqual(brazil.published_at, "2026-08-31T15:00:00+00:00")
        self.assertEqual(brazil.date_precision, "day")
        self.assertIn("soybean production", brazil.summary)
        grain = items["Brazil: Grain and Feed Update"]
        self.assertEqual(grain.published_at, "2026-08-01T00:00:00+00:00")
        self.assertEqual(grain.date_precision, "month")
        # "Grain and Feed Update" names no crop; the slug prior supplies them.
        self.assertEqual(grain.commodity_hint, ["wheat", "corn", "rice"])

    def test_a_time_outside_the_url_month_is_not_trusted(self):
        body = '<meta property="og:title" content="X: Y" /><time datetime="2019-01-02T00:00:00Z">'
        item = parse_fas_gain_page(body, "https://x/data/gain/2026/08/x-y", 2026, 8, self.source)
        self.assertEqual(item.date_precision, "month")
        self.assertTrue(item.published_at.startswith("2026-08-01"))


class GainReuseAndBlockTests(FasGainPagesTests):
    def test_known_pages_are_not_fetched_again(self):
        now = datetime(2026, 9, 26, tzinfo=timezone.utc)
        first = fetch_fas_gain_pages(self.source, fetch=self.fetch, max_items=40, now=now)["items"]
        fetched = []

        def counting(url):
            fetched.append(url)
            return self.fetch(url)

        res = fetch_fas_gain_pages(self.source, fetch=counting, max_items=40, now=now, known=first)
        self.assertEqual(len(res["items"]), len(first))
        self.assertFalse(any("/data/gain/" in u for u in fetched))

    def test_a_blocked_site_stops_after_five_list_pages(self):
        calls = []

        def blocked(url):
            calls.append(url)
            raise OSError("403")

        source = dict(self.source, html=dict(self.source["html"], list_urls=[f"/regions/r{i}" for i in range(40)]))
        res = fetch_fas_gain_pages(source, fetch=blocked, max_items=40)
        self.assertFalse(res["ok"])
        self.assertEqual(len(calls), 5)


class CarryOverTests(unittest.TestCase):
    def test_failed_source_keeps_its_last_reports(self):
        from commodity_reports import build as build_mod

        sources = [{"id": "src_a", "agency": "A", "kind": "rss", "url": "https://a.example/feed"}]
        previous = {"items": [
            {"source_id": "src_a", "url": "https://a.example/1", "title": {"original": "Fresh"},
             "summary": "", "published_at": "2026-09-20T00:00:00+00:00"},
            {"source_id": "src_a", "url": "https://a.example/2", "title": {"original": "Stale"},
             "summary": "", "published_at": "2026-06-01T00:00:00+00:00"},
            {"source_id": "gone", "url": "https://b.example/1", "title": {"original": "Removed source"},
             "summary": "", "published_at": "2026-09-20T00:00:00+00:00"},
        ]}
        now = datetime(2026, 9, 26, tzinfo=timezone.utc)
        carried = build_mod.previous_raws(previous, sources, now)
        self.assertEqual([r.title for r in carried["src_a"]], ["Fresh"])
        self.assertNotIn("gone", carried)
        # A source with its own longer window (GAIN: 150 days) carries its
        # older reports too.
        long_src = [{"id": "src_a", "agency": "A", "kind": "fas_gain_pages", "url": "u", "html": {"max_age_days": 150}}]
        self.assertEqual(sorted(r.title for r in build_mod.previous_raws(previous, long_src, now)["src_a"]),
                         ["Fresh", "Stale"])

        orig = build_mod.fetch_source
        build_mod.fetch_source = lambda s, **kw: {"source_id": s["id"], "ok": False, "items": [],
                                                   "count": 0, "error": "HTTPError: 403"}
        try:
            raw, status = build_mod._collect_live(sources, ua="t", timeout=1, max_per=10, carried=carried)
        finally:
            build_mod.fetch_source = orig
        self.assertEqual([r.title for r in raw], ["Fresh"])
        self.assertEqual(status[0]["carried_over"], 1)
        self.assertFalse(status[0]["ok"])


class SourcePriorNeedsAMarketStoryTests(unittest.TestCase):
    def setUp(self):
        self.commodity = CommodityTagger.from_config(cfg("commodities.json"))
        self.country = CountryTagger.from_config(cfg("countries.json"))
        self.scorer = ReportScorer(cfg("series_catalog.json"))

    def tagged(self, title, summary=""):
        t = tag_report(title=title, summary=summary, commodity_tagger=self.commodity,
                       country_tagger=self.country, commodity_hint=["rubber"])
        apply_series_commodity_fallback(t, self.scorer, title, summary)
        return t.commodities

    def test_event_news_from_a_rubber_body_is_not_a_rubber_report(self):
        self.assertEqual(self.tagged(
            "Dr. suttipong angthong secretary general of the association of natural rubber producing "
            "countries anrpc took center stage as a distinguished speaker at the prestigious world "
            "elastomer technology and engineering forum wetef held in shanghai"), [])
        self.assertEqual(self.tagged("Anrpc strengthens global engagement at irgce 2026"), [])

    def test_market_news_and_named_reports_still_land(self):
        self.assertEqual(self.tagged("Anrpc releases monthly nr statistical report july 2026"), ["rubber"])
        self.assertEqual(self.tagged("Thailand to cut exports under new AETS quota"), ["rubber"])
        tin = tag_report(title="Tin to be traded on Indonesia's new commodity exchange", summary="",
                         commodity_tagger=self.commodity, country_tagger=self.country, commodity_hint=["tin"])
        self.assertEqual(tin.commodities, ["tin"])


class EventHeadlineTests(unittest.TestCase):
    def setUp(self):
        self.commodity = CommodityTagger.from_config(cfg("commodities.json"))
        self.country = CountryTagger.from_config(cfg("countries.json"))
        self.scorer = ReportScorer(cfg("series_catalog.json"))

    def score(self, title, summary=""):
        raw = RawReport(source_id="int_anrpc", agency="ANRPC", agency_ko="ANRPC", url="https://x/1",
                        title=title, summary=summary, published_at=None, commodity_hint=["rubber"])
        t = tag_report(title=title, summary=summary, commodity_tagger=self.commodity,
                       country_tagger=self.country, commodity_hint=["rubber"])
        apply_series_commodity_fallback(t, self.scorer, title, summary)
        return self.scorer.score(raw, t, now=NOW)

    def test_forum_and_meeting_headlines_are_dropped(self):
        self.assertIsNone(self.score("Sustainable natural rubber forum: aligning priorities for resilient supply chain"))
        self.assertIsNone(self.score("PEFC International and ANRPC convene to advance sustainability standards in the global natural rubber sector"))
        self.assertIsNone(self.score("VRA mời tham gia hội nghị và họp mặt doanh nhân cao su Việt Nam năm 2026"))
        # Slug-derived headline, diacritics gone.
        self.assertIsNone(self.score("Vra moi tham gia hoi nghi va hop mat doanh nhan cao su viet nam nam 2026"))

    def test_reports_and_figures_survive(self):
        self.assertIsNotNone(self.score("ANRPC releases Monthly NR Statistical Report July 2026"))
        self.assertIsNotNone(self.score("Natural rubber exports at the forum's host country fell 12%"))


class RelevanceByCommodityTests(unittest.TestCase):
    """EIA, crops, metals: only market stories, only the right window."""

    def setUp(self):
        self.commodity = CommodityTagger.from_config(cfg("commodities.json"))
        self.country = CountryTagger.from_config(cfg("countries.json"))
        self.scorer = ReportScorer(cfg("series_catalog.json"))

    def run_one(self, title, summary="", **raw_kw):
        raw = RawReport(source_id="s", agency="A", agency_ko="A", url="https://x/" + title[:20],
                        title=title, summary=summary, published_at=None, **raw_kw)
        t = tag_report(title=title, summary=summary, commodity_tagger=self.commodity,
                       country_tagger=self.country, commodity_hint=raw.commodity_hint,
                       commodity_text=raw.commodity_from)
        apply_series_commodity_fallback(t, self.scorer, title, summary)
        item = self.scorer.score(raw, t, now=NOW)
        return item.commodities if item else None

    def test_eia_electricity_is_not_crude_and_oil_market_news_is(self):
        self.assertIsNone(self.run_one("EIA forecasts strongest four-year growth in U.S. electricity demand since 2000"))
        self.assertIn("oil", self.run_one("EIA increases global oil production forecast after the opening of the Strait of Hormuz"))
        self.assertEqual(sorted(self.run_one("EIA releases latest Short-Term Energy Outlook amid Middle East conflict")),
                         ["gas", "oil", "thermal_coal"])
        self.assertNotIn("oil", self.commodity.tag("Malaysia palm oil production rose 4% in August"))
        self.assertNotIn("oil", self.commodity.tag("Brazil: Biofuels Annual -- ethanol blending and renewable diesel capacity"))

    def test_multi_commodity_series_reach_every_window_they_cover(self):
        # EIA's STEO revises oil, gas and coal even when the headline names oil only.
        got = self.run_one("Short-Term Energy Outlook: EIA expects lower crude oil prices")
        self.assertEqual(sorted(got), ["gas", "oil", "thermal_coal"])
        # An oil story that cites the STEO in its body is still an oil story.
        self.assertEqual(self.run_one("United States on track for record crude oil production in 2026",
                                      "In our latest Short-Term Energy Outlook we forecast 13.9 million b/d."),
                         ["oil"])
        # A single-commodity EIA story stays on its own window.
        self.assertEqual(self.run_one("EIA expects highest natural gas inventories in a decade heading into winter"), ["gas"])

    def test_housekeeping_notices_are_dropped(self):
        for title in ("USDA Crop Progress report delayed until 5pm ET",
                      "NASS suspends pecan estimates for December and January",
                      "USDA NASS to Re-Survey Operators with Previously Unharvested Corn and Soybeans",
                      "Aviso de pauta 2013 3o levantamento da safra de cafe 2026",
                      "MPOB(T/P)39/26 – Kerja-Kerja Penyelenggaraan Am Ladang Sawit",
                      "International Aluminium Institute Appoints Jonathan Grant as New Secretary General",
                      "IAI has new a Secretary General",
                      "NASS Reinstates Select Data Collection Programs and Reports"):
            self.assertIsNone(self.run_one(title, market_only=True), title)
        self.assertEqual(self.run_one("Produção de café é estimada em 67,6 milhões de sacas", market_only=True), ["coffee"])

    def test_a_publisher_name_in_the_body_is_not_its_supply_series(self):
        # MPOB_SUPPLY_DEMAND used to match on "mpob", so every MPOB post was
        # a series item and skipped the event filter.
        self.assertIsNone(self.run_one("Persidangan Kebangsaan Pekebun Kecil Sawit (PKPKS) 2026",
                                       "Anjuran MPOB di Kuala Lumpur.", market_only=True))

    def test_market_only_board_keeps_market_news_only(self):
        self.assertIsNone(self.run_one("Aluminium cans lead global beverage recycling", market_only=True))
        self.assertEqual(self.run_one("Gulf aluminium output collapses by 40% as global supply crisis deepens",
                                      market_only=True), ["aluminum"])

    def test_title_only_feed_ignores_crops_mentioned_in_passing(self):
        self.assertIsNone(self.run_one("Rewiring the Egg Supply Chain in Austria",
                                       "Feed made from imported soybean meal is a large share of costs.",
                                       market_only=True, commodity_from="title"))


class FirstSeenTests(unittest.TestCase):
    def test_first_seen_is_set_then_kept_across_builds(self):
        import json as _json
        import tempfile

        doc = build_commodity_reports(fetch_live=False, fixture_dir=FIXTURES, per_bucket=8, now=NOW)
        self.assertTrue(all(i["first_seen_at"] == NOW.isoformat() for i in doc["items"]))
        # A later live build reads the previous file; with nothing fetched the
        # items it republishes (none here) would keep their first_seen_at.
        # Exercise the carry directly through a fixture rebuild that names
        # the previous file.
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            _json.dump(doc, fh)
        from commodity_reports import build as build_mod

        later = datetime(2026, 8, 20, tzinfo=timezone.utc)
        orig = build_mod._collect_live
        raw_fixture, _ = build_mod._collect_fixtures(
            [s for s in build_mod.load_json(build_mod.CONFIG / "sources.json")["sources"] if s.get("enabled", True)],
            FIXTURES, 40, NOW)
        build_mod._collect_live = lambda *a, **k: (raw_fixture, [])
        try:
            doc2 = build_commodity_reports(fetch_live=True, per_bucket=8, now=later, previous_path=fh.name)
        finally:
            build_mod._collect_live = orig
        firsts = {i["id"]: i["first_seen_at"] for i in doc2["items"]}
        shared = set(firsts) & {i["id"] for i in doc["items"]}
        self.assertTrue(shared)
        self.assertTrue(all(firsts[i] == NOW.isoformat() for i in shared))


class ArchiveTests(unittest.TestCase):
    """The board keeps what scrolled off a feed, up to ARCHIVE_DAYS."""

    def test_scrolled_off_reports_stay_and_old_ones_go(self):
        from commodity_reports import build as build_mod

        now = datetime(2026, 9, 26, tzinfo=timezone.utc)
        sources = [{"id": "src_a", "agency": "A", "kind": "rss", "url": "https://a.example/feed"}]
        previous = {"items": [
            {"source_id": "src_a", "url": "https://a.example/old-but-recent", "title": {"original": "Recent"},
             "summary": "", "published_at": "2026-09-01T00:00:00+00:00"},
            {"source_id": "src_a", "url": "https://a.example/too-old", "title": {"original": "Too old"},
             "summary": "", "published_at": "2026-05-01T00:00:00+00:00"},
            {"source_id": "src_a", "url": "https://a.example/undated", "title": {"original": "Undated"},
             "summary": "", "published_at": None, "first_seen_at": "2026-06-01T00:00:00+00:00"},
        ]}
        carried = build_mod.previous_raws(previous, sources, now)
        self.assertEqual([r.title for r in carried["src_a"]], ["Recent"])

        fresh = RawReport(source_id="src_a", agency="A", agency_ko="A", url="https://a.example/new",
                          title="New", summary="", published_at="2026-09-25T00:00:00+00:00")
        orig = build_mod.fetch_source
        build_mod.fetch_source = lambda s, **kw: {"source_id": s["id"], "ok": True, "items": [fresh],
                                                   "count": 1, "error": None}
        try:
            raw, status = build_mod._collect_live(sources, ua="t", timeout=1, max_per=10, carried=carried)
        finally:
            build_mod.fetch_source = orig
        self.assertEqual(sorted(r.title for r in raw), ["New", "Recent"])
        self.assertEqual(status[0]["archived"], 1)

    def test_news_time_uses_month_end_and_first_seen(self):
        from commodity_reports.build import news_time

        now = datetime(2026, 9, 26, tzinfo=timezone.utc)
        self.assertEqual(news_time("2026-07-01T00:00:00+00:00", "month", None, now).date().isoformat(), "2026-07-31")
        self.assertEqual(news_time(None, None, "2026-09-20T00:00:00+00:00", now).date().isoformat(), "2026-09-20")
        self.assertEqual(news_time(None, None, None, now), now)


class CommodityScopeTests(unittest.TestCase):
    """commodity_scope: a narrow source is never filed under anything else."""

    def test_grain_exchange_macro_column_is_not_an_oil_report(self):
        from commodity_reports import build as build_mod

        def raw(url, title):
            return RawReport(source_id="ar_bcr", agency="BCR", agency_ko="BCR", url=url, title=title,
                             summary="", published_at="2026-09-25T00:00:00+00:00", lang="es",
                             default_country="ARG", commodity_scope=["soybeans", "corn", "wheat"])

        items = [
            raw("https://bcr.example/macro", "Reservas internacionales y petróleo marcan la agenda económica y financiera"),
            raw("https://bcr.example/maiz", "Maíz en racha: más de un millón de toneladas de maíz exportadas por semana"),
        ]

        def fake_fetch(s, **kw):
            ok = s["id"] == "ar_bcr"
            return {"source_id": s["id"], "ok": ok, "items": items if ok else [],
                    "count": len(items) if ok else 0, "error": None if ok else "skipped"}

        orig = build_mod.fetch_source, build_mod.fetch_fas_gain_pages
        build_mod.fetch_source = fake_fetch
        build_mod.fetch_fas_gain_pages = lambda s, **kw: fake_fetch(s)
        try:
            doc = build_commodity_reports(fetch_live=True, now=datetime(2026, 9, 26, tzinfo=timezone.utc))
        finally:
            build_mod.fetch_source, build_mod.fetch_fas_gain_pages = orig
        bcr = {it["url"]: it["commodities"] for it in doc["items"] if it["source_id"] == "ar_bcr"}
        self.assertNotIn("https://bcr.example/macro", bcr)
        self.assertEqual(bcr.get("https://bcr.example/maiz"), ["corn"])


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
