"""Segment breakdowns (XBRL) and order backlog (report body). Fixtures copy the
context layouts of 삼성전자 / 한화오션 / NAVER FY2025 and the backlog tables of
삼성중공업, HD한국조선해양, 두산에너빌리티 and 현대건설 3Q 2026."""
import unittest

from dart_kfa.order_backlog import backlog_from_report, parse_backlog_table
from dart_kfa.segments import segment_breakdowns

SCOPE = "ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis"


def instance(contexts, facts):
    """contexts: {id: (start, end, {axis: member})}; facts: [(concept, ctx, value)]"""
    ctx = []
    for cid, (start, end, dims) in contexts.items():
        members = "".join(f'<xbrldi:explicitMember dimension="{a}">{m}</xbrldi:explicitMember>' for a, m in dims.items())
        ctx.append(f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="x">e</xbrli:identifier>'
                   f'<xbrli:segment>{members}</xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>{start}'
                   f'</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>')
    fx = "".join(f'<ifrs-full:{c} contextRef="{cid}" unitRef="KRW" decimals="-6">{v}</ifrs-full:{c}>' for c, cid, v in facts)
    return ('<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
            'xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2023-03-23/ifrs-full">' + "".join(ctx) + fx + "</xbrli:xbrl>").encode()


CUR, PRI = ("2025-01-01", "2025-12-31"), ("2024-01-01", "2024-12-31")
CONS = {SCOPE: "ifrs-full:ConsolidatedMember"}


