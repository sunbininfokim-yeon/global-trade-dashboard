"""Regulatory capital tables. The fragments copy the table layouts (and the
numbers) of real FY2025 / 2026 reports: DB생명 (20260327000191, 반기
20260814001853), DB손해보험 (정정 전/후), KB금융, 키움증권, 현대카드, 현대캐피탈."""
import unittest

from dart_kfa.regulatory_capital import extract, regulatory_from_reports, regulatory_kind


def table(rows, before=""):
    body = "".join("<TR>" + "".join(f"<TD>{c}</TD>" for c in r) + "</TR>" for r in rows)
    return f"<P>{before}</P><TABLE>{body}</TABLE>"


DBL_FY = (
    table([["(단위: 백만원, %)"]], "5. 재무건전성 등 기타 참고사항 가. 지급여력비율")
    + table([["구 분", "제 37 기", "제 36 기", "제 35기"],
             ["가용자본(지급여력금액) (A)", "2,684,258", "2,195,627", "2,680,173"],
             ["요구자본(지급여력기준금액) (B)", "998,874", "1,052,279", "873,799"],
             ["지급여력비율 (A/B)", "268.7", "208.7", "306.7"]], "(단위: 백만원, %)")
    + table([["주1) 지급여력비율 = 지급여력(A)/지급여력기준(B) ×100주2) 연결 재무제표 기준임"
              "주3) 제37(당)기말 수치는 경과조치 후이며, 제37(당)기 경과조치 전 지급여력비율은 186.2%"
              "(지급여력 2,684,258백만원, 지급여력기준 1,441,852백만원)입니다."]])
)
DBL_H1 = (
    table([["구 분", "제 38기 2분기", "제 37 기", "제 36 기"],
           ["가용자본(지급여력금액) (A)", "3,300,462", "2,684,258", "2,195,627"],
           ["요구자본(지급여력기준금액) (B)", "1,082,628", "998,874", "1,052,279"],
           ["지급여력비율 (A/B)", "304.9", "268.7", "208.7"]], "가. 지급여력비율 (단위: 백만원, %)")
    + table([["주2) 연결 재무제표 기준임 주3) 경과조치 전 지급여력비율은 203.1%(지급여력 3,300,462백만원, 지급여력기준 1,624,801백만원)"]])
)


class KICS(unittest.TestCase):
    def test_db_life_fy2025(self):
        r = extract(DBL_FY, "kics", period_end="2025-12-31", receipt="20260327000191")
        p = r["points"][0]
        self.assertEqual((p["period_end"], p["ratio"], p["available"], p["required"]),
                         ("2025-12-31", 2.687, 2_684_258e6, 998_874e6))
        self.assertTrue(p["ratio_matches_a_over_b"])
        self.assertEqual([x["period_end"] for x in r["points"]], ["2025-12-31", "2024-12-31", "2023-12-31"])
        self.assertEqual(r["scope"], "CFS")
        self.assertAlmostEqual(r["pre_transitional"]["ratio"], 1.862)
        self.assertEqual(r["pre_transitional"]["required"], 1_441_852e6)
        self.assertEqual(r["thresholds"][0]["ratio"], 1.0)

    def test_interim_contributes_only_its_own_date(self):
        reports = [{"kind": "H1", "period_end": "2026-06-30", "receipt": "20260814001853", "doc": DBL_H1},
                   {"kind": "FY", "period_end": "2025-12-31", "receipt": "20260327000191", "doc": DBL_FY}]
        r = regulatory_from_reports(reports, kind="kics")
        self.assertEqual([(p["period_end"], p["ratio"], p["report"]) for p in r["series"]],
                         [("2023-12-31", 3.067, "FY"), ("2024-12-31", 2.087, "FY"),
                          ("2025-12-31", 2.687, "FY"), ("2026-06-30", 3.049, "H1")])
        self.assertAlmostEqual(r["pre_transitional"]["ratio"], 2.031)   # latest report's footnote

    def test_correction_before_table_is_skipped(self):
        rows = lambda a, b, ratio: [["구분", "제59(당)기 말", "제58(전)기 말", "제57(전전)기 말"],
                                    ["지급여력금액(A)", a, "19,097,308", "19,575,206"],
                                    ["지급여력기준금액(B)", b, "9,402,579", "8,396,170"],
                                    ["지급여력비율(A/B)", ratio, "203.1", "233.1"]]
        doc = (table(rows("21,555,174", "9,895,449", "217.8"), "주5) 정정 전 (단위 : 백만원, %)")
               + table(rows("21,552,235", "9,876,353", "218.2"), "주6) 정정 후 (단위 : 백만원, %)"))
        self.assertEqual(extract(doc, "kics", period_end="2025-12-31", receipt="x")["points"][0]["ratio"], 2.182)


