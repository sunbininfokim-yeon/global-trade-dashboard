"""Build market microstructure snapshot tables from day inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .formulas import (
    conc_named,
    concentration,
    delta_pct,
    impact_ratio,
    ir_band,
    letf_turnover_ratio,
    leverage_exposure_pct,
    total_rebalance,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _scenario_block(
    products: list[dict[str, Any]],
    adv: float,
    r: float,
    *,
    low: float,
    high: float,
) -> dict[str, Any]:
    tr = total_rebalance(products, r=r)
    ir = impact_ratio(tr["tr_abs_sum"], adv)
    return {
        "R": r,
        "tr_abs_sum": tr["tr_abs_sum"],
        "tr_long": tr["tr_long"],
        "tr_inverse": tr["tr_inverse"],
        "ir_pct": None if ir is None else round(ir, 4),
        "band": ir_band(ir, low=low, high=high),
    }


def build_snapshot(day: dict[str, Any], *, anchors: dict[str, Any] | None = None) -> dict[str, Any]:
    """day fixture → paper-aligned metric tables + calibration rows."""
    anchors = anchors or load_json(CONFIG / "paper_anchors.json")
    bands = anchors.get("ir_bands", {})
    low = float(bands.get("low_lt_pct", 3.0))
    high = float(bands.get("watch_lt_pct", 10.0))
    fx = float(day.get("fx_usdkrw") or anchors.get("fx_usdkrw_for_demo", 1400))

    kospi = day["kospi"]
    mcaps = {k: float(v) for k, v in kospi["constituent_mcaps_krw"].items()}
    univ = float(kospi["total_mcap_krw"])
    ranked_tickers = sorted(mcaps.items(), key=lambda kv: -kv[1])
    conc = {
        "conc_top2_samsung_hynix_pct": round(
            conc_named(mcaps, ["005930", "000660"], univ) or 0.0, 4
        ),
        "conc_top5_pct": round(concentration(mcaps, univ, 5) or 0.0, 4),
        "conc_top10_pct": round(concentration(mcaps, univ, 10) or 0.0, 4),
        "top5_tickers": [t for t, _ in ranked_tickers[:5]],
        "top10_tickers": [t for t, _ in ranked_tickers[:10]],
        "top5_mcap_krw": [round(v, 0) for _, v in ranked_tickers[:5]],
        "top10_mcap_krw": [round(v, 0) for _, v in ranked_tickers[:10]],
        "universe_mcap_krw": univ,
        "n_constituents_in_input": len(mcaps),
        "note_ko": (
            "Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. "
            "constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정."
        ),
        "quality": kospi.get("quality", "demo"),
        "source": kospi.get("source", "fixture"),
    }

    stocks_out: list[dict[str, Any]] = []
    for st in day["stocks"]:
        products = st["letf_products"]
        adv = float(st["adv_spot_krw"])
        ff = float(st["free_float_mcap_krw"])
        letf_tv = float(st.get("letf_trading_value_krw", 0.0))
        aum_sum = sum(float(p["aum"]) for p in products)
        aum_long = sum(float(p["aum"]) for p in products if float(p["L"]) > 0)
        aum_inv = sum(float(p["aum"]) for p in products if float(p["L"]) < 0)
        tv_long = sum(float(p.get("trading_value") or 0) for p in products if float(p["L"]) > 0)
        tv_inv = sum(float(p.get("trading_value") or 0) for p in products if float(p["L"]) < 0)
        lev_pct = leverage_exposure_pct(products, ff)
        turn = letf_turnover_ratio(letf_tv, adv)
        day_r = st.get("day_return")
        scenarios = {
            "r_minus_5pct": _scenario_block(products, adv, -0.05, low=low, high=high),
            "r_minus_10pct": _scenario_block(products, adv, -0.10, low=low, high=high),
            "r_plus_5pct": _scenario_block(products, adv, 0.05, low=low, high=high),
        }
        realized = None
        if day_r is not None:
            realized = _scenario_block(products, adv, float(day_r), low=low, high=high)
            scenarios["r_realized"] = realized

        flows_krw = st.get("flows_krw") or {}
        foreign_net = flows_krw.get("foreign_net_krw")
        retail_net = flows_krw.get("retail_net_krw")
        inst_net = flows_krw.get("institution_net_krw")
        # How flows are tangled: LETF turnover vs spot, long vs inverse, retail vs foreign
        tangle = {
            "letf_vs_spot_turnover": None if turn is None else round(turn, 4),
            "long_aum_share": round(aum_long / aum_sum, 4) if aum_sum > 0 else None,
            "inverse_aum_share": round(aum_inv / aum_sum, 4) if aum_sum > 0 else None,
            "long_tv_share": round(tv_long / letf_tv, 4) if letf_tv > 0 else None,
            "inverse_tv_share": round(tv_inv / letf_tv, 4) if letf_tv > 0 else None,
            "retail_vs_foreign_net_krw": {
                "retail": retail_net,
                "foreign": foreign_net,
                "institution": inst_net,
                "retail_minus_foreign": (
                    None
                    if retail_net is None or foreign_net is None
                    else retail_net - foreign_net
                ),
            },
            "realized_ir_pct": None if realized is None else realized["ir_pct"],
            "realized_band": None if realized is None else realized["band"],
            "wag_the_dog_band": (
                None
                if turn is None
                else ("high" if turn >= 0.5 else "mid" if turn >= 0.2 else "low")
            ),
            "note_ko": "LETF 거래대금 ÷ 현물 당일 거래대금과 롱·인버스 AUM·거래 비중을 함께 기록한 관측 프록시입니다. 실제 리밸런싱 체결·가격 영향·투자자 포지션은 이 값만으로 확인할 수 없습니다.",
        }

        stocks_out.append(
            {
                "ticker": st["ticker"],
                "name": st.get("name"),
                "venue": "kr",
                "adv_spot_krw": adv,
                # The source is the single-day FDR Amount / KRX ACC_TRDVAL,
                # despite the legacy ``adv`` name.  Keep both keys so the UI
                # history contract can state its denominator unambiguously.
                "spot_trading_value_krw": adv,
                "free_float_mcap_krw": ff,
                "free_float_ratio_assumed": st.get("free_float_ratio_assumed"),
                "market_cap_krw": float(st.get("market_cap_krw", ff)),
                "close": st.get("close"),
                "day_return": day_r,
                "letf_aum_sum_krw": aum_sum,
                "letf_aum_long_krw": aum_long,
                "letf_aum_inverse_krw": aum_inv,
                "letf_trading_value_krw": letf_tv,
                "leverage_exposure_pct": None if lev_pct is None else round(lev_pct, 4),
                "letf_turnover_ratio": None if turn is None else round(turn, 4),
                "foreign_hold_ratio_pct": st.get("foreign_hold_ratio_pct"),
                "flows_krw": flows_krw,
                "flows_shares": st.get("flows_shares"),
                "flow_tangle": tangle,
                "short_interest_shares": st.get("short_interest_shares"),
                "short_ratio_pct": st.get("short_ratio_pct"),
                "scenarios": scenarios,
                "products": [
                    {
                        "ticker": p["ticker"],
                        "name": p.get("name"),
                        "L": p["L"],
                        "aum": p["aum"],
                        "trading_value": p.get("trading_value"),
                        "beta": p.get("beta", 1.0),
                        "structure": p.get("structure"),
                        "direction": p.get("direction"),
                    }
                    for p in products
                ],
                "quality": st.get("quality", "demo"),
                "source": st.get("source", "fixture"),
            }
        )

    # Market-wide levered AUM (KR single-stock focus + optional all-levered)
    all_products = [p for st in stocks_out for p in st["products"]]
    kr_ss_aum = sum(float(p["aum"]) for p in all_products)
    market_lev = day.get("market_levered_etf", {})
    total_lev_aum_krw = float(market_lev.get("aum_krw", kr_ss_aum))
    total_lev_aum_usd = total_lev_aum_krw / fx

    flows = day.get("flows", {})
    foreign_vs_retail = {
        "foreign_net_krw": flows.get("foreign_net_krw"),
        "retail_net_krw": flows.get("retail_net_krw"),
        "institution_net_krw": flows.get("institution_net_krw"),
        "scope": flows.get("scope", "kospi_cash"),
        "quality": flows.get("quality", "demo"),
        "source": flows.get("source", "fixture"),
    }

    # Paper calibration rows
    casino = next(p for p in anchors["papers"] if p["id"] == "ai_casino_closing")
    aum_anchor = next(a for a in casino["anchors"] if a["field"] == "levered_etf_aum_usd_recent")
    lev_anchor = next(a for a in casino["anchors"] if a["field"] == "leverage_exposure_pct")

    # Stock-level: brief formula with |L|
    ff_combo = sum(float(s["free_float_mcap_krw"]) for s in stocks_out)
    lev_stock = leverage_exposure_pct(all_products, ff_combo) if ff_combo > 0 else None

    # Paper 2.1%: Soc Gen chart treats levered-ETF AUM / market free float
    # (not always ×|L|). Keep both; do not mutate the brief formula to force-fit.
    mkt_ff = float(kospi.get("free_float_mcap_krw") or 0.0)
    aum_pct_ff = (total_lev_aum_krw / mkt_ff * 100.0) if mkt_ff > 0 else None

    calibration = [
        {
            "field": "levered_etf_aum_usd",
            "paper_anchor": aum_anchor["value"],
            "model_value": round(total_lev_aum_usd, 2),
            "delta_pct": delta_pct(total_lev_aum_usd, aum_anchor["value"]),
            "note": "KR levered ETF AUM only (paper Korea chart); FX for USD",
            "quality": market_lev.get("quality", "demo"),
        },
        {
            "field": "leverage_exposure_pct_aum_over_ff",
            "paper_anchor": lev_anchor["value"],
            "model_value": None if aum_pct_ff is None else round(aum_pct_ff, 4),
            "delta_pct": delta_pct(aum_pct_ff, lev_anchor["value"]),
            "note": "paper-style: KR total levered ETF AUM / KOSPI free float (no |L|)",
            "quality": "estimated",
        },
        {
            "field": "leverage_exposure_pct_notional",
            "paper_anchor": None,
            "model_value": None if lev_stock is None else round(lev_stock, 4),
            "delta_pct": None,
            "note": "brief §4.3: Σ AUM×|L|×β / free_float of covered underlyings (KR only)",
            "quality": "estimated",
        },
    ]

    ext = day.get("external_venues") or {}
    kr_ss_notional_usd = sum(
        abs(float(p["L"])) * float(p["aum"]) / fx for p in all_products
    )
    hk_notional = float((ext.get("hk") or {}).get("notional_exposure_usd_sum") or 0.0)
    crypto_oi = float((ext.get("crypto") or {}).get("open_interest_notional_usd_sum") or 0.0)
    crypto_vol = float((ext.get("crypto") or {}).get("quote_volume_24h_usd_sum") or 0.0)
    us_notional = float((ext.get("us_proxy") or {}).get("notional_exposure_usd_sum") or 0.0)
    hk_dir = (ext.get("hk") or {}).get("direction_split") or {}
    us_dir = (ext.get("us_proxy") or {}).get("direction_split") or {}
    # KR single-stock long vs inverse notional
    kr_long_n = sum(
        abs(float(p["L"])) * float(p["aum"]) / fx
        for p in all_products
        if float(p["L"]) > 0
    )
    kr_inv_n = sum(
        abs(float(p["L"])) * float(p["aum"]) / fx
        for p in all_products
        if float(p["L"]) < 0
    )
    global_stack = {
        "note_ko": (
            "venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. "
            "다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 "
            "(스왑 상대 헷지 → 국내 압력)."
        ),
        "hedge_channel_ko": ext.get("hedge_channel_ko")
        or (
            "해외 레버·인버스·옵션 → 헷지 데스크 → 한국 현물/선물/국내 LETF 간접 압력"
        ),
        "kr_single_stock_letf_notional_usd": round(kr_ss_notional_usd, 2),
        "kr_single_stock_long_notional_usd": round(kr_long_n, 2),
        "kr_single_stock_inverse_notional_usd": round(kr_inv_n, 2),
        "hk_swap_letf_notional_usd": round(hk_notional, 2),
        "hk_direction_split": hk_dir,
        "us_levered_etf_notional_usd": round(us_notional, 2),
        "us_direction_split": us_dir,
        "crypto_perp_oi_notional_usd": round(crypto_oi, 2),
        "crypto_perp_quote_volume_24h_usd": round(crypto_vol, 2),
        "global_stack_usd": round(kr_ss_notional_usd + hk_notional + crypto_oi + us_notional, 2),
        "by_underlying_usd": ext.get("by_underlying_usd") or {},
        "hk_products": (ext.get("hk") or {}).get("products") or [],
        "crypto_products": (ext.get("crypto") or {}).get("products") or [],
        "us_proxy_products": (ext.get("us_proxy") or {}).get("products") or [],
        "quality": "observed" if ext else "missing",
        "source": ext.get("fetched_at") and "Yahoo HK/US + Binance perps (+ options via us_regime)" or None,
        "disclaimer_ko": (ext.get("disclaimer_ko") or ""),
    }

    # Per-stock: attach external exposure + HK products list
    hk_rows = global_stack.get("hk_products") or []
    for s in stocks_out:
        und = s["ticker"]
        bu = (ext.get("by_underlying_usd") or {}).get(und) or {}
        hk_u = float(bu.get("hk_usd") or 0.0)
        cr_u = float(bu.get("crypto_usd") or 0.0)
        adv_usd = float(s["adv_spot_krw"]) / fx
        s["products_hk"] = [
            {
                "ticker": p.get("ticker"),
                "name": p.get("name"),
                "L": p.get("L"),
                "direction": p.get("direction")
                or ("inverse" if float(p.get("L") or 0) < 0 else "long"),
                "aum_usd": p.get("aum_usd"),
                "notional_exposure_usd": p.get("notional_exposure_usd"),
                "trading_value_usd": p.get("trading_value_usd"),
                "structure": p.get("structure") or "swap",
                "venue": "hk",
                "kr_spot_impact": p.get("kr_spot_impact") or "indirect_swap",
                "note_ko": "스왑. 국내 cash 회전율 합산 금지 / spillover 모니터 1급.",
            }
            for p in hk_rows
            if str(p.get("underlying") or "") == und and not p.get("error")
        ]
        s["external_vs_spot"] = {
            "hk_notional_usd": round(hk_u, 2),
            "crypto_oi_usd": round(cr_u, 2),
            "hk_over_spot_adv": None if adv_usd <= 0 else round(hk_u / adv_usd, 4),
            "crypto_oi_over_spot_adv": None if adv_usd <= 0 else round(cr_u / adv_usd, 4),
            "note_ko": (
                "규모 비교용. 스왑→한국 기관 헷지 경로 가능 "
                "(YouTube wag reverse / 유튜브 하닉 레버 역산 계열)."
            ),
            "ticker_note_ko": "HK 하닉 2x 메인=7709.HK. products=국내, products_hk=홍콩.",
        }

    cat = (day.get("public_extras") or {}).get("letf_category_share") or {}
    kospi_tv = cat.get("kospi_cash_tv_krw")
    lev_tv = cat.get("levered_inverse_tv_krw")
    kospi_letf_tv_share_pct = (
        None
        if not kospi_tv or not lev_tv
        else round(100.0 * float(lev_tv) / float(kospi_tv), 3)
    )
    market_ratios = {
        "label_ko": "코스피·전시장 레버/곱버스·파생 비중",
        "levered_inverse_etf_tv_over_kospi_cash_tv_pct": kospi_letf_tv_share_pct,
        "long_tv_jo": cat.get("long_tv_jo"),
        "inverse_tv_jo": cat.get("inverse_tv_jo"),
        "gobus_tv_jo": cat.get("gobus_tv_jo"),
        "inverse_share_of_lev_tv_pct": cat.get("inverse_share_of_lev_tv_pct"),
        "by_direction": cat.get("by_direction"),
        "by_letf_category_tv_share_of_kospi_pct": {
            k: ((cat.get("by_category") or {}).get(k) or {}).get("share_of_kospi_tv_pct")
            for k in ("index", "single_stock", "sector", "overseas")
        },
        "top_inverse_gobus_by_tv": cat.get("top_inverse_gobus_by_tv"),
        "definitions_ko": {
            "gobus": "곱버스·지수 인버스2X 포함. by_direction / gobus_tv_jo.",
            "single_stock_inverse": "stocks inv AUM·inv_tv_share (하닉/삼전 인버스2X).",
            "global": "global_leverage_stack us_proxy(SOXL/SOXS…) + hk + options (us_regime).",
        },
        "quality": cat.get("quality") or "missing",
        "source": cat.get("source"),
    }

    return {
        "schema_version": "market-microstructure-v1",
        "as_of": day["as_of"],
        "disclaimer_ko": "공개 상품 AUM·거래대금 기반 추정. 증권사 고객 레버리지 공시가 아님. 투자 권유 아님.",
        "broker_leverage_disclosure": {
            "available": False,
            "note_ko": "증권사는 종목별 고객 레버리지 비율을 공시하지 않음. 대체: LETF AUM, FreeSIS 신용·미수 집계, KRX 투자자별 매매.",
            "public_proxies": [
                "krx_letf_aum",
                "krx_letf_turnover",
                "kofia_freesis_margin",
                "krx_investor_flows",
                "krx_short_interest",
                "yahoo_hk_letf",
                "yahoo_us_levered_inverse",
                "binance_stock_perps",
                "us_options_regime",
            ],
        },
        "fx_usdkrw": fx,
        "concentration": conc,
        "foreign_vs_retail": foreign_vs_retail,
        "market_levered_etf": {
            "aum_krw": total_lev_aum_krw,
            "aum_usd": round(total_lev_aum_usd, 2),
            "single_stock_kr_aum_krw": kr_ss_aum,
            "quality": market_lev.get("quality", "demo"),
            "source": market_lev.get("source", "fixture"),
        },
        "market_letf_derivatives_ratios": market_ratios,
        "global_leverage_stack": global_stack,
        "stocks": stocks_out,
        "paper_calibration": calibration,
        "ir_bands": {"low_lt_pct": low, "watch_lt_pct": high},
        "public_extras": day.get("public_extras"),
        "flows_kospi_market": day.get("flows_kospi_market"),
        "deposit_credit": (day.get("public_extras") or {}).get("deposit_credit"),
        "letf_category_share": (day.get("public_extras") or {}).get("letf_category_share"),
        "short_interest_meta": (day.get("public_extras") or {}).get("short_interest"),
        "ticker_note_7708_vs_7709_ko": (
            "하이닉스 HK 2x 메인=7709.HK. 7708 아님."
        ),
    }


def markdown_tables(snap: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Market microstructure tables — {snap['as_of']}")
    lines.append("")
    lines.append(snap["disclaimer_ko"])
    lines.append("")
    lines.append("## 0. 증권사 레버리지 공시?")
    lines.append("")
    lines.append("| 항목 | 값 |")
    lines.append("|------|-----|")
    b = snap["broker_leverage_disclosure"]
    lines.append(f"| available | {b['available']} |")
    lines.append(f"| note | {b['note_ko']} |")
    lines.append(f"| public_proxies | {', '.join(b['public_proxies'])} |")
    lines.append("")

    c = snap["concentration"]
    lines.append("## 1. Concentration (paper: concentration matters)")
    lines.append("")
    lines.append("| metric | value | source | quality |")
    lines.append("|--------|------:|--------|---------|")
    lines.append(
        f"| Conc_top2 (005930+000660) % | {c['conc_top2_samsung_hynix_pct']} | {c['source']} | {c['quality']} |"
    )
    lines.append(f"| Conc_top5 % | {c['conc_top5_pct']} | {c['source']} | {c['quality']} |")
    lines.append(f"| Conc_top10 % | {c['conc_top10_pct']} | {c['source']} | {c['quality']} |")
    if c.get("top5_tickers"):
        lines.append(f"| Top5 tickers | {', '.join(c['top5_tickers'])} | | |")
    if c.get("top10_tickers"):
        lines.append(f"| Top10 tickers | {', '.join(c['top10_tickers'])} | | |")
    if c.get("note_ko"):
        lines.append("")
        lines.append(c["note_ko"])
    lines.append("")

    f = snap["foreign_vs_retail"]
    lines.append("## 2. Foreign vs retail (paper: foreign vs retail)")
    lines.append("")
    lines.append("| actor | net_krw | scope | quality |")
    lines.append("|-------|--------:|-------|---------|")
    lines.append(
        f"| foreign | {f['foreign_net_krw']} | {f['scope']} | {f['quality']} |"
    )
    lines.append(f"| retail | {f['retail_net_krw']} | {f['scope']} | {f['quality']} |")
    lines.append(
        f"| institution | {f['institution_net_krw']} | {f['scope']} | {f['quality']} |"
    )
    lines.append("")

    m = snap["market_levered_etf"]
    lines.append("## 3. Leveraged ETF AUM (paper: leverage reset)")
    lines.append("")
    lines.append("| metric | KRW | USD | source | quality |")
    lines.append("|--------|----:|----:|--------|---------|")
    lines.append(
        f"| total levered ETF AUM | {m['aum_krw']:,.0f} | {m['aum_usd']:,.2f} | {m['source']} | {m['quality']} |"
    )
    lines.append(
        f"| KR single-stock LETF AUM (listed) | {m['single_stock_kr_aum_krw']:,.0f} | {m['single_stock_kr_aum_krw']/snap['fx_usdkrw']:,.2f} | sum products | {m['quality']} |"
    )
    lines.append("")

    lines.append("## 4. Stock LETF turnover & leverage exposure")
    lines.append("")
    lines.append(
        "| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |"
    )
    lines.append("|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|")
    for s in snap["stocks"]:
        lines.append(
            f"| {s['ticker']} | {s['letf_aum_sum_krw']:,.0f} | {s['adv_spot_krw']:,.0f} | "
            f"{s['letf_turnover_ratio']} | {s['leverage_exposure_pct']} | {s['short_ratio_pct']} |"
        )
    lines.append("")

    lines.append("## 4b. Flow tangle (수급이 어떻게 꼬였는지)")
    lines.append("")
    lines.append(
        "| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |"
    )
    lines.append(
        "|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|"
    )
    for s in snap["stocks"]:
        t = s.get("flow_tangle") or {}
        fk = s.get("flows_krw") or {}
        lines.append(
            f"| {s['ticker']} | {s.get('day_return')} | {t.get('wag_the_dog_band')} | "
            f"{None if t.get('long_aum_share') is None else round(100*t['long_aum_share'],1)} | "
            f"{None if t.get('inverse_aum_share') is None else round(100*t['inverse_aum_share'],1)} | "
            f"{None if t.get('inverse_tv_share') is None else round(100*t['inverse_tv_share'],1)} | "
            f"{fk.get('retail_net_krw')} | {fk.get('foreign_net_krw')} | {t.get('realized_ir_pct')} |"
        )
    lines.append("")
    lines.append(
        "해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. "
        "인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭."
    )
    lines.append("")

    lines.append("## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)")
    lines.append("")
    lines.append("| underlying | product | L | AUM | trading_value | structure |")
    lines.append("|------------|---------|--:|----:|--------------:|-----------|")
    for s in snap["stocks"]:
        for p in s.get("products") or []:
            lines.append(
                f"| {s['ticker']} | {p['ticker']} {p.get('name','')} | {p['L']} | "
                f"{p['aum']:,.0f} | {p.get('trading_value') or 0:,.0f} | {p.get('structure')} |"
            )
    lines.append("")

    g = snap.get("global_leverage_stack") or {}
    lines.append("## 4d. Global leverage stack (HK + crypto, venue-separated)")
    lines.append("")
    lines.append(g.get("note_ko") or "")
    lines.append("")
    lines.append("| venue | metric | USD |")
    lines.append("|-------|--------|----:|")
    lines.append(f"| KR single-stock LETF | notional AUM×\|L\| | {g.get('kr_single_stock_letf_notional_usd')} |")
    lines.append(f"| HK CSOP swap LETF | notional AUM×\|L\| | {g.get('hk_swap_letf_notional_usd')} |")
    lines.append(f"| Crypto Binance perps | OI notional | {g.get('crypto_perp_oi_notional_usd')} |")
    lines.append(f"| Crypto Binance perps | 24h quote volume | {g.get('crypto_perp_quote_volume_24h_usd')} |")
    lines.append(f"| Stack (KR+HK+crypto OI) | sum (reference only) | {g.get('global_stack_usd')} |")
    lines.append("")
    lines.append("| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |")
    lines.append("|------------|----------------:|--------------:|------------:|-------------------:|")
    for s in snap["stocks"]:
        e = s.get("external_vs_spot") or {}
        lines.append(
            f"| {s['ticker']} | {e.get('hk_notional_usd')} | {e.get('crypto_oi_usd')} | "
            f"{e.get('hk_over_spot_adv')} | {e.get('crypto_oi_over_spot_adv')} |"
        )
    lines.append("")
    lines.append("| HK product | underlying | L | AUM USD | TV USD | impact |")
    lines.append("|------------|------------|--:|--------:|-------:|--------|")
    for p in g.get("hk_products") or []:
        if p.get("error"):
            lines.append(f"| {p.get('ticker')} | {p.get('underlying')} |  |  |  | ERROR {p.get('error')} |")
            continue
        lines.append(
            f"| {p.get('ticker')} {p.get('name','')} | {p.get('underlying')} | {p.get('L')} | "
            f"{p.get('aum_usd')} | {p.get('trading_value_usd')} | {p.get('kr_spot_impact')} |"
        )
    lines.append("")
    lines.append("| Crypto product | underlying | OI USD | 24h vol USD | funding | impact |")
    lines.append("|---------------|------------|-------:|------------:|--------:|--------|")
    for p in g.get("crypto_products") or []:
        if p.get("error"):
            lines.append(f"| {p.get('ticker')} | {p.get('underlying')} |  |  |  | ERROR |")
            continue
        lines.append(
            f"| {p.get('ticker')} | {p.get('underlying')} | {p.get('open_interest_notional_usd')} | "
            f"{p.get('quote_volume_24h_usd')} | {p.get('last_funding_rate')} | {p.get('kr_spot_impact')} |"
        )
    lines.append("")

    lines.append("## 5. Rebalancing short-gamma scenarios (TR / IR)")
    lines.append("")
    lines.append("| ticker | R | TR_abs | IR % | band |")
    lines.append("|--------|--:|-------:|-----:|------|")
    for s in snap["stocks"]:
        for key, sc in s["scenarios"].items():
            lines.append(
                f"| {s['ticker']} | {sc['R']} | {sc['tr_abs_sum']:,.0f} | {sc['ir_pct']} | {sc['band']} |"
            )
    lines.append("")

    lines.append("## 6. Paper calibration")
    lines.append("")
    lines.append("| field | paper_anchor | model_value | delta_pct | quality |")
    lines.append("|-------|-------------:|------------:|----------:|---------|")
    for row in snap["paper_calibration"]:
        dp = row["delta_pct"]
        dp_s = "" if dp is None else f"{dp:.2f}"
        lines.append(
            f"| {row['field']} | {row['paper_anchor']} | {row['model_value']} | {dp_s} | {row['quality']} |"
        )
    lines.append("")

    dc = snap.get("deposit_credit") or {}
    if dc:
        lines.append("## 7. Deposit & credit (Naver / FreeSIS-style)")
        lines.append("")
        lines.append(dc.get("note_ko") or "")
        lines.append("")
        lines.append("| metric | 억원 | as_of | quality |")
        lines.append("|--------|-----:|-------|---------|")
        lines.append(
            f"| 고객예탁금 | {dc.get('investor_deposit_eok')} | {dc.get('as_of')} | {dc.get('quality')} |"
        )
        lines.append(
            f"| 신용잔고 | {dc.get('credit_balance_eok')} | {dc.get('as_of')} | {dc.get('quality')} |"
        )
        lines.append(
            f"| 신용/예탁금 % | {dc.get('credit_over_deposit_pct')} |  |  |"
        )
        lines.append("")

    fm = snap.get("flows_kospi_market") or {}
    if fm:
        lines.append("## 8. KOSPI market investor flows")
        lines.append("")
        lines.append("| actor | net_krw | date | quality |")
        lines.append("|-------|--------:|------|---------|")
        lines.append(
            f"| foreign | {fm.get('foreign_net_krw')} | {fm.get('date_raw')} | {fm.get('quality')} |"
        )
        lines.append(f"| retail | {fm.get('retail_net_krw')} | {fm.get('date_raw')} | {fm.get('quality')} |")
        lines.append(
            f"| institution | {fm.get('institution_net_krw')} | {fm.get('date_raw')} | {fm.get('quality')} |"
        )
        lines.append("")

    lc = snap.get("letf_category_share") or {}
    if lc.get("by_category"):
        lines.append("## 9. Levered ETF TV by category")
        lines.append("")
        lines.append(lc.get("note_ko") or "")
        lines.append("")
        lines.append("| category | n | TV 조 | % of lev TV | % of KOSPI TV |")
        lines.append("|----------|--:|------:|------------:|--------------:|")
        for cat, v in (lc.get("by_category") or {}).items():
            lines.append(
                f"| {cat} | {v.get('n_products')} | {v.get('trading_value_jo')} | "
                f"{v.get('share_of_lev_tv_pct')} | {v.get('share_of_kospi_tv_pct')} |"
            )
        lines.append("")

    sm = snap.get("short_interest_meta") or {}
    lines.append("## 10. Short interest")
    lines.append("")
    lines.append(f"| quality | {sm.get('quality')} |")
    lines.append(f"| source | {sm.get('source')} |")
    lines.append(f"| note | {sm.get('note_ko')} |")
    lines.append("")
    if sm.get("by_ticker"):
        lines.append("| ticker | shares | ratio % |")
        lines.append("|--------|-------:|--------:|")
        for t, v in sm["by_ticker"].items():
            lines.append(
                f"| {t} | {v.get('short_interest_shares')} | {v.get('short_ratio_pct')} |"
            )
        lines.append("")

    return "\n".join(lines)
