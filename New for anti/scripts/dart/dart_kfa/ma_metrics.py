"""M&A / sell-side style derived metrics from resolved amounts."""

from __future__ import annotations

from typing import Any


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _cell(
    value: float | None, *, unit: str, label: str, reason: str | None = None
) -> dict[str, Any]:
    return {
        "value": None if value is None else round(value, 4),
        "unit": unit,
        "label": label,
        "reason": reason,
    }


def _sum_present(*vals: float | None) -> float | None:
    present = [v for v in vals if v is not None]
    if not present:
        return None
    return float(sum(present))


def compute_ma_metrics(
    amounts: dict[str, float | None],
    base_metrics: dict[str, Any] | None = None,
    *,
    entity_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic M&A screen metrics. Missing inputs → null + reason."""
    base_metrics = base_metrics or {}
    cash = _f(amounts.get("CASH"))
    msi_c = _f(amounts.get("MARKETABLE_SECURITIES_CURRENT"))
    msi_nc = _f(amounts.get("MARKETABLE_SECURITIES_NONCURRENT"))
    total_liab = _f(amounts.get("TOTAL_LIABILITIES"))
    current_liab = _f(amounts.get("CURRENT_LIABILITIES"))
    revenue = _f(amounts.get("REVENUE"))
    opinc = _f(amounts.get("OPERATING_INCOME"))
    cfo = _f(amounts.get("CFO"))
    capex = _f(amounts.get("CAPEX"))
    da = _f(amounts.get("DEPRECIATION"))
    lease = _f(amounts.get("LEASE_LIABILITIES"))
    contract = _f(amounts.get("CONTRACT_LIABILITIES"))
    interest = _f(amounts.get("INTEREST_EXPENSE"))
    std = _f(amounts.get("SHORT_TERM_DEBT"))
    ltd_c = _f(amounts.get("LONG_TERM_DEBT_CURRENT"))
    ltd_nc = _f(amounts.get("LONG_TERM_DEBT_NONCURRENT"))
    cp = _f(amounts.get("COMMERCIAL_PAPER"))
    # Some filings only expose aggregated LongTermDebt
    ltd_all = _f(amounts.get("LONG_TERM_DEBT"))

    fcf_cell = base_metrics.get("fcf") or {}
    fcf = _f(fcf_cell.get("value"))
    if fcf is None and cfo is not None and capex is not None:
        fcf = cfo - abs(capex)

    cash_and_investments = _sum_present(cash, msi_c, msi_nc)
    cash_investments_complete = cash is not None and msi_c is not None and msi_nc is not None

    # A usable debt bridge needs explicit current and non-current buckets.
    # Missing concepts are not assumed to be zero.
    # Current maturities and short-term funding are different buckets.  One
    # present tag cannot silently prove the other is zero.
    current_debt_present = ltd_c is not None and (std is not None or cp is not None)
    noncurrent_debt_present = ltd_nc is not None or ltd_all is not None
    if ltd_nc is not None:
        gross_debt = _sum_present(std, ltd_c, ltd_nc, cp)
    elif ltd_all is not None:
        gross_debt = _sum_present(std, ltd_all, cp)
    else:
        gross_debt = _sum_present(std, ltd_c, cp)
    debt_components_complete = current_debt_present and noncurrent_debt_present
    if gross_debt is None:
        gross_reason = "missing:interest_bearing_debt_tags"
    elif not debt_components_complete:
        gross_reason = "partial:current_and_noncurrent_debt_components_required"
    else:
        gross_reason = None

    net_debt = None
    net_debt_reason = None
    if (
        gross_debt is not None
        and debt_components_complete
        and cash_and_investments is not None
        and cash_investments_complete
    ):
        net_debt = gross_debt - cash_and_investments
    else:
        missing = []
        if not debt_components_complete:
            missing.append("complete_debt_components")
        if not cash_investments_complete:
            missing.append("cash_and_marketable_securities_coverage")
        net_debt_reason = "partial:" + ",".join(missing) if missing else "missing:gross_debt_or_cash"

    # Legacy proxy kept for diagnostics (NOT primary net debt)
    noncurrent_liab = None
    if total_liab is not None and current_liab is not None:
        noncurrent_liab = total_liab - current_liab
    legacy_ncl_minus_cash = None
    if noncurrent_liab is not None and cash is not None:
        legacy_ncl_minus_cash = noncurrent_liab - cash

    net_debt_incl_lease = None
    if net_debt is not None and lease is not None:
        net_debt_incl_lease = net_debt + lease

    ebitda_proxy = None
    ebitda_reason = None
    if opinc is not None and da is not None:
        ebitda_proxy = opinc + abs(da)
    elif opinc is not None:
        ebitda_reason = "missing:depreciation_for_ebitda_proxy"

    net_debt_ebitda = None
    nde_reason = None
    if net_debt is not None and ebitda_proxy not in (None, 0):
        net_debt_ebitda = net_debt / ebitda_proxy
    else:
        nde_reason = "missing:net_debt_or_ebitda"

    fcf_margin = None
    if fcf is not None and revenue not in (None, 0):
        fcf_margin = 100.0 * fcf / revenue

    cfo_to_ebitda = None
    if cfo is not None and ebitda_proxy not in (None, 0):
        cfo_to_ebitda = cfo / ebitda_proxy

    net_cash = None
    if net_debt is not None:
        net_cash = -net_debt

    interest_burden = None
    ib_reason = "missing:interest_or_oi"
    if interest is not None and opinc not in (None, 0):
        interest_burden = interest / abs(opinc)
        ib_reason = None

    # Interest coverage = EBIT(operating income) / interest (standard "x" times).
    interest_coverage = None
    ic_reason = "missing:interest_or_oi"
    if interest is not None and interest != 0 and opinc is not None:
        interest_coverage = opinc / abs(interest)
        ic_reason = None

    # Rough all-in coupon proxy from P&L + balance-sheet stock — NOT a TRACE YTM.
    effective_interest_rate_pct = None
    eir_reason = "missing:interest_or_gross_debt"
    if interest is not None and gross_debt not in (None, 0) and debt_components_complete:
        effective_interest_rate_pct = 100.0 * abs(interest) / abs(gross_debt)
        eir_reason = "proxy:interest_expense_over_gross_ib_debt"

    out = {
        "fcf": _cell(fcf, unit="currency", label="FCF", reason=fcf_cell.get("reason")),
        "fcf_margin": _cell(
            fcf_margin,
            unit="pct",
            label="FCF 마진",
            reason=None if fcf_margin is not None else "missing:fcf_or_revenue",
        ),
        "ebitda_proxy": _cell(
            ebitda_proxy, unit="currency", label="EBITDA 대용", reason=ebitda_reason
        ),
        "gross_interest_bearing_debt": _cell(
            gross_debt,
            unit="currency",
            label="이자부 총차입금",
            reason=gross_reason,
        ),
        "cash_and_marketable_securities": _cell(
            cash_and_investments,
            unit="currency",
            label="현금+시장성유가증권",
            reason=(
                None
                if cash_investments_complete
                else "partial:cash_and_marketable_securities_coverage"
            ),
        ),
        "net_debt": _cell(
            net_debt,
            unit="currency",
            label="순차입금(이자부−현금−유가증권)",
            reason=net_debt_reason,
        ),
        "net_debt_proxy": _cell(
            legacy_ncl_minus_cash,
            unit="currency",
            label="(레거시) 비유동부채−현금",
            reason="legacy_proxy_not_net_debt"
            if legacy_ncl_minus_cash is not None
            else "missing:noncurrent_liab_or_cash",
        ),
        "net_debt_incl_lease": _cell(
            net_debt_incl_lease,
            unit="currency",
            label="순차입+리스",
            reason=(
                None
                if net_debt_incl_lease is not None
                else ("missing:lease_liabilities" if net_debt is not None else net_debt_reason)
            ),
        ),
        "net_debt_to_ebitda": _cell(
            net_debt_ebitda,
            unit="x",
            label="Net Debt/EBITDA",
            reason=nde_reason,
        ),
        "net_cash": _cell(
            net_cash,
            unit="currency",
            label="순현금(= −순차입)",
            reason=None if net_cash is not None else net_debt_reason,
        ),
        "cfo_to_ebitda": _cell(
            cfo_to_ebitda,
            unit="x",
            label="CFO/EBITDA",
            reason=None if cfo_to_ebitda is not None else "missing:cfo_or_ebitda",
        ),
        "interest_burden": _cell(
            interest_burden, unit="x", label="이자/영업이익", reason=ib_reason
        ),
        "interest_coverage": _cell(
            interest_coverage,
            unit="x",
            label="이자보상배율(영업이익/이자)",
            reason=ic_reason,
        ),
        "effective_interest_rate_pct": _cell(
            effective_interest_rate_pct,
            unit="pct",
            label="유효이자율 대용(이자비용/이자부차입)",
            reason=eir_reason,
        ),
        "lease_to_liabilities": _cell(
            None
            if lease is None or total_liab in (None, 0)
            else 100.0 * lease / abs(total_liab),
            unit="pct",
            label="리스부채/총부채",
            reason=None if lease is not None else "missing:LEASE_LIABILITIES",
        ),
        "contract_liab_to_liabilities": _cell(
            None
            if contract is None or total_liab in (None, 0)
            else 100.0 * contract / abs(total_liab),
            unit="pct",
            label="계약부채/총부채",
            reason=None if contract is not None else "missing:CONTRACT_LIABILITIES",
        ),
        "notes_ko": [
            "FCF = CFO − |Capex| (DART 음수·SEC 양수 Capex 모두 처리).",
            "순차입 = 이자부차입(단기차입·유동성장기차입·장기차입·CP) − (현금+유동/비유동 시장성유가증권).",
            "레거시 net_debt_proxy(비유동부채−현금)는 진단용이며 순차입이 아닙니다.",
            "이자보상배율 = 영업이익 / |이자비용| (EBIT 정의를 공시 영업이익으로 근사).",
            "유효이자율 대용 = |이자비용| / 이자부차입. 신규 발행 쿠폰·YTM이 아님.",
        ],
    }
    if (entity_policy or {}).get("is_financial_entity"):
        # Every item in this pack assumes industrial debt, cash conversion or
        # EBITDA.  Keeping a raw partial value would invite an unsafe EV/FCF
        # interpretation, so the entire M&A layer is explicitly unavailable.
        from .entity_policy import not_applicable_cell

        for key, cell in list(out.items()):
            if isinstance(cell, dict) and "value" in cell:
                out[key] = not_applicable_cell(cell, "not_applicable:financial_entity_ma_metric")
        out["notes_ko"] = ["금융업 발행사는 산업기업 M&A·현금흐름·순차입 지표를 계산하지 않습니다."]
    return out
