"""Minutes and opinion summaries: BOK (HWP paragraphs) and BOJ (PDF text)."""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor.cb_collect import boj, bok  # noqa: E402
from macro_monitor.cb_collect.hwp import paragraphs_from_body  # noqa: E402


def _record(tag: int, payload: bytes) -> bytes:
    return struct.pack("<I", (tag & 0x3FF) | (0 << 10) | (len(payload) << 20)) + payload


class HwpRecords(unittest.TestCase):
    def test_paragraph_text_with_controls(self):
        # a normal paragraph, one with a 16-byte extended control (a table anchor) inside, a tab, and a non-text record
        p1 = "일부 위원은 질의하였음.".encode("utf-16-le") + b"\r\x00"
        ext = struct.pack("<H", 11) + b"\x00" * 14                      # code 11 + 7 more code units
        p2 = "가".encode("utf-16-le") + ext + "나\t다".encode("utf-16-le")
        body = _record(67, p1) + _record(66, b"\x00\x00") + _record(67, p2)
        self.assertEqual(paragraphs_from_body(body), ["일부 위원은 질의하였음.", "가나 다"])

    def test_long_record_uses_the_32_bit_size(self):
        text = ("가" * 3000).encode("utf-16-le")
        body = struct.pack("<I", 67 | (0xFFF << 20)) + struct.pack("<I", len(text)) + text
        self.assertEqual(paragraphs_from_body(body), ["가" * 3000])


# --- BOK minutes -----------------------------------------------------------------------------

PARAS = [
    "2026년도 제16차", "금융통화위원회(정기) 의사록",
    "3. 출석위원 ", "신 현 송  의 장 (총재) ", "장 용 성  위 원", "황 건 일  위 원", "권 민 수  위 원 (부총재)",
    "4. 결석위원", "없    음", "5. 참 여 자", "김 언 성  감    사", "6. 회의경과",
    "〈의안 제27호 ― 통화정책방향〉",
    "(1) 전일 개최된 동향보고회의에서는 조사국장이 보고하였음.",
    "(3) 위원 토의내용",
    "(가) 경제전망(2026.8월)",
    "일부 위원은 향후 전망과 관련하여 비관 시나리오의 영향을 질의하였음.",
    "이에 대해 관련 부서는 직접적인 영향은 크지 않을 것으로 답변하였음.",
    "이어서 동 위원은 건설투자 회복의 이유를 질의하였음.",
    "다른 일부 위원은 8월 물가가 높아질 것으로 언급하였음.",
    "(다) ｢통화정책방향｣에 관한 토론",
    "또 다른 일부 위원은 중립금리 추정의 불확실성을 고려해야 한다는 의견을 나타내었음.",
    "(4) 한국은행 기준금리 결정에 관한 위원별 의견 개진",
    "당일 개최된 본회의에서는 위원별 의견 개진이 있었음.",
    "다수의 위원들은 국내외 금융·경제 상황을 종합적으로 고려할 때 기준금리를 현 2.75% 수준에서 3.00%로 인상하는 것이 바람직하다는 견해를 나타낸 반면 일부 위원은 기준금리를 현 2.75% 수준에서 동결할 것을 주장하였음.",
    "일부 위원은 금번 회의에서 현재 2.75%인 기준금리를 3.00%로 인상하는 것이 적절하다는 의견을 나타내었음.",
    "세계 경제는 완만한 성장세를 이어갈 것으로 전망됩니다.",
    "이러한 여건을 종합해 볼 때 3.00%로 인상하는 것이 바람직하다는 의견입니다.",
    "또 다른 일부 위원은 금번 회의에서 기준금리를 동결하여 2.75% 수준을 유지하는 것이 적절하다는 의견을 표명하였음.",
    "세계경제는 불확실성이 지속되고 있는 모습입니다.",
    "(5) 토의결론",
    "위원들은 다수결로 기준금리를 2.75%에서 3.00%로 0.25%p 인상하기로 결정하였음.",
    "(6) 심의결과",
    "앞서의 토의결과를 반영하여 위원들은 다수 의견이 반영된 구체적인 의결문안을 작성하였음.",
    "의결문 작성·가결",
    "(다만, 황건일 위원은 한국은행 기준금리를 0.25%p 인상하는 것에 대해 명백히 반대의사를 표시하고 현 수준에서 동결할 것을 주장하였음.)",
    "의결사항",
    "<의안 제28호– 「지급결제제도 운영·관리규정」 개정(안)>",
    "일부 위원은 외국인의 범위에 대해 질의하였음.",
]


