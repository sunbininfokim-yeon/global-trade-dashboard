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


if __name__ == "__main__":
    unittest.main()
