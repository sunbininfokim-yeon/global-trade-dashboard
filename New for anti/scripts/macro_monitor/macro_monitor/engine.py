"""Assemble macro_monitor_v1 country packs from config + series builders."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from .series import build_indicator, format_value, month_ends

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


@lru_cache(maxsize=1)
def _load_officials() -> dict[str, Any]:
    path = _CONFIG_DIR / "officials.json"
    if not path.is_file():
        return {"asof": None, "countries": {}}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_electricity_ember() -> dict[str, Any]:
    path = _CONFIG_DIR / "electricity_ember_v1.json"
    if not path.is_file():
        return {"countries": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def officials_for(iso3: str) -> dict[str, Any] | None:
    """Central bank head + finance-side minister for a country pack."""
    doc = _load_officials()
    row = (doc.get("countries") or {}).get(iso3)
    if not row:
        return None
    out: dict[str, Any] = {
        "asof": doc.get("asof"),
        "central_bank": row.get("central_bank"),
        "finance": row.get("finance"),
    }
    if doc.get("note_ko"):
        out["rule_ko"] = doc["note_ko"]
    if iso3 == "KOR" and doc.get("korea_rule_ko"):
        out["korea_rule_ko"] = doc["korea_rule_ko"]
    return out


def _official_has_name(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    if block.get("name_en") or block.get("name_ko"):
        return True
    for person in block.get("set") or []:
        if isinstance(person, dict) and (person.get("name_en") or person.get("name_ko")):
            return True
    return False


def _yearly_twh_to_monthly(
    history_yearly: list[dict[str, Any]],
    dates: list[str],
) -> list[float | None]:
    """Step-fill annual TWh onto month-end dates (year Y uses that year's total)."""
    by_y: dict[int, float] = {}
    for h in history_yearly or []:
        try:
            by_y[int(h["year"])] = float(h["value"])
        except (KeyError, TypeError, ValueError):
            continue
    years = sorted(by_y)
    out: list[float | None] = []
    for d in dates:
        y = int(d[:4])
        val: float | None = None
        for yy in years:
            if yy <= y:
                val = by_y[yy]
            else:
                break
        out.append(round(val, 4) if val is not None else None)
    return out


def _attach_electricity_generation(
    *,
    iso3: str,
    specs_by_id: dict[str, Any],
    cfg_map: dict[str, Any],
    dates: list[str],
    by_id: dict[str, Any],
    indicators: list[dict[str, Any]],
) -> None:
    """Growth chip: annual generation TWh + click energy_mix (Ember)."""
    if "electricity_generation" not in specs_by_id or "electricity_generation" in by_id:
        return
    ember_row = (_load_electricity_ember().get("countries") or {}).get(iso3)
    if not ember_row:
        return
    spec = specs_by_id["electricity_generation"]
    cfg = dict(cfg_map.get("electricity_generation") or {})
    twh = float(ember_row["generation_twh"])
    values = _yearly_twh_to_monthly(ember_row.get("history_yearly") or [], dates)
    if values and values[-1] is None:
        values[-1] = twh
    ind = build_indicator(
        series_id="electricity_generation",
        spec=spec,
        country_cfg={**cfg, "base": twh},
        dates=dates,
        seed=_seed_for(iso3, "electricity_generation"),
        values_override=values,
    )
    mix = ember_row.get("energy_mix") or {}
    mix_series = list(mix.get("series") or [])
    ind["value"] = twh
    ind["display"] = format_value(twh, spec.get("format") or "twh0")
    ind["display_chip"] = ind["display"]
    ind["asof"] = f"{ember_row.get('asof_year')}-12-31"
    ind["energy_mix"] = {
        "asof_year": mix.get("asof_year") or ember_row.get("asof_year"),
        "unit": mix.get("unit") or "pct",
        "basis": mix.get("basis") or "share_of_generation",
        "series": mix_series,
        "chart_type": "bar",
    }
    # components alias for UIs that already render component bars
    ind["components"] = [
        {
            "id": s["id"],
            "label_ko": s["label_ko"],
            "value": s["value"],
            "display": f"{s['value']:.1f}%",
            "unit": "pct",
            "twh": s.get("twh"),
        }
        for s in mix_series
    ]
    ind.setdefault("ui", {})["click_view"] = "energy_mix"
    ind["chart_type"] = "line"
    ind["source"] = ember_row.get("source") or "Ember"
    ind["quality"] = "ember_yearly"
    if ember_row.get("note_ko"):
        ind["note_ko"] = ember_row["note_ko"]
    if ember_row.get("license"):
        ind["license"] = ember_row["license"]
    indicators.append(ind)
    by_id[ind["id"]] = ind


def _apply_qra_engine_file(by_id: dict[str, Any]) -> None:
    """Attach compare/components from public/data/qra_engine_v1.json when present."""
    if "qra_issuance" not in by_id:
        return
    try:
        from .qra.build import load_latest_issuance
    except Exception:
        return
    hit = load_latest_issuance()
    if not hit:
        return
    ind = by_id["qra_issuance"]
    if hit.get("components") and len(hit["components"]) >= 6:
        ind["components"] = hit["components"]
    elif hit.get("components") and not ind.get("components"):
        ind["components"] = hit["components"]
    if hit.get("compare"):
        ind["compare"] = hit["compare"]
        ind.setdefault("ui", {})["click_view"] = "compare_bar_table"
        ind.setdefault("ui", {})["secondary_view"] = "maturity_components"
        cur = next(
            (s for s in (hit["compare"].get("series") or []) if s.get("id") == "current"),
            None,
        )
        if cur and cur.get("value") is not None:
            ind["value"] = float(cur["value"])
            ind["display"] = format_value(ind["value"], ind.get("unit") or "bn")
            ind["display_chip"] = ind["display"]
    if hit.get("history_net_borrowing"):
        ind["history_net_borrowing"] = hit["history_net_borrowing"]
    if hit.get("summary_ko"):
        ind["note_ko"] = hit["summary_ko"]
    if hit.get("flags"):
        ind["flags"] = hit["flags"]
    if hit.get("tga_vs_qra"):
        ind["tga_vs_qra"] = hit["tga_vs_qra"]
    ind["source"] = hit.get("source") or "qra_engine_v1"
    ind["quality"] = "engine"
    if hit.get("asof"):
        ind["asof"] = str(hit["asof"])[:10]


CATEGORIES_ORDER = ("liquidity", "rates", "fx", "equity", "growth", "inflation")

# Within-tab chip order (canonical). Unknown ids keep relative order after known ones.
# Growth: hard data first, PMI/ISM surveys last (US-style).
CHIP_ORDER: dict[str, list[str]] = {
    "liquidity": [
        "net_liquidity",
        "fed_total_assets",
        "boj_total_assets",
        "boe_total_assets",
        "ecb_total_assets",
        "cbr_total_assets",
        "sarb_total_assets",
        "boi_total_assets",
        "bok_total_assets",
        "boc_total_assets",
        "rba_total_assets",
        "snb_total_assets",
        "boj_assets_gdp",
        "boj_assets_yoy",
        "fed_ust_holdings",
        "boj_jgb_share",
        "boj_jgb_ops",
        "fed_ust_ops",
        "ecb_bond_ops",
        "boe_gilt_ops",
        "boj_etf_holdings",
        "boj_jreit",
        "fed_mbs",
        "on_rrp",
        "fima_repo",
        "discount_window",
        "tga",
        "qra_issuance",
        "m2_vs_2019",
        "m2_yoy",
        "m3_vs_2019",
        "m3_yoy",
        "m4_vs_2019",
        "m4_yoy",
        "fiscal_deficit_gdp",
        "debt_to_gdp",
        "primary_fiscal_balance",
    ],
    "rates": [
        # 1) policy rates
        "effr",
        "call_rate",
        "bank_rate",
        "bok_base_rate",
        "us_kr_rate_gap",
        "boi_rate",
        "boc_overnight",
        "rba_cash_rate",
        "snb_policy_rate",
        "selic_rate",
        "rbi_repo",
        "sarb_repo",
        "cbr_key_rate",
        "nbk_base_rate",
        "hk_base_rate",
        "cbc_discount",
        "sbv_refinancing",
        "sbv_discount",
        "deposit_facility",
        "mro_rate",
        "mlf_rate",
        "lpr_1y",
        "lpr_5y",
        "vn_deposit_rate",
        "vn_lending_rate",
        # 2) policy watch / standing facilities
        "fedwatch",
        "tpi_active",
        "laf_balance",
        # 3) money-market refs (stick together)
        "sofr",
        "sonia",
        "sora",
        "hibor_1m",
        "hibor_3m",
        # 4) local curve: short → long
        "bond_3m",
        "bond_2y",
        "sgs_2y",
        "ktb_3y",
        "acgb_3y",
        "bond_10y",
        "bund_10y",
        "btp_10y",
        "sgs_10y",
        "sagb_10y",
        "ofz_10y",
        "bond_30y",
        "tips_10y",
        "ofz_auction_cover",
        # 5) curve spreads (after the curve they describe)
        "spread_10y3m",
        "spread_10y2y",
        "spread_30y10y",
        # 6) cross-country rate/yield spreads (only the ones that matter)
        "us_ca_2y_spread",
        "us_au_10y_spread",
        "us_chn_10y_spread",
        "gilt_bund_10y",
        "ch_bund_10y_spread",
        "hibor_sofr_spread",
        "sofr_sora_spread",
        # 7) credit spreads (grouped)
        "hy_oas",
        "corp_spread_aa",
        "cp_spread",
        "btp_bund_spread",
        "lgfv_spread",
        "cn_hy_prop_spread",
        # 8) sovereign credit package last
        "sovereign_cds_5y",
        "br_cds_5y",
        "za_cds_5y",
        "sovereign_ratings",
    ],
    "fx": [
        "dxy",
        "eurusd",
        "usdjpy",
        "yen_imm_net",
        "gbpusd",
        "usdcnh",
        "usdcny",
        "usdkrw",
        "usdils",
        "usdinr",
        "usdcad",
        "audusd",
        "usdchf",
        "usdbrl",
        "usdzar",
        "usdhkd",
        "usdsgd",
        "usdvnd",
        "usdkzt",
        "usdtwd",
        "usdrub",
        "cnyrub",
        "current_account",
        "fx_reserves",
        "fx_intervention",
        "us_fx_watch",
    ],
    "equity": [
        # onshore / local first, then offshore mirrors, then flows, then vol
        "spx",
        "ndx",
        "rut",
        "sse_composite",
        "csi300",
        "hscei",
        "ta125",
        "hsi",
        "hstech",
        "nikkei",
        "topix",
        "kospi",
        "kosdaq",
        "euro_stoxx50",
        "stoxx_banks",
        "dax40",
        "cac40",
        "ftse100",
        "ftse250",
        "northbound_flow",
        "southbound_flow",
        "foreign_equity_flow",
        "foreign_equity_kr",
        "foreign_equity_flow_za",
        "vix",
        "vkospi",
        "nikkei_vi",
    ],
    "growth": [
        "gdpnow",
        "gdp",
        "electricity_generation",
        "export_yoy_kr",
        "export_yoy_vn",
        "export_yoy_tw",
        "export_yoy",
        "nodx_yoy",
        "semi_export_yoy",
        "high_tech_export_yoy",
        # commodity export drivers (BR/AU/CA/ZA/KZ) — same slot as KR semis
        "iron_ore",
        "soybeans",
        "crude_oil",
        "wcs_oil",
        "coking_coal",
        "gold_price",
        "platinum_price",
        "coal_price",
        "uranium",
        "cpc_blend",
        "nfp",
        "employment_change",
        "unemployment",
        "sahm",
        "initial_claims",
        "job_applicant_ratio",
        "shunto_wage",
        "real_wage_yoy",
        "awe_ex_bonus",
        # surveys intentionally last — see _chip_rank
    ],
    "inflation": [
        "cpi_yoy",
        "core_cpi_yoy",
        "core_cpi_jp",
        "core_core_cpi",
        "tokyo_cpi",
        "hicp_yoy",
        "core_hicp_yoy",
        "trimmed_mean_cpi",
        "export_price_yoy",
        "import_price_yoy",
        "bei_10y",
        "cgpi",
        "ppi_yoy",
    ],
}


def _is_growth_survey(series_id: str) -> bool:
    s = series_id.lower()
    return (
        s.startswith("ism_")
        or "pmi" in s
        or s.endswith("_pmi")
        or s in ("ivey_pmi", "absa_pmi", "sipmm_pmi", "nbs_pmi", "caixin_pmi")
    )


def _chip_rank(category: str, series_id: str) -> tuple[int, int, str]:
    """Sort key: (bucket, index, id). Surveys in growth go last."""
    if category == "growth" and _is_growth_survey(series_id):
        return (2, 0, series_id)
    order = CHIP_ORDER.get(category) or []
    if series_id in order:
        return (0, order.index(series_id), series_id)
    return (1, 0, series_id)


def _sort_chips(category: str, chips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(chips, key=lambda c: _chip_rank(category, c["id"]))

USA_HEADLINES = [
    "net_liquidity",
    "bond_10y",
    "dxy",
    "spx",
    "gdpnow",
    "core_cpi_yoy",
]
JPN_HEADLINES = [
    "boj_jgb_share",
    "bond_10y",
    "usdjpy",
    "nikkei",
    "shunto_wage",
    "core_cpi_jp",
]
UK_HEADLINES = [
    "bond_30y",
    "gilt_bund_10y",
    "bank_rate",
    "gbpusd",
    "awe_ex_bonus",
    "services_cpi",
]
CN_HEADLINES = [
    "tsf_yoy",
    "m1_m2_spread",
    "lpr_5y",
    "usdcnh",
    "ppi_yoy",
    "property_fai",
]
EZ_HEADLINES = [
    "btp_bund_spread",
    "deposit_facility",
    "eurusd",
    "hcob_pmi_mfg",
    "hicp_yoy",
    "pepp_balance",
]
RU_HEADLINES = [
    "nwf_liquid",
    "cbr_key_rate",
    "cnyrub",
    "urals_brent_spread",
    "rtsi",
    "cpi_yoy",
]
HK_HEADLINES = [
    "aggregate_balance",
    "usdhkd",
    "hibor_sofr_spread",
    "hsi",
    "ccl_index",
    "retail_sales_yoy",
]
SG_HEADLINES = [
    "sgd_neer",
    "neer_slope",
    "nodx_yoy",
    "sora",
    "mas_core_infl",
    "sti",
]
ZA_HEADLINES = [
    "load_shedding_hours",
    "debt_to_gdp",
    "sarb_repo",
    "usdzar",
    "sagb_10y",
    "cpi_yoy",
]
IN_HEADLINES = [
    "cad_gdp",
    "rbi_repo",
    "usdinr",
    "gdp_yoy",
    "fpi_flow",
    "cpi_yoy",
]
IL_HEADLINES = [
    "sovereign_cds_5y",
    "boi_rate",
    "usdils",
    "ta125",
    "high_tech_export_yoy",
    "cpi_yoy",
]
KR_HEADLINES = [
    "semi_export_yoy",
    "usdkrw",
    "bok_base_rate",
    "household_credit",
    "kospi",
    "cpi_yoy",
]
CA_HEADLINES = [
    "hh_debt_income",
    "boc_overnight",
    "usdcad",
    "wcs_oil",
    "teranet_hpi",
    "cpi_trim",
]
AU_HEADLINES = [
    "iron_ore",
    "hh_debt_income",
    "rba_cash_rate",
    "audusd",
    "corelogic_hpi",
    "trimmed_mean_cpi",
]
CH_HEADLINES = [
    "eurchf",
    "sight_deposits",
    "snb_policy_rate",
    "smi",
    "kof_barometer",
    "cpi_yoy",
]
BR_HEADLINES = [
    "primary_fiscal_balance",
    "selic_rate",
    "usdbrl",
    "iron_ore",
    "ibovespa",
    "ipca",
]
VN_HEADLINES = [
    "fdi_disbursed",
    "usdvnd",
    "credit_growth_quota",
    "export_yoy_vn",
    "vnindex",
    "cpi_yoy",
]
KZ_HEADLINES = [
    "nfrk_assets",
    "usdkzt",
    "crude_oil",
    "nbk_base_rate",
    "uranium",
    "cpi_yoy",
]
TW_HEADLINES = [
    "usdtwd",
    "hedge_ratio",
    "taiex",
    "export_orders_yoy",
    "cbc_discount",
    "cpi_yoy",
]
THIN_HEADLINES = ["bond_10y", "usdjpy", "eurusd", "spx", "gdp_yoy", "cpi_yoy", "effr"]

USA_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (미국)",
    "items": [
        {
            "id": "liquidity_causality",
            "title_ko": "유동성 ↔ 자산가격 인과 불확실",
            "body_ko": (
                "순유동성 증가가 주식 상승을 기계적으로 보장하지 않는다. "
                "침체·지정학 등 외생변수 시 자금은 위험자산이 아닌 단기 국채 등으로 몰릴 수 있다."
            ),
        },
        {
            "id": "qt_qra_offset",
            "title_ko": "연준 QT ↔ 재무부 발행 상쇄",
            "body_ko": (
                "연준 보유국채 run-off가 해당 만기 금리 상승으로 직결되지 않는다. "
                "QRA에서 장기채를 줄이고 T-Bill을 늘리면 QT 수급 충격이 상쇄될 수 있으며, "
                "발행 전략은 정책 결정이라 데이터만으로 사전 예측 불가하다."
            ),
        },
        {
            "id": "threshold_nonlinearity",
            "title_ko": "임계치의 비선형성",
            "body_ko": (
                "HY OAS·FIMA 등 스트레스 지표는 문제가 수면 위로 나오기 전 낮은 수준을 유지하는 "
                "후행 경향이 있다. RRP 고갈→지준 감소 발작 등 임계치를 정확히 도출하는 것은 불가능하다."
            ),
        },
    ],
}

JPN_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (일본)",
    "items": [
        {
            "id": "boj_etf_exit",
            "title_ko": "BOJ ETF 출구 전략 불확실",
            "body_ko": (
                "중앙은행이 주식을 대량 보유한 사례는 일본이 유일하다. ETF 잔고는 추적 가능하나 "
                "매각(Exit) 선례·룰이 없어, 규모만으로 증시 충격의 시점·강도를 예측할 수 없다."
            ),
        },
        {
            "id": "jgb_price_discovery",
            "title_ko": "금리 가격발견 기능 훼손",
            "body_ko": (
                "YCC와 대규모 매입으로 BOJ가 JGB의 절반 이상을 흡수하면서 시장 유동성이 고갈되고 "
                "금리 형성이 왜곡되었다. 현재 금리가 순수 펀더멘털·민간 성장 전망을 반영한다고 단정할 수 없다."
            ),
        },
        {
            "id": "fx_intervention_short",
            "title_ko": "외환 개입 효과의 단기성",
            "body_ko": (
                "실개입 규모·외환보유액 감소를 확인해도, 미·일 금리차가 좁혀지지 않으면 "
                "개입 효과는 며칠~몇 주 내 소멸하는 경향이 있다. 개입 수치만으로 장기 환율 변곡점을 확언하기 어렵다."
            ),
        },
    ],
}