class BokMinutes(unittest.TestCase):
    def setUp(self):
        self.r = bok.parse_minutes_hwp(PARAS, prior_rate=2.75, rate=3.0)

    def test_attendance(self):
        self.assertEqual(self.r["present"], ["신현송", "장용성", "황건일", "권민수"])
        self.assertEqual(self.r["absent"], [])

    def test_discussion_blocks_carry_their_followups(self):
        subs = self.r["discussion"]["subsections"]
        self.assertEqual([s["title"][:4] for s in subs], ["(가) ", "(다) "])
        first = subs[0]["blocks"][0]
        self.assertEqual((first["quantifier"], first["group"]), ("일부 위원", "some"))
        self.assertEqual(len(first["followups"]), 2)               # the staff reply and the member's follow-up
        self.assertEqual(subs[0]["blocks"][1]["quantifier"], "다른 일부 위원")
        self.assertEqual(subs[1]["blocks"][0]["quantifier"], "또 다른 일부 위원")

    def test_other_agenda_items_are_not_read(self):
        text = " ".join(b["text"] for s in self.r["discussion"]["subsections"] for b in s["blocks"])
        self.assertNotIn("외국인", text)

    def test_distribution_sentence_and_member_stances(self):
        o = self.r["opinions"]
        self.assertTrue(o["distribution"].startswith("다수의 위원들은"))
        self.assertEqual([(m["stance"], m["target_rate_pct"]) for m in o["members"]], [("raise", 3.0), ("hold", 2.75)])
        self.assertEqual(len(o["members"][0]["statement"]), 2)
        self.assertIn("2.75%에서 3.00%로", o["conclusion"])

    def test_vote_names_the_dissenter_and_derives_the_for_count(self):
        v = self.r["vote"]
        self.assertEqual(v["against"], [{"name": "황건일", "preferred_rate_pct": 2.75, "direction": "hold"}])
        self.assertEqual(v["favor_count"], 3)
        self.assertEqual(v["source"], "minutes")
        self.assertFalse(v["unanimous"])


class MinutesVote(unittest.TestCase):
    def vote(self, para, prior=3.0, rate=3.0, present=("a", "b", "c", "d", "e", "f", "g")):
        return bok.parse_minutes_vote(["의결문 작성·가결", para], present=list(present), prior_rate=prior, rate=rate)

    def test_unanimous(self):
        v = bok.parse_minutes_vote(["앞서의 토의결과를 반영하여 위원 전원 찬성으로 가결하였음."], present=["a", "b"], prior_rate=3.0, rate=3.0)
        self.assertTrue(v["unanimous"])
        self.assertEqual((v["favor_count"], v["against"]), (2, []))

    def test_two_dissenters_who_wanted_a_hold(self):
        v = self.vote("(다만, 장용성 위원과 유상대 위원은 한국은행 기준금리를 0.25%포인트 인하하는 것에 대해 명백히 반대의사를 표시하고 현 수준에서 동결할 것을 주장하였음.)", prior=3.25, rate=3.0)
        self.assertEqual([a["name"] for a in v["against"]], ["장용성", "유상대"])
        self.assertEqual({(a["direction"], a["preferred_rate_pct"]) for a in v["against"]}, {("hold", 3.25)})

    def test_dissent_for_a_cut_is_priced_from_the_current_rate(self):
        v = self.vote("(다만, 신성환 위원은 한국은행 기준금리를 현 수준에서 동결하는 것에 대해 명백히 반대의사를 표시하고 0.25%p 인하할 것을 주장하였음.)", prior=3.0, rate=3.0)
        self.assertEqual((v["against"][0]["direction"], v["against"][0]["preferred_rate_pct"]), ("lower", 2.75))

    def test_no_recognisable_result_is_none(self):
        self.assertIsNone(bok.parse_minutes_vote(["의결사항"], present=["a"], prior_rate=3.0, rate=3.0))

    def test_missing_agenda_item_is_an_error(self):
        with self.assertRaises(ValueError):
            bok.parse_minutes_hwp(["3. 출석위원", "6. 회의경과"], prior_rate=3.0, rate=3.0)


