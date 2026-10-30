"""Japan add-ons wired through world_public_series (the main Japan pipeline is jp_public_series.py)."""

from __future__ import annotations

from .world_public_series import Card, card

CARDS: list[Card] = [
    card("fx_intervention", "monthly", "tn_jpy", "tn_jpys", "외환개입(월)",
         "재무성 외환평형조작 실적의 월 합계(조 엔)입니다. 음수 = 달러 매도·엔 매수. 일별 내역은 분기가 끝난 뒤 공개되므로 "
         "마지막 공개 분기까지만 표시합니다(그 뒤 달은 0이 아니라 미공개). 재무성 CSV.",
         "mof:feio", "https://www.mof.go.jp/english/policy/international_policy/reference/feio/index.html",
         lambda f: f.get("mof_fx"), chart="bar"),
]