UK_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (영국)",
    "items": [
        {
            "id": "ldi_otc_hidden",
            "title_ko": "파생 레버리지 사전 포착 불가",
            "body_ko": (
                "2022 LDI처럼 연금펀드 OTC IRS 레버리지·증거금 여력은 BOE BS나 Gilt 금리에 노출되지 않는다. "
                "거시 지표는 Fire sale이 시작된 뒤에야 후행 반응한다."
            ),
        },
        {
            "id": "ftse100_decouple",
            "title_ko": "FTSE 100 ↔ 내수 디커플링",
            "body_ko": (
                "FTSE 100 매출의 약 75%가 해외다. 파운드 약세 시 환차익 기대로 지수가 오르는 "
                "역상관이 자주 관찰된다. 주가 상승을 내수 펀더멘털 개선으로 추론하면 논리적 오류다."
            ),
        },
        {
            "id": "m4_inflation_nonlinear",
            "title_ko": "M4 팽창 ↔ 물가 비선형",
            "body_ko": (
                "통화량이 늘어도 자금이 금융자산에 머물거나 유통속도가 떨어지면 인플레로 직결되지 않는다. "
                "M4 증감만으로 특정 시점 CPI를 정량 계산·예측할 수 없다."
            ),
        },
    ],
}

CN_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (중국)",
    "items": [
        {
            "id": "official_smoothing",
            "title_ko": "공식 통계 평활화",
            "body_ko": (
                "공식 GDP·실업은 변동폭을 축소해 발표하는 경향이 있다. 목표치(예: 5%)에 맞춰도 "
                "체감 경기·기업 실적으로 직결된다고 볼 수 없다. 커창지수·원자재 수입 등과 교차검증이 필요하나 완전 대체는 아니다."
            ),
        },
        {
            "id": "lgfv_shadow",
            "title_ko": "그림자금융·LGFV 규모 불확실",
            "body_ko": (
                "TSF에 안 잡히는 음성 부채·비은행 신용의 정확한 규모는 파악 불가하다. "
                "LGFV 스프레드가 안정적이어도 건전성인지 암묵적 보증 착시인지 데이터만으로 구별할 수 없다."
            ),
        },
        {
            "id": "m2_deflation_coexist",
            "title_ko": "M2 팽창 ↔ 디플레 공존",
            "body_ko": (
                "M2는 높게 유지되나 PPI·CPI 하락(디플레 우려)이 공존한다. "
                "통화가 유효수요가 아니라 부채 차환·예금 퇴장으로 가면 M2 기반 인플레 전망은 성립하지 않는다."
            ),
        },
        {
            "id": "policy_exogenous",
            "title_ko": "규제라는 비정량 외생변수",
            "body_ko": (
                "세 개의 레드라인·플랫폼 규제 등 정책 개입은 사전 예고 없이 시계열을 무력화한다. "
                "과거 데이터로 자산가격을 정량 예측하는 모델은 불가능하다."
            ),
        },
    ],
}

