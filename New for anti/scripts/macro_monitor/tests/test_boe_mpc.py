"""Bank of England MPC page parsing (macro_monitor.cb_collect.boe) and the GBR block.

The text fixtures are the Bank's own sentences, copied from the published Summary and Minutes.
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor.cb_collect import boe  # noqa: E402
from macro_monitor.cb_collect.assemble import assemble_boe  # noqa: E402

CONFIG = Path(__file__).resolve().parent.parent / "config" / "boe_mpc_v1.json"

# --- vote paragraphs as published -------------------------------------------------------------
FEB_2024 = ("21: Six members (Andrew Bailey, Sarah Breeden, Ben Broadbent, Megan Greene, Huw Pill and Dave Ramsden) voted in favour of the "
            "proposition. Three members voted against the proposition. Two members (Jonathan Haskel and Catherine L Mann) preferred to "
            "increase Bank Rate by 0.25 percentage points, to 5.5%. One member (Swati Dhingra) preferred to reduce Bank Rate by 0.25 "
            "percentage points, to 5%.")
MAY_2025 = ("26: Five members (Andrew Bailey, Sarah Breeden, Megan Greene, Clare Lombardelli and Dave Ramsden) voted in favour of the "
            "proposition. Four members voted against the proposition. Two members (Swati Dhingra and Alan Taylor) preferred to reduce Bank "
            "Rate by 0.5 percentage points, to 4%. Two members (Catherine L Mann and Huw Pill) preferred to leave Bank Rate unchanged, at 4.5%.")
AUG_2025_STEP1 = ("22: Four members voted in favour of the proposition (Andrew Bailey, Sarah Breeden, Swati Dhingra and Dave Ramsden). "
                  "Four members (Megan Greene, Clare Lombardelli, Catherine L Mann and Huw Pill) preferred to maintain Bank Rate at 4.25%. "
                  "One member (Alan Taylor) preferred to reduce Bank Rate by 0.5 percentage points, to 3.75%.")
AUG_2025_STEP2 = ("24: Five members (Andrew Bailey, Sarah Breeden, Swati Dhingra, Dave Ramsden and Alan Taylor) voted to reduce Bank Rate by "
                  "0.25 percentage points, to 4%. One of these members (Alan Taylor), who would otherwise have preferred to reduce Bank Rate by "
                  "0.5 percentage points, voted for a 0.25 percentage points reduction rather than maintaining Bank Rate. Four members (Megan "
                  "Greene, Clare Lombardelli, Catherine L Mann and Huw Pill) voted to maintain Bank Rate at 4.25%.")
SEP_2025_ONE = ("51: Seven members (Andrew Bailey, Sarah Breeden, Megan Greene, Clare Lombardelli, Catherine L Mann, Huw Pill and Dave Ramsden) "
                "voted in favour of the first proposition. Two members (Swati Dhingra and Alan Taylor) voted against this proposition, "
                "preferring to reduce Bank Rate by 0.25 percentage points, to 3.75%.")
SEP_2025_TWO = ("52: Seven members (Andrew Bailey, Sarah Breeden, Swati Dhingra, Megan Greene, Clare Lombardelli, Dave Ramsden and Alan Taylor) "
                "voted in favour of the second proposition. Two members voted against this proposition. Catherine L Mann preferred a stock "
                "reduction of £62 billion. Huw Pill preferred a stock reduction of £100 billion.")
APR_2026 = ("18: Eight members (Andrew Bailey, Sarah Breeden, Swati Dhingra, Megan Greene, Clare Lombardelli, Catherine L Mann, Dave Ramsden, "
            "Alan Taylor) voted in favour of the proposition. Huw Pill voted against the proposition, preferring to increase Bank Rate by "
            "0.25 percentage points, to 4%.")
MAR_2026 = "33: The Committee voted unanimously in favour of the proposition."

TALLY_FEB_2024 = ("At its meeting ending on 31 January 2024, the MPC voted by a majority of 6–3 to maintain Bank Rate at 5.25%. "
                  "Two members preferred to increase Bank Rate by 0.25 percentage points, to 5.5%.")


class Decision(unittest.TestCase):
    def test_majority_hold(self):
        d = boe.parse_decision(TALLY_FEB_2024)
        self.assertEqual((d["action"], d["rate_pct"], d["prior_rate_pct"], d["change_bp"]), ("maintain", 5.25, 5.25, 0))
        self.assertEqual((d["tally_for"], d["tally_against"], d["unanimous"]), (6, 3, False))

    def test_cut_states_its_size_and_the_prior_rate_follows(self):
        d = boe.parse_decision("the Monetary Policy Committee (MPC) voted by a majority of 5–4 to reduce Bank Rate by 0.25 percentage points, to 4%.")
        self.assertEqual((d["action"], d["rate_pct"], d["prior_rate_pct"], d["change_bp"]), ("lower", 4.0, 4.25, -25))

    def test_unanimous(self):
        d = boe.parse_decision("the MPC voted unanimously to increase Bank Rate by 0.25 percentage points, to 4%.")
        self.assertEqual((d["action"], d["prior_rate_pct"], d["unanimous"], d["tally_for"]), ("raise", 3.75, True, None))

    def test_no_sentence_raises(self):
        with self.assertRaises(ValueError):
            boe.parse_decision("The Committee discussed conditions.")


class VoteParagraphs(unittest.TestCase):
    def test_split_dissent_in_both_directions(self):
        v = boe.parse_vote_paragraph(FEB_2024, rate_pct=5.25)
        self.assertEqual(len(v["for"]), 6)
        self.assertEqual({(a["name"], a["alt_rate_pct"]) for a in v["against"]},
                         {("Jonathan Haskel", 5.5), ("Catherine L Mann", 5.5), ("Swati Dhingra", 5.0)})

    def test_dissenters_who_disagree_with_each_other(self):
        v = boe.parse_vote_paragraph(MAY_2025, rate_pct=4.25)      # the decision was a cut to 4.25%
        self.assertEqual(len(v["for"]), 5)
        alts = {a["name"]: a["alt_rate_pct"] for a in v["against"]}
        self.assertEqual(alts, {"Swati Dhingra": 4.0, "Alan Taylor": 4.0, "Catherine L Mann": 4.5, "Huw Pill": 4.5})

    def test_single_dissenter_and_first_proposition(self):
        v = boe.parse_vote_paragraph(APR_2026, rate_pct=3.75)
        self.assertEqual((len(v["for"]), [a["name"] for a in v["against"]], v["against"][0]["alt_rate_pct"]), (8, ["Huw Pill"], 4.0))
        v = boe.parse_vote_paragraph(SEP_2025_ONE, rate_pct=4.0)
        self.assertEqual((len(v["for"]), len(v["against"])), (7, 2))

    def test_head_count_disagreeing_with_names_raises(self):
        with self.assertRaises(ValueError):
            boe.parse_vote_paragraph("Six members (Andrew Bailey, Sarah Breeden) voted in favour of the proposition.", rate_pct=4.0)


class ChooseVote(unittest.TestCase):
    def test_two_step_vote_uses_the_step_the_tally_describes(self):
        d = boe.parse_decision("the MPC voted by a majority of 5–4 to reduce Bank Rate by 0.25 percentage points, to 4%.")
        v = boe.choose_vote([AUG_2025_STEP1, AUG_2025_STEP2, "25: On this basis, the MPC voted by a majority of 5–4 to reduce Bank Rate."], d)
        self.assertEqual((len(v["for"]), len(v["against"])), (5, 4))
        self.assertIn("Alan Taylor", v["for"])
        self.assertEqual(len(v["earlier"]), 1)                        # the first 4-4-1 round is kept as text
        self.assertTrue(any("otherwise have preferred" in n for n in v["notes"]))

    def test_gilt_stock_vote_is_not_a_bank_rate_vote(self):
        d = boe.parse_decision("the MPC voted by a majority of 7–2 to maintain Bank Rate at 4%.")
        v = boe.choose_vote([SEP_2025_ONE, SEP_2025_TWO], d)
        self.assertEqual((len(v["for"]), len(v["against"])), (7, 2))
        self.assertEqual(v["earlier"], [])

    def test_unanimous(self):
        d = boe.parse_decision("the MPC voted unanimously to maintain Bank Rate at 3.75%.")
        self.assertEqual(boe.choose_vote([MAR_2026], d)["kind"], "unanimous")

    def test_tally_that_the_paragraph_cannot_reproduce_raises(self):
        d = boe.parse_decision("the MPC voted by a majority of 5–4 to maintain Bank Rate at 4%.")
        with self.assertRaises(ValueError):
            boe.choose_vote([APR_2026], d)


def _page(*, vote_paragraph, tally, groups=None, present=None, published="17 September 2026"):
    """A page shaped like the Bank's: Summary, Minutes with h3 sections, attendance as list items."""
    views = ""
    for label, members in (groups or []):
        views += f"<p><strong>{label}</strong></p>" + "".join(f"<p><strong>{n}:</strong> {n} explains the vote.</p>" for n in members)
    people = "".join(f"<li>{n}</li>" for n in (present or ["Andrew Bailey, Chair", "Sarah Breeden"]))
    return f"""<html><body><main><h1>Bank Rate maintained</h1><p>Published on {published}</p>
    <h2>Monetary Policy Summary, September 2026</h2><p>{tally}</p><p>Inflation is expected to rise.</p>
    <h2>Minutes of the Monetary Policy Committee meeting ending on 16 September 2026</h2>
    <p>1: The Committee discussed conditions.</p>
    <h3>The immediate policy decisions</h3><p>46: The Chair invited the Committee to vote.</p><p>{vote_paragraph}</p>
    <h3>MPC members’ views on Bank Rate</h3><p>Members set out the rationale.</p>{views}
    <h3>Operational considerations</h3><p>50: The stock was £488 billion.</p>
    <p>51: The following members of the Committee were present:</p><ul>{people}</ul>
    <p>Jane Roe was present as the Treasury representative.</p>
    <h3>Latest and upcoming MPC dates</h3></main></body></html>"""


