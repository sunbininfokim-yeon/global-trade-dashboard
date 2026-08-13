"""Map SEC companyfacts → DART-like rows so L1/L2 engines reuse the same path."""

from __future__ import annotations

from typing import Any

# Standard account → preferred US-GAAP concept tags.
# Picker requires coverage for the target fiscal year (by period end date).
US_GAAP_TAGS: dict[str, list[str]] = {
    "TOTAL_ASSETS": ["Assets"],
    "CURRENT_ASSETS": ["AssetsCurrent"],
    "CASH": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
    "MARKETABLE_SECURITIES_CURRENT": ["MarketableSecuritiesCurrent"],
    "MARKETABLE_SECURITIES_NONCURRENT": ["MarketableSecuritiesNoncurrent"],
    "INVENTORIES": ["InventoryNet", "InventoryFinishedGoods"],
    "TRADE_RECEIVABLES": [
        "AccountsReceivableNetCurrent",
        "AccountsReceivableNet",
    ],
    "TOTAL_LIABILITIES": ["Liabilities"],
    "CURRENT_LIABILITIES": ["LiabilitiesCurrent"],
    "SHORT_TERM_DEBT": ["ShortTermBorrowings"],
    "LONG_TERM_DEBT_CURRENT": ["LongTermDebtCurrent"],
    "LONG_TERM_DEBT_NONCURRENT": ["LongTermDebtNoncurrent"],
    "LONG_TERM_DEBT": ["LongTermDebt"],
    "COMMERCIAL_PAPER": ["CommercialPaper"],
    "EQUITY": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "REVENUE": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ],
    "COGS": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
    ],
    "OPERATING_INCOME": ["OperatingIncomeLoss"],
    "NET_INCOME": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "INTEREST_EXPENSE": ["InterestExpense", "InterestExpenseDebt"],
    "INCOME_TAX_EXPENSE": ["IncomeTaxExpenseBenefit"],
    "PROFIT_BEFORE_TAX": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "CFO": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "CAPEX": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "LEASE_LIABILITIES": [
        "OperatingLeaseLiability",
        "LeaseLiability",
        "OperatingLeaseLiabilityCurrent",
    ],
    "DEPRECIATION": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
}

SJ = {
    "TOTAL_ASSETS": "BS",
    "CURRENT_ASSETS": "BS",
    "CASH": "BS",
    "MARKETABLE_SECURITIES_CURRENT": "BS",
    "MARKETABLE_SECURITIES_NONCURRENT": "BS",
    "INVENTORIES": "BS",
    "TRADE_RECEIVABLES": "BS",
    "TOTAL_LIABILITIES": "BS",
    "CURRENT_LIABILITIES": "BS",
    "SHORT_TERM_DEBT": "BS",
    "LONG_TERM_DEBT_CURRENT": "BS",
    "LONG_TERM_DEBT_NONCURRENT": "BS",
    "LONG_TERM_DEBT": "BS",
    "COMMERCIAL_PAPER": "BS",
    "LEASE_LIABILITIES": "BS",
    "EQUITY": "BS",
    "REVENUE": "IS",
    "COGS": "IS",
    "OPERATING_INCOME": "IS",
    "NET_INCOME": "IS",
    "INTEREST_EXPENSE": "IS",
    "INCOME_TAX_EXPENSE": "IS",
    "PROFIT_BEFORE_TAX": "IS",
    "DEPRECIATION": "IS",
    "CFO": "CF",
    "CAPEX": "CF",
}


def _period_end_year(p: dict[str, Any]) -> int | None:
    end = str(p.get("end") or "")
    if len(end) >= 4 and end[:4].isdigit():
        return int(end[:4])
    return None


def _annual_usd_points(concept: dict[str, Any]) -> list[dict[str, Any]]:
    units = concept.get("units") or {}
    series = units.get("USD") or units.get("USD/shares") or []
    out = []
    for p in series:
        if not isinstance(p, dict):
            continue
        form = (p.get("form") or "").upper()
        fp = (p.get("fp") or "").upper()
        # Prefer annual 10-K / FY
        if form not in {"10-K", "10-K/A"} and fp != "FY":
            continue
        if p.get("val") is None:
            continue
        out.append(p)
    # sort by period end then filed
    out.sort(key=lambda x: (str(x.get("end") or ""), str(x.get("filed") or "")))
    return out


