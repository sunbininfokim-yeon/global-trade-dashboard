"""Deterministic causal checklist (원스/이코노미21 해설서 로직 — 기사 복제 아님)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _edge(
    cause: str,
    action: str,
    market: str,
    *,
    confidence: str,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "cause": cause,
        "action": action,
        "market_implication": market,
        "confidence": confidence,  # high=원문 숫자, med=원문 문구, low=해설 템플릿
        "evidence": evidence or {},
    }


def build_causal_pack(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    event keys:
      estimates: DocParse dict | None
      policy: DocParse dict | None
    """
    edges: List[Dict[str, Any]] = []
    flags: List[str] = []
    est = event.get("estimates") or {}
    pol = event.get("policy") or {}

    quarters = est.get("quarters") or []
    estimates = [q for q in quarters if q.get("kind") == "estimate"]
    actuals = [q for q in quarters if q.get("kind") == "actual"]

    if estimates:
        q0 = estimates[0]
        vs = q0.get("vs_prior_bn")
        cash = q0.get("end_cash_balance_bn")
        nb = q0.get("net_borrowing_bn")

        if vs is not None:
            if vs >= 25:
                flags.append("net_borrowing_up_vs_prior")
                edges.append(
                    _edge(
                        f"순발행 추정치 직전대비 +${vs:g}B",
                        f"{q0.get('period')} privately-held net marketable ${nb:g}B",
                        "국채 순공급↑ → 금리(특히 쿠폰 커브) 상승 압력 가능",
                        confidence="high",
                        evidence={"vs_prior_bn": vs, "net_borrowing_bn": nb},
                    )
                )
            elif vs <= -25:
                flags.append("net_borrowing_down_vs_prior")
                edges.append(
                    _edge(
                        f"순발행 추정치 직전대비 ${vs:g}B",
                        f"{q0.get('period')} privately-held net marketable ${nb:g}B",
                        "국채 순공급↓ → 수급 부담 완화 가능",
                        confidence="high",
                        evidence={"vs_prior_bn": vs, "net_borrowing_bn": nb},
                    )
                )
            else:
                flags.append("net_borrowing_near_prior")

        if cash is not None:
            if cash >= 900:
                flags.append("tga_cash_high")
                edges.append(
                    _edge(
                        f"기말 현금(TGA) 가정 ${cash:g}B (높음)",
                        "차입으로 TGA 잔고를 채우거나 유지",
                        "TGA↑는 은행 준비금·유동성 흡수 경로 (ΔReserves 항)",
                        confidence="med",
                        evidence={"end_cash_balance_bn": cash},
                    )
                )
            elif cash <= 500:
                flags.append("tga_cash_low")
                edges.append(
                    _edge(
                        f"기말 현금(TGA) 가정 ${cash:g}B (낮음)",
                        "낮은 현금 목표 → 차입 필요 축소 가능",
                        "TGA↓는 유동성 방출 경로로 해석되는 경우가 많음",
                        confidence="med",
                        evidence={"end_cash_balance_bn": cash},
                    )
                )

    bill = pol.get("bill_stance")
    coupon = pol.get("coupon_stance")

    if bill == "increase":
        flags.append("bill_auction_increase")
        edges.append(
            _edge(
                "단기 재정·현금 수요 / 계절성",
                "T-bill 입찰 규모 확대(원문)",
                "RRP·MMF·단기 금리 경로에 영향; QT(SOMA run-off) 충격 완충 서사와 자주 결합",
                confidence="med",
                evidence={"bill_stance": bill, "snippet": (pol.get("stance_snippets") or [None])[0]},
            )
        )
    elif bill == "maintain":
        flags.append("bill_auction_maintain")
        edges.append(
            _edge(
                "현재 전망 유지",
                "T-bill 벤치마크 입찰 규모 유지(원문)",
                "단기채 순발행은 재정흐름에 따라 여전히 변동 가능(입찰≠순발행)",
                confidence="med",
                evidence={"bill_stance": bill},
            )
        )
    elif bill == "reduce":
        flags.append("bill_auction_reduce")
        edges.append(
            _edge(
                "세수·현금 유입 전망",
                "T-bill 입찰 규모 축소(원문)",
                "단기 순상환 시 준비금/RRP 경로에 유동성 공급 서사",
                confidence="med",
                evidence={"bill_stance": bill},
            )
        )

    if coupon == "increase_bias":
        flags.append("coupon_increase_bias")
        edges.append(
            _edge(
                "구조적 수요·재정 전망 평가",
                "명목 쿠폰/FRN 발행 '증가(increases)' 평가(원문)",
                "장기물 공급↑ 시 장기금리 상승 압력 서사",
                confidence="med",
                evidence={"coupon_stance": coupon},
            )
        )
    elif coupon == "change_bias":
        flags.append("coupon_change_bias")
        edges.append(
            _edge(
                "재정·SOMA·수요 불확실성",
                "명목 쿠폰/FRN 발행 '변화(changes)' 평가(원문) — 증감 모두 열어둠",
                "방향 중립; 다음 분기 숫자 확인 필요",
                confidence="med",
                evidence={"coupon_stance": coupon},
            )
        )
    elif coupon == "maintain":
        flags.append("coupon_maintain")
        edges.append(
            _edge(
                "현 입찰 규모로 조달 여력 충분(원문 취지)",
                "명목 쿠폰/FRN 입찰 규모 당분간 유지",
                "쿠폰 순발행은 만기상환·바이백에 따라 달라질 수 있음",
                confidence="med",
                evidence={"coupon_stance": coupon},
            )
        )

    # Guidebook reminders (always attached as low-confidence checklist)
    edges.append(
        _edge(
            "해설서 규칙",
            "Net Marketable Borrowing ≠ 총발행; 만기상환·SOMA add-on·바이백 구분",
            "표의 NEW MONEY / TBAC 권장과 QRA 본문 순발행을 혼동하지 말 것",
            confidence="low",
            evidence={"rule": "net_vs_gross"},
        )
    )

    summary_ko_parts: List[str] = []
    if estimates:
        q0 = estimates[0]
        bit = f"{q0.get('period')} 순발행 추정 ${q0.get('net_borrowing_bn'):g}B"
        if q0.get("end_cash_balance_bn") is not None:
            bit += f", 기말현금 ${q0['end_cash_balance_bn']:g}B"
        if q0.get("vs_prior_bn") is not None:
            arrow = "▲" if q0["vs_prior_bn"] > 0 else "▼"
            bit += f" (직전대비 {arrow}${abs(q0['vs_prior_bn']):g}B)"
        summary_ko_parts.append(bit)
    if bill:
        summary_ko_parts.append(f"T-bill 스탠스={bill}")
    if coupon:
        summary_ko_parts.append(f"쿠폰 스탠스={coupon}")
    if actuals:
        a0 = actuals[0]
        summary_ko_parts.append(f"직전실적 {a0.get('period')} ${a0.get('net_borrowing_bn'):g}B")

    return {
        "flags": flags,
        "edges": edges,
        "summary_ko": " · ".join(summary_ko_parts) if summary_ko_parts else "파싱 데이터 부족",
        "limitations_ko": (
            "인과 에지는 재무부 원문 숫자/문구 + 고정 해설 템플릿이다. "
            "금리·주가 예측이 아니며, 기자 해석과의 일치는 별도 대조가 필요하다."
        ),
    }


def auctions_to_issuance_components(auctions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map refunding-week auction sizes to qra_issuance-like bars (coupons only)."""
    tenor_map = {
        "2-year": ("c2y", "2Y"),
        "3-year": ("c3y", "3Y"),
        "5-year": ("c5y", "5Y"),
        "7-year": ("c7y", "7Y"),
        "10-year": ("c10y", "10Y"),
        "20-year": ("c20y", "20Y"),
        "30-year": ("c30y", "30Y"),
    }
    by_id: Dict[str, Dict[str, Any]] = {}
    for a in auctions:
        tenor = (a.get("tenor") or "").lower()
        if tenor not in tenor_map:
            continue
        if a.get("instrument") not in ("note", "bond"):
            continue
        cid, label = tenor_map[tenor]
        by_id[cid] = {
            "id": cid,
            "label_ko": label,
            "tenor": tenor.replace("-year", "y"),
            "value": float(a["amount_bn"]),
        }
    order = ["c2y", "c3y", "c5y", "c7y", "c10y", "c20y", "c30y"]
    return [by_id[k] for k in order if k in by_id]