EZ_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (유로존)",
    "items": [
        {
            "id": "average_masking",
            "title_ko": "평균 지표의 분절 은폐",
            "body_ko": (
                "유로존 평균 GDP·PMI가 좋아 보여도 남유럽 서비스 호조와 독일 제조업 침체가 혼재일 수 있다. "
                "평균만으로 개별국 부채 위기·산업 경쟁력 저하를 진단할 수 없다."
            ),
        },
        {
            "id": "btp_bund_distorted",
            "title_ko": "BTP−Bund의 인위적 왜곡",
            "body_ko": (
                "스프레드는 분절화 핵심 척도이나 PEPP 재투자 유연화·TPI라는 암묵적 개입이 가격에 반영된다. "
                "스프레드 안정 ≠ 남유럽 구조적 재정건전성 확보."
            ),
        },
        {
            "id": "m3_bank_channel",
            "title_ko": "M3 ↔ 신용경로 제약",
            "body_ko": (
                "은행 중심 금융구조상 유동성이 생산적 투자로 가는 경로가 미국보다 제한적이다. "
                "TLTRO 상환 과정에서 신용이 언제 급격히 위축될지 M3 속도만으로 사전 계산할 수 없다."
            ),
        },
    ],
}

RU_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (러시아)",
    "items": [
        {
            "id": "data_manipulation",
            "title_ko": "국가 통계 신뢰성 결여",
            "body_ko": (
                "전쟁 이후 무역수지·예산·자본흐름 등 핵심 발표가 중단되거나 산출이 자의적으로 바뀌었다. "
                "공식 GDP·물가만으로 펀더멘털 강도를 평가할 수 없다."
            ),
        },
        {
            "id": "war_gdp_illusion",
            "title_ko": "비생산적 GDP 성장 착시",
            "body_ko": (
                "GDP(+)는 군수 생산·재정 투입의 결과일 수 있다. 군수품은 전장에서 소모되어 "
                "민간 자본 축적으로 이어지지 않으므로, GDP 상승 ≠ 실물 건전성 향상."
            ),
        },
        {
            "id": "fx_capital_controls",
            "title_ko": "자본통제 ↔ 환율 디커플링",
            "body_ko": (
                "USD/RUB는 자본통제·수출기업 외환 강제매각으로 인위 관리된다. "
                "환율 방어 ≠ 대외 충격 흡수력 강화. 자유시장 가정 정량예측은 한계가 명확하다."
            ),
        },
    ],
}