TALLY = "At its meeting ending on 16 September 2026, the MPC voted by a majority of 2–1 to maintain Bank Rate at 3.75%."
VOTE = ("47: Two members (Andrew Bailey and Sarah Breeden) voted in favour of the proposition. Huw Pill voted against the proposition, "
        "preferring to increase Bank Rate by 0.25 percentage points, to 4%.")


class Page(unittest.TestCase):
    def test_published_day_is_taken_from_the_page_and_sections_are_kept(self):
        r = boe.parse_meeting(_page(vote_paragraph=VOTE, tally=TALLY), url="u")
        self.assertEqual((r["meeting_date"], r["meeting_end_date"]), ("2026-09-17", "2026-09-16"))
        self.assertEqual(r["vote"]["for_source"], "minutes_vote_paragraph")
        self.assertEqual([p["name"] for p in r["minutes"]["present"]], ["Andrew Bailey", "Sarah Breeden"])
        self.assertEqual(r["minutes"]["present"][0]["role"], "Chair")
        self.assertEqual(r["minutes"]["treasury_representative"], "Jane Roe")
        self.assertEqual(r["summary_paragraphs"], ["Inflation is expected to rise."])       # the tally paragraph is kept apart
        self.assertEqual([s["heading"] for s in r["minutes"]["sections"]], [None, "The immediate policy decisions", "Operational considerations"])

    def test_member_views_must_agree_with_the_vote_paragraph(self):
        groups = [("Votes to maintain Bank Rate at 3.75%", ["Andrew Bailey", "Sarah Breeden"]),
                  ("Votes to increase Bank Rate to 4%", ["Huw Pill"])]
        r = boe.parse_meeting(_page(vote_paragraph=VOTE, tally=TALLY, groups=groups), url="u")
        self.assertEqual([(v["name"], v["group_rate_pct"]) for v in r["member_views"]],
                         [("Andrew Bailey", 3.75), ("Sarah Breeden", 3.75), ("Huw Pill", 4.0)])
        wrong = [("Votes to maintain Bank Rate at 3.75%", ["Andrew Bailey", "Huw Pill"]),
                 ("Votes to increase Bank Rate to 4%", ["Sarah Breeden"])]
        with self.assertRaises(ValueError):
            boe.parse_meeting(_page(vote_paragraph=VOTE, tally=TALLY, groups=wrong), url="u")

    def test_unanimous_meeting_takes_names_from_the_groups(self):
        groups = [("Votes to maintain Bank Rate at 3.75%", ["Andrew Bailey", "Sarah Breeden"])]
        r = boe.parse_meeting(_page(vote_paragraph="33: The Committee voted unanimously in favour of the proposition.",
                                    tally="At its meeting ending on 16 September 2026, the MPC voted unanimously to maintain Bank Rate at 3.75%.",
                                    groups=groups), url="u")
        self.assertEqual((r["vote"]["for"], r["vote"]["for_source"]), (["Andrew Bailey", "Sarah Breeden"], "member_views"))

    def test_page_without_minutes_is_not_held(self):
        with self.assertRaises(boe.NotHeld):
            boe.parse_meeting("<html><main><h1>Bank Rate</h1><p>Published on 5 November 2026</p></main></html>", url="u")

    def test_slug_and_url(self):
        self.assertEqual(boe.meeting_url(2026, 9), "https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2026/september-2026")


