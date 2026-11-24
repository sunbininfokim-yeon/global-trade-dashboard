"""Investor metrics. Statement rows copy 삼성전자 FY2025 (20260310002820) where
noted; the dilution fragments copy the layouts of 이연제약 3Q 2026
(20261113001586), 이마트 3Q 2026, 신한지주 H1 2026 and 삼성전자 FY2025."""
import unittest

from dart_kfa.investor_metrics import (
    annual_series, dilution_from_report, dividends_from_alot, growth, investor_metrics, lease_from_instance,
    piotroski, returns, shareholder_returns, treasury_from_tesstk,
)


def row(sj, aid, th, fr=None, bf=None, nm="", rc="R"):
    return {"sj_div": sj, "account_id": aid, "account_nm": nm, "rcept_no": rc,
            "thstrm_amount": th, "frmtrm_amount": fr, "bfefrmtrm_amount": bf}


def statements(y, rev, op, ni, ta, eq, extra=()):
    """Three years of a toy filer in one FY report (values: current, prior, prior2)."""
    return [
        row("IS", "ifrs-full_Revenue", *rev, rc=str(y)), row("IS", "dart_OperatingIncomeLoss", *op, rc=str(y)),
        row("IS", "ifrs-full_ProfitLoss", *ni, rc=str(y)), row("BS", "ifrs-full_Assets", *ta, rc=str(y)),
        row("BS", "ifrs-full_Equity", *eq, rc=str(y)), *extra]


class Series(unittest.TestCase):
    def test_newest_report_wins_and_five_years(self):
        fy25 = statements(2025, ("130", "110", "100"), ("13", "11", "10"), ("9", "8", "7"), ("500", "480", "450"),
                          ("300", "280", "260"))
        fy23 = statements(2023, ("99", "90", "80"), ("9", "8", "7"), ("6", "5", "4"), ("449", "430", "400"),
                          ("259", "240", "220"))
        s = annual_series({2025: fy25, 2023: fy23})
        self.assertEqual(s["years"], [2021, 2022, 2023, 2024, 2025])
        self.assertEqual(s["values"][2023]["revenue"], 100.0)      # FY2025 report's 전전기, not FY2023's 당기 (99)
        self.assertEqual(s["values"][2021]["revenue"], 80.0)
        self.assertEqual(s["source"][2023]["revenue"]["report_year"], 2025)

    def test_cis_only_filer_and_name_fallback(self):
        rows = [row("CIS", "ifrs-full_Revenue", "10", "8"),
                row("CF", "-표준계정코드 미사용-", "3", "2", nm="리스부채의 상환")]
        v = annual_series({2025: rows})["values"]
        self.assertEqual((v[2025]["revenue"], v[2025]["lease_repayment"]), (10.0, 3.0))


class Growth(unittest.TestCase):
    def setUp(self):
        fy25 = statements(2025, ("133.1", "121", "110"), ("10", "-5", "4"), ("9", "8", "7"),
                          ("500", "480", "450"), ("300", "280", "260"))
        fy23 = statements(2023, ("110", "100", "90"), ("4", "3", "2"), ("7", "6", "5"),
                          ("450", "430", "400"), ("260", "240", "220"))
        self.s = annual_series({2025: fy25, 2023: fy23})

    def test_yoy_cagr_and_turnaround(self):
        g = growth(self.s, 2025, financial=False)
        self.assertAlmostEqual(g["revenue"]["yoy"]["value"], 0.1)
        self.assertAlmostEqual(g["revenue"]["cagr_3y"]["value"], 0.1)       # 100 -> 133.1 over three years
        self.assertIsNone(g["op"]["yoy"]["value"])
        self.assertEqual(g["op"]["yoy"]["reason"], "turnaround")
        self.assertEqual(g["parent_income"]["yoy"]["current"], 9.0)         # no parent line -> total profit

    def test_financial_skips_sales(self):
        g = growth(self.s, 2025, financial=True)
        self.assertEqual(g["revenue"]["yoy"]["reason"], "not_applicable:financial")
        self.assertIsNotNone(g["parent_income"]["yoy"]["value"])


