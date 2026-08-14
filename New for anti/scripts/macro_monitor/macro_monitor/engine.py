"""Assemble macro_monitor_v1 country packs from config + series builders."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from .explainers import KIT_EXPLAINERS, USA_EXPLAINERS
from .issuance_layers import attach_issuance_layers
from .series import build_indicator, format_value, month_ends


_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _status_for_indicator(ind: dict[str, Any]) -> str:
    """Return the public data-state label; never infer live from a value.

    Most of this pack is synthetic: build_indicator() starts every indicator at
    fixture_synth/demo, and only the handful listed in live_catalog get a real
    value pinned over the last point. Without an explicit label a fixture and a
    live quote render identically, which is how "당국 공표·추정" ended up on a
    number nobody ever fetched.
    """
    quality = str(ind.get("quality") or "").lower()
    source = str(ind.get("source") or "").lower()
    if quality.startswith("live"):
        return "live" if quality == "live" else "live_latest"
    if quality == "ember_yearly":
        return "delayed_official"
    if quality == "engine" or source == "qra_engine_v1":
        return "official_snapshot"
    if quality == "demo" or source in {"fixture_synth", "derived"}:
        return "demo"
    return "unknown"


def _mark_indicator_provenance(ind: dict[str, Any]) -> None:
    """Normalise provenance fields shared by JSON, Worker and UI readers."""
    ind["data_status"] = _status_for_indicator(ind)
    ind.setdefault("observed_at", ind.get("asof"))
    ind.setdefault("retrieved_at", None)


def _status_summary(indicators: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for ind in indicators:
        status = str(ind.get("data_status") or "unknown")
        out[status] = out.get(status, 0) + 1
    return out


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
    if hit.get("sources_uses"):
        ind["sources_uses"] = hit["sources_uses"]
    if hit.get("quarters"):
        ind["quarters"] = hit["quarters"]
    ind["source"] = hit.get("source") or "qra_engine_v1"
    ind["quality"] = "engine"
    if hit.get("asof"):
        ind["asof"] = str(hit["asof"])[:10]
    attach_issuance_layers(ind, sibling_ids=set(by_id.keys()))
    # Mirror maturity bars onto TGA (line primary + QRA maturity secondary)
    if "tga" in by_id and ind.get("components"):
        tga = by_id["tga"]
        tga["chart_type"] = "line"
        tga.setdefault("ui", {})["click_view"] = "line"
        tga["ui"]["secondary_view"] = "qra_maturity_bar_table"
        tga["maturity_components"] = ind["components"]
        tga["maturity_table"] = ind.get("table") or [
            {
                "kind": c.get("kind")
                or ("bill" if "bill" in str(c.get("id", "")).lower() else "coupon"),
                "label_ko": c.get("label_ko"),
                "tenor": c.get("tenor"),
                "value_bn": c.get("value"),
            }
            for c in ind["components"]
        ]
        if hit.get("tga_vs_qra"):
            tga["tga_vs_qra"] = hit["tga_vs_qra"]


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
        "dts_marketable_net",
        "public_debt_outstanding",
        "mts_deficit",
        "mts_receipts",
        "mts_outlays",
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

# Map preview (국가 클릭 전): 공통 5슬롯 + 국가 key 1개
HEADLINE_ROLE_KO = {
    "growth": "성장",
    "policy_rate": "기준금리",
    "inflation": "물가",
    "credit_rating": "신용등급",
    "fx": "환율",
    "key": "핵심",
}
HEADLINE_ROLE_ORDER = (
    "growth",
    "policy_rate",
    "inflation",
    "credit_rating",
    "fx",
    "key",
)

# kit → {role: series_id}
KIT_HEADLINES: dict[str, dict[str, str]] = {
    "us_macro_benchmark_v1": {
        "growth": "gdp",
        "policy_rate": "effr",
        "inflation": "core_cpi_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "dxy",
        "key": "spx",
    },
    "jp_macro_v1": {
        "growth": "gdp",
        "policy_rate": "call_rate",
        "inflation": "core_cpi_jp",
        "credit_rating": "sovereign_ratings",
        "fx": "usdjpy",
        "key": "nikkei",
    },
    "uk_macro_v1": {
        "growth": "gdp",
        "policy_rate": "bank_rate",
        "inflation": "services_cpi",
        "credit_rating": "sovereign_ratings",
        "fx": "gbpusd",
        "key": "ftse100",
    },
    "cn_macro_v1": {
        "growth": "gdp",
        "policy_rate": "lpr_1y",
        "inflation": "cpi_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "usdcnh",
        "key": "csi300",
    },
    "ez_macro_v1": {
        "growth": "gdp",
        "policy_rate": "deposit_facility",
        "inflation": "hicp_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "eurusd",
        "key": "euro_stoxx50",
    },
    "ru_macro_v1": {
        "growth": "gdp",
        "policy_rate": "cbr_key_rate",
        "inflation": "cpi_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "cnyrub",
        "key": "rtsi",
    },
    "hk_macro_v1": {
        "growth": "gdp",
        "policy_rate": "hibor_1m",
        "inflation": "composite_cpi",
        "credit_rating": "sovereign_ratings",
        "fx": "usdhkd",
        "key": "hsi",
    },
    "sg_macro_v1": {
        "growth": "gdp",
        "policy_rate": "sora",
        "inflation": "mas_core_infl",
        "credit_rating": "sovereign_ratings",
        "fx": "sgd_neer",
        "key": "sti",
    },
    "za_macro_v1": {
        "growth": "gdp",
        "policy_rate": "sarb_repo",
        "inflation": "cpi_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "usdzar",
        "key": "load_shedding_hours",
    },
    "in_macro_v1": {
        "growth": "gdp",
        "policy_rate": "rbi_repo",
        "inflation": "cpi_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "usdinr",
        "key": "nifty50",
    },
    "il_macro_v1": {
        "growth": "gdp",
        "policy_rate": "boi_rate",
        "inflation": "cpi_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "usdils",
        "key": "high_tech_export_yoy",
    },
    "kr_macro_v1": {
        "growth": "gdp",
        "policy_rate": "bok_base_rate",
        "inflation": "cpi_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "usdkrw",
        "key": "semi_export_yoy",
    },
    "ca_macro_v1": {
        "growth": "gdp",
        "policy_rate": "boc_overnight",
        "inflation": "cpi_trim",
        "credit_rating": "sovereign_ratings",
        "fx": "usdcad",
        "key": "wcs_oil",
    },
    "au_macro_v1": {
        "growth": "gdp",
        "policy_rate": "rba_cash_rate",
        "inflation": "trimmed_mean_cpi",
        "credit_rating": "sovereign_ratings",
        "fx": "audusd",
        "key": "iron_ore",
    },
    "ch_macro_v1": {
        "growth": "gdp",
        "policy_rate": "snb_policy_rate",
        "inflation": "cpi_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "eurchf",
        "key": "smi",
    },
    "br_macro_v1": {
        "growth": "gdp",
        "policy_rate": "selic_rate",
        "inflation": "ipca",
        "credit_rating": "sovereign_ratings",
        "fx": "usdbrl",
        "key": "ibovespa",
    },
    "vn_macro_v1": {
        "growth": "gdp",
        "policy_rate": "sbv_refinancing",
        "inflation": "cpi_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "usdvnd",
        "key": "fdi_disbursed",
    },
    "kz_macro_v1": {
        "growth": "gdp",
        "policy_rate": "nbk_base_rate",
        "inflation": "cpi_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "usdkzt",
        "key": "uranium",
    },
    "tw_macro_v1": {
        "growth": "gdp",
        "policy_rate": "cbc_discount",
        "inflation": "cpi_yoy",
        "credit_rating": "sovereign_ratings",
        "fx": "usdtwd",
        "key": "export_orders_yoy",
    },
}

THIN_HEADLINES = {
    "growth": "gdp_yoy",
    "policy_rate": "effr",
    "inflation": "cpi_yoy",
    "credit_rating": "sovereign_ratings",
    "fx": "usdjpy",
    "key": "spx",
}

# Back-compat aliases (tests / older call sites)
KIT_LIMITATIONS = KIT_EXPLAINERS
USA_LIMITATIONS = USA_EXPLAINERS


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


def _headlines_for(kit: str) -> list[tuple[str, str]]:
    """Return ordered (role, series_id) for map-preview headlines."""
    mapping = KIT_HEADLINES.get(kit) or THIN_HEADLINES
    out: list[tuple[str, str]] = []
    for role in HEADLINE_ROLE_ORDER:
        sid = mapping.get(role)
        if sid:
            out.append((role, sid))
    return out


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
            if cfg.get("table") and "table" not in by_id[sid]:
                by_id[sid]["table"] = cfg["table"]

    # QRA maturity table + TGA secondary view (fixture path)
    if "qra_issuance" in by_id:
        qind = by_id["qra_issuance"]
        comps = list(qind.get("components") or [])
        for c in comps:
            if not c.get("kind"):
                c["kind"] = (
                    "bill"
                    if "bill" in str(c.get("id", "")).lower()
                    or str(c.get("tenor", "")).lower() == "bills"
                    else "coupon"
                )
        if comps and not qind.get("table"):
            qind["table"] = [
                {
                    "kind": c.get("kind"),
                    "label_ko": c.get("label_ko"),
                    "tenor": c.get("tenor"),
                    "value_bn": c.get("value"),
                }
                for c in comps
            ]
        if "tga" in by_id and comps:
            tga = by_id["tga"]
            tga["chart_type"] = tga.get("chart_type") or "line"
            tga.setdefault("ui", {})["click_view"] = "line"
            tga["ui"]["secondary_view"] = "qra_maturity_bar_table"
            tga["maturity_components"] = comps
            tga["maturity_table"] = qind.get("table")
        attach_issuance_layers(qind, sibling_ids=set(by_id.keys()))

    for ind in indicators:
        _mark_indicator_provenance(ind)

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
            "observed_at": ind.get("observed_at"),
            "retrieved_at": ind.get("retrieved_at"),
            "source": ind.get("source"),
            "data_status": ind.get("data_status"),
            "chart_type": ind.get("chart_type"),
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
    for role, hid in _headlines_for(kit):
        lookup = hid
        if hid in ("gdp_yoy", "gdp_qoq", "gdp"):
            if "gdp" in by_id:
                lookup = "gdp"
            elif "gdp_yoy" in by_id:
                lookup = "gdp_yoy"
        if lookup not in by_id:
            continue
        i = by_id[lookup]
        headlines.append(
            {
                "id": i["id"],
                "role": role,
                "role_ko": HEADLINE_ROLE_KO.get(role, role),
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
        "data_status_summary": _status_summary(indicators),
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
            "data_status_summary": pack.get("data_status_summary") or {},
        }
        if pack.get("officials"):
            entry["officials"] = pack["officials"]
        index.append(entry)

    return {
        "schema_version": "macro-monitor-v1",
        "engine_version": "0.34.0",
        "generated_at": generated_at,
        "source": {
            "kind": "fixture_synth",
            "quality": "demo_not_live",
            "note": (
                "데모용 합성 시계열이다. 실시간이 아니며 KOSPI·주가 등은 base를 "
                "대략 맞춘 수준일 뿐 확정치가 아니다. 실데이터 어댑터(FRED/ECOS/yfinance) 이전."
            ),
        },
        "data_status_legend": {
            "live": "실데이터 시계열",
            "live_latest": "최근 관측치 실데이터 · 이전 이력은 아직 완전 교체 전",
            "official_snapshot": "공식 문서에서 파싱한 스냅샷 · 자동 실시간 값 아님",
            "delayed_official": "공식 연간/월간 데이터 · 발표 시차 존재",
            "demo": "합성 데모 데이터 · 시장 판단에 사용 금지",
            "unknown": "상태 미확인",
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
