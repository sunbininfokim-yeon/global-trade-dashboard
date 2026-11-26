"""SEC companyfacts -> the row shape the investor / financial modules read.

`investor_metrics`, `financial_kpis` and the snapshot builder's valuation bases
read OpenDART `fnlttSinglAcntAll` rows (sj_div, account_id, thstrm / frmtrm /
bfefrmtrm). This module builds the same rows from a US filer's companyfacts so
those modules run unchanged, with every row labelled `source: SEC`:

* each US-GAAP concept maps to the IFRS / DART account id the modules look
  for (Revenues -> ifrs-full_Revenue, NetIncomeLoss -> parent profit, ...);
  the first concept present for a year wins, as in sec_xbrl;
* flows take 10-K facts whose duration is one fiscal year (350-380 days, so
  52/53-week years count) ending at that year's fiscal year end; balances take
  the 10-K instant at that date; a later filing (restatement) wins;
* fiscal years are named by the calendar year they end in (NVIDIA's year to
  2026-01-25 is 2026).

Also: the fiscal-period layout the PE/CR engine's SEC adapter needs (actual
first day of the year and each 10-Q YTD end), LTM values from the latest
10-Q YTD, and US-only items: remaining performance obligations (backlog),
diluted-vs-basic share count gap, share-based compensation, R&D.
"""
from __future__ import annotations

from datetime import date