class Returns(unittest.TestCase):
    def test_roic_and_dupont(self):
        extra = [row("IS", "ifrs-full_ProfitLossBeforeTax", "20", "18"),
                 row("IS", "ifrs-full_IncomeTaxExpenseContinuingOperations", "5", "4.5"),
                 row("BS", "ifrs-full_LongtermBorrowings", "100", "100"),
                 row("BS", "ifrs-full_CashAndCashEquivalents", "50", "30")]
        s = annual_series({2025: statements(2025, ("200", "180"), ("20", "18"), ("15", "13"), ("500", "460"),
                                            ("300", "280"), extra)})
        r = returns(s, 2025, financial=False)
        # IC = (300+100-50 + 280+100-30)/2 = 350; NOPAT = 20 x 0.75
        self.assertAlmostEqual(r["roic"]["value"], 15 / 350)
        self.assertEqual(r["roic"]["tax_basis"], "effective")
        self.assertAlmostEqual(r["roic_pretax"]["value"], 20 / 350)
        d = r["dupont"]
        self.assertAlmostEqual(d["value"], 15 / 290)
        self.assertAlmostEqual(d["net_margin"] * d["asset_turnover"] * d["equity_multiplier"], d["value"])

    def test_loss_year_uses_labelled_statutory_rate(self):
        extra = [row("IS", "ifrs-full_ProfitLossBeforeTax", "-5", "-8", "-9"),
                 row("IS", "ifrs-full_IncomeTaxExpenseContinuingOperations", "-3", "1", "1"),
                 row("BS", "ifrs-full_LongtermBorrowings", "100", "100"),
                 row("BS", "ifrs-full_CashAndCashEquivalents", "50", "30")]
        s = annual_series({2025: statements(2025, ("200", "180"), ("20", "18"), ("-2", "-9"), ("500", "460"),
                                            ("300", "280"), extra)})
        r = returns(s, 2025, financial=False)["roic"]
        self.assertEqual(r["tax_basis"], "statutory_top_rate_assumed")
        self.assertAlmostEqual(r["value"], 20 * (1 - 0.264) / 350)


class Piotroski(unittest.TestCase):
    def test_all_nine_pass(self):
        rows = statements(2025, ("120", "100"), ("12", "9"), ("10", "5"), ("200", "200", "200"), ("120", "110"), [
            row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "15", "8"),
            row("BS", "ifrs-full_NoncurrentLiabilities", "30", "40", "40"),
            row("BS", "ifrs-full_CurrentAssets", "80", "70"), row("BS", "ifrs-full_CurrentLiabilities", "40", "40"),
            row("BS", "ifrs-full_IssuedCapital", "10", "10"), row("IS", "ifrs-full_GrossProfit", "36", "28"),
        ])
        f = piotroski(annual_series({2025: rows}), 2025, financial=False)
        self.assertEqual((f["value"], f["out_of"]), (9, 9))

    def test_too_few_inputs(self):
        f = piotroski(annual_series({2025: statements(2025, ("1", "1"), ("1", "1"), ("1", "1"), ("1", "1"), ("1", "1"))}),
                      2025, financial=False)
        self.assertIsNone(f["value"])
        self.assertTrue(f["reason"].startswith("missing:input"))


SAMSUNG_ALOT = [
    {"se": "(연결)현금배당성향(%)", "stock_knd": "-", "thstrm": "25.10", "frmtrm": "29.20", "lwfr": "67.80"},
    {"se": "현금배당금총액(백만원)", "stock_knd": "-", "thstrm": "11,107,906", "frmtrm": "9,810,767", "lwfr": "9,809,438"},
    {"se": "주당 현금배당금(원)", "stock_knd": "보통주", "thstrm": "1,668", "frmtrm": "1,446", "lwfr": "1,444"},
    {"se": "주당 현금배당금(원)", "stock_knd": "우선주", "thstrm": "1,669", "frmtrm": "1,447", "lwfr": "1,445"},
    {"se": "현금배당수익률(%)", "stock_knd": "보통주", "thstrm": "1.50", "frmtrm": "2.70", "lwfr": "1.90"},
]
SAMSUNG_TESSTK = [
    {"stock_knd": "보통주", "acqs_mth1": "총계", "bsis_qy": "29,700,000", "change_qy_acqs": "118,314,495",
     "change_qy_dsps": "6,040,880", "change_qy_incnr": "50,144,628", "trmend_qy": "91,828,987"},
    {"stock_knd": "보통주", "acqs_mth1": "배당가능이익범위 이내 취득", "bsis_qy": "29,700,000", "trmend_qy": "91,828,987"},
]