class Segments(unittest.TestCase):
    def test_samsung_layout_reconciles_to_segment_total(self):
        seg = lambda m: {**CONS, "ifrs-full:SegmentConsolidationItemsAxis": "ifrs-full:OperatingSegmentsMember",  # noqa: E731
                         "ifrs-full:SegmentsAxis": f"entity00126380:{m}MemberOfReportableSegmentsMemberOfDisclosureOfOperatingSegmentsTableOfMember"}
        ctxs = {"dx": (*CUR, seg("DxDivision")), "ds": (*CUR, seg("DsDivision")), "dxp": (*PRI, seg("DxDivision")),
                "tot": (*CUR, {**CONS, "ifrs-full:SegmentConsolidationItemsAxis": "ifrs-full:OperatingSegmentsMember"}),
                "rec": (*CUR, {**CONS, "ifrs-full:SegmentConsolidationItemsAxis": "ifrs-full:MaterialReconcilingItemsMember"}),
                "sep": (*CUR, {SCOPE: "ifrs-full:SeparateMember", "ifrs-full:SegmentsAxis": "entity00126380:DsDivisionMemberOfSegmentsMemberOfX"})}
        facts = [("Revenue", "dx", "187967346000000"), ("Revenue", "ds", "130128162000000"), ("Revenue", "dxp", "174800000000000"),
                 ("OperatingIncomeLoss", "dx", "12852650000000"), ("OperatingIncomeLoss", "ds", "24858075000000"),
                 ("Revenue", "tot", "318095508000000"), ("Revenue", "rec", "-30114556000000"), ("Revenue", "sep", "1")]
        labels = {"DxDivisionMemberOfReportableSegmentsMemberOfDisclosureOfOperatingSegmentsTableOfMember": "DX 부문 [구성요소]"}
        r = segment_breakdowns(instance(ctxs, facts), fs_div="CFS", fiscal_year_end="2025-12-31", labels=labels,
                               face_revenue=287_980_952e6)
        b = r["breakdowns"][0]
        self.assertEqual((b["kind"], b["reconciles"], b["reconciled_against"]), ("segment", True, "segment_total"))
        self.assertEqual([x["label"] for x in b["rows"]], ["DX 부문", "Ds Division"])
        dx = b["rows"][0]
        self.assertAlmostEqual(dx["margin"], 12852650 / 187967346)
        self.assertAlmostEqual(dx["revenue_yoy"], 187967346 / 174800000 - 1)
        self.assertEqual(b["reconciling_items"], {"MaterialReconcilingItemsMember": -30114556e6})

    def test_hanwha_members_on_consolidation_axis_with_elimination(self):
        on = lambda m: (*CUR, {**CONS, "ifrs-full:SegmentConsolidationItemsAxis": m})  # noqa: E731
        ctxs = {"a": on("entity00111704:CommercialvesselsegemntmemberOfSegmentsMemberOfDisclosureofconstructioncontractsTableOfMember"),
                "b": on("entity00111704:PlantOfSegmentsMemberOfDisclosureofsegmentationTableOfMember"),
                "c": on("ifrs-full:AllOtherSegmentsMember"), "e": on("ifrs-full:EliminationOfIntersegmentAmountsMember")}
        facts = [("Revenue", "a", "10523365000000"), ("Revenue", "b", "819373000000"),
                 ("Revenue", "c", "140695000000"), ("Revenue", "e", "-730827000000")]
        r = segment_breakdowns(instance(ctxs, facts), fs_div="CFS", fiscal_year_end="2025-12-31", face_revenue=10_752_606e6)
        b = r["breakdowns"][0]
        self.assertEqual(len(b["rows"]), 3)          # two differently named tables, one family
        self.assertTrue(b["reconciles"])
        self.assertEqual(b["reconciled_against"], "income_statement")

    def test_naver_typo_member_and_separate_members(self):
        p = lambda m, scope="ConsolidatedMember": (*CUR, {SCOPE: f"ifrs-full:{scope}",  # noqa: E731
                                                          "ifrs-full:ProductsAndServicesAxis": f"entity00266961:{m}OfProductsAndServicesMemberOfDisclosureOfOperatingSegmentsTableOfMember"})
        ctxs = {"s": p("SearchPlatformMember"), "e": p("EnterpriseMembr"), "cs": p("CommerceSeperateMember")}
        facts = [("Revenue", "s", "4168935595000"), ("Revenue", "e", "587807491000"), ("Revenue", "cs", "2709458578000")]
        r = segment_breakdowns(instance(ctxs, facts), fs_div="CFS", fiscal_year_end="2025-12-31", face_revenue=4_756_743_086_000)
        b = r["breakdowns"][0]
        self.assertEqual(sorted(x["member"][:8] for x in b["rows"]), ["Enterpri", "SearchPl"])
        self.assertTrue(b["reconciles"])

    def test_unreconciled_breakdown_is_flagged_not_forced(self):
        p = lambda m: (*CUR, {**CONS, "ifrs-full:ProductsAndServicesAxis": f"e:{m}MemberOfProductsTableOfMember"})  # noqa: E731
        r = segment_breakdowns(instance({"a": p("Phone"), "b": p("Memory")}, [("Revenue", "a", "126"), ("Revenue", "b", "104")]),
                               fs_div="CFS", fiscal_year_end="2025-12-31", face_revenue=333)
        self.assertFalse(r["breakdowns"][0]["reconciles"])

    def test_disagreeing_contexts_drop_the_value(self):
        p = lambda m: (*CUR, {**CONS, "ifrs-full:SegmentsAxis": f"e:{m}MemberOfSegTableOfMember"})  # noqa: E731
        ctxs = {"a": p("A"), "a2": p("A"), "b": p("B"), "c": p("C")}
        r = segment_breakdowns(instance(ctxs, [("Revenue", "a", "10"), ("Revenue", "a2", "11"), ("Revenue", "b", "5"),
                                               ("Revenue", "c", "6")]), fs_div="CFS", fiscal_year_end="2025-12-31")
        self.assertEqual(sorted(x["member"][:1] for x in r["breakdowns"][0]["rows"]), ["B", "C"])


def table(rows, before=""):
    body = "".join("<TR>" + "".join(f"<TD>{c}</TD>" for c in r) + "</TR>" for r in rows)
    return f"<P>{before}</P><TABLE>{body}</TABLE>"


SHI = table([["품목", "수주일자", "납기", "수주총액", "기납품액", "수주잔고"], ["금액", "금액", "금액"],
             ["조선해양", "~ 2026.09.30", "-", "587,324", "238,300", "349,024"],
             ["토건", "~ 2026.09.30", "-", "15,810", "14,027", "1,783"], ["합 계", "603,134", "252,327", "350,807"]],
            "다. 수주상황 (단위 : 억원)")
