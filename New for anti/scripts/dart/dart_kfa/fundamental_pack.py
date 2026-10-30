"""Practitioner-style fundamental pack (equity / credit / corp-fin desk).

Not a beginner tutorial dump. Surfaces the handful of lenses desks actually
use day-to-day, with 3y trends and YoY deltas where filings allow.
"""

from __future__ import annotations

from typing import Any


PACK_VERSION = "kfa-fundamental-pack-1.0.0"


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _cell(bag: dict[str, Any] | None, key: str) -> float | None:
    if not bag:
        return None
    v = bag.get(key)
    if isinstance(v, dict):
        return _f(v.get("value"))
    return _f(v)


def _trend(metrics: dict[str, Any], mid: str) -> list[float | None] | None:
    cell = metrics.get(mid) or {}
    t = cell.get("trend_3y")
    if not isinstance(t, list) or not t:
        return None
    return [_f(x) for x in t]


def _yoy(series: list[float | None] | None) -> float | None:
    """Last vs previous, as percent change when both positive-ish numbers."""
    if not series or len(series) < 2:
        return None
    a, b = series[-2], series[-1]
    if a is None or b is None or a == 0:
        return None
    return round(100.0 * (b - a) / abs(a), 2)


def _delta_pp(series: list[float | None] | None) -> float | None:
    """Percentage-point change for ratio series already in pct units."""
    if not series or len(series) < 2:
        return None
    a, b = series[-2], series[-1]
    if a is None or b is None:
        return None
    return round(b - a, 2)


def _traffic(status: str) -> str:
    return status  # ok | watch | risk | n/a


def _growth_status(rev_yoy: float | None, om_pp: float | None) -> str:
    if rev_yoy is None and om_pp is None:
        return _traffic("n/a")
    # soft rules — descriptive, not a rating agency model
    if rev_yoy is not None and rev_yoy <= -10:
        return _traffic("risk")
    if om_pp is not None and om_pp <= -3:
        return _traffic("watch")
    if rev_yoy is not None and rev_yoy < 0:
        return _traffic("watch")
    return _traffic("ok")


def _cash_status(eq: float | None, fcf: float | None, fcf_yoy: float | None) -> str:
    if eq is not None and eq < 0.7:
        return _traffic("risk")
    if fcf is not None and fcf < 0:
        return _traffic("risk")
    if fcf_yoy is not None and fcf_yoy <= -25:
        return _traffic("watch")
    if eq is not None and eq < 1.0:
        return _traffic("watch")
    return _traffic("ok")


def _leverage_status(nd_ebitda: float | None, net_debt: float | None) -> str:
    if net_debt is not None and net_debt < 0:
        return _traffic("ok")  # net cash
    if nd_ebitda is None:
        return _traffic("n/a")
    if nd_ebitda >= 4.0:
        return _traffic("risk")
    if nd_ebitda >= 2.5:
        return _traffic("watch")
    return _traffic("ok")


def _returns_status(roe: float | None, om: float | None) -> str:
    if roe is None and om is None:
        return _traffic("n/a")
    if om is not None and om < 5:
        return _traffic("watch")
    if roe is not None and roe < 8:
        return _traffic("watch")
    return _traffic("ok")