# (statement, target account id, US-GAAP concepts in priority order)
MAP = [
    ("IS", "ifrs-full_Revenue", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                                  "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]),
    ("IS", "ifrs-full_CostOfSales", ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]),
    ("IS", "ifrs-full_GrossProfit", ["GrossProfit"]),
    ("IS", "dart_OperatingIncomeLoss", ["OperatingIncomeLoss"]),
    ("IS", "ifrs-full_ProfitLossBeforeTax", [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]),
    ("IS", "ifrs-full_IncomeTaxExpenseContinuingOperations", ["IncomeTaxExpenseBenefit"]),
    ("IS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", ["NetIncomeLoss"]),
    ("IS", "ifrs-full_ProfitLoss", ["ProfitLoss", "NetIncomeLoss"]),
    ("IS", "ifrs-full_BasicEarningsLossPerShare", ["EarningsPerShareBasic"]),
    ("IS", "ifrs-full_InterestExpense", ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"]),
    # banks
    ("IS", "ifrs-full_InterestRevenueExpense", ["InterestIncomeExpenseNet", "InterestIncomeExpenseAfterProvisionForLoanLoss"]),
    ("IS", "ifrs-full_RevenueFromInterest", ["InterestAndDividendIncomeOperating", "InterestIncomeOperating"]),
    ("IS", "ifrs-full_FeeAndCommissionIncome", ["NoninterestIncome"]),
    ("IS", "ifrs-full_ImpairmentLossImpairmentGainAndReversalOfImpairmentLossDeterminedInAccordanceWithIFRS9",
     ["ProvisionForLoanLeaseAndOtherLosses", "ProvisionForLoanAndLeaseLosses", "ProvisionForCreditLossesNet"]),
    ("IS", "ifrs-full_SellingGeneralAndAdministrativeExpense", ["NoninterestExpense", "SellingGeneralAndAdministrativeExpense"]),
    ("BS", "ifrs-full_Assets", ["Assets"]),
    ("BS", "ifrs-full_CurrentAssets", ["AssetsCurrent"]),
    ("BS", "ifrs-full_CurrentLiabilities", ["LiabilitiesCurrent"]),
    ("BS", "ifrs-full_Liabilities", ["Liabilities"]),
    ("BS", "ifrs-full_NoncurrentLiabilities", ["LiabilitiesNoncurrent"]),
    ("BS", "ifrs-full_EquityAttributableToOwnersOfParent", ["StockholdersEquity"]),
    ("BS", "ifrs-full_Equity", ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"]),
    ("BS", "ifrs-full_CashAndCashEquivalents", ["CashAndCashEquivalentsAtCarryingValue",
                                                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
    ("BS", "ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents", ["ShortTermInvestments", "MarketableSecuritiesCurrent",
                                                                          "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]),
    ("BS", "ifrs-full_CurrentTradeReceivables", ["AccountsReceivableNetCurrent"]),
    ("BS", "ifrs-full_Inventories", ["InventoryNet"]),
    ("BS", "ifrs-full_RetainedEarnings", ["RetainedEarningsAccumulatedDeficit"]),
    ("BS", "ifrs-full_IssuedCapital", ["CommonStockValue", "CommonStocksIncludingAdditionalPaidInCapital"]),
    ("BS", "ifrs-full_SharePremium", ["AdditionalPaidInCapitalCommonStock", "AdditionalPaidInCapital"]),
    ("BS", "ifrs-full_ShorttermBorrowings", ["ShortTermBorrowings", "CommercialPaper"]),
    ("BS", "ifrs-full_CurrentPortionOfLongtermBorrowings", ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"]),
    ("BS", "ifrs-full_LongtermBorrowings", ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"]),
    ("BS", "ifrs-full_CurrentLeaseLiabilities", ["OperatingLeaseLiabilityCurrent"]),
    ("BS", "ifrs-full_NoncurrentLeaseLiabilities", ["OperatingLeaseLiabilityNoncurrent"]),
    ("BS", "ifrs-full_InvestmentAccountedForUsingEquityMethod", ["EquityMethodInvestments"]),
    ("BS", "dart_LoansAtAmortisedCost", ["LoansAndLeasesReceivableNetReportedAmount", "LoansAndLeasesReceivableNetOfDeferredIncome"]),
    ("BS", "ifrs-full_DepositsFromCustomers", ["Deposits"]),
    ("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", ["NetCashProvidedByUsedInOperatingActivities",
                                                               "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]),
    ("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
     ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]),
    ("CF", "ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities", ["PaymentsToAcquireIntangibleAssets"]),
    ("CF", "ifrs-full_DividendsPaidClassifiedAsFinancingActivities", ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"]),
    ("CF", "dart_AcquisitionOfTreasuryShares", ["PaymentsForRepurchaseOfCommonStock"]),
    ("CF", "ifrs-full_InterestPaidClassifiedAsOperatingActivities", ["InterestPaidNet", "InterestPaid"]),
    ("CF", "ifrs-full_PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities", ["FinanceLeasePrincipalPayments"]),
    ("CF", "ifrs-full_AdjustmentsForDepreciationAndAmortisationExpense",
     ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization",
      "DepreciationAmortizationAndOther", "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment"]),
]
UNITS = ("USD", "USD/shares")


def _days(p):
    return (date.fromisoformat(p["end"]) - date.fromisoformat(p["start"])).days


def _points(facts, concept):
    units = ((facts.get("facts") or {}).get("us-gaap") or {}).get(concept, {}).get("units") or {}
    for u in UNITS:
        if u in units:
            return units[u]
    return []


def fiscal_year_ends(facts) -> list[str]:
    """10-K fiscal year ends (a one-year Revenue / NetIncomeLoss duration), oldest first."""
    ends = set()
    for concept in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "NetIncomeLoss"):
        for p in _points(facts, concept):
            if (p.get("form") or "").startswith("10-K") and p.get("start") and 350 <= _days(p) <= 380:
                ends.add(p["end"])
    return sorted(ends)


def _value(facts, concepts, end, flow):
    for concept in concepts:
        best = None
        for p in _points(facts, concept):
            if not (p.get("form") or "").startswith("10-K") or p.get("end") != end:
                continue
            if flow and not (p.get("start") and 350 <= _days(p) <= 380):
                continue
            if not flow and p.get("start"):
                continue
            if best is None or (p.get("filed") or "") > (best.get("filed") or ""):
                best = p
        if best is not None:
            return float(best["val"]), concept
    return None, None


def annual_rows(facts, ends: list[str]) -> dict:
    """{fiscal_year: rows} like OpenDART FY reports: the report for year Y holds
    Y (thstrm), Y-1 (frmtrm) and Y-2 (bfefrmtrm). Two reports cover five years."""
    by_end = {e: int(e[:4]) for e in ends}
    out = {}
    newest = sorted(ends)[-1:] + sorted(ends)[-3:-2]
    for anchor in newest:
        i = ends.index(anchor)
        years = [ends[j] if j >= 0 else None for j in (i, i - 1, i - 2)]
        rows = []
        for sj, target, concepts in MAP:
            vals, used = [], None
            for e in years:
                v, c = _value(facts, concepts, e, sj != "BS") if e else (None, None)
                vals.append(v)
                used = used or c
            if all(v is None for v in vals):
                continue
            fmt = lambda v: None if v is None else (str(int(v)) if float(v).is_integer() else str(v))  # noqa: E731
            rows.append({"sj_div": sj, "account_id": target, "account_nm": used, "source": "SEC",
                         "rcept_no": f"SEC-10K-{anchor}", "thstrm_amount": fmt(vals[0]),
                         "frmtrm_amount": fmt(vals[1]), "bfefrmtrm_amount": fmt(vals[2])})
        _derive_liabilities(facts, rows, years, anchor)
        out[by_end[anchor]] = rows
    return out


def _derive_liabilities(facts, rows, years, anchor):
    """Many US filers (Walmart) never tag total liabilities: derive it as
    LiabilitiesAndStockholdersEquity − total equity, and non-current
    liabilities as total − current, labelled as derived."""
    have = {r["account_id"]: r for r in rows}
    fields = ("thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount")

    def val(aid, i):
        r = have.get(aid)
        x = r.get(fields[i]) if r else None
        return float(x) if x not in (None, "") else None
    if "ifrs-full_Liabilities" not in have:
        vals = []
        for i, e in enumerate(years):
            total, _ = _value(facts, ["LiabilitiesAndStockholdersEquity"], e, False) if e else (None, None)
            eq = val("ifrs-full_Equity", i)
            vals.append(total - eq if total is not None and eq is not None else None)
        if any(v is not None for v in vals):
            row = {"sj_div": "BS", "account_id": "ifrs-full_Liabilities", "account_nm": "derived:LiabilitiesAndStockholdersEquity-Equity",
                   "source": "SEC", "rcept_no": f"SEC-10K-{anchor}"}
            row.update({f: (None if v is None else str(v)) for f, v in zip(fields, vals)})
            rows.append(row)
            have[row["account_id"]] = row
    # No operating-income line (ExxonMobil, many conglomerates): EBIT as
    # pretax income + interest expense, labelled derived.
    if "dart_OperatingIncomeLoss" not in have and "ifrs-full_ProfitLossBeforeTax" in have:
        vals = [(val("ifrs-full_ProfitLossBeforeTax", i) + (val("ifrs-full_InterestExpense", i) or 0))
                if val("ifrs-full_ProfitLossBeforeTax", i) is not None else None for i in range(3)]
        if any(v is not None for v in vals):
            row = {"sj_div": "IS", "account_id": "dart_OperatingIncomeLoss",
                   "account_nm": "derived:EBIT=PretaxIncome+InterestExpense", "source": "SEC", "rcept_no": f"SEC-10K-{anchor}"}
            row.update({f: (None if v is None else str(v)) for f, v in zip(fields, vals)})
            rows.append(row)
            have[row["account_id"]] = row
    if "ifrs-full_NoncurrentLiabilities" not in have and "ifrs-full_Liabilities" in have:
        vals = [(val("ifrs-full_Liabilities", i) - val("ifrs-full_CurrentLiabilities", i))
                if val("ifrs-full_Liabilities", i) is not None and val("ifrs-full_CurrentLiabilities", i) is not None else None
                for i in range(3)]
        if any(v is not None for v in vals):
            row = {"sj_div": "BS", "account_id": "ifrs-full_NoncurrentLiabilities", "account_nm": "derived:Liabilities-LiabilitiesCurrent",
                   "source": "SEC", "rcept_no": f"SEC-10K-{anchor}"}
            row.update({f: (None if v is None else str(v)) for f, v in zip(fields, vals)})
            rows.append(row)


def report_periods(facts, fiscal_year_end: str) -> dict:
    """Actual fiscal-year start and 10-Q YTD ends, for adapt_sec_companyfacts."""
    start = None
    for concept in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "NetIncomeLoss"):
        for p in _points(facts, concept):
            if p.get("end") == fiscal_year_end and p.get("start") and 350 <= _days(p) <= 380:
                start = p["start"]
                break
        if start:
            break
    if not start:
        return {}
    out = {"FY": {"start": start, "end": fiscal_year_end}}
    for fp, bucket in (("Q1", "Q1"), ("Q2", "H1"), ("Q3", "Q3")):
        ends = [p["end"] for c in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "NetIncomeLoss")
                for p in _points(facts, c) if (p.get("form") or "").startswith("10-Q") and p.get("fp") == fp and p.get("start") == start]
        if ends:
            out[bucket] = {"start": start, "end": max(ends)}
    return out


def ltm(facts, fiscal_year_end: str) -> dict | None:
    """LTM = FY + current YTD − prior-year YTD, from the newest 10-Q after the FY."""
    def ytd_pairs(concepts):
        for concept in concepts:
            pts = [p for p in _points(facts, concept) if (p.get("form") or "").startswith("10-Q") and p.get("start")
                   and p["end"] > fiscal_year_end]
            if pts:
                cur = max(pts, key=lambda p: (p["end"], _days(p), p.get("filed") or ""))
                prior = [p for p in _points(facts, concept) if p.get("start") and abs(_days(p) - _days(cur)) <= 7
                         and abs((date.fromisoformat(cur["end"]) - date.fromisoformat(p["end"])).days - 364) <= 10]
                if prior:
                    return cur, max(prior, key=lambda p: p.get("filed") or "")
        return None, None

    out = {}
    for key, concepts in (("revenue", MAP[0][2]), ("operating_income", ["OperatingIncomeLoss"]),
                          ("net_income_parent", ["NetIncomeLoss"]), ("net_income", ["ProfitLoss", "NetIncomeLoss"])):
        fy, _ = _value(facts, concepts, fiscal_year_end, True)
        cur, prior = ytd_pairs(concepts)
        if fy is not None and cur and prior:
            out[key] = fy + float(cur["val"]) - float(prior["val"])
            out["period_end"] = cur["end"]
    if not out.get("period_end"):
        return None
    for key, concepts in (("parent_equity", ["StockholdersEquity"]),
                          ("equity", ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"])):
        pts = [p for c in concepts for p in _points(facts, c) if p.get("end") == out["period_end"] and not p.get("start")]
        if pts:
            out[key] = float(max(pts, key=lambda p: p.get("filed") or "")["val"])
    out["report"] = "10-Q"
    return out


def us_extras(facts, fiscal_year_end: str, revenue: float | None) -> dict:
    """US-only items from the 10-K: RPO backlog, diluted share gap, SBC, R&D."""
    out = {}
    rpo, _ = _value(facts, ["RevenueRemainingPerformanceObligation"], fiscal_year_end, False)
    if rpo:
        out["backlog"] = {"backlog": rpo, "period_end": fiscal_year_end, "status": "parsed", "report": "10-K",
                          "label": "잔여 수행의무(RPO)", "source": "SEC companyfacts us-gaap:RevenueRemainingPerformanceObligation"}
        if revenue:
            out["backlog"]["backlog_to_revenue"] = rpo / revenue
            out["backlog"]["revenue_basis"] = f"FY{fiscal_year_end[:4]}"
    basic, _ = _value(facts, ["WeightedAverageNumberOfSharesOutstandingBasic"], fiscal_year_end, True)
    diluted, _ = _value(facts, ["WeightedAverageNumberOfDilutedSharesOutstanding"], fiscal_year_end, True)
    if basic is None or diluted is None:
        units = ((facts.get("facts") or {}).get("us-gaap") or {})
        def shares(concept):
            for p in (units.get(concept, {}).get("units", {}).get("shares") or []):
                if (p.get("form") or "").startswith("10-K") and p.get("end") == fiscal_year_end and p.get("start"):
                    return float(p["val"])
            return None
        basic, diluted = shares("WeightedAverageNumberOfSharesOutstandingBasic"), shares("WeightedAverageNumberOfDilutedSharesOutstanding")
    if basic and diluted:
        out["dilution"] = {"status": "us_diluted_shares", "potential_shares": max(diluted - basic, 0),
                           "issued_common": basic, "potential_ratio": max(diluted - basic, 0) / basic,
                           "period_end": fiscal_year_end, "receipt": "10-K",
                           "note": "희석 가중평균 주식수 − 기본 가중평균 주식수 (스톡옵션·RSU·전환증권). 미국 공시 기준"}
    notes = {"fiscal_year_end": fiscal_year_end, "receipt": "SEC 10-K"}
    for key, concepts in (("sbc", ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"]),
                          ("rd_expensed", ["ResearchAndDevelopmentExpense",
                                           "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"])):
        v, c = _value(facts, concepts, fiscal_year_end, True)
        notes[key] = {"value": v, "concept": c} if v is not None else {"value": None}
    if revenue:
        if notes["rd_expensed"]["value"] is not None:
            notes["rd_to_sales"] = {"value": notes["rd_expensed"]["value"] / revenue, "basis": "연구개발비 ÷ 매출"}
        if notes["sbc"]["value"] is not None:
            notes["sbc_to_sales"] = {"value": notes["sbc"]["value"] / revenue, "basis": "주식보상비용 ÷ 매출"}
    if notes["sbc"]["value"] is not None or notes["rd_expensed"]["value"] is not None:
        out["note_items"] = notes
    return out


# SEC SIC code -> engine kit (pe_cr_inputs.json kits).
SIC_KITS = [
    ((1000, 1099), "mining_smelting"), ((1200, 1299), "mining_smelting"), ((1400, 1499), "mining_smelting"),
    ((3330, 3341), "mining_smelting"),
    ((3674, 3674), "semiconductor"), ((3570, 3579), "it_hardware"), ((3660, 3679), "it_hardware"),
    ((7370, 7379), "it_services"), ((2833, 2836), "pharma_bio"), ((8731, 8731), "pharma_bio"),
    ((3711, 3716), "automotive"), ((2911, 2911), "refining_energy"), ((1311, 1389), "refining_energy"),
    ((4911, 4991), "utilities"), ((4812, 4899), "telecom"), ((4512, 4522), "airlines"),
    ((3720, 3729), "aerospace_defense"), ((3760, 3769), "aerospace_defense"), ((3812, 3812), "aerospace_defense"),
    ((2800, 2899), "chemicals"), ((3310, 3399), "steel_metals"), ((2000, 2111), "food_beverage"),
    ((5961, 5961), "retail_mixed"), ((5200, 5999), "retail_wholesale"), ((5000, 5199), "retail_wholesale"),
    ((1500, 1799), "construction"), ((4400, 4499), "shipping"), ((3500, 3569), "machinery"), ((3580, 3599), "machinery"),
    ((3600, 3659), "electrical_battery"), ((3690, 3699), "electrical_battery"), ((7810, 7841), "media_entertainment"),
    ((6000, 6799), "financial"),
]
SIC_FINANCIAL_KIND = [((6020, 6036), "basel"), ((6710, 6719), "basel"), ((6141, 6159), "credit_finance"),
                      ((6200, 6299), "ncr"), ((6311, 6411), "kics")]


def kit_for_sic(sic) -> str:
    try:
        n = int(sic)
    except (TypeError, ValueError):
        return "general"
    for (lo, hi), kit in SIC_KITS:
        if lo <= n <= hi:
            return kit
    return "manufacturing" if 2000 <= n <= 3999 else "general"


def financial_kind_for_sic(sic) -> str | None:
    try:
        n = int(sic)
    except (TypeError, ValueError):
        return None
    return next((k for (lo, hi), k in SIC_FINANCIAL_KIND if lo <= n <= hi), None)


# --------------------------------------------------------------------------- quarterly
Q_BALANCES = {
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "equity": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"],
    "parent_equity": ["StockholdersEquity"],
    "current_assets": ["AssetsCurrent"], "current_liabilities": ["LiabilitiesCurrent"], "liabilities": ["Liabilities"],
    "borrowings_short": ["ShortTermBorrowings", "CommercialPaper"],
    "borrowings_current_portion": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "borrowings_long": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "lease_current": ["OperatingLeaseLiabilityCurrent"], "lease_noncurrent": ["OperatingLeaseLiabilityNoncurrent"],
    "_total": ["LiabilitiesAndStockholdersEquity"],
}


def _instant(facts, concepts, end):
    for c in concepts:
        pts = [p for p in _points(facts, c) if p.get("end") == end and not p.get("start")
               and (p.get("form") or "")[:4] in ("10-Q", "10-K")]
        if pts:
            return float(max(pts, key=lambda p: p.get("filed") or "")["val"])
    return None


def _ltm_at(facts, concepts, end, fy_ends):
    if end in fy_ends:
        v, _ = _value(facts, concepts, end, True)
        return v
    prior_fy = max((e for e in fy_ends if e < end), default=None)
    if not prior_fy:
        return None
    fy, _ = _value(facts, concepts, prior_fy, True)
    for c in concepts:
        cur = [p for p in _points(facts, c) if p.get("end") == end and p.get("start")
               and (p.get("form") or "").startswith("10-Q") and p["start"] > prior_fy]
        if not cur:
            continue
        cur = max(cur, key=lambda p: (_days(p), p.get("filed") or ""))
        prior = [p for p in _points(facts, c) if p.get("start") and abs(_days(p) - _days(cur)) <= 7
                 and abs((date.fromisoformat(cur["end"]) - date.fromisoformat(p["end"])).days - 364) <= 10]
        if fy is not None and prior:
            return fy + float(cur["val"]) - float(max(prior, key=lambda p: p.get("filed") or "")["val"])
    return None


def sec_points(facts, n: int = 8) -> list[dict]:
    """Last n 10-Q/10-K balance-sheet dates, in the shape quarterly.series reads."""
    ends = sorted({p["end"] for p in _points(facts, "Assets") if not p.get("start")
                   and (p.get("form") or "")[:4] in ("10-Q", "10-K")})[-n:]
    fy_ends = set(fiscal_year_ends(facts))
    pts = []
    for e in ends:
        bal = {k: _instant(facts, c, e) for k, c in Q_BALANCES.items()}
        if bal.get("liabilities") is None and bal.get("_total") is not None and bal.get("equity") is not None:
            bal["liabilities"] = bal["_total"] - bal["equity"]
        bal = {k: v for k, v in bal.items() if v is not None and not k.startswith("_")}
        ltm = {"revenue": _ltm_at(facts, MAP[0][2], e, fy_ends), "op": _ltm_at(facts, ["OperatingIncomeLoss"], e, fy_ends)}
        pts.append({"period_end": e, "report": "10-K" if e in fy_ends else "10-Q", "balances": bal,
                    "ltm": {k: v for k, v in ltm.items() if v is not None}})
    return pts


def shares_outstanding(facts):
    pts = (((facts.get("facts") or {}).get("dei") or {}).get("EntityCommonStockSharesOutstanding") or {}).get("units", {}).get("shares") or []
    if not pts:
        return None
    last = max(p["end"] for p in pts)
    return float(sum(p["val"] for p in pts if p["end"] == last))      # all classes on the cover page