class Others(unittest.TestCase):
    def test_kb_basel(self):
        doc = table([["구분", "2025년", "2024년", "2023년"], ["자기자본(a=b+e)", "57,824", "56,849", "53,744"],
                     ["기본자본(b=c+d)", "54,292", "52,477", "49,391"], ["보통주자본(c)", "49,353", "46,794", "43,664"],
                     ["위험가중자산(f)", "356,996", "345,981", "321,319"], ["총자본비율(a/f)", "16.20", "16.43", "16.73"],
                     ["기본자본비율(b/f)", "15.21", "15.17", "15.37"], ["보통주자본비율(c/f)", "13.82", "13.53", "13.59"]],
                    "[KB금융지주] 1) BIS기준 자기자본비율 (단위: 십억원, %, %p)")
        p = extract(doc, "basel", period_end="2025-12-31", receipt="x")["points"][0]
        self.assertEqual((p["cet1_ratio"], p["tier1_ratio"], p["total_ratio"]), (0.1382, 0.1521, 0.162))
        self.assertEqual((p["rwa"], p["cet1"], p["total_capital"]), (356_996e9, 49_353e9, 57_824e9))

    def test_kiwoom_ncr(self):
        doc = table([["구 분", "제27기", "제26기", "제25기"], ["영업용순자본(A)", "4,676,809", "3,511,468", "3,138,396"],
                     ["총 위 험 액(B)", "2,640,701", "1,809,904", "1,475,174"], ["잉여자본(A-B)", "2,036,108", "1,701,563", "1,663,222"],
                     ["필요유지자기자본(C)", "131,425", "130,725", "130,725"], ["순자본비율[(A-B)/C]", "1,549.25%", "1,301.64%", "1,272.31%"]],
                    "(1) 순자본비율 (단위 : 백만원)")
        p = extract(doc, "ncr", period_end="2025-12-31", receipt="x")["points"][0]
        self.assertAlmostEqual(p["ratio"], 15.4925)
        self.assertEqual(p["total_risk"], 2_640_701e6)

    def test_card_label_in_second_cell(self):
        doc = table([["구분", "제31기", "제30기", "제29기", "비고"], ["자본의 적정성", "조정자기자본비율", "16.79", "15.71", "16.45"],
                     ["단순자기자본비율", "12.64", "11.74", "12.34", "* 자기자본 ÷ 총자산 ×100"]], "[자본의 적정성 및 재무건전성 관련 지표]")
        r = extract(doc, "credit_finance", period_end="2025-12-31", receipt="x", subtype="card")
        self.assertEqual([p["ratio"] for p in r["points"]], [0.1679, 0.1571, 0.1645])
        self.assertEqual(r["thresholds"][0]["ratio"], 0.08)

    def test_change_column_is_not_a_year(self):
        doc = table([["구분", "제33기", "제32기", "제32기 대비 증감"], ["조정총자산(A)", "40,654,572", "39,219,650", "1,434,922"],
                     ["조정자기자본(B)", "6,599,110", "6,081,328", "517,782"], ["조정자기자본비율(B/A)(주)", "16.23", "15.51", "0.72"]],
                    "(단위 : 백만원)")
        r = extract(doc, "credit_finance", period_end="2025-12-31", receipt="x")
        self.assertEqual([(p["period_end"], p["ratio"]) for p in r["points"]], [("2025-12-31", 0.1623), ("2024-12-31", 0.1551)])
        self.assertEqual(r["points"][0]["adjusted_equity"], 6_599_110e6)
        self.assertEqual(r["thresholds"][0]["ratio"], 0.07)

    def test_notes_layout_with_fraction_ratios(self):
        # 신한·KB 감사보고서 주석 "자기자본비율에 대한 공시": labels spill over two cells, ratios as fractions
        doc = table([["", "", "", "자본위험"], ["총자기자본", "56,260,597"], ["총자기자본", "기본자본", "53,006,305"],
                     ["기본자본", "보통주자본", "47,115,338"], ["위험가중자산", "352,907,638"], ["총자본비율", "0.1594"],
                     ["총자본비율", "기본자본비율", "0.1502"], ["기본자본비율", "보통주자본비율", "0.1335"]],
                    "자기자본비율에 대한 공시 당기 (단위 : 백만원)")
        p = extract(doc, "basel", period_end="2025-12-31", receipt="x")["points"][0]
        self.assertEqual((p["total_ratio"], p["tier1_ratio"], p["cet1_ratio"]), (0.1594, 0.1502, 0.1335))
        self.assertEqual((p["tier1"], p["cet1"], p["rwa"]), (53_006_305e6, 47_115_338e6, 352_907_638e6))

    def test_history_table_is_not_the_current_period(self):
        # 신한 반기보고서 "관련 지표의 변동현황": first column is 2014
        doc = table([["관련지표", "14년 말", "15년 말"], ["총자본비율", "13.05%", "13.39%"],
                     ["기본자본비율", "11.15%", "11.41%"], ["보통주자본비율", "10.40%", "10.77%"]], "(단위: 십억원)")
        self.assertIsNone(extract(doc, "basel", period_end="2026-06-30", receipt="x"))

    def test_no_table_no_numbers(self):
        self.assertIsNone(extract("<P>지급여력비율은 양호합니다.</P>", "kics", period_end="2025-12-31", receipt="x"))

    def test_kind_routing(self):
        self.assertEqual(regulatory_kind("insurance", "DB생명보험"), ("kics", None))
        self.assertEqual(regulatory_kind("bank", "(주)KB금융지주"), ("basel", None))
        self.assertEqual(regulatory_kind(None, "키움증권"), ("ncr", None))
        self.assertEqual(regulatory_kind(None, "현대카드"), ("credit_finance", "card"))
        self.assertEqual(regulatory_kind("npl_asset_management", "연합자산관리"), (None, None))


if __name__ == "__main__":
    unittest.main()