def build_fundamental_pack(
    *,
    corp: dict[str, Any] | None,
    period: dict[str, Any] | None,
    metrics: dict[str, Any],
    ma: dict[str, Any],
    industry: dict[str, Any] | None = None,
    valuation: dict[str, Any] | None = None,
    market: dict[str, Any] | None = None,
    amounts_current: dict[str, float | None] | None = None,
    amounts_prior: dict[str, float | None] | None = None,
    amounts_prior2: dict[str, float | None] | None = None,
    entity_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a desk-style fundamental brief from KFA outputs."""
    industry = industry or {}
    amounts_current = amounts_current or {}
    amounts_prior = amounts_prior or {}
    amounts_prior2 = amounts_prior2 or {}

    if (entity_policy or {}).get("is_financial_entity"):
        # This function otherwise reads raw CFO, Capex and debt amounts into
        # cash/leverage bridges.  Financial issuers therefore return only
        # filing-led safe fields rather than a cosmetically empty industrial
        # desk brief.
        return {
            "schema_version": PACK_VERSION,
            "style": "financial_entity_safe",
            "disclaimer_ko": "공시 기반 정리이며 투자의견·신용등급이 아닙니다.",
            "corp": corp,
            "period": period,
            "entity_policy": entity_policy,
            "safe_metrics": {
                "reported_operating_income": _f(amounts_current.get("OPERATING_INCOME")),
                "net_income": _f(amounts_current.get("NET_INCOME")),
                "equity": _f(amounts_current.get("EQUITY")),
                "total_assets": _f(amounts_current.get("TOTAL_ASSETS")),
                "roe_pct": _cell(metrics, "roe"),
                "roa_pct": _cell(metrics, "roa"),
            },
            "not_applicable": (entity_policy.get("safe_output_policy") or {}).get("not_applicable") or [],
            "valuation_context": {
                "status": "not_applicable",
                "reason": "not_applicable:financial_entity_industrial_valuation",
            },
            "method_ko": [
                "금융업은 보고 영업이익·순이익·자본·자산 중심으로 표시합니다.",
                "산업기업 CFO/FCF·순차입·유동성·EBITDA·DCF/EV 산식은 적용하지 않습니다.",
            ],
        }

    rev = [
        _f(amounts_prior2.get("REVENUE")),
        _f(amounts_prior.get("REVENUE")),
        _f(amounts_current.get("REVENUE")),
    ]
    ni = [
        _f(amounts_prior2.get("NET_INCOME")),
        _f(amounts_prior.get("NET_INCOME")),
        _f(amounts_current.get("NET_INCOME")),
    ]
    oi = [
        _f(amounts_prior2.get("OPERATING_INCOME")),
        _f(amounts_prior.get("OPERATING_INCOME")),
        _f(amounts_current.get("OPERATING_INCOME")),
    ]

    om_t = _trend(metrics, "operating_margin")
    nm_t = _trend(metrics, "net_margin")
    roe_t = _trend(metrics, "roe")
    fcf_t = _trend(metrics, "fcf")
    eq_t = _trend(metrics, "earnings_quality")
    inv_t = _trend(metrics, "inventory_turnover")
    cr_t = _trend(metrics, "current_ratio")
    dr_t = _trend(metrics, "debt_ratio")

    fcf = _cell(ma, "fcf")
    if fcf is None:
        fcf = _cell(metrics, "fcf")
    fcf_m = _cell(ma, "fcf_margin")
    ebitda = _cell(ma, "ebitda_proxy")
    gross_debt = _cell(ma, "gross_interest_bearing_debt")
    cash_msi = _cell(ma, "cash_and_marketable_securities")
    net_debt = _cell(ma, "net_debt")
    nd_ebitda = _cell(ma, "net_debt_to_ebitda")
    eq = _cell(metrics, "earnings_quality")
    om = _cell(metrics, "operating_margin")
    nm = _cell(metrics, "net_margin")
    roe = _cell(metrics, "roe")
    roa = _cell(metrics, "roa")

    rev_yoy = _yoy(rev)
    ni_yoy = _yoy(ni)
    fcf_yoy = _yoy(fcf_t)
    om_pp = _delta_pp(om_t)

    # Peer snapshot (BOK) — Korea context; still useful as structural benchmark
    peer_vs = ((industry.get("bok_peer") or {}).get("vs") or {}).get("metrics") or {}
    peer_lines = []
    for key in ("operating_margin_vs_peer_net_margin", "net_margin", "debt_ratio", "current_ratio"):
        cell = peer_vs.get(key)
        if not isinstance(cell, dict):
            continue
        peer_lines.append(
            {
                "id": key,
                "firm": cell.get("firm") or cell.get("firm_operating_margin"),
                "peer_avg": cell.get("peer_avg") or cell.get("peer_net_margin"),
                "vs_peer": cell.get("vs_peer"),
                "note_ko": cell.get("note_ko"),
            }
        )

    mk = market or {}
    multiples = (mk.get("multiples") if mk.get("ok") else None) or mk.get("multiples") or {}
    quote = (mk.get("quote") if mk.get("ok") else None) or {}

    band = (valuation or {}).get("value_band") or {}
    dcf_mid = band.get("value_per_share_mid")
    px = _f(quote.get("price") or multiples.get("price"))
    dcf_gap_pct = None
    if dcf_mid is not None and px not in (None, 0):
        dcf_gap_pct = round(100.0 * (float(dcf_mid) / float(px) - 1.0), 1)

    flags = list(industry.get("flags") or [])
    kit = industry.get("industry_kit")
    notes = list(industry.get("notes_ko") or [])
    bg = industry.get("background") or {}
    if bg.get("headline_ko"):
        notes = [bg["headline_ko"], *notes]

    # Finance-subsidiary / leverage optical distortion — common desk comment
    desk_notes: list[str] = []
    if nd_ebitda is not None and _cell(metrics, "debt_ratio") is not None:
        dr = _cell(metrics, "debt_ratio")
        if dr is not None and dr > 200 and nd_ebitda < 3:
            desk_notes.append(
                "부채비율은 높은데 Net Debt/EBITDA는 관리 가능 구간 — "
                "금융자회사·운전자본성 차입·자사주(자본 축소) 착시 여부를 확인하세요."
            )
    if eq is not None and eq >= 1.0 and fcf is not None and fcf > 0:
        desk_notes.append("이익의 질·FCF가 흑자 — 회계이익이 현금으로 뒷받침되는 편입니다.")
    if om_pp is not None and om_pp <= -2:
        desk_notes.append(
            f"영업이익률이 전년 대비 {om_pp:.1f}%p — 사이클·믹스·원가 중 무엇을 보는지 분리하세요."
        )
    if inv_t and inv_t[-1] is not None and inv_t[-1] < 4:
        desk_notes.append(
            "재고회전이 낮은 편(중장비·제조 전형) — 수요 둔화 시 재고·NWC 리스크를 같이 봅니다."
        )

    scorecard = [
        {
            "id": "growth",
            "label_ko": "성장",
            "status": _growth_status(rev_yoy, om_pp),
            "primary": {"revenue_yoy_pct": rev_yoy, "ni_yoy_pct": ni_yoy},
            "lens_ko": "Equity: YoY 매출·이익. 사이클 업종은 절대 레벨보다 방향·피크 여부를 봄.",
        },
        {
            "id": "profitability",
            "label_ko": "수익성",
            "status": _returns_status(roe, om),
            "primary": {
                "operating_margin_pct": om,
                "net_margin_pct": nm,
                "om_yoy_pp": om_pp,
            },
            "lens_ko": "Equity/IB: 영업마진 추세가 핵심. 피어 대비 구조적 프리미엄·디스카운트.",
        },
        {
            "id": "cash_conversion",
            "label_ko": "현금전환",
            "status": _cash_status(eq, fcf, fcf_yoy),
            "primary": {
                "cfo_to_ni": eq,
                "fcf": fcf,
                "fcf_margin_pct": fcf_m,
                "fcf_yoy_pct": fcf_yoy,
            },
            "lens_ko": "Credit/Equity: CFO/NI·FCF. M&A는 FCF와 NWC 변동을 실사 핵심으로 봄.",
        },
        {
            "id": "leverage",
            "label_ko": "레버리지",
            "status": _leverage_status(nd_ebitda, net_debt),
            "primary": {
                "net_debt": net_debt,
                "net_debt_to_ebitda": nd_ebitda,
                "gross_debt": gross_debt,
                "cash_and_msi": cash_msi,
                "interest_coverage": _cell(ma, "interest_coverage"),
                "effective_interest_rate_pct": _cell(ma, "effective_interest_rate_pct"),
            },
            "lens_ko": "Credit/M&A: Net Debt/EBITDA·이자보상배율이 본지표. 총부채/자본만 보면 금융자회사에서 왜곡.",
        },
        {
            "id": "returns",
            "label_ko": "자본수익률",
            "status": _returns_status(roe, om),
            "primary": {"roe_pct": roe, "roa_pct": roa},
            "lens_ko": "Equity: ROE는 자사주·레버리지에 민감. 가능하면 ROIC와 같이 해석.",
        },
    ]

    # Compact 3y table — what a one-pager actually prints
    trend_rows = []
    for label, series, unit in (
        ("Revenue", rev, "currency"),
        ("Operating income", oi, "currency"),
        ("Net income", ni, "currency"),
        ("Operating margin", om_t, "pct"),
        ("Net margin", nm_t, "pct"),
        ("ROE", roe_t, "pct"),
        ("FCF", fcf_t or [None, None, fcf], "currency"),
        ("CFO/NI", eq_t, "x"),
        ("Inventory turnover", inv_t, "x"),
        ("Current ratio", cr_t, "pct"),
        ("Debt ratio", dr_t, "pct"),
    ):
        if series is None or all(x is None for x in series):
            continue
        trend_rows.append(
            {
                "metric": label,
                "unit": unit,
                "y_2": series[0] if len(series) > 0 else None,
                "y_1": series[1] if len(series) > 1 else None,
                "y_0": series[2] if len(series) > 2 else None,
                "yoy": _yoy(series) if unit == "currency" else _delta_pp(series),
                "yoy_unit": "pct" if unit == "currency" else ("pp" if unit == "pct" else "Δ"),
            }
        )

    # Headline in desk tone
    name = (corp or {}).get("name") or (corp or {}).get("code") or "Issuer"
    bits = []
    if rev_yoy is not None:
        bits.append(f"매출 YoY {rev_yoy:+.1f}%")
    if om is not None:
        bits.append(f"OPM {om:.1f}%")
    if nd_ebitda is not None:
        bits.append(f"ND/EBITDA {nd_ebitda:.2f}x")
    elif net_debt is not None and net_debt < 0:
        bits.append("순현금")
    if fcf is not None:
        bits.append("FCF+" if fcf >= 0 else "FCF-")
    headline = f"{name}: " + ", ".join(bits) if bits else f"{name}: fundamental pack"

    return {
        "schema_version": PACK_VERSION,
        "style": "practitioner_desk",
        "disclaimer_ko": "공시·시세 기반 정리이며 투자의견·신용등급이 아닙니다.",
        "corp": corp,
        "period": period,
        "industry_kit": kit,
        "headline_ko": headline,
        "scorecard": scorecard,
        "trend_3y": {
            "columns_ko": ["2년전", "1년전", "당기"],
            "rows": trend_rows,
        },
        "cash_bridge": {
            "cfo": _f(amounts_current.get("CFO")),
            "capex_abs": None
            if amounts_current.get("CAPEX") is None
            else abs(float(amounts_current["CAPEX"])),
            "fcf": fcf,
            "fcf_margin_pct": fcf_m,
            "earnings_quality_cfo_ni": eq,
        },
        "leverage_bridge": {
            "gross_interest_bearing_debt": gross_debt,
            "cash_and_marketable_securities": cash_msi,
            "net_debt": net_debt,
            "ebitda_proxy": ebitda,
            "net_debt_to_ebitda": nd_ebitda,
            "note_ko": "Net Debt = 이자부차입 − (현금+시장성유가증권). 리스 포함본은 ma_metrics.net_debt_incl_lease.",
        },
        "returns_block": {
            "operating_margin_pct": om,
            "net_margin_pct": nm,
            "roe_pct": roe,
            "roa_pct": roa,
            "asset_turnover": _cell(metrics, "asset_turnover"),
            "inventory_turnover": _cell(metrics, "inventory_turnover"),
        },
        "peer_context": {
            "source_ko": "한국은행 기업경영분석 업종평균(구조 비교용). 미국 발행사 peer 대용은 아님.",
            "lines": peer_lines,
        },
        "market_multiples": {
            "price": px,
            "market_cap": multiples.get("market_cap"),
            "per": multiples.get("per"),
            "pbr": multiples.get("pbr"),
            "ev_ebitda": multiples.get("ev_ebitda"),
            "available": bool(multiples.get("market_cap") or px),
        },
        "valuation_context": {
            "dcf_value_per_share_mid": dcf_mid,
            "dcf_band": {
                "low": band.get("value_per_share_low"),
                "high": band.get("value_per_share_high"),
            },
            "vs_market_pct": dcf_gap_pct,
            "note_ko": "DCF는 가정 밴드. 시가와 괴리 = 시장 기대 vs 모델 가정의 차이로 해석.",
        },
        "flags": flags,
        "desk_notes_ko": desk_notes + notes[:4],
        "method_ko": [
            "1) 성장·마진 3년 방향",
            "2) 현금전환(CFO/NI, FCF)",
            "3) Net Debt/EBITDA (연결 부채비율은 보조)",
            "4) 시세 배수 + (선택) DCF 가정 민감도",
            "5) 업종 왜곡(금융자회사·재고·계약부채) 플래그",
        ],
    }


def attach_market_to_pack(
    pack: dict[str, Any],
    *,
    market: dict[str, Any] | None,
    valuation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Patch market multiples / DCF vs price after live quote attach."""
    if not pack:
        return pack
    out = dict(pack)
    mk = market or {}
    multiples = (mk.get("multiples") if mk.get("ok") else None) or mk.get("multiples") or {}
    quote = (mk.get("quote") if mk.get("ok") else None) or {}
    px = _f(quote.get("price") or multiples.get("price"))
    band = (valuation or {}).get("value_band") or out.get("valuation_context", {}).get("dcf_band") or {}
    # normalize band keys
    if "low" not in band and "value_per_share_low" in ((valuation or {}).get("value_band") or {}):
        vb = (valuation or {}).get("value_band") or {}
        band = {
            "low": vb.get("value_per_share_low"),
            "high": vb.get("value_per_share_high"),
        }
        dcf_mid = vb.get("value_per_share_mid")
    else:
        dcf_mid = out.get("valuation_context", {}).get("dcf_value_per_share_mid")
        if valuation and (valuation.get("value_band") or {}).get("value_per_share_mid") is not None:
            dcf_mid = valuation["value_band"]["value_per_share_mid"]
            vb = valuation["value_band"]
            band = {
                "low": vb.get("value_per_share_low"),
                "high": vb.get("value_per_share_high"),
            }

    dcf_gap_pct = None
    if dcf_mid is not None and px not in (None, 0):
        dcf_gap_pct = round(100.0 * (float(dcf_mid) / float(px) - 1.0), 1)

    out["market_multiples"] = {
        "price": px,
        "market_cap": multiples.get("market_cap"),
        "per": multiples.get("per"),
        "pbr": multiples.get("pbr"),
        "ev_ebitda": multiples.get("ev_ebitda"),
        "available": bool(multiples.get("market_cap") or px),
    }
    out["valuation_context"] = {
        "dcf_value_per_share_mid": dcf_mid,
        "dcf_band": band,
        "vs_market_pct": dcf_gap_pct,
        "note_ko": "DCF는 가정 밴드. 시가와 괴리 = 시장 기대 vs 모델 가정의 차이로 해석.",
    }
    return out