HK_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (홍콩)",
    "items": [
        {
            "id": "policy_mismatch",
            "title_ko": "금리 ↔ 경기의 구조적 불일치",
            "body_ko": (
                "LERS 때문에 미국 금리 인상 시 홍콩도 기계적으로 따라간다. "
                "내수 침체여도 긴축이 강제되어, '침체→금리인하→경기방어' 인과가 작동하지 않는다."
            ),
        },
        {
            "id": "hsi_not_local",
            "title_ko": "항셍 ≠ 홍콩 내수",
            "body_ko": (
                "HSI 시총의 80%+가 본토 기업이다. 지수는 중국 기업 실적·정책에 좌우되며 "
                "소매·고용 등 로컬 펀더멘털을 대변하지 않는다. HSI↑ ≠ 홍콩 경제 회복."
            ),
        },
        {
            "id": "ab_vs_bank_deposits",
            "title_ko": "총결제잔액 ↔ 대출여력 괴리",
            "body_ko": (
                "Aggregate Balance가 500억 HKD 이하로 줄어도 대형은행은 고객예금이 풍부해 "
                "즉각 신용경색이 안 올 수 있다. 은행간 유동성 수치만으로 위기 임계점을 특정할 수 없다."
            ),
        },
    ],
}

SG_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (싱가포르)",
    "items": [
        {
            "id": "sora_not_mas_stance",
            "title_ko": "SORA ≠ MAS 긴축",
            "body_ko": (
                "국내 금리(SORA) 상승을 MAS 긴축이나 내수 과열로 읽는 것은 오류다. "
                "SORA는 주로 연준에 연동된다. 자국 펀더멘털·당국 의도는 S$NEER 밴드에서 본다."
            ),
        },
        {
            "id": "headline_cpi_coe",
            "title_ko": "헤드라인 CPI 착시",
            "body_ko": (
                "COE·임대료 등 비시장·일시 요인이 헤드라인 CPI를 끌어올릴 수 있다. "
                "단일 CPI로 긴축 전환 임계점을 계산할 수 없다. MAS Core를 우선한다."
            ),
        },
        {
            "id": "m2_wm_hub",
            "title_ko": "M2 ↔ 내수 유동성 괴리",
            "body_ko": (
                "자산관리 허브라 M2 팽창의 상당수는 Family Office 등 대기성 외국인 자금일 수 있다. "
                "M2를 내수 인플레·로컬 주가의 직접 원인으로 연결하는 모델은 한계가 있다."
            ),
        },
    ],
}

ZA_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (남아공)",
    "items": [
        {
            "id": "commodity_logistics_break",
            "title_ko": "원자재 ↔ 실물 인과 단절",
            "body_ko": (
                "금·백금 가격이 올라도 Transnet 철도·항만 적체로 수출 물량을 못 소화하면 "
                "단가↑→흑자→랜드강세·GDP 경로가 성립하지 않는다. 원자재만으로 성장을 추론할 수 없다."
            ),
        },
        {
            "id": "load_shedding_exogenous",
            "title_ko": "Load Shedding 외생변수",
            "body_ko": (
                "금리인하·M3 증가 등 부양 조건이 있어도 Eskom 정전이 심화되면 생산·소비가 즉각 멈춘다. "
                "인프라 결함은 예측 모델 밖이라 금융 데이터만으로 분기 GDP를 정량 산출할 수 없다."
            ),
        },
        {
            "id": "m3_vs_investment",
            "title_ko": "M3 ↔ 내수 활성화 괴리",
            "body_ko": (
                "실업 30%+ 구조와 정책 불확실성으로 M3 증가가 민간 고정자본 형성으로 잘 안 간다. "
                "유동성은 단기 금융자산·자본유출 압력으로 작용할 수 있어 M3로 수요견인 성장을 예측하기 어렵다."
            ),
        },
    ],
}

IN_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (인도)",
    "items": [
        {
            "id": "informal_economy",
            "title_ko": "공식통계 ↔ 비공식경제 괴리",
            "body_ko": (
                "GDP·PMI 고성장은 대기업·공식부문에 치우칠 수 있다. 고용의 80%+ 비공식 부문 침체는 "
                "실시간 반영되지 않아, 지표상 고성장=전체 체력·구매력 향상으로 일대일 치환할 수 없다."
            ),
        },
        {
            "id": "repo_food_cpi",
            "title_ko": "금리 ↔ 인플레 통제 단절",
            "body_ko": (
                "CPI의 ~45%가 식료품이라 몬순·공급측 요인이 크다. Repo 인상으로 작황을 통제할 수 없어 "
                "긴축→물가하락 기계적 인과가 성립하지 않으며, 금융데이터로 미래 CPI를 수치 예측하기 어렵다."
            ),
        },
        {
            "id": "m3_credit_allocation",
            "title_ko": "M3 ↔ 자본배분 비효율",
            "body_ko": (
                "M3 증가가 인프라·고용 창출 민간투자로 균형 배분된다고 볼 수 없다. "
                "리스크 회피 시 우량 대기업·특정 자산으로 편중되어 M3 총량으로 전반 성장률을 정량 계산할 수 없다."
            ),
        },
    ],
}

KR_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (한국)",
    "items": [
        {
            "id": "export_domestic_decouple",
            "title_ko": "수출(반도체) ↔ 내수 디커플링",
            "body_ko": (
                "반도체 수출·무역흑자가 고용·낙수효과를 통해 내수 소비로 이어진다고 단정할 수 없다. "
                "GDP가 양호해도 자영업·비수출 중소기업 침체가 공존해 총량만으로 체감경기를 진단할 수 없다."
            ),
        },
        {
            "id": "rate_cut_to_housing",
            "title_ko": "금리정책의 비대칭·통제불능",
            "body_ko": (
                "기준금리 인하가 실물 투자·소비로 직결되지 않고 주담대·수도권 부동산으로 유입되는 "
                "경로가 고착화되어 있다. 특정 금리 수준의 실물 효과를 전통 거시모델로 예측하기 어렵다."
            ),
        },
        {
            "id": "m2_asset_nonlinear",
            "title_ko": "M2 ↔ 자산가격 비선형",
            "body_ko": (
                "M2 증가분은 생산적 자본보다 부동산·특정 주식에 편중되거나 단기 예금으로 퇴장할 수 있다. "
                "M2 총량으로 인플레율이나 주식시장 전반 상승 동력을 수치화하기 어렵다."
            ),
        },
    ],
}

CA_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (캐나다)",
    "items": [
        {
            "id": "immigration_gdp_illusion",
            "title_ko": "이민 유입 ↔ 실물성장 착시",
            "body_ko": (
                "대규모 이민으로 총량 실질GDP는 플러스를 유지해도 인구 증가가 성장을 상회하면 "
                "1인당 실질GDP는 정체·하락할 수 있다. 분기 GDP만으로 생산성·가계 구매력 향상을 "
                "인과 추론하는 것은 잘못된 해석이다."
            ),
        },
        {
            "id": "rate_cut_mortgage_renewal",
            "title_ko": "금리 ↔ 주택시장 비선형",
            "body_ko": (
                "다수가 변동금리 또는 단기(통상 5년) 고정 모기지다. BOC가 금리를 인하해도 "
                "갱신 가계는 초저금리 시절보다 높은 이자를 부담할 수 있어 "
                "‘금리인하=즉시 주택·소비 활성화’ 기계적 예측은 성립하지 않는다."
            ),
        },
        {
            "id": "m3_resource_dependence",
            "title_ko": "M3 ↔ 자원의존 경제",
            "body_ko": (
                "M3 증가가 산업 고도화(R&D·설비)로 연결됐다는 증거는 희박하다. "
                "미국 사이클·천연자원 수출에 종속되어 국내 통화량만으로 인플레 강도나 CAD 가치를 "
                "모델링하기 어렵다."
            ),
        },
    ],
}

AU_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (호주)",
    "items": [
        {
            "id": "immigration_gdp_gap",
            "title_ko": "인구증가 ↔ 펀더멘털 괴리",
            "body_ko": (
                "분기 총량 실질GDP 플러스가 대규모 이민·인구증가 효과일 수 있다. "
                "1인당 실질GDP는 다수 분기 마이너스인 경우가 많아, 총량 GDP만으로 "
                "생산성·내수 건전성을 추론하는 것은 잘못된 논리다."
            ),
        },
        {
            "id": "commodities_domestic_decouple",
            "title_ko": "원자재 수출 ↔ 내수 디커플링",
            "body_ko": (
                "철광석 급등·무역흑자·광산 수익이 비광업 고용·임금으로 즉각 전이되지 않는다. "
                "내수는 RBA 긴축·가계 이자부담에 억눌려 수출 호조를 가계 소비 확대와 "
                "정량 연결하는 모델은 성립하지 않는다."
            ),
        },
        {
            "id": "mortgage_cliff",
            "title_ko": "가계부채 ↔ 금리파급 예측불가",
            "body_ko": (
                "주담대 상당수가 변동금리이거나 고정기간이 2–3년으로 짧다. "
                "대규모 고정→변동 전환(Mortgage Cliff) 시 RBA가 추가 인상하지 않아도 "
                "가처분소득이 급감할 수 있어, Cash Rate만으로 소비·주택 조정폭을 "
                "기계적으로 계산할 수 없다."
            ),
        },
    ],
}

