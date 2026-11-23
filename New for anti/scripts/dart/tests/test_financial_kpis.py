"""업권 지표. Face rows copy KB금융 FY2025 (CFS); table fragments copy the layouts
of KB금융 / 신한지주 / DB손해보험 3Q 2026 reports."""
import unittest

from dart_kfa.financial_kpis import computed, financial_kpis, reported_ratios


def row(sj, aid, th, fr=None, nm=""):
    return {"sj_div": sj, "account_id": aid, "account_nm": nm, "thstrm_amount": th, "frmtrm_amount": fr}


KB = [
    row("BS", "ifrs-full_Assets", "797923033000000", "761000000000000"),
    row("BS", "ifrs-full_Equity", "60829989000000", "58000000000000"),
    row("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "60000000000000", "57000000000000"),
    row("BS", "dart_LoansAtAmortisedCost", "491978044000000", "472080000000000"),
    row("BS", "ifrs-full_DepositsFromCustomers", "462397026000000"),
    row("IS", "ifrs-full_ProfitLoss", "5840715000000"),
    row("IS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "5833162000000"),
    row("IS", "ifrs-full_InterestRevenueExpense", "13073093000000"),
    row("IS", "ifrs-full_FeeAndCommissionIncomeExpense", "4098287000000"),
    row("IS", "ifrs-full_ImpairmentLossImpairmentGainAndReversalOfImpairmentLossDeterminedInAccordanceWithIFRS9", "2362878000000"),
    row("IS", "ifrs-full_SellingGeneralAndAdministrativeExpense", "7064573000000"),
    row("IS", "-표준계정코드 미사용-", "10880589000000", nm="신용손실충당금 반영전 영업이익"),
]


class Computed(unittest.TestCase):
    def test_bank(self):
        c = computed(KB, "basel")
        self.assertAlmostEqual(c["cost_income"]["value"], 7064573 / (7064573 + 10880589))
        self.assertAlmostEqual(c["credit_cost"]["value"], 2362878 / ((491978044 + 472080000) / 2))
        self.assertAlmostEqual(c["loans_to_deposits"]["value"], 491978044 / 462397026)
        self.assertAlmostEqual(c["roe"]["value"], 5833162 / 58500000)
        self.assertEqual(c["net_interest_income"]["unit"], "money")

    def test_bank_without_ppop_row_uses_operating_profit(self):
        rows = [row("IS", "ifrs-full_GeneralAndAdministrativeExpense", "6402500000000"),
                row("IS", "ifrs-full_ImpairmentLossImpairmentGainAndReversalOfImpairmentLossDeterminedInAccordanceWithIFRS9", "2002965000000"),
                row("IS", "ifrs-full_ProfitLossFromOperatingActivities", "7023357000000")]
        c = computed(rows, "basel")
        self.assertAlmostEqual(c["cost_income"]["value"], 6402500 / (6402500 + 7023357 + 2002965))

    def test_insurer(self):
        rows = [row("IS", "ifrs-full_InsuranceRevenue", "9718551000000"), row("IS", "ifrs-full_InsuranceServiceResult", "981030000000"),
                row("IS", "dart_InvestmentIncomeExpenses", "1599439000000")]
        c = computed(rows, "kics")
        self.assertAlmostEqual(c["insurance_margin"]["value"], 981030 / 9718551)
        self.assertAlmostEqual(c["insurance_share_of_profit"]["value"], 981030 / (981030 + 1599439))

    def test_missing_input_is_reported(self):
        self.assertEqual(computed([], "credit_finance")["credit_cost_to_revenue"]["reason"], "missing:input")

    def test_unregulated_returns_none(self):
        self.assertIsNone(financial_kpis(KB, kind=None))


def table(rows, before=""):
    body = "".join("<TR>" + "".join(f"<TD>{c}</TD>" for c in r) + "</TR>" for r in rows)
    return f"<P>{before}</P><TABLE>{body}</TABLE>"


class Reported(unittest.TestCase):
    def test_group_table_wins_and_subsidiary_is_labelled(self):
        doc = ("<P>[지배회사에 관한 사항] [KB금융지주]</P>"
               + table([["구 분", "2026년 3분기말", "2025년말"], ["총여신", "523,474", "509,026"], ["고정이하여신비율", "0.98", "0.99"]],
                       "(3) 자산건전성 관련 지표 1) 고정이하여신비율 (단위 : 십억원, %)")
               + "<P>[주요 종속회사에 관한 사항] [KB국민은행]</P>"
               + table([["구 분", "2026년 3분기", "2025년"], ["고정이하여신비율", "0.30", "0.28"], ["대손충당금적립률(A/B)", "191.39", "206.01"]],
                       "(3) 건전성 1) 자산건전성 현황 (단위 : 백만원, %)"))
        r = reported_ratios(doc, "basel")
        self.assertAlmostEqual(r["npl_ratio"]["value"], 0.0098)
        self.assertFalse(r["npl_ratio"]["subsidiary"])
        self.assertTrue(r["coverage_ratio"]["subsidiary"])
        self.assertEqual(r["npl_ratio"]["series"][0], ("2026년 3분기말", 0.0098))

    def test_consolidated_label_wins(self):
        doc = (table([["구 분", "2026년 9월 말"], ["고정이하여신비율", "0.31%"]], "은행 (단위 : 십억원)")
               + table([["구 분", "2026년 9월 말"], ["고정이하여신비율", "0.78%"]], "다. 건전성 (1) 연결기준 (단위 : 십억원)"))
        self.assertAlmostEqual(reported_ratios(doc, "basel")["npl_ratio"]["value"], 0.0078)

    def test_foreign_currency_tables_are_skipped(self):
        doc = table([["구분", "2026년3분기"], ["손해율", "36.5"], ["합산비율", "98.6"]], "(3) 수익성 현황 (단위 : 백만VND, %)")
        self.assertEqual(reported_ratios(doc, "kics"), {})

    def test_out_of_range_values_are_skipped(self):
        doc = table([["구분", "당기"], ["연체율", "45.0"]], "(단위 : %)")
        self.assertEqual(reported_ratios(doc, "credit_finance"), {})


if __name__ == "__main__":
    unittest.main()
