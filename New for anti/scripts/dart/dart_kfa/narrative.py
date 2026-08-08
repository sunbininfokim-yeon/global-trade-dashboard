"""L4 — template NLG (no LLM). Deterministic sentences from metric dicts."""

from __future__ import annotations

from typing import Any


def _pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}%"


def narratives_ko(
    metrics: dict[str, Any],
    *,
    parse_status: str,
    industry: dict[str, Any] | None = None,
    ma: dict[str, Any] | None = None,
) -> list[str]:
    lines: list[str] = []
    if parse_status == "unverified":
        lines.append(
            "재무제표 검산(자산=부채+자본)이 통과하지 않아 지표는 참고용으로만 표시합니다."
        )

    if industry and industry.get("label_ko"):
        lines.append(f"산업 키트: {industry['label_ko']}.")
        bg = industry.get("background") or {}
        if bg.get("headline_ko"):
            lines.append(bg["headline_ko"])
        for note in (industry.get("notes_ko") or [])[:2]:
            lines.append(note)
        peer = (industry.get("bok_peer") or {}).get("vs") or {}
        if peer.get("available"):
            cr = (peer.get("metrics") or {}).get("current_ratio") or {}
            if cr.get("peer_avg") is not None and cr.get("firm") is not None:
                lines.append(
                    f"유동비율 {cr['firm']:.1f}% (한은 업종평균 {cr['peer_avg']:.1f}%, Δ {cr['delta']:+.1f}%p)."
                )
            dr = (peer.get("metrics") or {}).get("debt_ratio") or {}
            if dr.get("peer_avg") is not None and dr.get("firm") is not None:
                lines.append(
                    f"부채비율 {dr['firm']:.1f}% (한은 업종평균 {dr['peer_avg']:.1f}%, Δ {dr['delta']:+.1f}%p)."
                )
        for flag in industry.get("flags") or []:
            if flag.get("severity_ko"):
                lines.append(f"주의: {flag['severity_ko']}")

    cr = metrics.get("current_ratio") or {}
    if cr.get("value") is not None:
        v = float(cr["value"])
        tip = "단기 지급능력은 확보돼 있습니다." if v >= 100 else "유동부채가 유동자산을 상회합니다."
        lines.append(f"유동비율 {_pct(v)}입니다. {tip}")

    debt = metrics.get("debt_ratio") or {}
    if debt.get("value") is not None:
        lines.append(f"부채비율 {_pct(float(debt['value']))}입니다.")
        adj = (industry or {}).get("adjusted_metrics") or {}
        if "debt_ratio_ex_lease" in adj and adj["debt_ratio_ex_lease"].get("value") is not None:
            lines.append(
                f"리스 제외 부채비율 {_pct(float(adj['debt_ratio_ex_lease']['value']))}입니다."
            )
        if (
            "debt_ratio_ex_contract_liab" in adj
            and adj["debt_ratio_ex_contract_liab"].get("value") is not None
        ):
            lines.append(
                "계약부채·선수금 제외 부채비율 "
                f"{_pct(float(adj['debt_ratio_ex_contract_liab']['value']))}입니다."
            )

    om = metrics.get("operating_margin") or {}
    if om.get("value") is not None:
        lines.append(f"영업이익률 {_pct(float(om['value']))}입니다. (가정 입력 기본값으로 사용)")

    roe = metrics.get("roe") or {}
    if roe.get("value") is not None:
        lines.append(f"ROE {_pct(float(roe['value']))}입니다.")

    if ma and (ma.get("fcf") or {}).get("value") is not None:
        lines.append(f"FCF {ma['fcf']['value']:,.0f} (통화 단위는 공시와 동일).")

    eq = metrics.get("earnings_quality") or {}
    if eq.get("value") is not None:
        q = float(eq["value"])
        note = "영업현금이 회계이익을 뒷받침합니다." if q >= 1 else "영업현금이 회계이익보다 작습니다."
        lines.append(f"이익의 질(CFO/순이익) {q:.2f}배. {note}")

    if industry and industry.get("watch_notes"):
        lines.append("확인 권장 주석: " + ", ".join(industry["watch_notes"][:5]))

    if not lines:
        lines.append("산출 가능한 핵심 지표가 없습니다(계정 매핑 부족).")
    return lines