CH_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (스위스)",
    "items": [
        {
            "id": "chf_not_fundamentals",
            "title_ko": "환율 강세 ↔ 국내 펀더멘털 단절",
            "body_ko": (
                "CHF 급등은 내수 고성장·기업 실적 개선이 아니라 유로존·지정학 리스크 시 "
                "도피성 자금 유입의 결과일 수 있다. 환율을 내수 건전성 척도로 역산하는 것은 "
                "잘못된 논리다."
            ),
        },
        {
            "id": "sight_deposits_not_inflation",
            "title_ko": "요구불예금 ↔ 인플레 무관",
            "body_ko": (
                "Sight Deposits 증가는 국내 대출·소비 확대가 아니라 SNB 환율방어(외환매입·프랑지급) "
                "기술적 결과다. 기초통화량 팽창을 미래 인플레·자산가격 급등과 정량 연결하는 "
                "모델은 성립하지 않는다."
            ),
        },
        {
            "id": "smi_gdp_decouple",
            "title_ko": "SMI ↔ 실물경제 디커플링",
            "body_ko": (
                "SMI 구성 기업 매출의 대부분(네슬레·노바티스 등)이 해외에서 발생한다. "
                "지수 등락은 내수 GDP가 아니라 글로벌 수요·달러/유로에 종속되어 "
                "SMI를 내수 GDP 선행지표로 취급할 수 없다."
            ),
        },
    ],
}

BR_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (브라질)",
    "items": [
        {
            "id": "selic_investment_gap",
            "title_ko": "SELIC ↔ 실물투자 괴리",
            "body_ko": (
                "BCB가 금리를 인하해도 재정 적자 우려가 있으면 장기 국채금리는 오히려 오를 수 있다. "
                "재정 포퓰리즘 환경에서 기업은 설비투자보다 단기 이자수익에 집중하므로, "
                "완화 데이터만으로 고정자본 형성·GDP 성장을 정량 산출할 수 없다."
            ),
        },
        {
            "id": "commodities_domestic_limit",
            "title_ko": "원자재↑ ↔ 내수 한계",
            "body_ko": (
                "대두·철광석 급등으로 BRL이 일시 강세·수출 호조여도 혜택은 소수 대형 수출기업에 "
                "집중되고 내수 소비재 고용·가계 구매력으로 직결되지 않는다. "
                "무역흑자만으로 내수 회복·1인당 소득 증가를 추론할 수 없다."
            ),
        },
        {
            "id": "m3_ipca_climate",
            "title_ko": "M3 ↔ IPCA 단절",
            "body_ko": (
                "IPCA는 가뭄·수력 감소·전기료·농작물 흉작 등 공급측·기후 외생변수에 취약하다. "
                "M3가 통제돼도 물가가 급등할 수 있어, 과거 통화량 추이로 미래 IPCA를 "
                "정량 도출하는 모델은 오류를 수반한다."
            ),
        },
    ],
}

VN_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (베트남)",
    "items": [
        {
            "id": "fdi_export_domestic_gap",
            "title_ko": "FDI·수출 ↔ 내수 단절",
            "body_ko": (
                "수출·무역흑자 최대치라도 약 70%+가 FDI 기업 실적이며, 이익은 본국 송금·유보로 "
                "빠질 수 있다. 총량 수출 호조를 내수 구매력·자국 경제 질적 성장과 정량 치환하면 오류다."
            ),
        },
        {
            "id": "managed_fx_opacity",
            "title_ko": "관리변동 ↔ 외환리스크 측정불가",
            "body_ko": (
                "USD/VND가 밴드 안 안정이어도 외환 건전성을 증명하지 않는다. "
                "펀더멘털 약화 시 비공개 외환보유 소모·환전 지연 등 비시장 통제가 작동해 "
                "표면 환율만으로 위기 시점을 단정할 수 없다."
            ),
        },
        {
            "id": "credit_quota_blocks_rates",
            "title_ko": "신용쿼터 ↔ 금리파급 한계",
            "body_ko": (
                "기준금리를 인하해도 Credit Quota가 소진되면 실물 자금 공급이 차단된다. "
                "반부패·회사채 규제와 겹치면 금리와 무관하게 부동산·투자가 멈출 수 있어 "
                "M2·정책금리로 GDP 상승을 기계적으로 계산할 수 없다."
            ),
        },
    ],
}

KZ_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (카자흐스탄)",
    "items": [
        {
            "id": "commodities_domestic_gap",
            "title_ko": "원자재 수출 ↔ 내수 단절",
            "body_ko": (
                "유가·우라늄 급등으로 GDP·무역흑자가 늘어도 수익은 국영·외국계 에너지·NFRK로 "
                "귀속된다. 비자원 고용·가계 실질임금으로의 기계적 낙수는 성립하지 않아 "
                "총량 GDP로 내수 건전성을 추론하면 오류다."
            ),
        },
        {
            "id": "cpc_geopolitics",
            "title_ko": "CPC 물류 차단 · 비정량 외생",
            "body_ko": (
                "지표가 안정해도 원유 수출 80%+를 담당하는 러시아 경유 CPC가 지정학적으로 "
                "중단되면 펀더멘털이 즉시 붕괴한다. 시계열·거시모델로 발생 시점·충격 규모를 "
                "사전 정량 예측할 수 없다."
            ),
        },
        {
            "id": "rate_imported_inflation",
            "title_ko": "금리 ↔ 수입 인플레 제약",
            "body_ko": (
                "CPI는 RUB 변동·글로벌 공급망 등 공급측·수입 물가 요인이 크다. "
                "NBK 긴축으로 수요를 눌러도 전통적 수요억제→CPI 하락 모델이 작동하지 않아 "
                "금리 조정만으로 향후 CPI 하락폭을 수치화할 수 없다."
            ),
        },
    ],
}

TW_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (대만)",
    "items": [
        {
            "id": "hedge_fx_nonlinear",
            "title_ko": "생보 환헤지 ↔ 환율 비선형",
            "body_ko": (
                "헤지 비용 상승으로 생보가 헤지비율을 일시에 축소·재조정하면 펀더멘털 변화 없이도 "
                "USD/TWD에 극단 변동이 난다. 무역·경상흑자만으로 생보 파생 포지션에 따른 "
                "단기 환율 급등락을 정량 예측할 수 없다."
            ),
        },
        {
            "id": "taiex_domestic_decouple",
            "title_ko": "가권 ↔ 내수 디커플링",
            "body_ko": (
                "가권 사상 최고는 글로벌 AI·TSMC 실적을 반영할 뿐 비IT 임금·내수 소비로 "
                "직결되지 않는다. 주가 상승을 전체 경제 건전성 향상으로 인과 추론하면 오류다."
            ),
        },
        {
            "id": "excess_savings_offshore",
            "title_ko": "초과저축·M2 ↔ 생산적 투자",
            "body_ko": (
                "M2·초과저축이 커도 지정학 불확실성으로 자본이 국내 고정설비보다 역외로 유출될 수 있다. "
                "총량 유동성으로 장기 GDP 잠재력·내수 인플레를 정량 계산하는 모델은 성립하지 않는다."
            ),
        },
        {
            "id": "cross_strait_nonquant",
            "title_ko": "양안 지정학 · 비정량",
            "body_ko": (
                "외환보유·경상·생보 건전성이 안정해도 지정학 외생변수 발생 시 매크로 데이터는 "
                "가격 결정력을 상실한다. 시계열로 위기 시점·자산 충격 규모를 사전 정량 예측할 수 없다."
            ),
        },
    ],
}

