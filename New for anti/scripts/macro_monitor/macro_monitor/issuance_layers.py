"""US Treasury issuance view stack — diachronic + static layers.

Purpose: one click on QRA should not dump every table; the UI walks a
deliberate stack so a reader gets (1) this announcement dissected, then
(2) the same numbers on a time axis, then (3) neighboring macro context.

Static  (정태)  = cross-section at one announcement / one quarter
Diachron (통시) = successive announcements, daily DTS, multi-quarter path
"""

from __future__ import annotations

from typing import Any


# Canonical layer catalogue (UI renders in band order, then sort).
# `bind` points at fields on the qra_issuance indicator (or sibling series ids).

ISSUANCE_LAYER_CATALOG: list[dict[str, Any]] = [
    # ── Hero ──────────────────────────────────────────────
    {
        "id": "L0_chip",
        "band": "hero",
        "band_ko": "표제",
        "axis": "static",
        "axis_ko": "정태 · 현재 요약",
        "sort": 0,
        "default_open": True,
        "title_ko": "당기 순발행",
        "subtitle_ko": "칩 숫자 = privately held net marketable ($B)",
        "view": "chip",
        "bind": {"fields": ["value", "display", "flags", "note_ko"]},
        "why_ko": "한 줄로 ‘지금 얼마 빌릴 계획인지’만 남긴다.",
    },
    # ── Band A: static dissection of THIS announcement ───
    {
        "id": "A1_compare",
        "band": "static_dissect",
        "band_ko": "A · 정태 해부 (이 발표)",
        "axis": "static",
        "axis_ko": "정태 · 교차 비교",
        "sort": 10,
        "default_open": True,
        "title_ko": "순발행 3-way",
        "subtitle_ko": "전분 실적 · 직전 공시 예측 · 당기 공시",
        "view": "compare_bar_table",
        "bind": {"fields": ["compare"]},
        "why_ko": (
            "같은 ‘분기 숫자’를 세 시점으로 맞춰 본다. "
            "예측 수정(▲$B)이 기사가 말하는 핵심 문장이다."
        ),
    },
    {
        "id": "A2_mix",
        "band": "static_dissect",
        "band_ko": "A · 정태 해부 (이 발표)",
        "axis": "static",
        "axis_ko": "정태 · 구성",
        "sort": 20,
        "default_open": True,
        "title_ko": "무이표(Bill) vs 이표(Coupon)",
        "subtitle_ko": "총순발행을 단기·중장기로 쪼갠 스택",
        "view": "bill_coupon_stack",
        "bind": {
            "fields": ["components", "table", "flags"],
            "derive": "group_components_by_kind",  # bill | coupon
        },
        "why_ko": "쿠폰은 거의 고정, 빌이 재정 버퍼 — 구조 한 장.",
    },
    {
        "id": "A3_maturity",
        "band": "static_dissect",
        "band_ko": "A · 정태 해부 (이 발표)",
        "axis": "static",
        "axis_ko": "정태 · 만기 구조",
        "sort": 30,
        "default_open": False,
        "title_ko": "만기별 표 · 바",
        "subtitle_ko": "T-Bill / Note / Bond · FRN 등 테너 단위",
        "view": "maturity_bar_table",
        "bind": {"fields": ["components", "table"]},
        "why_ko": "정밀 숫자는 표, 방향은 만기 바. A2의 확대경.",
    },
    {
        "id": "A4_sources_uses",
        "band": "static_dissect",
        "band_ko": "A · 정태 해부 (이 발표)",
        "axis": "static",
        "axis_ko": "정태 · 자금조달 항등식",
        "sort": 40,
        "default_open": False,
        "title_ko": "Sources & Uses",
        "subtitle_ko": "Need · Marketable · Other · ΔCash · 기말 TGA 가정",
        "view": "sources_uses_table",
        "bind": {"fields": ["sources_uses", "tga_vs_qra"]},
        "why_ko": "순발행 숫자가 ‘왜’ 그 값인지 — 필요 자금과 현금 목표.",
    },
    # ── Band B: diachronic ────────────────────────────────
    {
        "id": "B1_quarter_path",
        "band": "diachronic",
        "band_ko": "B · 통시 (시간축)",
        "axis": "diachronic",
        "axis_ko": "통시 · 분기 경로",
        "sort": 50,
        "default_open": False,
        "title_ko": "분기 순발행 궤적",
        "subtitle_ko": "공시마다의 primary estimate (라인/스파크)",
        "view": "history_line",
        "bind": {"fields": ["history_net_borrowing", "quarters"]},
        "why_ko": "한 분기가 아닌, 수년 동안 조달 규모가 어떻게 변했는지.",
    },
    {
        "id": "B2_revision",
        "band": "diachronic",
        "band_ko": "B · 통시 (시간축)",
        "axis": "diachronic",
        "axis_ko": "통시 · 예측 수정",
        "sort": 60,
        "default_open": False,
        "title_ko": "동일 분기 예측 수정",
        "subtitle_ko": "5월 공시 → 8월 공시처럼 같은 기간의 재추정",
        "view": "revision_strip",
        "bind": {
            "fields": ["sources_uses", "compare"],
            "note": "sources_uses rows with same period, different announcement_date",
        },
        "why_ko": "기사 ‘빌 3480→4090’ 패턴. 스탠스 문안보다 숫자 수정이 본심.",
    },
    {
        "id": "B3_daily_flow",
        "band": "diachronic",
        "band_ko": "B · 통시 (시간축)",
        "axis": "diachronic",
        "axis_ko": "통시 · 일별 실적",
        "sort": 70,
        "default_open": False,
        "title_ko": "DTS 순발행 · TGA 잔고",
        "subtitle_ko": "QRA 사이 실제로 얼마나 찍고 현금을 쌓았는지",
        "view": "linked_series",
        "bind": {
            "sibling_series": ["dts_marketable_net", "tga", "public_debt_outstanding"],
        },
        "why_ko": "발표는 분기, 실제 조달은 매일. 가정 vs 실적 통시.",
    },
    # ── Band C: relative coordinates ──────────────────────
    {
        "id": "C1_holder",
        "band": "context",
        "band_ko": "C · 좌표 (누가 / 유동성)",
        "axis": "static",
        "axis_ko": "정태 · 보유 주체",
        "sort": 80,
        "default_open": False,
        "title_ko": "SOMA 보유 국채",
        "subtitle_ko": "연준이 들고 있는 만기 스택 (발행 ≠ 보유)",
        "view": "linked_series",
        "bind": {"sibling_series": ["fed_ust_holdings", "fed_total_assets", "fed_ust_ops"]},
        "why_ko": "공급(발행) 옆에 수요·흡수(연준 BS)를 두면 곡선 압력이 읽힌다.",
    },
    {
        "id": "C2_liquidity",
        "band": "context",
        "band_ko": "C · 좌표 (누가 / 유동성)",
        "axis": "static",
        "axis_ko": "정태 · 시스템 유동성",
        "sort": 90,
        "default_open": False,
        "title_ko": "순유동성 · ON RRP · MTS 적자",
        "subtitle_ko": "발행이 남기는 유동성·재정 잔상",
        "view": "linked_series",
        "bind": {
            "sibling_series": [
                "net_liquidity",
                "on_rrp",
                "mts_deficit",
                "mts_receipts",
                "mts_outlays",
            ],
        },
        "why_ko": "발행 규모만 보지 말고, 은행 준비금·월간 재정 흐름까지 한 축.",
    },
]