class Shareholder(unittest.TestCase):
    def test_samsung_dividends_and_treasury(self):
        d = dividends_from_alot(SAMSUNG_ALOT, 2025)
        self.assertEqual(d["dps_common"], {"2025": 1668.0, "2024": 1446.0, "2023": 1444.0})
        self.assertAlmostEqual(d["payout_ratio"]["2025"], 0.251)
        self.assertEqual(d["cash_dividends_total"]["2025"], 11_107_906e6)
        t = treasury_from_tesstk(SAMSUNG_TESSTK)
        self.assertEqual((t["common"]["cancelled"], t["common"]["end"]), (50_144_628, 91_828_987))

    def test_total_payout_uses_declared_dividends(self):
        rows = [row("IS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "44260956000000"),
                row("CF", "ifrs-full_DividendsPaidClassifiedAsFinancingActivities", "9897183000000"),
                row("CF", "dart_AcquisitionOfTreasuryShares", "8189263000000")]
        out = shareholder_returns(annual_series({2025: rows}), 2025, dividends=dividends_from_alot(SAMSUNG_ALOT, 2025),
                                  treasury=treasury_from_tesstk(SAMSUNG_TESSTK), issued_common=5_919_637_922)
        p = out["total_payout_ratio"]
        self.assertEqual(p["dividend_basis"], "declared")
        self.assertAlmostEqual(p["value"], (11_107_906e6 + 8_189_263e6) / 44_260_956e6)
        self.assertAlmostEqual(out["treasury_ratio"]["value"], 91_828_987 / 5_919_637_922)

    def test_no_dividend_filer_ignores_subsidiary_payouts(self):
        # 두산에너빌리티: no dividend of its own; consolidated CF pays 두산밥캣's minorities.
        alot = [{"se": "현금배당금총액(백만원)", "stock_knd": "-", "thstrm": "-", "frmtrm": "-", "lwfr": "-"},
                {"se": "주당 현금배당금(원)", "stock_knd": "보통주", "thstrm": "-", "frmtrm": "-", "lwfr": "-"}]
        rows = [row("IS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "100"),
                row("CF", "ifrs-full_DividendsPaidClassifiedAsFinancingActivities", "90"),
                row("CF", "dart_AcquisitionOfTreasuryShares", "10")]
        d = dividends_from_alot(alot, 2025)
        self.assertTrue(d["none_paid"])
        p = shareholder_returns(annual_series({2025: rows}), 2025, dividends=d, treasury=None,
                                issued_common=None)["total_payout_ratio"]
        self.assertAlmostEqual(p["value"], 0.1)


def t(cells_rows, before=""):
    body = "".join("<TR>" + "".join(f"<TD>{c}</TD>" for c in r) + "</TR>" for r in cells_rows)
    return f"<P>{before}</P><TABLE>{body}</TABLE>"


CB_HEADER = [["종류＼구분", "회차", "발행일", "만기일", "권면(전자등록)총액", "전환대상주식의 종류", "전환청구가능기간",
              "전환조건", "", "미상환사채", "", "비고"],
             ["전환비율(%)", "전환가액", "권면(전자등록)총액", "전환가능주식수"]]
CB_ISSUE = ["무기명식 무이권부무보증 사모 전환사채", "제3회", "2024.10.25", "2029.10.25", "85,000", "이연제약(주) 기명식 보통주식",
            "2025.10.26~2029.10.18", "100", "11,858", "85,000", "7,168,156", "-"]
CB_TOTAL = ["합 계", "-", "-", "-", "85,000", "-", "-", "100", "11,858", "85,000", "7,168,156", "-"]


class Dilution(unittest.TestCase):
    def test_outstanding_cb_from_total_row(self):
        doc = ("<P>가. 미상환 전환사채 발행현황</P>"
               + t([["(기준일 :", "2026년 09월 30일", ")", "(단위 : 백만원, 주)"]])
               + t(CB_HEADER + [CB_ISSUE, CB_TOTAL], "(기준일 : 2026년 09월 30일 ) (단위 : 백만원, 주)")
               + "<P>* 26년 4분기 중 4회차(110억원) 및 5회차(90억원) 발행 ... 보고서 제출일 현재</P>"
               + t(CB_HEADER + [CB_ISSUE, ["합 계", "-", "-", "-", "285,000", "-", "-", "100", "-", "281,050", "9,071,000", "-"]],
                   "(기준일 : 2026년 11월 13일 ) (단위 : 백만원, 주)")
               + "<P>나. 미상환 신주인수권부사채 등 발행현황</P><P>해당사항 없음</P><P>4. 주식의 총수 등</P>")
        r = dilution_from_report(doc, receipt="20261113001586", period_end="2026-09-30")
        cb = r["instruments"]["convertible_bond"]
        self.assertEqual((cb["outstanding"], cb["shares"], cb["as_of"]), (85_000e6, 7_168_156, "2026-09-30"))
        self.assertEqual(cb["after_period"]["shares"], 9_071_000)
        self.assertEqual(r["instruments"]["bond_with_warrant"]["status"], "none_reported")
        self.assertEqual((r["status"], r["potential_shares"]), ("reported", 7_168_156))

    def test_none_declared_sentence(self):
        emart = ("<P>※ 당사는 보고서 작성 기준일 현재 미상환전환사채, 신주인수권부사채, 전환형 조건부 자본증권, "
                 "신주인수권에 표시된 증서 등 향후 자본금을 증가시킬 수 있는 증권을 발행하지 않았습니다.</P>")
        shinhan = "<P>나. 전환사채 등 발행현황 - 해당사항 없음 [채무증권의 발행 등과 관련된 사항]</P>"
        for doc in (emart, shinhan):
            r = dilution_from_report(doc, receipt="x", period_end="2026-06-30")
            self.assertEqual((r["status"], r["potential_shares"]), ("none_declared", 0))

    def test_quarterly_placeholder_is_undetermined(self):
        q3 = ("<P>3. 자본금 변동사항 자본금 변동사항은 기업공시서식 작성기준에 따라 분기보고서에 기재하지 않습니다.</P>"
              "<P>4. 주식의 총수 등</P><P>크림 주식회사 제 1회 사모 전환사채</P>")
        r = dilution_from_report(q3, receipt="x", period_end="2026-09-30")
        self.assertEqual((r["status"], r["potential_shares"]), ("undetermined", None))

    def test_filled_capital_section_without_cb_heading(self):
        fy = ("<P>3. 자본금 변동사항 당사는 이사회 결의를 통해 57,056,664주(보통주 50,144,628주, 우선주 6,912,036주)를 "
              "소각하였습니다. 한편, 발행주식의 액면총액은 673,561백만원으로 이익소각으로 인하여 납입자본금과 상이합니다.</P>"
              "<P>4. 주식의 총수 등</P>")
        toc = "<P>3. 자본금 변동사항 ----------------------- 4. 주식의 총수 등 -----------------------</P>"
        self.assertEqual(dilution_from_report(toc + fy, receipt="x", period_end="2025-12-31")["status"],
                         "not_in_capital_section")
        self.assertEqual(dilution_from_report(toc, receipt="x", period_end="2025-12-31")["status"], "undetermined")


def ctx(instant, **dims):
    return {"start": None, "end": None, "instant": instant, "typed": False,
            "dims": {"ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis": "ifrs-full:ConsolidatedMember", **dims}}


class Lease(unittest.TestCase):
    def test_category_members_are_not_totals(self):
        # NAVER FY2025: 0 under amortised cost, the whole balance outside IFRS 7.
        cat = "ifrs-full:CategoriesOfFinancialLiabilitiesAxis"
        contexts = {"a": ctx("2025-12-31"), "b": ctx("2025-12-31", **{cat: "ifrs-full:FinancialLiabilitiesAtAmortisedCostCategoryMember"}),
                    "c": ctx("2025-12-31", **{"ifrs-full:MaturityAxis": "ifrs-full:NotLaterThanOneYearMember"})}
        facts = [{"concept": "LeaseLiabilities", "context": "a", "text": "1187801271000"},
                 {"concept": "LeaseLiabilities", "context": "b", "text": "0"},
                 {"concept": "LeaseLiabilities", "context": "c", "text": "233036238000"}]
        self.assertEqual(lease_from_instance(contexts, facts, fs_div="CFS", instant="2025-12-31"),
                         (1187801271000, "carrying"))

    def test_undiscounted_fallback_is_labelled(self):
        contexts = {"a": ctx("2025-12-31")}
        facts = [{"concept": "GrossLeaseLiabilities", "context": "a", "text": "5549301000000"}]
        self.assertEqual(lease_from_instance(contexts, facts, fs_div="CFS", instant="2025-12-31"),
                         (5549301000000, "undiscounted"))


class Bridge(unittest.TestCase):
    def test_bridge_signs_and_fccr(self):
        rows = statements(2025, ("100", "90"), ("10", "9"), ("8", "7"), ("200", "190"), ("100", "95"), [
            row("BS", "ifrs-full_NoncurrentRecognisedLiabilitiesDefinedBenefitPlan", "12"),
            row("BS", "ifrs-full_NoncurrentRecognisedAssetsDefinedBenefitPlan", "2"),
            row("BS", "ifrs-full_OtherShorttermProvisions", "5"), row("BS", "ifrs-full_OtherLongtermProvisions", "3"),
            row("BS", "ifrs-full_InvestmentAccountedForUsingEquityMethod", "20"),
            row("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "6"),
            row("CF", "ifrs-full_InterestPaidClassifiedAsOperatingActivities", "2"),
            row("CF", "ifrs-full_PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities", "2"),
        ])
        m = investor_metrics({2025: rows}, fiscal_year=2025, financial=False, lease_in_net_debt=False,
                             xbrl_lease=30, xbrl_lease_basis="carrying", ebitda=18, ebitda_card="ebitda")
        ev = m["ev_bridge"]
        self.assertEqual(ev["adjustment_core"], 10 + 30 - 20)
        self.assertEqual(ev["adjustment_conservative"], 10 + 30 - 20 + 8)
        self.assertAlmostEqual(ev["fixed_charge_coverage"]["value"], (18 - 6) / 4)

    def test_financial_gets_no_bridge(self):
        m = investor_metrics({2025: []}, fiscal_year=2025, financial=True)
        self.assertEqual(m["ev_bridge"]["reason"], "not_applicable:financial")
        self.assertEqual(m["distress"]["z_double_prime"]["reason"], "not_applicable:financial")


if __name__ == "__main__":
    unittest.main()


class Kits(unittest.TestCase):
    def test_trading_house(self):
        from dart_kfa.investor_metrics import industry_metrics
        rows = statements(2025, ("7554", "7000"), ("140", "120"), ("90", "80"), ("5000", "4800"), ("2000", "1900"), [
            row("IS", "ifrs-full_GrossProfit", "288", "260"), row("IS", "ifrs-full_CostOfSales", "7266", "6740"),
            row("IS", "ifrs-full_ProfitLossBeforeTax", "100", "90"),
            row("IS", "ifrs-full_ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod", "40", "30"),
            row("BS", "ifrs-full_CurrentTradeReceivables", "1170", "1000"), row("BS", "ifrs-full_Inventories", "315", "266")])
        h = industry_metrics(annual_series({2025: rows}), 2025, "trading_house")["history"]["2025"]
        self.assertAlmostEqual(h["gross_margin"], 288 / 7554)
        self.assertAlmostEqual(h["equity_method_share"], 0.4)
        self.assertAlmostEqual(h["dso"], (1170 + 1000) / 2 / 7554 * 365)
        self.assertAlmostEqual(h["dio"], (315 + 266) / 2 / 7266 * 365)

    def test_mining_uses_note_da_when_cash_flow_is_summarised(self):
        from dart_kfa.investor_metrics import industry_metrics
        rows = statements(2025, ("1000", "900"), ("80", "70"), ("50", "40"), ("3000", "2900"), ("2000", "1900"), [
            row("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "60")])
        s = annual_series({2025: rows})
        s["values"][2025]["cf_dep_amort_total"] = 20.0          # from the XBRL notes
        h = industry_metrics(s, 2025, "mining_smelting")["history"]["2025"]
        self.assertEqual((h["da_to_sales"], h["capex_to_da"], h["ebitda_margin"]), (0.02, 3.0, 0.1))

    def test_other_kits_get_nothing(self):
        from dart_kfa.investor_metrics import industry_metrics
        self.assertIsNone(industry_metrics(annual_series({}), 2025, "semiconductor"))