IL_LIMITATIONS = {
    "title_ko": "지표 분석·추론의 한계 (이스라엘)",
    "items": [
        {
            "id": "war_nonquant",
            "title_ko": "전쟁·지정학 · 비정량 외생",
            "body_ko": (
                "CDS·셰켈·TA-125는 휴전·합의·확전 뉴스에 즉시 반응한다. "
                "평시 거시모형(금리→수요→물가)으로 충격 시점·크기를 사전 정량 예측할 수 없다."
            ),
        },
        {
            "id": "labor_supply_war",
            "title_ko": "낮은 실업 ↔ 노동공급 착시",
            "body_ko": (
                "예비군 동원·숙련인력 이탈로 실업률이 낮아도 공급 제약이 심할 수 있다. "
                "미국식 U3 완전고용 해석을 그대로 이식하면 안 된다."
            ),
        },
        {
            "id": "tech_export_domestic",
            "title_ko": "하이테크 수출 ↔ 내수 디커플링",
            "body_ko": (
                "하이테크 수출·TA-125 강세가 비테크 내수·서비스 고용으로 즉시 전이되지 않는다. "
                "한국 반도체 수출과 같은 ‘총량≠체감’ 함정이 있다."
            ),
        },
        {
            "id": "fiscal_war_spend",
            "title_ko": "재정수지 ↔ 성장 착시",
            "body_ko": (
                "국방·재건 지출이 GDP를 밀어 올려도 민간 생산성·지속 가능 성장과 동일하지 않다. "
                "적자 확대=곧바로 위기, 또는 GDP↑=건전 회복으로 단정할 수 없다."
            ),
        },
    ],
}

KIT_LIMITATIONS = {
    "us_macro_benchmark_v1": USA_LIMITATIONS,
    "jp_macro_v1": JPN_LIMITATIONS,
    "uk_macro_v1": UK_LIMITATIONS,
    "cn_macro_v1": CN_LIMITATIONS,
    "ez_macro_v1": EZ_LIMITATIONS,
    "ru_macro_v1": RU_LIMITATIONS,
    "hk_macro_v1": HK_LIMITATIONS,
    "sg_macro_v1": SG_LIMITATIONS,
    "za_macro_v1": ZA_LIMITATIONS,
    "in_macro_v1": IN_LIMITATIONS,
    "kr_macro_v1": KR_LIMITATIONS,
    "ca_macro_v1": CA_LIMITATIONS,
    "au_macro_v1": AU_LIMITATIONS,
    "ch_macro_v1": CH_LIMITATIONS,
    "br_macro_v1": BR_LIMITATIONS,
    "vn_macro_v1": VN_LIMITATIONS,
    "kz_macro_v1": KZ_LIMITATIONS,
    "tw_macro_v1": TW_LIMITATIONS,
    "il_macro_v1": IL_LIMITATIONS,
}


def _seed_for(iso3: str, series_id: str) -> int:
    return sum(ord(c) for c in f"{iso3}:{series_id}") * 17 + 42


def _zip_derived(a: list[float], b: list[float], c: list[float] | None, op: str) -> list[float]:
    out: list[float] = []
    for i in range(len(a)):
        if op == "net_liq":
            out.append(a[i] - b[i] / 1000.0 - (c[i] if c else 0.0) / 1000.0)
        elif op == "spread_bp":
            out.append((a[i] - b[i]) * 100.0)
        elif op == "diff":
            out.append(a[i] - b[i])
        else:
            raise ValueError(op)
    return out


def _headlines_for(kit: str) -> list[str]:
    if kit.startswith("us_"):
        return USA_HEADLINES
    if kit.startswith("jp_"):
        return JPN_HEADLINES
    if kit.startswith("uk_"):
        return UK_HEADLINES
    if kit.startswith("cn_"):
        return CN_HEADLINES
    if kit.startswith("ez_"):
        return EZ_HEADLINES
    if kit.startswith("ru_"):
        return RU_HEADLINES
    if kit.startswith("hk_"):
        return HK_HEADLINES
    if kit.startswith("sg_"):
        return SG_HEADLINES
    if kit.startswith("za_"):
        return ZA_HEADLINES
    if kit.startswith("in_"):
        return IN_HEADLINES
    if kit.startswith("kr_"):
        return KR_HEADLINES
    if kit.startswith("ca_"):
        return CA_HEADLINES
    if kit.startswith("au_"):
        return AU_HEADLINES
    if kit.startswith("ch_"):
        return CH_HEADLINES
    if kit.startswith("br_"):
        return BR_HEADLINES
    if kit.startswith("vn_"):
        return VN_HEADLINES
    if kit.startswith("kz_"):
        return KZ_HEADLINES
    if kit.startswith("tw_"):
        return TW_HEADLINES
    if kit.startswith("il_"):
        return IL_HEADLINES
    return THIN_HEADLINES


