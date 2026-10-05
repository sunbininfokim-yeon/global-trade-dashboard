"""ECB Governing Council document parsing (macro_monitor.cb_collect.ecb) and the EMU block.

The text fixtures are the ECB's own sentences, copied from the published press releases and accounts.
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor.cb_collect import ecb  # noqa: E402
from macro_monitor.cb_collect.assemble import assemble_ecb  # noqa: E402

CONFIG = Path(__file__).resolve().parent.parent / "config" / "ecb_gc_v1.json"


class Rates(unittest.TestCase):
    def test_current_wording_lists_facilities_then_rates(self):
        r = ecb.parse_rates(["The Governing Council decided to raise the three key ECB interest rates by 25 basis points. Accordingly, the "
                             "interest rates on the deposit facility, the main refinancing operations and the marginal lending facility will be "
                             "increased to 2.50%, 2.65% and 2.90% respectively, with effect from 16 September 2026."])
        self.assertEqual((r["action"], r["change_bp"], r["dfr_pct"], r["mro_pct"], r["mlf_pct"]), ("raise", 25, 2.5, 2.65, 2.9))
        self.assertEqual((r["prior_dfr_pct"], r["effective_date"]), (2.25, "2026-09-16"))

    def test_mid_2024_wording_orders_the_facilities_differently(self):
        r = ecb.parse_rates(["The Governing Council decided to lower the three key ECB interest rates by 25 basis points. Accordingly, the "
                             "interest rate on the main refinancing operations and the interest rates on the marginal lending facility and the "
                             "deposit facility will be decreased to 4.25%, 4.50% and 3.75% respectively, with effect from 12 June 2024."])
        self.assertEqual((r["dfr_pct"], r["mro_pct"], r["mlf_pct"], r["prior_dfr_pct"]), (3.75, 4.25, 4.5, 4.0))

    def test_september_2024_split_the_deposit_rate_from_the_other_two(self):
        r = ecb.parse_rates(["The Governing Council decided to lower the deposit facility rate by 25 basis points. The deposit facility rate is the "
                             "rate through which the Governing Council steers the monetary policy stance. In addition, the spread between the "
                             "interest rate on the main refinancing operations and the deposit facility rate will be set at 15 basis points. "
                             "The spread between the rate on the marginal lending facility and the rate on the main refinancing operations will "
                             "remain unchanged at 25 basis points. Accordingly, the deposit facility rate will be decreased to 3.50%. The interest "
                             "rates on the main refinancing operations and the marginal lending facility will be decreased to 3.65% and 3.90% "
                             "respectively. The changes will take effect from 18 September 2024."])
        self.assertEqual((r["dfr_pct"], r["mro_pct"], r["mlf_pct"], r["effective_date"]), (3.5, 3.65, 3.9, "2024-09-18"))

    def test_hold_reads_the_verb_from_the_lead_paragraph(self):
        rates_only = ["The interest rates on the deposit facility, the main refinancing operations and the marginal lending facility will "
                      "remain unchanged at 2.00%, 2.15% and 2.40% respectively."]
        with self.assertRaises(ValueError):
            ecb.parse_rates(rates_only)                                      # the section alone does not say raise/lower/keep
        r = ecb.parse_rates(rates_only, whole_text="The Governing Council today decided to keep the three key ECB interest rates unchanged. " + rates_only[0])
        self.assertEqual((r["action"], r["change_bp"], r["dfr_pct"], r["prior_dfr_pct"]), ("maintain", 0, 2.0, 2.0))

    def test_rates_that_cannot_be_matched_to_facilities_raise(self):
        with self.assertRaises(ValueError):
            ecb.parse_rates(["The Governing Council decided to keep the three key ECB interest rates unchanged at 2.00%, 2.15% and 2.40%."])


class Projections(unittest.TestCase):
    def test_three_variables_from_the_september_2026_release(self):
        p = ecb.parse_projections([
            "The baseline of the new ECB staff projections sees headline inflation averaging 3.0% in 2026, 2.5% in 2027 and 2.1% in 2028. "
            "For inflation excluding energy and food, the baseline foresees 2.5% in 2026, 2.6% in 2027 and 2.3% in 2028. Compared with June, "
            "the baseline projection for inflation in 2026 is unchanged, while it has been revised up for 2027 and 2028. The baseline "
            "projection for economic growth is 0.9% for 2026, 1.4% for 2027 and 1.5% for 2028."])
        self.assertEqual(p, {"hicp": {2026: 3.0, 2027: 2.5, 2028: 2.1}, "core": {2026: 2.5, 2027: 2.6, 2028: 2.3}, "gdp": {2026: 0.9, 2027: 1.4, 2028: 1.5}})

    def test_one_value_shared_by_two_years(self):
        p = ecb.parse_projections(["Staff expect inflation excluding energy and food to average 2.4% in 2025 and 1.9% in 2026 and 2027, "
                                   "broadly unchanged since March."])
        self.assertEqual(p, {"core": {2025: 2.4, 2026: 1.9, 2027: 1.9}})

    def test_a_fourth_year_tacked_on_after_the_list(self):
        p = ecb.parse_projections(["Growth has been revised up to 1.4% in 2025, 1.2% in 2026 and 1.4% in 2027 and is expected to remain at "
                                   "1.4% in 2028."])
        self.assertEqual(p, {"gdp": {2025: 1.4, 2026: 1.2, 2027: 1.4, 2028: 1.4}})

    def test_loose_wording_is_left_out_not_guessed(self):
        p = ecb.parse_projections(["The economy is projected to grow by 1.2% in 2025, revised up from the 0.9% expected in June. The growth "
                                   "projection for 2026 is now slightly lower, at 1.0%, while the projection for 2027 is unchanged at 1.3%."])
        self.assertEqual(p, {})


class Listing(unittest.TestCase):
    HTML = """<dl>
      <dt isodate="2026-09-10"><div class="date">10 September 2026</div></dt><dd><div class="title"><a href="/press/pr/date/2026/html/ecb.mp260910~x.en.html">Monetary policy decisions</a></div></dd>
      <dt isodate="2026-09-10"><div class="date">10 September 2026</div></dt><dd><div class="title"><a href="/press/press_conference/monetary-policy-statement/shared/pdf/ecb.ds260910~y.en.pdf?abc">Combined monetary policy decisions and statement</a></div></dd>
      <dt isodate="2026-08-27"><div class="date">27 August 2026</div></dt><dd><div class="title"><a href="/press/accounts/2026/html/ecb.mg260827~z.en.html">Meeting of 22-23 July 2026</a></div></dd>
      <dt isodate="2026-09-10"><div class="date">10 September 2026</div></dt><dd><div class="title"><a href="/press/press_conference/monetary-policy-statement/2026/html/ecb.is260910~w.en.html">Christine Lagarde: Monetary policy statement (with Q&amp;A)</a></div></dd>
    </dl>"""

    def test_kinds_and_absolute_urls(self):
        rows = ecb.parse_listing(self.HTML)
        self.assertEqual([r["kind"] for r in rows], ["press_release", "account", "statement"])      # the combined PDF is not a document we read
        self.assertTrue(all(r["url"].startswith("https://www.ecb.europa.eu/") for r in rows))

    def test_account_titles_map_to_the_decision_day(self):
        self.assertEqual(ecb.account_decision_date("Meeting of 22-23 July 2026"), "2026-07-23")
        self.assertEqual(ecb.account_decision_date("Meeting of 3-5 June 2025"), "2025-06-05")
        self.assertEqual(ecb.account_decision_date("Meeting of 30 April-1 May 2025"), "2025-05-01")
        self.assertIsNone(ecb.account_decision_date("Meeting of 25 June 2025"))       # a one-day, non monetary policy meeting


ACCOUNT = """<html><main><h1>Meeting of 22-23 July 2026</h1>
<h2>Account of the monetary policy meeting of the Governing Council held in Frankfurt am Main on Wednesday and Thursday, 22-23 July 2026</h2>
<p>27 August 2026</p>
<h2>1. Review of financial, economic and monetary developments and policy options</h2>
<h3>Financial market developments</h3><p>Ms Schnabel started her presentation.</p>
<h2>2. Governing Council’s discussion and monetary policy decisions</h2>
<h3>Monetary policy decisions and communication</h3>
<p>Against this background, all members agreed with the proposal by Mr Lane to keep the three key ECB interest rates unchanged. Uncertainty had remained high.</p>
<p>Members stressed that the incoming data provided a strong case for a pause.</p>
<p>Some members noted that, as the incoming data had underlined the case for further policy tightening, they would not have opposed raising rates at the current meeting.</p>
<p>Taking into account the foregoing discussion among the members, upon a proposal by the President, the Governing Council took the decisions.</p>
<h3>Meeting of the ECB’s Governing Council, 22-23 July 2026</h3>
<ul><li>Ms Lagarde, President</li><li>Mr Vujčić, Vice-President</li><li>Mr Lane</li><li>Mr Kaasik*</li></ul>
<p>* Members not holding a voting right in July 2026 under Article 10.2 of the ESCB Statute.</p>
<ul><li>Mr Dombrovskis, Commissioner**</li></ul>
<p>Release of the next monetary policy account foreseen on 8 October 2026.</p>
<h2>European Central Bank</h2></main></html>"""


class Account(unittest.TestCase):
    def setUp(self):
        self.a = ecb.parse_account(ACCOUNT, url="u")

    def test_dates_and_sections(self):
        self.assertEqual((self.a["meeting_date"], self.a["released_on"], self.a["next_account_release"]), ("2026-07-23", "2026-08-27", "2026-10-08"))
        self.assertEqual([s["heading"] for s in self.a["sections"]], ["Financial market developments", "Monetary policy decisions and communication"])

    def test_attendance_marks_the_members_without_a_vote(self):
        self.assertEqual([(m["name"], m["voting"]) for m in self.a["members"]],
                         [("Lagarde", True), ("Vujčić", True), ("Lane", True), ("Kaasik", False)])       # the Commissioner is listed after the footnote and is not a member
        self.assertEqual(self.a["members"][0]["role"], "President")

    def test_agreement_sentence_is_carried_verbatim_with_the_councils_own_quantifier(self):
        self.assertEqual(self.a["agreement"]["quantifier"], "all")
        self.assertTrue(self.a["agreement"]["sentence"].startswith("Against this background, all members agreed with the proposal by Mr Lane"))

    def test_only_paragraphs_that_open_with_a_member_count_are_flagged_as_other_views(self):
        self.assertEqual(len(self.a["record_notes"]), 1)
        self.assertTrue(self.a["record_notes"][0]["lead"].startswith("Some members noted"))

    def test_almost_all_is_kept_as_almost_all(self):
        html = ACCOUNT.replace("all members agreed with the proposal by Mr Lane", "almost all members agreed with the proposal by Mr Lane")
        self.assertEqual(ecb.parse_account(html, url="u")["agreement"]["quantifier"], "almost all")

    def test_a_page_with_no_marked_non_voting_member_raises(self):
        with self.assertRaises(ValueError):
            ecb.parse_account(ACCOUNT.replace("Mr Kaasik*", "Mr Kaasik"), url="u")


class Calendar(unittest.TestCase):
    def test_decision_day_pairs_with_day_one(self):
        html = """<main><dl>
          <dt>30/09/2026</dt><dd>Governing Council of the ECB: non-monetary policy meeting (in Frankfurt)</dd>
          <dt>28/10/2026</dt><dd>Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 1)</dd>
          <dt>29/10/2026</dt><dd>Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 2), followed by press conference</dd></dl></main>"""
        self.assertEqual(ecb.parse_calendar(html), [{"decision_date": "2026-10-29", "day1": "2026-10-28"}])


@unittest.skipUnless(CONFIG.exists(), "collected file not present")
class Collected(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.meetings = cls.doc["meetings"]

    def test_deposit_rate_path_is_continuous(self):
        for a, b in zip(self.meetings, self.meetings[1:]):
            self.assertEqual(a["dfr_pct"], b["prior_dfr_pct"], f"{a['meeting_date']} -> {b['meeting_date']}")

    def test_the_corridor_is_what_the_framework_says(self):
        for m in self.meetings:
            if m["meeting_date"] >= "2024-09-12":                 # from 18 Sept 2024: MRO = DFR + 15bp, MLF = MRO + 25bp
                self.assertAlmostEqual(m["mro_pct"] - m["dfr_pct"], 0.15, places=2, msg=m["meeting_date"])
                self.assertAlmostEqual(m["mlf_pct"] - m["mro_pct"], 0.25, places=2, msg=m["meeting_date"])

    def test_every_account_is_attached_to_its_own_meeting(self):
        for m in self.meetings:
            if m.get("account"):
                self.assertEqual(m["account"]["meeting_date"], m["meeting_date"])
                self.assertTrue(any(x["voting"] for x in m["account"]["members"]))
                self.assertIsNotNone(m["account"]["agreement"], m["meeting_date"])

    def test_projection_years_are_consecutive(self):
        for m in self.meetings:
            for key, series in m["projections"].items():
                years = sorted(int(y) for y in series)
                self.assertEqual(years, list(range(years[0], years[0] + len(years))), f"{m['meeting_date']} {key}")


@unittest.skipUnless(CONFIG.exists(), "collected file not present")
class Assembled(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = assemble_ecb(json.loads(CONFIG.read_text(encoding="utf-8")), today=date(2026, 9, 25))

    def test_no_votes_are_invented(self):
        v = self.b["votes"]
        self.assertEqual((v["kind"], v["for"], v["against"]), ("consensus_only", None, []))
        self.assertIn("proposal", v["agreement"]["sentence"])
        self.assertIsNone(self.b["decision"]["majority"])

    def test_outlook_prior_is_the_previous_projection_round(self):
        t = self.b["outlook"]["table"]
        self.assertEqual(t["prior_made_in"], "2026-06")
        hicp = next(r for r in t["rows"] if r["id"] == "hicp")
        self.assertEqual([(v["year"], v["value"], v["prior"]) for v in hicp["values"]], [(2026, 3.0, 3.0), (2027, 2.5, 2.3), (2028, 2.1, 2.0)])

    def test_pending_account_gets_the_date_the_last_account_announced(self):
        pending = [r for r in self.b["releases"] if r["status"] != "released"]
        self.assertEqual([(r["meeting_date"], r["date"]) for r in pending], [("2026-09-10", "2026-10-08")])

    def test_schedule_and_shape(self):
        self.assertEqual(self.b["schedule"]["next_meeting_days"], ["2026-10-28", "2026-10-29"])
        self.assertEqual(self.b["iso3"], "EMU")
        json.dumps(self.b, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
