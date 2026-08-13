"""Indicator explainers (how to read) — complement, do not replace, limitations.

0.34 direction: limitations(inference caveats) → explainers(reading guide).
0.32 ships USA-first explainers; other kits fall back to limitations items.
"""

from __future__ import annotations

from typing import Any


def _item(
    id: str,
    title_ko: str,
    body_ko: str,
    *,
    series_ids: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": id,
        "title_ko": title_ko,
        "body_ko": body_ko,
    }
    if series_ids:
        out["series_ids"] = series_ids
    return out


# USA reading guides (not just "what we cannot know")
USA_EXPLAINERS: list[dict[str, Any]] = [
    _item(
        "cpi_dual_components",
        "CPI: 헤드라인·근원 한 칩, 구성은 클릭",
        (
            "칩은 Headline YoY | Core YoY 한 칸이다. "
            "주거·식료·에너지·서비스 기여도는 components / inflation_breakdown 클릭에서 본다. "
            "Dallas Trimmed Mean은 극단값을 잘라 본 기저 축으로 옆에 둔다. "
            "BEI는 미국 TIPS 기대물가 참고용이며 칩에서는 숨긴다."
        ),
        series_ids=["cpi_yoy", "core_cpi_yoy", "trimmed_mean_cpi"],
    ),
    _item(
        "gdp_dual_components",
        "GDP: YoY|QoQ 칩, 기여도는 구성",
        (
            "칩 표시는 YoY | QoQ(비연율). SAAR 연율 칩은 쓰지 않는다. "
            "소비·투자·정부·순수출 기여는 components로 분해한다."
        ),
        series_ids=["gdp", "gdp_yoy", "gdp_qoq"],
    ),
    _item(
        "labor_cross_check",
        "노동: NFP 단독 금지, 교차확인",
        (
            "NFP 월별 증감은 개정 폭이 크다. 실업률(앵커≈4.2), Initial Claims, Sahm과 같이 본다. "
            "NFP는 실업률 대체가 아니다. AHE·JOLTS 등은 이후 확장 예정."
        ),
        series_ids=["nfp", "unemployment", "initial_claims", "sahm"],
    ),
    _item(
        "net_liquidity_read",
        "순유동성 읽기",
        (
            "Net Liquidity = Fed 총자산 − TGA − ON RRP. "
            "TGA↑는 시중 흡수, RRP↓는 방출 해석이 흔하나 자산가격과 단선 인과는 성립하지 않는다."
        ),
        series_ids=["net_liquidity", "tga", "on_rrp", "fed_total_assets"],
    ),
    _item(
        "qra_tga_gap",
        "QRA ↔ TGA",
        (
            "QRA 칩 클릭: 전분 실적·직전 예측·당기 순발행 비교. "
            "tga_vs_qra는 실TGA와 QRA 기말현금 가정 갭이다. ±50B 밖이면 발행·유동성 해석에 유의."
        ),
        series_ids=["qra_issuance", "tga"],
    ),
    _item(
        "rates_hy_curve",
        "금리: 곡선 + 하이일드",
        (
            "정책금리(이벤트)와 10Y 등 시장금리(빈번 갱신)를 같은 주기로 보지 않는다. "
            "HY OAS는 신용 스트레스 축으로 국채 곡선 다음에 둔다."
        ),
        series_ids=["bond_10y", "hy_oas", "effr", "sofr"],
    ),
]


def build_explainers(kit: str, limitations: dict[str, Any] | None) -> dict[str, Any]:
    """Return explainers pack. USA gets reading guides; all kits keep caveat items linked."""
    items: list[dict[str, Any]] = []
    if kit.startswith("us_"):
        items.extend(USA_EXPLAINERS)
    # append limitation caveats as secondary explainer entries
    if limitations and limitations.get("items"):
        for it in limitations["items"]:
            items.append(
                {
                    "id": f"caveat_{it.get('id')}",
                    "title_ko": it.get("title_ko") or "",
                    "body_ko": it.get("body_ko") or "",
                    "kind": "caveat",
                }
            )
    title = "지표 설명"
    if limitations and limitations.get("title_ko"):
        # soften "한계" title for UI
        title = limitations["title_ko"].replace("분석·추론의 한계", "설명·읽기").replace("한계", "설명")
    return {
        "kind": "explainers",
        "title_ko": title if not kit.startswith("us_") else "지표 설명 (미국)",
        "items": items,
    }