def build_country_pack(
    country: dict[str, Any],
    series_specs: list[dict[str, Any]],
    country_series: dict[str, Any],
    *,
    asof: date | None = None,
    history_months: int = 120,
) -> dict[str, Any]:
    asof = asof or date.today()
    dates = month_ends(asof, history_months)
    iso3 = country["iso3"]
    cfg_map = dict(country_series.get(iso3) or {})
    kit = cfg_map.pop("kit", "thin_v1")
    purpose_ko = cfg_map.pop("purpose_ko", None)

    specs_by_id = {s["id"]: s for s in series_specs}
    raw_values: dict[str, list[float]] = {}
    indicators: list[dict[str, Any]] = []

    for spec in series_specs:
        sid = spec["id"]
        cfg = cfg_map.get(sid)
        if not cfg or cfg.get("skip") or cfg.get("derived") or cfg.get("composite") or spec.get("derived"):
            continue
        # Composites (stack/bar groups) are assembled after member series exist.
        if spec.get("composite"):
            continue
        ind = build_indicator(
            series_id=sid,
            spec=spec,
            country_cfg=cfg,
            dates=dates,
            seed=_seed_for(iso3, sid),
        )
        indicators.append(ind)
        longest = max(ind["history"].values(), key=lambda h: len(h["values"]))
        raw_values[sid] = longest["values"]

    derived_jobs = []
    if "net_liquidity" in cfg_map or iso3 == "USA":
        if all(k in raw_values for k in ("fed_total_assets", "tga", "on_rrp")):
            derived_jobs.append(
                (
                    "net_liquidity",
                    _zip_derived(
                        raw_values["fed_total_assets"],
                        raw_values["tga"],
                        raw_values["on_rrp"],
                        "net_liq",
                    ),
                )
            )
    if all(k in raw_values for k in ("bond_10y", "bond_2y")) and (
        "spread_10y2y" in cfg_map or iso3 in ("USA", "JPN", "GBR")
    ):
        derived_jobs.append(
            (
                "spread_10y2y",
                _zip_derived(raw_values["bond_10y"], raw_values["bond_2y"], None, "spread_bp"),
            )
        )
    if all(k in raw_values for k in ("bond_30y", "bond_10y")) and (
        "spread_30y10y" in cfg_map or iso3 == "JPN"
    ):
        derived_jobs.append(
            (
                "spread_30y10y",
                _zip_derived(raw_values["bond_30y"], raw_values["bond_10y"], None, "spread_bp"),
            )
        )
    if all(k in raw_values for k in ("m1_yoy", "m2_yoy")) and (
        "m1_m2_spread" in cfg_map or iso3 == "CHN"
    ):
        derived_jobs.append(
            (
                "m1_m2_spread",
                _zip_derived(raw_values["m1_yoy"], raw_values["m2_yoy"], None, "diff"),
            )
        )
    if all(k in raw_values for k in ("btp_10y", "bund_10y")) and (
        "btp_bund_spread" in cfg_map or iso3 == "EMU"
    ):
        derived_jobs.append(
            (
                "btp_bund_spread",
                _zip_derived(raw_values["btp_10y"], raw_values["bund_10y"], None, "spread_bp"),
            )
        )

    for sid, vals in derived_jobs:
        spec = specs_by_id[sid]
        cfg = cfg_map.get(sid) or {"derived": True}
        ind = build_indicator(
            series_id=sid,
            spec=spec,
            country_cfg=cfg,
            dates=dates,
            seed=_seed_for(iso3, sid),
            values_override=vals,
        )
        indicators.append(ind)
        raw_values[sid] = vals

    by_id = {i["id"]: i for i in indicators}

    # --- Composite: Fed SOMA UST holdings (stack by maturity) ---
    ust_members = ["fed_ust_le_1y", "fed_ust_1_5y", "fed_ust_5_10y", "fed_ust_gt_10y"]
    if "fed_ust_holdings" in specs_by_id and all(m in by_id for m in ust_members):
        if "fed_ust_holdings" not in by_id:
            totals: list[float | None] = []
            n = len(dates)
            member_hist = []
            for m in ust_members:
                longest = max(by_id[m]["history"].values(), key=lambda h: len(h["values"]))
                member_hist.append(longest["values"])
            for i in range(n):
                parts = []
                for hv in member_hist:
                    idx = i - (n - len(hv)) if len(hv) < n else i
                    if 0 <= idx < len(hv) and hv[idx] is not None:
                        parts.append(float(hv[idx]))
                totals.append(round(sum(parts), 6) if parts else None)
            # Align length to dates (member windows may be shorter — pad from left)
            if len(totals) != n:
                totals = ([None] * (n - len(totals))) + totals
            spec = specs_by_id["fed_ust_holdings"]
            cfg = cfg_map.get("fed_ust_holdings") or {"derived": True}
            ind = build_indicator(
                series_id="fed_ust_holdings",
                spec=spec,
                country_cfg=cfg,
                dates=dates,
                seed=_seed_for(iso3, "fed_ust_holdings"),
                values_override=totals,
            )
            ind["components"] = [
                {
                    "id": m,
                    "label_ko": by_id[m]["label_ko"],
                    "value": by_id[m]["value"],
                    "display": by_id[m]["display"],
                    "unit": by_id[m]["unit"],
                }
                for m in ust_members
            ]
            ind["stack_series"] = ust_members
            ind["chart_type"] = "stack"
            ind["derived"] = "sum(fed_ust_maturity_buckets)"
            ind["source"] = "derived"
            indicators.append(ind)
            by_id[ind["id"]] = ind
            for m in ust_members:
                by_id[m].setdefault("ui", {})["chip"] = False
                by_id[m].setdefault("ui", {})["group"] = "fed_ust_holdings"

    # --- Composite: BOJ ETF holdings (balance + market share) ---
    if (
        "boj_etf_holdings" in specs_by_id
        and "boj_etf" in by_id
        and "boj_etf_share" in by_id
        and "boj_etf_holdings" not in by_id
    ):
        etf = by_id["boj_etf"]
        share = by_id["boj_etf_share"]
        spec = specs_by_id["boj_etf_holdings"]
        cfg = cfg_map.get("boj_etf_holdings") or {"derived": True}
        ind = build_indicator(
            series_id="boj_etf_holdings",
            spec=spec,
            country_cfg=cfg,
            dates=dates,
            seed=_seed_for(iso3, "boj_etf_holdings"),
            values_override=max(etf["history"].values(), key=lambda h: len(h["values"]))["values"],
        )
        ind["value"] = etf["value"]
        ind["display"] = etf["display"]
        ind["display_chip"] = f"{etf['display']} · 비중 {share['display']}"
        ind["components"] = [
            {
                "id": "boj_etf",
                "label_ko": etf["label_ko"],
                "value": etf["value"],
                "display": etf["display"],
                "unit": etf["unit"],
            },
            {
                "id": "boj_etf_share",
                "label_ko": share["label_ko"],
                "value": share["value"],
                "display": share["display"],
                "unit": share["unit"],
            },
        ]
        ind["chart_type"] = "bar"
        ind["derived"] = True
        ind["source"] = "derived"
        indicators.append(ind)
        by_id[ind["id"]] = ind
        for m in ("boj_etf", "boj_etf_share"):
            by_id[m].setdefault("ui", {})["chip"] = False
            by_id[m].setdefault("ui", {})["group"] = "boj_etf_holdings"

    # --- Composite: CB bond ops (QE/QT monthly by tenor + runoff) ---
    for ops_id in ("boj_jgb_ops", "fed_ust_ops", "ecb_bond_ops", "boe_gilt_ops"):
        if ops_id not in specs_by_id or ops_id not in cfg_map or ops_id in by_id:
            continue
        ocfg = cfg_map[ops_id]
        components = list(ocfg.get("components") or [])
        if not components:
            continue
        # Net purchase = sum of tenor buys − runoff (runoff stored positive as sell)
        net = 0.0
        for c in components:
            v = float(c.get("value") or 0)
            if c.get("id", "").endswith("runoff") or c.get("side") == "sell":
                net -= abs(v)
            else:
                net += v
        spec = specs_by_id[ops_id]
        ind = build_indicator(
            series_id=ops_id,
            spec=spec,
            country_cfg={**{k: v for k, v in ocfg.items() if k != "components"}, "base": net},
            dates=dates,
            seed=_seed_for(iso3, ops_id),
        )
        ind["components"] = components
        ind["chart_type"] = ocfg.get("chart_type") or spec.get("chart_type") or "bar"
        fmt = spec.get("format", "tn2")
        ind["display"] = format_value(net, fmt)
        ind["display_chip"] = f"순매입 {ind['display']}"
        indicators.append(ind)
        by_id[ind["id"]] = ind
        for legacy in ocfg.get("hides") or []:
            if legacy in by_id:
                by_id[legacy].setdefault("ui", {})["chip"] = False
                by_id[legacy].setdefault("ui", {})["group"] = ops_id

    # --- Composite: QRA issuance by maturity (bar) ---
    if "qra_issuance" in specs_by_id and "qra_issuance" in cfg_map and "qra_issuance" not in by_id:
        qcfg = cfg_map["qra_issuance"]
        components = list(qcfg.get("components") or [])
        if components:
            total = sum(float(c.get("value") or 0) for c in components)
            spec = specs_by_id["qra_issuance"]
            ind = build_indicator(
                series_id="qra_issuance",
                spec=spec,
                country_cfg={**{k: v for k, v in qcfg.items() if k != "components"}, "base": total},
                dates=dates,
                seed=_seed_for(iso3, "qra_issuance"),
            )
            ind["components"] = components
            ind["chart_type"] = qcfg.get("chart_type") or spec.get("chart_type") or "bar"
            indicators.append(ind)
            by_id[ind["id"]] = ind
            for legacy in ("qra_coupon_bn", "qra_bill_bn"):
                if legacy in by_id:
                    by_id[legacy].setdefault("ui", {})["chip"] = False
                    by_id[legacy].setdefault("ui", {})["group"] = "qra_issuance"

    _apply_qra_engine_file(by_id)

    # --- Composite: Sovereign ratings (S&P / Moody's / Fitch) ---
    if (
        "sovereign_ratings" in specs_by_id
        and "sovereign_ratings" in cfg_map
        and "sovereign_ratings" not in by_id
    ):
        rcfg = cfg_map["sovereign_ratings"]
        components = list(rcfg.get("components") or [])
        if components:
            spec = specs_by_id["sovereign_ratings"]
            headline = rcfg.get("display") or components[0].get("rating") or "—"
            ind = build_indicator(
                series_id="sovereign_ratings",
                spec=spec,
                country_cfg={
                    **{k: v for k, v in rcfg.items() if k not in ("components", "display")},
                    "base": 0.0,
                },
                dates=dates,
                seed=_seed_for(iso3, "sovereign_ratings"),
            )
            ind["value"] = headline
            ind["display"] = str(headline)
            ind["display_chip"] = " · ".join(
                f"{c.get('label_ko', c.get('agency', ''))} {c.get('rating', '—')}" for c in components
            )
            ind["components"] = components
            ind["chart_type"] = "status"
            ind["source"] = "fixture_synth"
            indicators.append(ind)
            by_id[ind["id"]] = ind

    # --- Dual GDP (YoY | QoQ, not SAAR) ---
    if (
        "gdp_yoy" in by_id
        and "gdp_qoq" in by_id
        and "gdp" in specs_by_id
        and "gdp" not in by_id
    ):
        yoy, qoq = by_id["gdp_yoy"], by_id["gdp_qoq"]
        spec = specs_by_id["gdp"]
        cfg = cfg_map.get("gdp") or {"derived": True}
        ind = build_indicator(
            series_id="gdp",
            spec=spec,
            country_cfg=cfg,
            dates=dates,
            seed=_seed_for(iso3, "gdp"),
            values_override=max(yoy["history"].values(), key=lambda h: len(h["values"]))["values"],
        )
        # Prefer YoY as primary value/history; attach dual modes for UI toggle.
        ind["value"] = yoy["value"]
        ind["display"] = yoy["display"]
        ind["display_chip"] = f"{yoy['display']} | {qoq['display']}"
        ind["change_1m_pct"] = yoy.get("change_1m_pct")
        ind["change_1y_pct"] = yoy.get("change_1y_pct")
        ind["history"] = yoy["history"]
        ind["ui"] = {
            "dual": ["yoy", "qoq"],
            "default": "yoy",
            "dual_ids": {"yoy": "gdp_yoy", "qoq": "gdp_qoq"},
        }
        ind["modes"] = {
            "yoy": {
                "label_ko": "YoY",
                "id": "gdp_yoy",
                "value": yoy["value"],
                "display": yoy["display"],
                "unit": yoy["unit"],
                "history": yoy["history"],
            },
            "qoq": {
                "label_ko": "QoQ",
                "id": "gdp_qoq",
                "value": qoq["value"],
                "display": qoq["display"],
                "unit": qoq["unit"],
                "history": qoq["history"],
                "note_ko": "분기 대비 % (연율 SAAR 아님)",
            },
        }
        ind["chart_type"] = "line"
        ind["derived"] = True
        ind["source"] = "derived"
        indicators.append(ind)
        by_id[ind["id"]] = ind
        for sid in ("gdp_yoy", "gdp_qoq"):
            by_id[sid].setdefault("ui", {})["chip"] = False
            by_id[sid].setdefault("ui", {})["dual"] = ["yoy", "qoq"]
            by_id[sid]["ui"]["default"] = "yoy"
            by_id[sid]["ui"]["dual_ids"] = {"yoy": "gdp_yoy", "qoq": "gdp_qoq"}
            by_id[sid]["ui"]["group"] = "gdp"
        # Optional BEA/national-accounts style contribution breakdown
        gcfg = cfg_map.get("gdp") or {}
        if gcfg.get("components"):
            by_id["gdp"]["components"] = gcfg["components"]
            by_id["gdp"]["chart_type"] = "line+components"

    _attach_electricity_generation(
        iso3=iso3,
        specs_by_id=specs_by_id,
        cfg_map=cfg_map,
        dates=dates,
        by_id=by_id,
        indicators=indicators,
    )

    # US Treasury FX watch status (non-US)
    if "us_fx_watch" in by_id:
        wcfg = cfg_map.get("us_fx_watch") or {}
        if wcfg.get("display"):
            by_id["us_fx_watch"]["display"] = wcfg["display"]
            by_id["us_fx_watch"]["display_chip"] = wcfg["display"]
        if wcfg.get("status"):
            by_id["us_fx_watch"]["status"] = wcfg["status"]
        by_id["us_fx_watch"]["chart_type"] = "status"
        by_id["us_fx_watch"]["history_years_note"] = "semiannual report points"

    # Apply country_cfg chip:false / skip already handled at build time
    for sid, cfg in cfg_map.items():
        if sid in by_id and isinstance(cfg, dict):
            if cfg.get("chip") is False or (cfg.get("ui") or {}).get("chip") is False:
                by_id[sid].setdefault("ui", {})["chip"] = False
            if cfg.get("components") and "components" not in by_id[sid]:
                by_id[sid]["components"] = cfg["components"]

    by_category: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES_ORDER}
    for ind in indicators:
        if (ind.get("ui") or {}).get("chip") is False:
            continue
        cat = ind["category"]
        if cat not in by_category:
            by_category[cat] = []
        chip: dict[str, Any] = {
            "id": ind["id"],
            "label_ko": ind["label_ko"],
            "display": ind.get("display_chip") or ind["display"],
            "value": ind["value"],
            "unit": ind["unit"],
            "change_1m_pct": ind["change_1m_pct"],
            "change_1y_pct": ind["change_1y_pct"],
            "asof": ind["asof"],
            "note_ko": ind.get("note_ko"),
        }
        if ind.get("reference"):
            chip["reference"] = ind["reference"]
        if ind.get("analog_ko"):
            chip["analog_ko"] = ind["analog_ko"]
        if ind.get("chart_type"):
            chip["chart_type"] = ind["chart_type"]
        if ind.get("ui"):
            chip["ui"] = ind["ui"]
        by_category[cat].append(chip)

    for cat in list(by_category.keys()):
        by_category[cat] = _sort_chips(cat, by_category[cat])

    headlines = []
    for hid in _headlines_for(kit):
        # Prefer composite gdp chip when headline asks for gdp_yoy
        lookup = hid
        if hid in ("gdp_yoy", "gdp_qoq") and "gdp" in by_id:
            lookup = "gdp"
        if lookup in by_id:
            i = by_id[lookup]
            headlines.append(
                {
                    "id": i["id"],
                    "category": i["category"],
                    "label_ko": i["label_ko"],
                    "display": i.get("display_chip") or i["display"],
                }
            )

    active_cats = [c for c in CATEGORIES_ORDER if by_category.get(c)]
    pack: dict[str, Any] = {
        "iso3": iso3,
        "iso2": country.get("iso2"),
        "name_ko": country["name_ko"],
        "name_en": country["name_en"],
        "aliases": list(country.get("aliases") or []),
        "currency": country.get("currency"),
        "coords": {"lat": country.get("lat"), "lon": country.get("lon")},
        "kit": kit,
        "benchmark": kit.startswith("us_"),
        "featured": kit.startswith(
            (
                "us_",
                "jp_",
                "uk_",
                "cn_",
                "ez_",
                "ru_",
                "hk_",
                "sg_",
                "za_",
                "in_",
                "kr_",
                "ca_",
                "au_",
                "ch_",
                "br_",
                "vn_",
                "kz_",
                "tw_",
                "il_",
            )
        ),
        "asof": dates[-1],
        "active_categories": active_cats,
        "headlines": headlines,
        "categories": {k: by_category[k] for k in active_cats},
        "indicators": indicators,
    }
    if purpose_ko:
        pack["purpose_ko"] = purpose_ko
    officials = officials_for(iso3)
    if officials:
        pack["officials"] = officials
    if kit in KIT_LIMITATIONS:
        pack["limitations"] = KIT_LIMITATIONS[kit]
    return pack


