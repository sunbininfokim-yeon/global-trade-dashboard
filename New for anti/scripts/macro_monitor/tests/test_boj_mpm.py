"""Bank of Japan statement parsing (macro_monitor.cb_collect.boj), on excerpts of real statements."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor.cb_collect import boj  # noqa: E402

# 2026-09-18: a 7-2 hike with two dissenters, each with their own reason.
SEPT = """September 18, 2026
Bank of Japan
Change in the Guideline for Money Market Operations
1. At the Monetary Policy Meeting held today, the Policy Board of the Bank of Japan decided, by
a 7-2 majority vote, to set the following guideline for money market operations for the
intermeeting period: [Note]
The Bank will encourage the uncollateralized overnight call rate to remain at around 1.25
percent.1
3. Regarding the Funds-Supplying Operations, the Bank decided, by a unanimous vote, to change the loan rate.
4. Japan's economy has recovered moderately, although some weakness has been seen in part
(see Attachment). Financial conditions have been accommodative. In view of the aforementioned
developments, the Bank judged it appropriate to adjust the degree of monetary accommodation.
Accommodative financial conditions are expected to be maintained after the change in the policy interest
rate, continuing to firmly support economic activity. The Bank will conduct monetary policy as appropriate
from the perspective of sustainable and stable achievement of the target. Filler filler filler filler filler
filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler
filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler
filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler
filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler
filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler
filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler
filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler.
3
[Note] V oting for the action: UEDA Kazuo, HIMINO Ryozo, UCHIDA Shinichi, TAKA TA Hajime, TAMURA
Naoki, KOEDA Junko, and MASU Kazuyuki. Voting against the action: ASADA Toichiro and SATO
Ayano. Asada Toichiro dissented, considering that the CPI was below 2 percent and it was desirable to maintain the
guideline. Sato Ayano dissented, considering that developments had not substantially accelerated.
Attachment
Economic Activity and Prices in Japan: Current Situation and Outlook
1. Japan's economy has recovered moderately.
Reference
Meeting hours:
Policy Board members present:
UEDA Kazuo, Chairman (Governor)
HIMINO Ryozo (Deputy Governor)
UCHIDA Shinichi (Deputy Governor)
TAKATA Hajime
TAMURA Naoki
KOEDA Junko
MASU Kazuyuki
ASADA Toichiro
SATO Ayano
[Others present]
Release dates and times:
Change in the Guideline for Money Market Operations -- Friday, September 18 at 11:54
Summary of Opinions -- Thursday, October 1 at 8:50
Minutes of the Monetary Policy Meeting -- Thursday, November 5 at 8:50
"""

# 2026-06-16: 7-1 with the Governor absent.
JUNE_NOTE = """At the Monetary Policy Meeting held today, the Policy Board of the Bank of Japan decided, by a 7-1 majority vote, to set the following guideline: The Bank will encourage the uncollateralized overnight call rate to remain at around 1.0 percent.
[Note] Voting for the action: HIMINO Ryozo, UCHIDA Shinichi, NAKAGAWA Junko, TAKATA Hajime, TAMURA Naoki, KOEDA Junko, and MASU Kazuyuki. Voting against the action: ASADA Toichiro. Absent: UEDA Kazuo. Asada Toichiro dissented, considering that downside risks were greater. Reference
Policy Board members present:
HIMINO Ryozo (Deputy Governor)
[Others present]
"""

# 2026-04-28: three dissenters, one shared alternative.
APRIL_NOTE = """At the Monetary Policy Meeting held today, the Policy Board decided, by a 6-3 majority vote, to set the following guideline: The Bank will encourage the uncollateralized overnight call rate to remain at around 0.75 percent.
[Note] Voting for the action: UEDA Kazuo, HIMINO Ryozo, UCHIDA Shinichi, KOEDA Junko, MASU Kazuyuki, and ASADA Toichiro. Voting against the action: NAKAGAWA Junko, TAKATA Hajime, and TAMURA Naoki. Nakagawa Junko considered that risks to prices were skewed to the upside. Takata Hajime considered that the price stability target had been more or less achieved. Tamura Naoki considered that the Bank should set the policy interest rate as close to the neutral rate as possible. They proposed that the Bank set the guideline as follows: the Bank would encourage the uncollateralized overnight call rate to remain at around 1.0 percent. The proposals were defeated by majority votes. Reference
Policy Board members present:
UEDA Kazuo, Chairman (Governor)
[Others present]
"""

# 2025-06-17: the rate vote is unanimous; the [Note] names belong to the JGB purchase plan.
JUNE_2025 = """At the Monetary Policy Meeting held today, the Policy Board of the Bank of Japan decided, by a unanimous vote, to set the following guideline: The Bank will encourage the uncollateralized overnight call rate to remain at around 0.5 percent.
Regarding the reduction of its purchase amount of JGBs, the Bank decided, by an 8-1 majority vote, on a plan. [Note]
[Note] Voting for the action: UEDA Kazuo, HIMINO Ryozo. Voting against the action: TAMURA Naoki. Tamura Naoki considered that long-term rates should be market-determined. Reference
Policy Board members present:
UEDA Kazuo, Chairman (Governor)
HIMINO Ryozo (Deputy Governor)
TAMURA Naoki
[Others present]
"""


def _parse(text, day="2026-09-18"):
    return boj.parse_statement(text, meeting_date=day, source_url="https://example/k")


class StatementVotes(unittest.TestCase):
    def test_named_for_and_against_with_own_reasons(self):
        r = _parse(SEPT)
        self.assertEqual(r["guideline_rate_pct"], 1.25)
        self.assertFalse(r["unanimous"])
        self.assertEqual((r["vote_for_count"], r["vote_against_count"]), (7, 2))
        self.assertEqual(r["voting_for"][3], "Takata Hajime")          # "TAKA TA" repaired
        self.assertEqual([a["name"] for a in r["voting_against"]], ["Asada Toichiro", "Sato Ayano"])
        asada, sato = r["voting_against"]
        self.assertIn("CPI was below 2 percent", asada["reason"])
        self.assertNotIn("Sato", asada["reason"])
        self.assertIn("had not substantially accelerated", sato["reason"])
        self.assertIsNone(asada["proposal_rate_pct"])

    def test_absent_member_is_not_a_dissenter(self):
        r = _parse(JUNE_NOTE, "2026-06-16")
        self.assertEqual([a["name"] for a in r["voting_against"]], ["Asada Toichiro"])
        self.assertEqual(r["members_absent"], ["Ueda Kazuo"])
        self.assertEqual((r["vote_for_count"], r["vote_against_count"]), (7, 1))

    def test_shared_alternative_rate_goes_to_every_dissenter(self):
        r = _parse(APRIL_NOTE, "2026-04-28")
        self.assertEqual([a["proposal_rate_pct"] for a in r["voting_against"]], [1.0, 1.0, 1.0])
        # the group sentence is not part of any one member's own reason
        self.assertNotIn("They proposed", r["voting_against"][2]["reason"])

    def test_unanimous_rate_vote_ignores_another_decisions_note(self):
        r = _parse(JUNE_2025, "2025-06-17")
        self.assertTrue(r["unanimous"])
        self.assertEqual(r["voting_against"], [])
        self.assertEqual(r["voting_for_source"], "unanimous_all_present")
        self.assertEqual(r["voting_for"], ["Ueda Kazuo", "Himino Ryozo", "Tamura Naoki"])

    def test_tally_that_does_not_match_the_names_is_an_error(self):
        broken = SEPT.replace("7-2 majority", "8-1 majority")
        with self.assertRaises(ValueError):
            _parse(broken)

    def test_release_dates_come_from_the_statement(self):
        r = _parse(SEPT)
        self.assertEqual(r["releases"], {"summary_of_opinions": "2026-10-01", "minutes": "2026-11-05"})

    def test_release_in_next_year(self):
        text = "Summary of Opinions -- Monday, December 28 at 8:50 Minutes of the Monetary Policy Meeting -- Wednesday, January 27 at 8:50"
        self.assertEqual(boj.parse_releases(text, boj.date(2025, 12, 19)),
                         {"summary_of_opinions": "2025-12-28", "minutes": "2026-01-27"})

    def test_narrative_stops_before_the_vote_note_and_attachment(self):
        n = _parse(SEPT)["narrative"]
        self.assertTrue(n.startswith("Japan's economy has recovered moderately"))
        self.assertNotIn("Voting", n)
        self.assertNotIn("Attachment Economic", n)

    def test_short_outlook_month_statement_has_no_narrative(self):
        self.assertIsNone(_parse(JUNE_2025, "2025-06-17")["narrative"])


class Names(unittest.TestCase):
    def test_names(self):
        self.assertEqual(boj.parse_names("UEDA Kazuo, HIMINO Ryozo, and SATO Ayano."), ["Ueda Kazuo", "Himino Ryozo", "Sato Ayano"])
        self.assertEqual(boj.parse_names("TAKA TA Hajime and ASADA Toichiro"), ["Takata Hajime", "Asada Toichiro"])


class Statements(unittest.TestCase):
    def test_index_keeps_only_the_main_document(self):
        html = """<table><tr><td>Sept. 18, 2026</td><td><a href="/en/mopo/mpmdeci/mpr_2026/k260918b.pdf">(Reference) Change [PDF 197KB]</a></td></tr>
        <tr><td>Sept. 18, 2026</td><td><a href="/en/mopo/mpmdeci/mpr_2026/k260918a.pdf">Change in the Guideline [PDF 204KB]</a></td></tr>
        <tr><td>Jan. 23, 2026</td><td><a href="/en/mopo/mpmdeci/state_2026/k260123a.htm">Statement on Monetary Policy</a></td></tr></table>"""
        rows = boj.parse_statements_index(html)
        self.assertEqual([(r["meeting_date"], r["format"]) for r in rows], [("2026-09-18", "pdf"), ("2026-01-23", "htm")])
        self.assertTrue(rows[0]["url"].startswith("https://www.boj.or.jp/"))


FORECAST = """Forecasts of the Majority of the Policy Board Members y/y % chg. Real GDP CPI (all items less fresh food) (Reference) CPI (all items less fresh food and energy)
Fiscal 2025 +1.0 to +1.0 [+1.0] +2.7 +3.0
Forecasts made in January 2026 +0.8 to +0.9 [+0.9] +2.7 to +2.8 [+2.7] +2.9 to +3.1 [+3.0]
Fiscal 2026 +0.4 to +0.7 [+0.5] +2.8 to +3.0 [+2.8] +2.5 to +2.7 [+2.6]
Forecasts made in January 2026 +0.8 to +1.0 [+1.0] +1.9 to +2.0 [+1.9] +2.0 to +2.3 [+2.2]
Fiscal 2028 +0.7 to +0.8 [+0.8] +2.0 to +2.2 [+2.0] +2.1 to +2.4 [+2.2]
Notes: 1. Figures in brackets indicate the medians"""


class Forecasts(unittest.TestCase):
    def test_ranges_medians_and_previous_round(self):
        t = boj.parse_forecast_table(FORECAST)
        self.assertEqual(t["prior_made_in"], "January 2026")
        y26 = next(y for y in t["years"] if y["fiscal_year"] == 2026)
        self.assertEqual((y26["cpi"]["range_low"], y26["cpi"]["range_high"], y26["cpi"]["median"]), (2.8, 3.0, 2.8))
        self.assertEqual(y26["prior"]["cpi"]["median"], 1.9)

    def test_a_finished_fiscal_year_prints_bare_figures(self):
        y25 = boj.parse_forecast_table(FORECAST)["years"][0]
        self.assertTrue(y25["cpi"]["single"])
        self.assertEqual(y25["cpi"]["median"], 2.7)
        self.assertIsNone(y25["cpi"]["range_low"])

    def test_a_new_fiscal_year_has_no_previous_round(self):
        y28 = next(y for y in boj.parse_forecast_table(FORECAST)["years"] if y["fiscal_year"] == 2028)
        self.assertIsNone(y28["prior"])

    def test_no_table_is_none(self):
        self.assertIsNone(boj.parse_forecast_table("nothing here"))


SCHEDULE = """<table><caption>Table : 2026</caption>
<tr><th>Date of MPM</th><th>Release Schedule</th></tr><tr><th>Outlook</th><th>Summary</th><th>Minutes</th></tr>
<tr><td>Sept. 17 (Thurs.), 18 (Fri.) [PDF 204KB]</td><td>-</td><td>Oct. 1 (Thurs.)</td><td>Nov. 5 (Thurs.)</td></tr>
<tr><td>Oct. 29 (Thurs.), 30 (Fri.)</td><td>Oct. 30 (Fri.)</td><td>Nov. 10 (Tues.)</td><td>Dec. 23 (Wed.)</td></tr>
<tr><td>Dec. 17 (Thurs.), 18 (Fri.)</td><td>-</td><td>Dec. 28 (Mon.)</td><td>Jan. 27 (Wed.), 2027</td></tr></table>
<table><caption>Table : 2027</caption>
<tr><td>Dec. 16 (Thurs.), 17 (Fri.)</td><td>-</td><td>Dec. 27 (Mon.)</td><td>To be announced</td></tr></table>"""


class Schedule(unittest.TestCase):
    def test_calendar_rows(self):
        rows = boj.parse_schedule(SCHEDULE)
        by = {r["decision_date"]: r for r in rows}
        self.assertEqual(by["2026-10-30"]["meeting_days"], ["2026-10-29", "2026-10-30"])
        self.assertEqual(by["2026-10-30"]["outlook_release"], "2026-10-30")
        self.assertIsNone(by["2026-09-18"]["outlook_release"])
        self.assertEqual(by["2026-12-18"]["minutes_release"], "2027-01-27")        # carries its own year

    def test_a_date_not_yet_fixed_is_none_not_a_guess(self):
        by = {r["decision_date"]: r for r in boj.parse_schedule(SCHEDULE)}
        self.assertIsNone(by["2027-12-17"]["minutes_release"])


if __name__ == "__main__":
    unittest.main()