def _amount_at_year(points: list[dict[str, Any]], year: int) -> float | None:
    """Pick amount for calendar/fiscal period ending in `year`.

    SEC companyfacts often repeat comparatives under the *filing* fy (e.g. fy=2025
    rows with end=2023-12-31 / 2024-12-31). Match on period end date, not filing fy.
    """
    matched = [p for p in points if _period_end_year(p) == year]
    if not matched:
        return None

    def score(p: dict[str, Any]) -> tuple:
        frame = p.get("frame") or ""
        # Prefer CY{year} / CY{year}Q4I consolidated frames, then blank frame
        if frame.startswith(f"CY{year}"):
            frame_rank = 2
        elif frame == "":
            frame_rank = 1
        else:
            frame_rank = 0
        return (str(p.get("filed") or ""), frame_rank)

    matched.sort(key=score)
    return float(matched[-1]["val"])


def _pick_tag_points(
    facts: dict[str, Any],
    tags: list[str],
    *,
    prefer_fy: int | None = None,
) -> tuple[str | None, list[dict[str, Any]]]:
    """Pick first tag that has annual USD points; if prefer_fy set, require that year."""
    gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    fallback: tuple[str | None, list[dict[str, Any]]] = (None, [])
    for tag in tags:
        concept = gaap.get(tag)
        if not concept:
            continue
        pts = _annual_usd_points(concept)
        if not pts:
            continue
        if prefer_fy is not None:
            if _amount_at_year(pts, prefer_fy) is None:
                if fallback[0] is None:
                    fallback = (tag, pts)
                continue
        return tag, pts
    return fallback


def facts_to_fnltt_payload(
    facts: dict[str, Any],
    *,
    ticker: str | None = None,
    cik: str | None = None,
    asof_fy: int | None = None,
) -> dict[str, Any]:
    """Build a DART-shaped {status, list:[rows]} for analyze_payload()."""
    entity = facts.get("entityName") or ticker or "SEC"
    # determine latest FY from Assets period ends
    _, asset_pts = _pick_tag_points(facts, US_GAAP_TAGS["TOTAL_ASSETS"])
    if not asset_pts:
        raise ValueError("no annual Assets facts found")
    end_years = sorted({y for p in asset_pts if (y := _period_end_year(p)) is not None})
    if not end_years:
        raise ValueError("no period-end years in Assets")
    fy = asof_fy or end_years[-1]
    y0, y1, y2 = fy, fy - 1, fy - 2

    rows: list[dict[str, Any]] = []
    for std, tags in US_GAAP_TAGS.items():
        tag, pts = _pick_tag_points(facts, tags, prefer_fy=fy)
        if not tag:
            continue
        th = _amount_at_year(pts, y0)
        fr = _amount_at_year(pts, y1)
        bf = _amount_at_year(pts, y2)
        if th is None and fr is None and bf is None:
            continue
        rows.append(
            {
                "rcept_no": f"SEC-{cik or ''}-{fy}",
                "reprt_code": "10-K",
                "bsns_year": str(fy),
                "corp_code": cik or "",
                "stock_code": (ticker or "").upper(),
                "fs_div": "CFS",
                "sj_div": SJ.get(std, "BS"),
                "account_id": f"us-gaap_{tag}",
                "account_nm": tag,
                "thstrm_amount": None if th is None else str(int(th) if th == int(th) else th),
                "frmtrm_amount": None if fr is None else str(int(fr) if fr == int(fr) else fr),
                "bfefrmtrm_amount": None if bf is None else str(int(bf) if bf == int(bf) else bf),
                "currency": "USD",
            }
        )

    return {
        "status": "000",
        "message": "sec-companyfacts",
        "list": rows,
        "meta": {
            "source": "sec_companyfacts",
            "entityName": entity,
            "ticker": ticker,
            "cik": cik,
            "fy": fy,
        },
    }


def shares_outstanding(facts: dict[str, Any], *, fy: int | None = None) -> float | None:
    """Best-effort common shares from DEI / us-gaap."""
    facts_root = facts.get("facts") or {}
    for taxonomy, tags in (
        ("dei", ["EntityCommonStockSharesOutstanding"]),
        ("us-gaap", ["CommonStockSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic"]),
    ):
        block = facts_root.get(taxonomy) or {}
        for tag in tags:
            concept = block.get(tag)
            if not concept:
                continue
            units = concept.get("units") or {}
            pts = units.get("shares") or units.get("pure") or []
            annual = [
                p
                for p in pts
                if isinstance(p, dict)
                and p.get("val") is not None
                and (
                    (p.get("form") or "").upper() in {"10-K", "10-K/A"}
                    or (p.get("fp") or "").upper() == "FY"
                )
            ]
            if not annual:
                annual = [p for p in pts if isinstance(p, dict) and p.get("val") is not None]
            if not annual:
                continue
            annual.sort(key=lambda x: (int(x.get("fy") or 0), str(x.get("end") or "")))
            if fy is not None:
                matched = [p for p in annual if int(p.get("fy") or 0) == fy]
                if matched:
                    return float(matched[-1]["val"])
            return float(annual[-1]["val"])
    return None
