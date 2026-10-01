"""Russia add-ons wired through world_public_series (the main Russia pipeline is ru_public_series.py)."""

from __future__ import annotations

from .world_public_series import IMF_URL, Card, card, imf_current_account

CARDS: list[Card] = [
    card("current_account", "quarterly", "bn_usd", "bn1usds", "경상수지",
         "경상수지(분기, 십억 달러)입니다. IMF 국제수지 통계(러시아은행 보고 기반).", "imf:BOP:CAB", IMF_URL,
         imf_current_account("RUS")),
]