class Quantifiers(unittest.TestCase):
    def test_korean(self):
        self.assertEqual(bok.quantifier_of("또 다른 일부 위원은 금번 회의에서 인상하는 것이 적절하다는 의견을 나타내었음."), ("또 다른 일부 위원", "some"))
        self.assertEqual(bok.quantifier_of("한편 일부 위원은 반도체 가격이 급등했다고 언급하였음.")[1], "some")
        self.assertEqual(bok.quantifier_of("다수의 위원들은 인상이 바람직하다는 견해를 나타내었음.")[1], "many")
        self.assertEqual(bok.quantifier_of("모든 위원들은 동결이 바람직하다는 견해를 나타내었음.")[1], "all")
        self.assertIsNone(bok.quantifier_of("동 위원은 추가 질의하였음."))
        self.assertIsNone(bok.quantifier_of("관련 부서는 답변하였음."))

    def test_english(self):
        self.assertEqual(boj.boj_quantifier("Some members said that risks were skewed to the upside."), ("Some members", "some"))
        self.assertEqual(boj.boj_quantifier("Based on this recognition, one member expressed the view that it was appropriate.")[1], "few")
        self.assertEqual(boj.boj_quantifier("Most members shared the recognition that the economy was recovering.")[1], "most")
        self.assertEqual(boj.boj_quantifier("Members discussed monetary policy.")[1], "unqualified")
        self.assertIsNone(boj.boj_quantifier("The staff explained that prices had risen."))
        self.assertIsNone(boj.boj_quantifier("These members continued that the risk had decreased."))


# --- BOJ minutes / opinions ------------------------------------------------------------------

MINUTES = """A Monetary Policy Meeting was held in Tokyo.
I. Summary of Staff Reports on Economic and Financial Developments
The staff explained that the economy had recovered.
II. Summary of Discussions by the Policy Board on Economic and Financial Developments
Members discussed developments. Most members shared the recognition that the economy was recovering. These members added that consumption was firm. One member said that AI demand had spread.
III. Staff Reports on a Plan
The staff first explained the plan.
IV. Summary of Discussions on Monetary Policy
Members exchanged views. Many members said that a hike was appropriate. Some members noted risks. Based on this, one member expressed the view that it was appropriate to adjust the rate.
V. Remarks by Government Representatives
The government representatives said things.
VI. Votes
A. Vote on the Guideline for Money Market Operations Based on the above discussions, the chairman put a proposal to a vote. The Policy Board decided the proposal by a majority vote. The Bank will encourage the rate to remain at around 1.0 percent. Votes for the proposal: HIMINO Ryozo, UCHIDA Shinichi, and MASU Kazuyuki. Votes against the proposal: ASADA Toichiro. Absent: UEDA Kazuo. Asada Toichiro dissented, considering that risks were on the downside.
D. Vote on the Plan for Outright Purchases of JGBs To reflect the majority view, the chairman formulated a proposal. Tamura Naoki, however, proposed a larger reduction. Tamura Naoki's proposal was defeated by a majority vote. Votes for the proposal: TAMURA Naoki. Votes against the proposal: HIMINO Ryozo, UCHIDA Shinichi, MASU Kazuyuki, and ASADA Toichiro. Absent: UEDA Kazuo. The chairman's proposal was decided by a majority vote. Votes for the proposal: HIMINO Ryozo, UCHIDA Shinichi, MASU Kazuyuki, and ASADA Toichiro. Votes against the proposal: TAMURA Naoki. Absent: UEDA Kazuo.
VII. Approval of the Minutes
The Policy Board approved unanimously the minutes.
"""


