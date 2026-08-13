"""Compose liquidity panel bias from structured events."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def compute_liquidity_bias(
    *,
    qra_signals: List[str],
    beige_tone: Optional[str],
    rules: Dict[str, Any],
    reporter_signals: Optional[List[str]] = None,
) -> Dict[str, Any]:
    weights = rules.get("bias_weights", {})
    score = 0.0
    drivers: List[str] = []

    for sig in qra_signals:
        w = float(weights.get(sig, 0.0))
        if w:
            score += w
            drivers.append(sig)

    if beige_tone == "soft":
        score += float(weights.get("beige_book_soft", 0.0))
        drivers.append("beige_book_soft")
    elif beige_tone == "firm":
        score += float(weights.get("beige_book_tight", 0.0))
        drivers.append("beige_book_firm")

    for sig in reporter_signals or []:
        w = float(weights.get(sig, 0.0))
        if w:
            score += w
            drivers.append(sig)

    if score >= 0.8:
        bias = "tightening"
        headline = "유동성: 재무부 순발행·현금 잔고 신호가 타이트 쪽으로 기울음"
    elif score <= -0.8:
        bias = "easing"
        headline = "유동성: 발행·현금 신호가 완화 쪽으로 기울음"
    elif abs(score) >= 0.3:
        bias = "mixed"
        headline = "유동성: 공식 신호 혼조"
    else:
        bias = "neutral"
        headline = "유동성: 신규 공식 시그널 약함 또는 대기"

    # Append reporter theme if present
    if any(s.startswith("reporter_") for s in drivers):
        headline = headline + " · 지정기자 분석 테마 반영"

    return {
        "bias": bias,
        "score": round(score, 3),
        "headline_ko": headline,
        "drivers": drivers,
    }
