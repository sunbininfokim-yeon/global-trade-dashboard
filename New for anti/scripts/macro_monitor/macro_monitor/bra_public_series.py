"""Brazil: Banco Central do Brasil SGS and IBGE SIDRA (both keyless), World Bank Pink Sheet for the
export commodities.

Not here, and why: the 10-year NTN-F yield (no keyless series found), current account and primary
balance (the SGS codes could not be confirmed without metadata -- left out rather than guessed),
foreign portfolio flows, S&P Global PMIs (licensed), CDS.
"""

from __future__ import annotations

from . import us_public_series as ups
from .world_public_series import Card, card, monthly_last

GDP_SOURCE = "ibge:sidra:5932"
_SGS = "https://www3.bcb.gov.br/sgspub/"
_SIDRA = "https://sidra.ibge.gov.br/tabela/{t}"
_WB = "https://www.worldbank.org/en/research/commodity-markets"
BU_PER_MT = 0.0272155          # one bushel of soybeans is 27.2155 kg

CARDS: list[Card] = [
    card("selic_rate", "monthly", "%", "pct2", "SELIC",
         "Selic 목표금리(Copom)입니다. 차트는 각 달 말, 최신 점은 오늘까지. BCB SGS 432.",
         "bcb:sgs:432", _SGS, lambda f: monthly_last(f.get("bcb", 432))),
    card("ipca", "monthly", "%", "pct1", "IPCA",
         "IPCA(공식 소비자물가) 12개월 누적 상승률입니다. BCB SGS 13522(IBGE 발표).",
         "bcb:sgs:13522", _SGS, lambda f: f.get("bcb", 13522)),
    card("ipca_15", "monthly", "%", "pct1", "IPCA-15",
         "IPCA-15(월 중순 기준 선행 물가) 12개월 누적 상승률입니다. IBGE SIDRA 7062.",
         "ibge:sidra:7062", _SIDRA.format(t="7062"), lambda f: f.get("sidra", "t/7062/n1/all/v/1120/p/all/c315/7169")),
    card("unemployment", "monthly", "%", "pct1", "실업률",
         "실업률(PNAD 연속조사, 3개월 이동)입니다. 날짜는 3개월 구간의 마지막 달. BCB SGS 24369(IBGE).",
         "bcb:sgs:24369", _SGS, lambda f: f.get("bcb", 24369)),
    card("fx_reserves", "monthly", "bn_usd", "bn0usd", "외환보유액",
         "국제준비자산(유동성 기준, 월말, 십억 달러)입니다. BCB SGS 3546.",
         "bcb:sgs:3546", _SGS, lambda f: ups.scale(f.get("bcb", 3546), 1e-3)),
    card("m3_yoy", "monthly", "%", "pct1", "M3 전년비",
         "통화량 M3(월말 잔액) 전년 동월 대비입니다. BCB SGS 27813.",
         "bcb:sgs:27813", _SGS, lambda f: ups.pct_change(f.get("bcb", 27813), 12)),
    card("m3_vs_2019", "monthly", "%", "pct1", "M3 vs 2019-12",
         "(현재 M3 − 2019-12 M3) / 2019-12 M3 × 100. BCB SGS 27813.",
         "bcb:sgs:27813", _SGS, lambda f: ups.vs_base(f.get("bcb", 27813), "2019-12-01")),
    card("debt_to_gdp", "monthly", "%", "pct1", "총공공부채/GDP",
         "일반정부 총부채(DBGG) / GDP입니다. BCB SGS 13762.",
         "bcb:sgs:13762", _SGS, lambda f: f.get("bcb", 13762)),
    card("ibc_br", "monthly", "index", "num1", "IBC-Br",
         "중앙은행 경제활동지수 IBC-Br(계절조정, GDP 월간 대용)입니다. BCB SGS 24364.",
         "bcb:sgs:24364", _SGS, lambda f: f.get("bcb", 24364)),
    card("gdp_qoq", "quarterly", "%", "pct1", "실질GDP QoQ",
         "실질GDP(계절조정) 전기 대비 %입니다(연율 아님). IBGE SIDRA 5932.",
         "ibge:sidra:5932", _SIDRA.format(t="5932"), lambda f: f.get("sidra", "t/5932/n1/all/v/6564/p/all/c11255/90707")),
    card("gdp_yoy", "quarterly", "%", "pct1", "실질GDP YoY",
         "실질GDP 전년 동기 대비입니다. IBGE SIDRA 5932.",
         "ibge:sidra:5932", _SIDRA.format(t="5932"), lambda f: f.get("sidra", "t/5932/n1/all/v/6562/p/all/c11255/90707")),
    card("iron_ore", "monthly", "usd_t", "usd0", "철광석",
         "철광석(중국 CFR 현물, 달러/건조톤, 월평균)입니다. 세계은행 Pink Sheet.", "worldbank:pinksheet", _WB,
         lambda f: f.get("pink")["Iron ore, cfr spot"]),
    card("soybeans", "monthly", "usd_bu", "usd1", "대두",
         "대두(달러/부셸, 월평균)입니다. 세계은행 Pink Sheet의 달러/톤을 부셸(27.2155kg)로 환산.",
         "worldbank:pinksheet", _WB, lambda f: ups.scale(f.get("pink")["Soybeans"], BU_PER_MT)),
    card("crude_oil", "monthly", "usd_bbl", "usd1", "원유",
         "브렌트유(달러/배럴, 월평균)입니다. 세계은행 Pink Sheet.", "worldbank:pinksheet", _WB,
         lambda f: f.get("pink")["Crude oil, Brent"]),
]
