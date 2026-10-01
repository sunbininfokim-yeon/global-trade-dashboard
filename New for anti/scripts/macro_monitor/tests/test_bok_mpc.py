"""Bank of Korea decision parsing (macro_monitor.cb_collect.bok), on excerpts of real releases."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor.cb_collect import bok  # noqa: E402


def _page(paragraphs: list[str]) -> str:
    body = "".join(f'<p class="0"><span>{p}</span></p>' for p in paragraphs)
    return f'<html><body><div class="dbdata"><p>통화정책방향</p>{body}</div></body></html>'


HIKE = ("□&nbsp;금융통화위원회는 다음 통화정책방향 결정시까지 한국은행 기준금리를 현재의 </span><span>2.75% </span><span>수준에서 </span>"
        "<span>3.00%로 상향 조정하여 통화정책을 운용하기로 하였다.")
HOLD_2025 = "□ 금융통화위원회는 다음 통화정책방향 결정시까지 한국은행 기준금리를 현재의 2.50% 수준에서 유지하여 통화정책을 운용하기로 하였다 ."
HOLD_2023 = "□ 금융통화위원회는 다음 통화정책방향 결정시까지 한국은행 기준금리를 현 수준(3.50%)에서 유지하여 통화정책을 운용하기로 하였다."
CUT = "□ 금융통화위원회는 다음 통화정책방향 결정시까지 한국은행 기준금리를 현재의 3.25% 수준에서 3.00%로 하향 조정하여 통화정책을 운용하기로 하였다."
VOTE_SPLIT = "□ 금번 기준금리 인상 결정에 대해 금융통화위원 6명은 찬성하였으며, 황건일 위원은 기준금리를 2.75%로 유지하는 것이 바람직하다는 의견을 나타냈다."
VOTE_TWO = "□ 금번 기준금리 결정에 대해 금융통화위원 5명은 찬성하였으며, 장용성 위원과 유상대 위원은 기준금리를 2.75%로 인상하는 것이 바람직하다는 의견을 나타냈다."
VOTE_ALL = "□ 금번 기준금리 동결 결정에 대해서는 금융통화위원 7명 모두 찬성하였다."


def _parse(first, *rest):
    return bok.parse_decision(_page([first, *rest]), meeting_date="2026-08-27", source_url="u")


class Decision(unittest.TestCase):
    def test_hike_across_span_boundaries(self):
        r = _parse(HIKE)
        self.assertEqual((r["prior_rate_pct"], r["rate_pct"], r["action"], r["change_bp"]), (2.75, 3.0, "raise", 25))

    def test_hold_in_both_wordings(self):
        for text, rate in ((HOLD_2025, 2.5), (HOLD_2023, 3.5)):
            r = _parse(text)
            self.assertEqual((r["prior_rate_pct"], r["rate_pct"], r["action"], r["change_bp"]), (rate, rate, "maintain", 0))

    def test_cut(self):
        r = _parse(CUT)
        self.assertEqual((r["action"], r["change_bp"], r["rate_pct"]), ("lower", -25, 3.0))

    def test_spacing_before_punctuation_is_normalised(self):
        self.assertNotIn("하였다 .", _parse(HOLD_2025)["paragraphs"][0])

    def test_vote_paragraph_is_not_part_of_the_compared_text(self):
        r = _parse(HIKE, "□ 세계경제는 완만한 성장세를 보였다.", VOTE_SPLIT)
        self.assertEqual(len(r["paragraphs"]), 2)
        self.assertNotIn("찬성", " ".join(r["paragraphs"]))

    def test_release_without_a_vote_sentence_has_no_vote(self):
        self.assertIsNone(_parse(HOLD_2025, "□ 세계경제는 완만하다.")["vote"])

    def test_missing_body_or_rate_is_an_error(self):
        with self.assertRaises(ValueError):
            bok.parse_decision("<html><body>nothing</body></html>", meeting_date="2026-08-27", source_url="u")
        with self.assertRaises(ValueError):
            _parse("□ 금융통화위원회는 다음 통화정책방향 결정시까지 정책을 운용한다.")


class Vote(unittest.TestCase):
    def test_one_dissenter_with_his_preferred_rate(self):
        v = bok.parse_vote(VOTE_SPLIT)
        self.assertEqual(v["favor_count"], 6)
        self.assertEqual(v["against"], [{"name": "황건일", "preferred_rate_pct": 2.75, "direction": "hold"}])
        self.assertFalse(v["unanimous"])

    def test_two_dissenters_share_one_preference(self):
        v = bok.parse_vote(VOTE_TWO)
        self.assertEqual([a["name"] for a in v["against"]], ["장용성", "유상대"])
        self.assertEqual({a["direction"] for a in v["against"]}, {"higher"})

    def test_all_in_favour(self):
        v = bok.parse_vote(VOTE_ALL)
        self.assertTrue(v["unanimous"])
        self.assertEqual((v["favor_count"], v["against"]), (7, []))

    def test_unrecognised_sentence_is_none(self):
        self.assertIsNone(bok.parse_vote("□ 위원회는 결정하였다."))


class Outlook(unittest.TestCase):
    def test_forecast_sentences_kept_verbatim(self):
        para = ("□ 국내경제는 견조하다. 이에 따라 금년 및 내년 성장률은 지난 5월 전망치(각각 2.6%, 2.1%)를 큰 폭 상회하는 3.3% 및 2.9%를 나타낼 것으로 전망된다. "
                "향후 성장경로에는 불확실성이 잠재해 있다.")
        got = bok.outlook_sentences([para])
        self.assertEqual(len(got), 1)
        self.assertIn("각각 2.6%, 2.1%", got[0])
        self.assertTrue(got[0].startswith("이에 따라"))

    def test_sentences_without_a_prior_forecast_are_skipped(self):
        self.assertEqual(bok.outlook_sentences(["□ 물가상승률은 2%대 후반 수준을 이어갔다."]), [])


LIST = """<ul>
<li><span>보도자료</span><a href="/portal/bbs/P0000559/view.do?nttId=11064191&searchCnd=1">통화정책방향(2026.8.27)</a><span>등록일 2026.08.27</span></li>
<li><span>의결사항</span><a href="/portal/bbs/P0000093/view.do?nttId=11064199&searchCnd=1">2026년도 의안 제27호 - 통화정책방향</a><span>등록일 2026.08.27</span></li>
<li><span>의사록</span><a href="/portal/bbs/B0000245/view.do?nttId=11064775&searchCnd=1">금융통화위원회 의사록(2026년 제16차)(2026.8.27)</a><span>등록일 2026.09.15</span></li>
<li><span>의사록</span><a href="/portal/bbs/B0000245/view.do?nttId=10094518&searchCnd=1">금융통화위원회 의사록(2024년도 제19차)(2024.10.23)</a><span>등록일 2024.11.11</span></li>
</ul>"""


class Listing(unittest.TestCase):
    def test_decision_rows_exclude_resolutions(self):
        rows = bok.decision_rows(bok.parse_search(LIST))
        self.assertEqual([(r["meeting_date"], r["ntt_id"]) for r in rows], [("2026-08-27", "11064191")])

    def test_minutes_rows_both_title_forms(self):
        rows = bok.minutes_rows(bok.parse_search(LIST))
        self.assertEqual([(r["meeting_date"], r["registered_on"], r["session_no"]) for r in rows],
                         [("2026-08-27", "2026-09-15", 16), ("2024-10-23", "2024-11-11", 19)])


class Minutes(unittest.TestCase):
    HEAD = ("1. 일 자 2026년 8월 27일(목) 2. 장 소 금융통화위원회 회의실 3. 출석위원 신 현 송 의 장 (총재) 장 용 성 위 원 황 건 일 위 원 "
            "김 종 화 위 원 이 수 형 위 원 김 진 일 위 원 권 민 수 위 원 (부총재) 4. 결석위원 없 음 5. 참 여 자 김 언 성 감 사")

    def test_attendance_with_syllable_spacing(self):
        got = bok.parse_minutes_attendance(self.HEAD)
        self.assertEqual(got["present"], ["신현송", "장용성", "황건일", "김종화", "이수형", "김진일", "권민수"])
        self.assertEqual(got["absent"], [])

    def test_absentee(self):
        text = self.HEAD.replace("4. 결석위원 없 음", "4. 결석위원 김 진 일 위 원").replace("김 진 일 위 원 권 민 수", "권 민 수")
        got = bok.parse_minutes_attendance(text)
        self.assertEqual(got["absent"], ["김진일"])
        self.assertNotIn("김진일", got["present"])

    def test_no_block_is_an_error(self):
        with self.assertRaises(ValueError):
            bok.parse_minutes_attendance("의사록 본문")


class Calendar(unittest.TestCase):
    def test_schedule_dates(self):
        html = "<table><tr><td>01월 15일(목)</td></tr><tr><td>10월 22일(목)</td></tr><tr><td>11월 26일(목)</td></tr></table>"
        self.assertEqual(bok.parse_schedule(html, 2026), ["2026-01-15", "2026-10-22", "2026-11-26"])

    def test_unpublished_year_is_empty(self):
        self.assertEqual(bok.parse_schedule("<p>등록된 일정이 없습니다</p>", 2027), [])


ROSTER = ("금융통화위원회 위원 의장 신현송 申鉉松 임 기 2026. 04. 21 ~ 2030. 04. 20 선임절차 한국은행 총재(당연직) "
          "위원 장용성 張鏞成 임 기 2023. 04. 21 ~ 2027. 04. 20 선임절차 추천기관 ㆍ 의 추천 "
          "위원 권민수 權珉秀 임 기 2026. 08. 21 ~ 2029. 08. 20 선임절차 한국은행 부총재(당연직) 추천기관: 재정경제부 장관")


class Roster(unittest.TestCase):
    def test_roles_and_terms(self):
        got = bok.parse_roster(f"<p>{ROSTER}</p>")
        self.assertEqual([(m["name"], m["role"]) for m in got], [("신현송", "의장(총재)"), ("장용성", "위원"), ("권민수", "부총재")])
        self.assertEqual(got[2]["term_start"], "2026-08-21")


# --- 경제전망 tables (text as pypdf reads the summary PDFs) ---------------------------------------

AUG_2026 = (
    "<국내 성장률 전망1)> <국내 GDP 전망경로> (%) 2025 2026e) 2027e) GDP 1.1 3.3 [2.6] 2.9 [2.1] •민간소비 1.5 2.1 [2.0] 2.3 [2.1] "
    "•재화수출 3.3 9.7 [4.9] 4.6 [3.3] •건설투자 -9.7 0.2 [0.6] 1.9 [1.5] •설비투자 1.5 6.8 [4.4] 4.7 [2.7] "
    "주: 1) [ ]는 26.5월 전망치 자료: 조사국 "
    "<물가·경상수지·고용 전망1)> 2025 2026e) 2027e) 소비자물가 상승률(%) 2.1 2.7 [2.7] 2.3 [2.3] • 근원물가 상승률(%) 1.9 2.5 [2.4] 2.5 [2.3] "
    "경상수지(억달러) 1,231 4,500 [2,500] 4,300 [1,900] 취업자수 증감(만명) 19 14 [18] 20 [17] 고용률(%) 62.9 62.9 63.0 주: 1) [ ]는 26.5월 전망치"
)
MAY_2026 = (   # the previous round's figures come together after the new ones
    "<국내 성장률 전망1)> <국내 GDP 전망경로> (%) 2025 2026e) 2027e) GDP 1.0 2.6 2.1 [2.0] [1.8] • 민간소비 1.3 2.0 2.1 [1.8] [1.8] "
    "주: 1) [ ]내는 26.2월 전망치 자료: 조사국 "
    "<물가·경상수지·고용 전망1)> <소비자물가 전망경로> 2025 2026e) 2027e) 소비자물가 2.1 2.7 2.3 [2.2] [2.0] • 근원물가 1.9 2.4 2.3 [2.1] [2.0] "
    "경상수지 1,231 2,500 1,900 (억달러) [1,700] [1,400] 취업자수 증감 (만명) 19 18 17 [17] [15] 자료: 조사국"
)
NOV_2025 = (   # four columns, the newest year has no previous figure
    "<국내 성장률 전망1)> (%) 2024 2025e) 2026e) 2027e) GDP 2.0 1.0 1.8 1.9 [0.9] [1.6] • 민간소비 1.1 1.3 1.7 1.7 [1.4] [1.6] 주: 1) [ ]내는 25.8월 전망치"
)


def _row(table, key):
    return next(r for r in table["rows"] if r["id"] == key)


def _pairs(row):
    return [(v["year"], v["value"], v["prior"], v["forecast"]) for v in row["values"]]


class OutlookTable(unittest.TestCase):
    def test_previous_figure_after_each_value(self):
        t = bok.parse_outlook_table(AUG_2026)
        self.assertEqual(t["prior_made_in"], "26.5")
        self.assertEqual(t["years"], [2025, 2026, 2027])
        self.assertEqual(_pairs(_row(t, "gdp")), [(2025, 1.1, None, False), (2026, 3.3, 2.6, True), (2027, 2.9, 2.1, True)])

    def test_previous_figures_grouped_at_the_end(self):
        t = bok.parse_outlook_table(MAY_2026)
        self.assertEqual(_pairs(_row(t, "gdp"))[1:], [(2026, 2.6, 2.0, True), (2027, 2.1, 1.8, True)])
        ca = _row(t, "current_account")                               # the unit sits between the label and the figures
        self.assertEqual((ca["values"][1]["value"], ca["values"][1]["prior"]), (2500.0, 1700.0))

    def test_a_new_year_has_no_previous_figure(self):
        t = bok.parse_outlook_table(NOV_2025)
        self.assertEqual(_pairs(_row(t, "gdp")), [(2024, 2.0, None, False), (2025, 1.0, 0.9, True), (2026, 1.8, 1.6, True), (2027, 1.9, None, True)])

    def test_thousands_and_units(self):
        t = bok.parse_outlook_table(AUG_2026)
        ca = _row(t, "current_account")
        self.assertEqual((ca["unit"], ca["values"][0]["value"], ca["values"][2]["value"]), ("억달러", 1231.0, 4300.0))
        self.assertEqual(_row(t, "employment_change")["values"][1]["prior"], 18.0)

    def test_a_row_whose_counts_do_not_fit_is_dropped_not_guessed(self):
        broken = AUG_2026.replace("GDP 1.1 3.3 [2.6] 2.9 [2.1]", "GDP 1.1 3.3 [2.6]")
        t = bok.parse_outlook_table(broken)
        self.assertNotIn("gdp", [r["id"] for r in t["rows"]])
        self.assertIn("consumption", [r["id"] for r in t["rows"]])

    def test_chart_titles_are_not_rows(self):
        t = bok.parse_outlook_table(AUG_2026)
        self.assertEqual([r["id"] for r in t["rows"]].count("gdp"), 1)

    def test_no_table_is_none(self):
        self.assertIsNone(bok.parse_outlook_table("경제전망 요약 본문"))

    def test_release_rows(self):
        rows = [{"title": "경제전망(2026년 8월)", "registered_on": "2026-08-27", "board": "B0000502", "ntt_id": "1"},
                {"title": "경제전망보고서(2026년 8월)", "registered_on": "2026-08-27", "board": "P0002359", "ntt_id": "2"}]
        self.assertEqual([r["ntt_id"] for r in bok.outlook_release_rows(rows)], ["1"])


if __name__ == "__main__":
    unittest.main()