class Calendar(unittest.TestCase):
    def test_rows_report_flags_and_next_due(self):
        html = """<main><h2>2026 confirmed dates</h2><table>
          <tr><td>Thursday 5 February</td><td>February MPC Summary and minutes and February Monetary Policy Report</td></tr>
          <tr><td>Thursday 19 March</td><td>March MPC Summary and minutes</td></tr></table>
          <h2>Current Bank Rate 3.75%</h2><p>Next due: 5 November 2026</p>
          <h2>2027 confirmed dates</h2><table><tr><td>Thursday 4 February</td><td>February MPC Summary and minutes</td></tr></table></main>"""
        c = boe.parse_calendar(html)
        self.assertEqual(c["next_due"], "2026-11-05")
        self.assertEqual([(r["decision_date"], r["monetary_policy_report"]) for r in c["rows"]],
                         [("2026-02-05", True), ("2026-03-19", False), ("2027-02-04", False)])


def _report_page(head, rows, *, cols=("2026 Q3", "2027 Q3"), note="(b) Four-quarter inflation rate."):
    body = "".join(rows)
    return f"""<html><main><h1>Monetary Policy Report - July 2026</h1><p>Published on 30 July 2026</p>
    <h3>{head}</h3><table><tr><td></td>{"".join(f"<td>{c}</td>" for c in cols)}</tr>{body}</table>
    <div class="text-small img-note"><ul><li>(a) Figures in parentheses show the previous Report.</li><li>{note}</li></ul></div></main></html>"""


