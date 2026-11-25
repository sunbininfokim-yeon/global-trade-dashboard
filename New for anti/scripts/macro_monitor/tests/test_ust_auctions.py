"""ust_auctions: TreasuryDirect rows, buyback rows, per-tenor comparison and the pack upsert."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import ust_auctions as ua  # noqa: E402


def td(date, term="10-Year", hy="4.500", btc="2.50", pd=1e9, dr=2e9, ind=7e9, **kw):
    return {"competitiveAuctionCloseDate": f"{date}T00:00:00", "originalSecurityTerm": term, "securityTerm": term,
            "highYield": hy, "bidToCoverRatio": btc, "primaryDealersCompetitiveParAwarded": str(pd),
            "directBiddersCompetitiveParAwarded": str(dr), "indirectBiddersCompetitiveParAwarded": str(ind),
            "offeringAmount": "10000000000", "inflationProtected": "No", "floatingRate": "No", "reopening": "No",
            "cusip": f"C{date}", **kw}


class Parse(unittest.TestCase):
    def test_shares_are_of_the_competitive_award(self):
        r = ua.parse_auction(td("2026-10-07"))
        self.assertEqual((r["pd_pct"], r["direct_pct"], r["indirect_pct"]), (10.0, 20.0, 70.0))
        self.assertEqual((r["tenor"], r["offering_bn"], r["high_yield"]), ("10y", 10.0, 4.5))

    def test_tips_frn_and_pending_results_are_skipped(self):
        self.assertIsNone(ua.parse_auction(td("2026-10-07", inflationProtected="Yes")))
        self.assertIsNone(ua.parse_auction(td("2026-10-07", floatingRate="Yes")))
        self.assertIsNone(ua.parse_auction(td("2026-10-07", hy="")))
        self.assertIsNone(ua.parse_auction(td("2026-10-07", term="13-Week")))

    def test_buyback_row(self):
        r = ua.parse_buyback({"operation_date": "2026-10-27", "operation_type": "Liquidity Support",
                              "security_type": "Nominal Coupons", "maturity_bucket": "20Y to 30Y",
                              "total_par_amt_offered": "10746000000.00", "max_par_amt_redeemed": "6000000000",
                              "total_par_amt_accepted": "6000000000.00", "nbr_issues_accepted": "6",
                              "nbr_issues_eligible": "35"})
        self.assertEqual((r["accepted_bn"], r["offered_to_max"], r["bucket_ko"], r["type_ko"]),
                         (6.0, 1.79, "20~30년", "유동성 지원"))
        self.assertEqual(ua.bucket_ko("1Mo to 2Y"), "1개월~2년")


class Summaries(unittest.TestCase):
    def setUp(self):
        self.rows = [ua.parse_auction(td("2026-09-09", hy="4.300", btc="2.40", pd=2e9, dr=2e9, ind=6e9)),
                     ua.parse_auction(td("2026-09-10", term="30-Year", hy="4.900")),
                     ua.parse_auction(td("2026-10-07"))]

    def test_tenor_compared_with_its_own_previous_auction(self):
        latest = {r["tenor"]: r for r in ua.latest_by_tenor(self.rows)}
        self.assertEqual(latest["10y"]["d_yield_bp"], 20.0)
        self.assertEqual(latest["10y"]["d_pd_pp"], -10.0)
        self.assertNotIn("d_yield_bp", latest["30y"])

    def test_monthly_dealer_share_is_offering_weighted(self):
        self.assertEqual(ua.monthly_dealer_share(self.rows), [("2026-09-01", 15.0), ("2026-10-01", 10.0)])

    def test_upsert_adds_card_and_chip_once_and_keeps_a_hidden_chip_hidden(self):
        country = {"indicators": [], "categories": {"liquidity": []}}
        card = ua.auction_card(self.rows, "2026-11-01T00:00:00Z")
        self.assertTrue(ua.upsert(country, card))
        self.assertFalse(ua.upsert(country, card))
        self.assertEqual(len(country["indicators"]), 1)
        country["categories"]["liquidity"][0]["hidden"] = True
        self.assertFalse(ua.upsert(country, card))
        self.assertTrue(country["categories"]["liquidity"][0]["hidden"])
        self.assertEqual(card["display"], "딜러 10.0%")


class BuybackRail(unittest.TestCase):
    PAGE = ('<p><a href=/news/press-releases/sb0678>Policy Statement: 2026 - 4th Quarter</a></p>'
            '<p><a href=/system/files/221/Tentative-Buyback-ScheduleQ42026.xml>Buyback Schedule: XML Format</a><br>'
            '<a href=/system/files/221/Tentative-Buyback-ScheduleQ42026.pdf>Buyback Schedule: PDF Format</a></p>')
    XML = """<BuyBackCalendar><BuybackCalendarName>November 2026 Refunding Tentative Buyback Calendar V1</BuybackCalendarName>
      <StartDate>2026-11-12</StartDate><EndDate>2027-02-09</EndDate>
      <BuybackCalendarDate><PurchaseBucketName>Nominal Coupons 20Y to 30Y</PurchaseBucketName><SecurityType>NOMINAL COUPONS</SecurityType>
        <OperationType>Liquidity Support</OperationType><MaximumPurchaseAmountDollars>6000000000</MaximumPurchaseAmountDollars>
        <AnnouncementDate>2026-11-16</AnnouncementDate><OperationDate>2026-11-17</OperationDate></BuybackCalendarDate>
      <BuybackCalendarDate><PurchaseBucketName>Nominal Coupons 10Y to 20Y</PurchaseBucketName><SecurityType>NOMINAL COUPONS</SecurityType>
        <OperationType>Liquidity Support</OperationType><MaximumPurchaseAmountDollars>6000000000</MaximumPurchaseAmountDollars>
        <AnnouncementDate>2026-12-01</AnnouncementDate><OperationDate>2026-12-02</OperationDate></BuybackCalendarDate>
    </BuyBackCalendar>"""
    STATEMENT = ("<p>BUYBACKS</p><p>Treasury anticipates that, over the course of the upcoming quarter, it will purchase up to "
                 "$70 billion in off-the-run securities across buckets for liquidity support and up to $25 billion in the "
                 "1-month to 2-year maturity bucket for cash management purposes.</p>")
    RSS = """<rss><channel>
      <item><title>Treasury Buyback Nets Least Long-Dated Debt Since Expansion - TradingView</title><link>https://n/1</link>
        <pubDate>Tue, 17 Nov 2026 20:00:00 GMT</pubDate><source url="x">TradingView</source></item>
      <item><title>CoinShares Sells Entire ETH Treasury to Fund $40M Share Buyback - Coinpedia</title><link>https://n/2</link>
        <pubDate>Wed, 18 Nov 2026 10:00:00 GMT</pubDate><source url="x">Coinpedia</source></item>
      <item><title>Market stress prompts Treasury to intervene with R$14bn bond buyback - Valor</title><link>https://n/3</link>
        <pubDate>Tue, 27 Oct 2026 10:00:00 GMT</pubDate><source url="x">Valor</source></item>
    </channel></rss>"""

    def test_refunding_links_and_calendar(self):
        docs = ua.find_refunding_docs(self.PAGE)
        self.assertTrue(docs["schedule_xml"].endswith("Tentative-Buyback-ScheduleQ42026.xml"))
        self.assertEqual(docs["policy_statement"], "https://home.treasury.gov/news/press-releases/sb0678")
        cal = ua.parse_schedule_xml(self.XML)
        self.assertEqual((cal["start"], cal["end"], len(cal["operations"])), ("2026-11-12", "2027-02-09", 2))
        self.assertEqual(cal["operations"][0]["bucket_ko"], "20~30년")
        self.assertEqual(cal["operations"][0]["max_bn"], 6.0)

    def test_ceilings_and_progress(self):
        c = ua.parse_policy_ceilings(self.STATEMENT)
        self.assertEqual((c["liquidity_bn"], c["cash_bn"]), (70.0, 25.0))
        rows = [{"date": "2026-11-05", "type": "Cash Management", "accepted_bn": 4.0},
                {"date": "2026-11-17", "type": "Liquidity Support", "accepted_bn": 1.183}]
        q = ua.quarter_progress(rows, "2026-11-12", "2027-02-09", c)
        self.assertEqual([(i["used_bn"], i["ceiling_bn"]) for i in q["items"]], [(1.183, 70.0), (0, 25.0)])

    def test_news_keeps_treasury_buybacks_only(self):
        got = ua.parse_news_rss(self.RSS, "en")
        self.assertEqual([g["title"] for g in got], ["Treasury Buyback Nets Least Long-Dated Debt Since Expansion"])
        self.assertEqual((got[0]["source"], got[0]["published_at"]), ("TradingView", "2026-11-17"))

    def test_news_dedupes_wire_copies(self):
        a = {"title": "美 20~30년물 국채 60억달러 바이백…장기물 2회 연속 한도 채워(상보)", "published_at": "2026-10-09"}
        b = {"title": "美 20~30년물 국채 60억달러 바이백…장기물 2회 연속 한도 채워", "published_at": "2026-10-09"}
        self.assertEqual(len(ua.merge_news([[a], [b]])), 1)

    def test_upcoming_skips_done_operations(self):
        cal = ua.parse_schedule_xml(self.XML)
        rows = [{"date": "2026-11-17", "type": "Liquidity Support", "bucket": "20Y to 30Y", "accepted_bn": 1.183,
                 "security_type": "Nominal Coupons", "offered_to_max": 0.76, "max_bn": 6.0, "offered_bn": 4.548}]
        ex = ua.buyback_extras(rows, cal, None, {}, [], [], "2026-11-17")
        self.assertEqual([o["date"] for o in ex["calendar"]["upcoming"]], ["2026-12-02"])
        self.assertEqual(ex["long_end"]["20Y to 30Y"]["points"][0]["offered_to_max"], 0.76)


if __name__ == "__main__":
    unittest.main()