BANDS: list[dict[str, Any]] = [
    {
        "id": "hero",
        "title_ko": "표제",
        "read_ko": "칩 한 줄 — 지금 순발행.",
    },
    {
        "id": "static_dissect",
        "title_ko": "A · 정태 해부",
        "read_ko": "이 발표를 가로로 자른다: 비교 → 빌/쿠폰 → 만기 → S&U.",
    },
    {
        "id": "diachronic",
        "title_ko": "B · 통시",
        "read_ko": "같은 메트릭을 세로(시간)로: 분기 궤적 → 재추정 → 일별 DTS/TGA.",
    },
    {
        "id": "context",
        "title_ko": "C · 좌표",
        "read_ko": "발행의 주변: 연준 보유 · 시스템 유동성 · 월간 재정.",
    },
]


def build_issuance_layers(
    *,
    available_fields: set[str] | None = None,
    available_siblings: set[str] | None = None,
) -> dict[str, Any]:
    """Filter catalog to what JSON can actually bind; always keep structure."""
    fields = available_fields or set()
    siblings = available_siblings or set()

    layers_out: list[dict[str, Any]] = []
    for layer in ISSUANCE_LAYER_CATALOG:
        row = dict(layer)
        bind = dict(layer.get("bind") or {})
        present = True
        needed = set(bind.get("fields") or [])
        if needed and fields:
            # soft: at least one field present if we have field info
            if not (needed & fields) and layer["id"] not in ("L0_chip",):
                row["data_ready"] = False
            else:
                row["data_ready"] = True
        else:
            row["data_ready"] = True
        sibs = list(bind.get("sibling_series") or [])
        if sibs and siblings:
            row["bind"] = {
                **bind,
                "sibling_series": [s for s in sibs if s in siblings] or sibs,
            }
            row["data_ready"] = bool(row["bind"]["sibling_series"])
        layers_out.append(row)

    return {
        "title_ko": "미 국채 발행 · 레이어 스택",
        "kind": "issuance_layers",
        "engine_note_ko": (
            "정태(A)를 먼저 연 뒤 통시(B)로 넘긴다. "
            "기사처럼 표·순발행·분기를 한 덩어리로 쏟지 말고 밴드 단위로 쌓는다."
        ),
        "read_path_ko": [
            "L0 칩 → A1 3-way 비교 (기본)",
            "A2 빌|쿠폰 → 필요 시 A3 만기 표",
            "A4 Sources&Uses (왜 그 숫자인지)",
            "B1 분기 궤적 → B2 재추정 → B3 일별 DTS/TGA",
            "C 연준 보유·순유동성·MTS (좌표)",
        ],
        "bands": BANDS,
        "layers": layers_out,
        "ui": {
            "drawer": "issuance_layers",
            "default_layer_id": "A1_compare",
            "band_tabs": [b["id"] for b in BANDS if b["id"] != "hero"],
            # hero always sticky on top of drawer
            "hero_layer_id": "L0_chip",
        },
    }


def attach_issuance_layers(indicator: dict[str, Any], sibling_ids: set[str] | None = None) -> None:
    """Mutate qra_issuance (or similar) with layers + ui.layers pointer."""
    fields = {k for k, v in indicator.items() if v is not None}
    payload = build_issuance_layers(
        available_fields=fields,
        available_siblings=sibling_ids,
    )
    indicator["issuance_layers"] = payload
    ui = indicator.setdefault("ui", {})
    ui["layers_view"] = "issuance_layers"
    # keep existing compare as first-open; layers document the rest
    ui.setdefault("click_view", "compare_bar_table")
    ui["layer_default"] = "A1_compare"