def _tr(*cells):
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


class Report(unittest.TestCase):
    def test_scenario_table_is_split_into_blocks_with_footnote_definitions(self):
        html = _report_page("Table 3.B: Summary of outputs of the central projection and scenarios ( a )", [
            _tr("Central projection"), _tr("CPI inflation ( b )", "2.9", "2.6"), _tr("Bank Rate ( i )", "3.8", "4.2"),
            _tr("Adverse scenario"), _tr("CPI inflation ( b )", "3.1", "4.1")])
        r = boe.parse_report(html, url="u")
        self.assertEqual((r["published"], r["summary"]["table_id"], r["summary"]["columns"]), ("2026-07-30", "3.B", ["2026 Q3", "2027 Q3"]))
        self.assertEqual([b["name"] for b in r["summary"]["blocks"]], ["Central projection", "Adverse scenario"])
        cpi = r["summary"]["blocks"][0]["rows"][0]
        self.assertEqual((cpi["id"], cpi["label_en"], cpi["notes"]), ("cpi", "CPI inflation", ["b"]))
        self.assertEqual([v["value"] for v in cpi["values"]], [2.9, 2.6])
        self.assertEqual(r["summary"]["footnotes"]["b"], "Four-quarter inflation rate.")

    def test_figure_in_brackets_is_the_previous_reports(self):
        html = _report_page("Table 3.A: Forecast summary ( a ) ( b )", [_tr("GDP ( c )", "1.4 (1.5)", "1.4 (1.3)"), _tr("Excess supply/ Excess demand ( f )", "-0.8 (-0.6)", "0")])
        blocks = boe.parse_report(html, url="u")["summary"]["blocks"]
        self.assertEqual(len(blocks), 1)                                   # no block heading: one unnamed block
        self.assertEqual([(v["value"], v["prior"]) for v in blocks[0]["rows"][0]["values"]], [(1.4, 1.5), (1.4, 1.3)])
        self.assertEqual([(v["value"], v["prior"]) for v in blocks[0]["rows"][1]["values"]], [(-0.8, -0.6), (0.0, None)])

    def test_dash_and_words_are_not_numbers(self):
        self.assertEqual(boe._cell("–"), (None, None))
        self.assertEqual(boe._cell("n/a"), (None, None))
        self.assertEqual(boe._cell("−1.1"), (-1.1, None))                  # the typographic minus

    def test_key_assumption_tables_are_not_forecast_summaries(self):
        html = _report_page("Table 3.A: Key assumptions and judgements in the central projection and scenarios", [_tr("Energy prices", "up", "down")])
        with self.assertRaises(boe.NotHeld):
            boe.parse_report(html, url="u")

    def test_annex_average_columns_are_left_out(self):
        html = _report_page("Table 3.B: Summary of scenarios ( a )", [_tr("CPI inflation ( b )", "3.1", "2.9")]).replace(
            "</main>", """<h3>Table A1.A: GDP ( a )</h3><table><tr><td></td><td>Average 1998–2007</td><td>2025</td><td>2026</td></tr>
            <tr><td>UK GDP ( c )</td><td>2.8</td><td>1.3</td><td>1.1</td></tr></table></main>""")
        annual = boe.parse_report(html, url="u")["annual"]
        self.assertEqual((annual[0]["columns"], annual[0]["blocks"][0]["rows"][0]["id"]), (["2025", "2026"], "gdp"))

    def test_report_url(self):
        self.assertEqual(boe.report_url(2026, 7), "https://www.bankofengland.co.uk/monetary-policy-report/2026/july-2026")