HDKSOE = table([["품 목", "수 주 일 자", "납기", "기초계약잔액", "신규계약액", "기납품액", "수주잔고"],
                ["수량", "금액", "수량", "금액", "수량", "금액", "수량", "금액"],
                ["조 선", "'26.06.30 까지", "-", "-", "70,801,620", "-", "28,488,584", "-", "14,147,343", "-", "85,142,861"],
                ["합 계", "-", "82,236,880", "-", "33,642,412", "-", "17,070,572", "-", "98,808,720"]],
               "나. 수주상황 (단위 : 백만원)")
DOOSAN = table([["구분", "주요 계약명", "기초", "증감", "매출계상액", "기말"],
                ["두산에너빌리티", "체코 Dukovany 5,6호기 NSSS 외", "233,931", "92,164", "57,203", "268,892"],
                ["두산밥캣", "연장보증 외", "2,287", "399", "391", "2,295"],
                ["합계", "236,218", "92,563", "57,594", "271,187"]],
               "다. 당분기말 현재 주요사업부문별 수주상황 (단위 : 억원)")


class Backlog(unittest.TestCase):
    def test_contract_total_layout(self):
        r = backlog_from_report(SHI, receipt="x", period_end="2026-09-30")
        self.assertEqual((r["status"], r["backlog"], r["delivered"]), ("parsed", 350_807e8, 252_327e8))
        self.assertTrue(r["roll_forward_ok"])

    def test_quantity_amount_pairs(self):
        r = backlog_from_report(HDKSOE, receipt="x", period_end="2026-06-30")
        self.assertEqual((r["opening"], r["new_orders"], r["backlog"]), (82_236_880e6, 33_642_412e6, 98_808_720e6))
        self.assertEqual(r["items"][0]["backlog"], 85_142_861e6)

    def test_opening_change_recognised_closing(self):
        r = backlog_from_report(DOOSAN, receipt="x", period_end="2026-09-30")
        self.assertEqual((r["columns"], r["backlog"]), (["opening", "new", "delivered", "backlog"], 271_187e8))

    def test_per_company_tables_are_summed(self):
        cols = ["구분", "공사명", "발주처", "공사착공일", "완공예정일", "기본도급액", "완성공사액", "계약잔액"]
        doc = (table([cols, ["국내", "디에이치 클래스트", "반포", "2024-03-29", "2027-11-28", "4,044,805", "1,959,981", "2,084,824"],
                      ["국내 / 해외 합계", "161,526,084", "88,063,807", "73,462,277"]], "다. 수주상황 1) 현대건설 (단위 : 백만원)")
               + table([cols, ["국내", "샤힌", "S-Oil㈜", "2023-01-02", "2026-12-31", "1,731,060", "1,686,317", "44,743"],
                        ["국내 / 해외 합계", "55,911,142", "30,073,390", "25,837,752"]], "2) 현대엔지니어링 (단위 : 백만원)")
               + "<P>5. 위험관리 및 파생거래</P>"
               + table([cols, ["x", "y", "z", "2020-01-01", "2021-01-01", "10", "4", "6"], ["합계", "10", "4", "6"]], "(단위 : 백만원) 수주"))
        r = backlog_from_report(doc, receipt="x", period_end="2026-09-30")
        self.assertEqual(r["backlog"], (73_462_277 + 25_837_752) * 1e6)
        self.assertEqual([p["part"] for p in r["parts"]], ["현대건설", "현대엔지니어링"])

    def test_balance_column_without_roll_forward_is_ignored(self):
        doc = table([["특수관계자", "기초", "기말 잔액"], ["삼성디스플레이", "100", "120"], ["합계", "100", "120"]],
                    "매출 및 수주상황 (단위 : 백만원)")
        self.assertEqual(backlog_from_report(doc, receipt="x", period_end="2025-12-31")["status"], "not_parsed")

    def test_no_section(self):
        self.assertEqual(backlog_from_report("<P>예금</P>", receipt="x", period_end="2025-12-31")["status"], "no_section")

    def test_unit_required(self):
        t = {"rows": [["품목", "수주총액", "기납품액", "수주잔고"], ["A", "10", "4", "6"]], "before": "수주상황"}
        self.assertIsNone(parse_backlog_table(t))


if __name__ == "__main__":
    unittest.main()