class BojMinutes(unittest.TestCase):
    def setUp(self):
        self.m = boj.parse_minutes(MINUTES)

    def test_blocks_start_at_a_member_count_and_absorb_the_continuation(self):
        econ = self.m["economy"]
        self.assertEqual([(b["quantifier"], b["group"]) for b in econ], [("Members", "unqualified"), ("Most members", "most"), ("One member", "few")])
        self.assertIn("These members added that consumption was firm.", econ[1]["text"])
        pol = self.m["policy"]
        self.assertEqual([b["group"] for b in pol], ["unqualified", "many", "some", "few"])
        self.assertTrue(pol[3]["text"].startswith("Based on this, one member"))

    def test_staff_report_parts_are_not_read_as_views(self):
        text = " ".join(b["text"] for b in self.m["economy"] + self.m["policy"])
        self.assertNotIn("The staff explained", text)

    def test_every_vote_with_names(self):
        votes = self.m["votes"]
        self.assertEqual([v["item"] for v in votes], ["A", "D"])
        a = votes[0]
        self.assertEqual(a["decision"], "majority")
        self.assertEqual(a["ballots"][0]["against"], ["Asada Toichiro"])
        self.assertEqual(a["ballots"][0]["absent"], ["Ueda Kazuo"])
        self.assertTrue(a["notes"][0].startswith("Asada Toichiro dissented"))

    def test_an_item_with_two_ballots_keeps_both(self):
        d = self.m["votes"][1]
        self.assertEqual(len(d["ballots"]), 2)
        self.assertIn("Tamura Naoki's proposal", d["ballots"][0]["label"])
        self.assertEqual(d["ballots"][0]["for"], ["Tamura Naoki"])
        self.assertEqual(d["ballots"][1]["against"], ["Tamura Naoki"])

    def test_staff_summary_and_government_remarks_are_read_as_headed_text(self):
        text = MINUTES.replace("I. Summary of Staff Reports on Economic and Financial Developments\n",
                               "I. Summary of Staff Reports on Economic and Financial Developments\nA. Market Operations\n")
        m = boj.parse_minutes(text)
        self.assertEqual([x["heading"] for x in m["staff"]], ["A. Market Operations"])
        self.assertIn("The staff explained that the economy had recovered.", m["staff"][0]["text"])
        self.assertEqual(m["government"], [{"heading": "", "text": "The government representatives said things."}])

    def test_parts_are_found_by_title_when_the_numbering_shifts(self):
        shifted = (MINUTES.replace("III. Staff Reports on a Plan\nThe staff first explained the plan.\n", "")
                   .replace("IV. Summary of Discussions on Monetary Policy", "III. Summary of Discussions on Monetary Policy")
                   .replace("V. Remarks by Government Representatives", "IV. Remarks by Government Representatives")
                   .replace("VI. Votes", "V. Votes"))
        m = boj.parse_minutes(shifted)
        self.assertEqual(len(m["policy"]), 4)
        self.assertEqual([v["item"] for v in m["votes"]], ["A", "D"])

    def test_missing_parts_are_an_error(self):
        with self.assertRaises(ValueError):
            boj.parse_minutes("I. Summary of Staff Reports\nSomething.")


OPINIONS = """August 10, 2026
Summary of Opinions at the Monetary Policy Meeting
I. Opinions on Economic and Financial Developments
Economic Developments
⚫
Japan's economy has recovered moderately, although some weakness
has been seen in part.
⚫  Concerns over an economic slowdown have subsided.
Prices
⚫  Underlying CPI inflation is likely to increase gradually.
II. Opinions on Monetary Policy
⚫  The short-term real interest rate has been negative.
⚫
It is necessary to take into account financing conditions.
III. Opinions from Government Representatives
Ministry of Finance
⚫  The government will mobilize its full capabilities.
Cabinet Office
⚫  The government will closely monitor the impact.
"""


class BojOpinions(unittest.TestCase):
    def test_sections_subheadings_and_bullets(self):
        o = boj.parse_opinions(OPINIONS)
        self.assertEqual([s["heading"] for s in o],
                         ["Opinions on Economic and Financial Developments", "Opinions on Monetary Policy", "Opinions from Government Representatives"])
        econ = o[0]["subsections"]
        self.assertEqual([(s["heading"], len(s["bullets"])) for s in econ], [("Economic Developments", 2), ("Prices", 1)])
        self.assertEqual(econ[0]["bullets"][0], "Japan's economy has recovered moderately, although some weakness has been seen in part.")
        self.assertEqual([(s["heading"], len(s["bullets"])) for s in o[1]["subsections"]], [("", 2)])
        self.assertEqual([s["heading"] for s in o[2]["subsections"]], ["Ministry of Finance", "Cabinet Office"])

    def test_document_index(self):
        html = """<table><tr><td>Aug. 10, 2026</td><td><a href="/en/mopo/mpmsche_minu/opinion_2026/opi260731.pdf">Meeting on July 30 and 31, 2026 [PDF 175KB]</a></td></tr>
        <tr><td>Feb. 2, 2026</td><td><a href="/en/mopo/mpmsche_minu/opinion_2026/opi260123.htm">Meeting on January 22 and 23, 2026</a></td></tr></table>"""
        rows = boj.parse_documents_index(html)
        self.assertEqual([(r["meeting_date"], r["released_on"], r["format"]) for r in rows],
                         [("2026-07-31", "2026-08-10", "pdf"), ("2026-01-23", "2026-02-02", "htm")])


if __name__ == "__main__":
    unittest.main()