@unittest.skipUnless(CONFIG.exists(), "collected file not present")
class Collected(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.meetings = cls.doc["meetings"]

    def test_every_vote_reproduces_the_stated_tally(self):
        for m in self.meetings:
            v = m["vote"]
            if m["unanimous"]:
                self.assertEqual(v["against"], [], m["meeting_date"])
            else:
                self.assertEqual((len(v["for"]), len(v["against"])), (m["tally_for"], m["tally_against"]), m["meeting_date"])
            self.assertEqual(len(set(v["for"]) | {a["name"] for a in v["against"]}), len(v["for"]) + len(v["against"]), m["meeting_date"])

    def test_rate_path_is_continuous(self):
        for a, b in zip(self.meetings, self.meetings[1:]):
            self.assertEqual(a["rate_pct"], b["prior_rate_pct"], f"{a['meeting_date']} -> {b['meeting_date']}")

    def test_the_decision_is_announced_the_day_after_the_meeting_ends(self):
        for m in self.meetings:
            end = date.fromisoformat(m["meeting_end_date"])
            self.assertEqual(m["meeting_date"], (end + timedelta(days=1)).isoformat())
            self.assertEqual(date.fromisoformat(m["meeting_date"]).weekday(), 3, m["meeting_date"])      # always a Thursday

    def test_reports_belong_to_forecast_rounds_and_read_all_columns(self):
        dates = {m["meeting_date"] for m in self.meetings}
        for r in self.doc["reports"]:
            self.assertIn(r["meeting_date"], dates)
            cols = r["summary"]["columns"]
            self.assertEqual(len(cols), 4, r["page"])
            for b in r["summary"]["blocks"]:
                for row in b["rows"]:
                    self.assertEqual(len(row["values"]), len(cols), f"{r['page']} {row['label_en']}")
                    self.assertTrue(all(v["value"] is not None for v in row["values"]), f"{r['page']} {row['label_en']}")

    def test_announcement_days_appear_on_the_banks_calendar(self):
        days = {r["decision_date"] for r in self.doc["calendar"]["rows"]}
        for m in self.meetings:
            if m["meeting_date"][:4] in {d[:4] for d in days}:
                self.assertIn(m["meeting_date"], days)


@unittest.skipUnless(CONFIG.exists(), "collected file not present")
class Assembled(unittest.TestCase):
    def test_block_shape(self):
        b = assemble_boe(json.loads(CONFIG.read_text(encoding="utf-8")), today=date(2026, 9, 25))
        self.assertEqual(b["iso3"], "GBR")
        self.assertEqual(b["decision"]["meeting_date"], "2026-09-17")
        self.assertEqual(b["votes"]["for_count"], len(b["votes"]["for"]))
        self.assertEqual(b["schedule"]["next_meeting_date"], "2026-11-05")
        self.assertEqual(b["schedule"]["next_outlook_release"], "2026-11-05")        # November is a Monetary Policy Report round
        self.assertEqual(sum(len(g["members"]) for g in b["member_views"]["groups"]), 9)
        o = b["outlook"]
        self.assertEqual((o["kind"], o["meeting_date"], o["previous"]["meeting_date"]), ("projection_blocks", "2026-07-30", "2026-04-30"))
        cpi = o["summary"]["blocks"][0]["rows"][0]
        self.assertEqual((cpi["id"], cpi["label_ko"] is not None, cpi["definition_en"] is not None), ("cpi", True, True))
        json.dumps(b, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
