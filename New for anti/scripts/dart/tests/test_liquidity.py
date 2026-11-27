"""1년 내 만기 차입금 · 넓힌 CCC/순차입금 · 만기 구간. Rows copy 삼성전자 FY2025
(단기차입금 tagged '-표준계정코드 미사용-') and 이마트 (combined receivables)."""
import unittest

from dart_kfa.liquidity import ccc_wide, flag_partial, maturity_ladders, net_debt_wide, refinancing


def r(sj, aid, th, fr=None, nm=""):
    return {"sj_div": sj, "account_id": aid, "account_nm": nm, "thstrm_amount": th, "frmtrm_amount": fr}


SAMSUNG = [r("BS", "-표준계정코드 미사용-", "17574980000000", nm="단기차입금"),
           r("BS", "ifrs-full_CurrentPortionOfLongtermBorrowings", "1177508000000", nm="유동성장기부채"),
           r("BS", "ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived", "6479517000000", nm="장기차입금"),
           r("BS", "ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued", "7134000000", nm="사채"),
           r("BS", "ifrs-full_CashAndCashEquivalents", "57856378000000", nm="현금및현금성자산"),
           r("BS", "ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents", "67965021000000", nm="단기금융상품"),
           r("BS", "ifrs-full_TradeAndOtherCurrentPayablesToTradeSuppliers", "13039380000000", nm="매입채무")]


class ShortTerm(unittest.TestCase):
    def test_name_matched_line_and_operating_liabilities_excluded(self):
        x = refinancing(SAMSUNG, ebitda=90_527_643e6)
        self.assertEqual(x["total"], 17_574_980e6 + 1_177_508e6)          # 매입채무 is not debt
        self.assertEqual([p["match"][:4] for p in x["parts"]], ["name", "id:i"])
        self.assertAlmostEqual(x["cover_by_cash"], (57_856_378 + 67_965_021) / (17_574_980 + 1_177_508))

    def test_net_debt_wide_counts_the_untagged_line(self):
        nd = net_debt_wide(SAMSUNG)
        self.assertEqual(nd["gross"], (17_574_980 + 1_177_508 + 6_479_517 + 7_134) * 1e6)
        self.assertEqual(nd["value"], nd["gross"] - 57_856_378e6)

    def test_single_lease_line_not_counted_twice(self):
        rows = [r("BS", "ifrs-full_CurrentLeaseLiabilities", "100", nm="리스부채"), r("BS", "ifrs-full_CashAndCashEquivalents", "10")]
        self.assertEqual(net_debt_wide(rows)["gross"], 100)


class CCC(unittest.TestCase):
    def test_combined_lines_are_labelled(self):
        rows = [r("IS", "ifrs-full_Revenue", "1000"), r("IS", "ifrs-full_CostOfSales", "800"),
                r("BS", "ifrs-full_TradeAndOtherCurrentReceivables", "120", "80", nm="매출채권및기타채권"),
                r("BS", "ifrs-full_Inventories", "90", "70"), r("BS", "ifrs-full_TradeAndOtherCurrentPayables", "150", "130", nm="매입채무및기타채무")]
        c = ccc_wide(rows)
        self.assertAlmostEqual(c["value"], 100 / 1000 * 365 + 80 / 800 * 365 - 140 / 800 * 365)
        self.assertTrue(c["includes_other"])


def ctx(dims):
    return {"start": None, "end": None, "instant": "2025-12-31", "typed": False,
            "dims": {"ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis": "ifrs-full:ConsolidatedMember", **dims}}


class Ladders(unittest.TestCase):
    def test_borrowings_and_guarantees(self):
        M = "ifrs-full:MaturityAxis"
        contexts = {"a": ctx({M: "ifrs-full:NotLaterThanOneYearMember"}), "b": ctx({M: "ifrs-full:LaterThanOneYearAndNotLaterThanTwoYearsMember"}),
                    "c": ctx({M: "e:LaterthantwoyearsmemberOfAggregatedTimeBandsMember"}), "x": ctx({M: "ifrs-full:NotLaterThanOneYearMember", "q": "z"})}
        facts = [{"concept": "Borrowings", "context": "a", "text": "343", "unit": "KRW"},
                 {"concept": "Borrowings", "context": "b", "text": "48", "unit": "KRW"},
                 {"concept": "Borrowings", "context": "c", "text": "248", "unit": "KRW"},
                 {"concept": "Borrowings", "context": "x", "text": "9999", "unit": "KRW"},
                 {"concept": "FinancialGuaranteeContractsUndiscountedCashFlows", "context": "a", "text": "1246", "unit": "KRW"}]
        lad = maturity_ladders(contexts, facts, fs_div="CFS", instant="2025-12-31")
        self.assertEqual([(b["bucket"], b["value"]) for b in lad["borrowings"]["buckets"]],
                         [("1년 이내", 343.0), ("1~2년", 48.0), ("2년 초과", 248.0)])
        self.assertEqual(lad["contingent"]["within_1y"], 1246.0)
        flag_partial(lad, borrowings_bs=60000, lease_bs=None)
        self.assertTrue(lad["borrowings"]["partial"])


if __name__ == "__main__":
    unittest.main()