def build_universe(
    countries_doc: dict[str, Any],
    series_doc: dict[str, Any],
    *,
    asof: date | None = None,
    generated_at: str,
    limitations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    countries = countries_doc["countries"]
    series_specs = series_doc["series"]
    categories = series_doc["categories"]
    country_series = series_doc["country_series"]

    packs = []
    index = []
    for c in countries:
        pack = build_country_pack(c, series_specs, country_series, asof=asof)
        packs.append(pack)
        entry: dict[str, Any] = {
            "iso3": pack["iso3"],
            "name_ko": pack["name_ko"],
            "name_en": pack["name_en"],
            "aliases": pack["aliases"],
            "coords": pack["coords"],
            "kit": pack["kit"],
            "benchmark": pack["benchmark"],
            "featured": pack.get("featured", False),
            "headlines": pack["headlines"],
        }
        if pack.get("officials"):
            entry["officials"] = pack["officials"]
        index.append(entry)

    return {
        "schema_version": "macro-monitor-v1",
        "engine_version": "0.31.0",
        "generated_at": generated_at,
        "source": {
            "kind": "fixture_synth",
            "quality": "demo_not_live",
            "note": (
                "데모용 합성 시계열이다. 실시간이 아니며 KOSPI·주가 등은 base를 "
                "대략 맞춘 수준일 뿐 확정치가 아니다. 실데이터 어댑터(FRED/ECOS/yfinance) 이전."
            ),
        },
        "disclaimer_ko": "데모·연구용 매크로 스냅샷입니다. 투자 권유가 아니며 실시간이 아닙니다.",
        "purpose_ko": (
            "주요국 풀 키트. 대만은 반도체·생보 환헤지·USD/TWD·수출주문이 핵심."
        ),
        "refresh_policy": {
            "doc": "scripts/macro_monitor/REFRESH_TIERS.md",
            "alpha_vantage": "last_resort_only",
            "preferred": ["fred", "ecos", "kosis", "yfinance"],
        },
        "ui": {
            "mode": "crop_monitor_like",
            "stages": ["world_map", "country_overlay"],
            "category_tabs": categories,
            "interaction": {
                "map_click": "open_country",
                "chip_click": "open_history_chart",
                "history_windows": ["5y", "10y"],
                "layout": "no_side_dashboards_map_background",
            },
            "claude_handoff": "scripts/macro_monitor/CLAUDE_UI_HANDOFF_FULL.md",
        },
        "limitations": limitations or USA_LIMITATIONS,
        "countries_index": index,
        "countries": packs,
    }


def resolve_country(universe: dict[str, Any], query: str) -> dict[str, Any] | None:
    q = (query or "").strip().lower()
    if not q:
        return None
    for pack in universe.get("countries") or []:
        keys = [pack.get("iso3"), pack.get("iso2"), pack.get("name_en"), pack.get("name_ko")]
        keys.extend(pack.get("aliases") or [])
        for k in keys:
            if k and str(k).lower() == q:
                return pack
    return None
