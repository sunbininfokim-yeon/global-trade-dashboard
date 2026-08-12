"""AI Casino–style brief from a market_microstructure snapshot.

Paper sections mirrored (Market Ear / Soc Gen framing):
  concentration · leverage reset · % of free float · foreign vs retail ·
  wag-the-dog / short-gamma · ranked leverage products (click detail).
"""

from __future__ import annotations

from typing import Any


def _bn(x: float | None, digits: int = 2) -> float | None:
    if x is None:
        return None
    return round(float(x) / 1e9, digits)


def _pct(num: float | None, den: float | None, digits: int = 4) -> float | None:
    if num is None or den is None or den <= 0:
        return None
    return round(float(num) / float(den) * 100.0, digits)


def rank_leverage_products(
    snap: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rank KR + HK leverage products by AUM USD (crypto OI listed separately)."""
    fx = float(snap.get("fx_usdkrw") or 1400.0)
    rows: list[dict[str, Any]] = []

    for s in snap.get("stocks") or []:
        und = s["ticker"]
        name_und = s.get("name") or und
        for p in s.get("products") or []:
            aum_krw = float(p.get("aum") or 0.0)
            aum_usd = aum_krw / fx
            L = float(p.get("L") or 0.0)
            rows.append(
                {
                    "rank_key": "aum_usd",
                    "venue": "KR",
                    "ticker": p.get("ticker"),
                    "name": p.get("name"),
                    "underlying": und,
                    "underlying_name": name_und,
                    "L": L,
                    "structure": p.get("structure"),
                    "direction": "long" if L > 0 else "inverse",
                    "aum_usd": round(aum_usd, 2),
                    "notional_exposure_usd": round(abs(L) * aum_usd, 2),
                    "trading_value_usd": round(float(p.get("trading_value") or 0.0) / fx, 2),
                    "kr_spot_impact": "direct_cash_or_futures",
                    "note_ko": "KRX LETF — TR/IR · wag-the-dog 대상.",
                }
            )

    g = snap.get("global_leverage_stack") or {}
    for p in g.get("hk_products") or []:
        if p.get("error"):
            continue
        rows.append(
            {
                "rank_key": "aum_usd",
                "venue": "HK",
                "ticker": p.get("ticker"),
                "name": p.get("name"),
                "underlying": p.get("underlying"),
                "underlying_name": None,
                "L": p.get("L"),
                "structure": p.get("structure"),
                "direction": p.get("direction"),
                "aum_usd": round(float(p.get("aum_usd") or 0.0), 2),
                "notional_exposure_usd": round(float(p.get("notional_exposure_usd") or 0.0), 2),
                "trading_value_usd": round(float(p.get("trading_value_usd") or 0.0), 2),
                "kr_spot_impact": p.get("kr_spot_impact") or "indirect_swap",
                "note_ko": "HK CSOP swap — 유연 L. KR 현물 리밸런싱과 합산 금지.",
            }
        )

    rows.sort(key=lambda r: -float(r.get("aum_usd") or 0.0))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    crypto_rows: list[dict[str, Any]] = []
    for p in g.get("crypto_products") or []:
        if p.get("error"):
            continue
        crypto_rows.append(
            {
                "venue": "CRYPTO",
                "ticker": p.get("ticker"),
                "underlying": p.get("underlying"),
                "bucket": p.get("bucket"),
                "open_interest_notional_usd": round(
                    float(p.get("open_interest_notional_usd") or 0.0), 2
                ),
                "quote_volume_24h_usd": round(float(p.get("quote_volume_24h_usd") or 0.0), 2),
                "last_funding_rate": p.get("last_funding_rate"),
                "kr_spot_impact": p.get("kr_spot_impact") or "indirect_synthetic",
                "note_ko": "TradFi perp — ETF 아님. OI는 노출 프록시.",
            }
        )
    crypto_rows.sort(
        key=lambda r: -float(r.get("open_interest_notional_usd") or 0.0)
    )
    for i, r in enumerate(crypto_rows, 1):
        r["rank"] = i

    return rows, crypto_rows


def _stock_youtube_impact(
    snap: dict[str, Any], day: dict[str, Any], ticker: str, fx: float
) -> dict[str, Any] | None:
    """YouTube / wag-the-dog style reverse: spot ADV vs LETF AUM & day TV & IR."""
    st_day = next((s for s in (day.get("stocks") or []) if s.get("ticker") == ticker), None)
    st = next((s for s in (snap.get("stocks") or []) if s.get("ticker") == ticker), None)
    if not st:
        return None
    products = st.get("products") or []
    mcap = float((st_day or {}).get("market_cap_krw") or st.get("market_cap_krw") or 0.0)
    ff = float(st.get("free_float_mcap_krw") or 0.0)
    adv = float(st.get("adv_spot_krw") or 0.0)
    letf_tv = float(
        (st_day or {}).get("letf_trading_value_krw")
        or st.get("letf_trading_value_krw")
        or sum(float(p.get("trading_value") or 0) for p in products)
    )
    aum = sum(float(p.get("aum") or 0) for p in products)
    notional = sum(abs(float(p.get("L") or 0)) * float(p.get("aum") or 0) for p in products)
    tangle = st.get("flow_tangle") or {}
    ext = st.get("external_vs_spot") or {}
    realized = (st.get("scenarios") or {}).get("r_realized") or {}

    by_aum = sorted(products, key=lambda p: -float(p.get("aum") or 0))
    top3_kr = [
        {
            "ticker": p.get("ticker"),
            "name": p.get("name"),
            "L": p.get("L"),
            "aum_krw": float(p.get("aum") or 0),
            "aum_usd": round(float(p.get("aum") or 0) / fx, 2),
            "trading_value_krw": float(p.get("trading_value") or 0),
            "structure": p.get("structure"),
            "note_ko": "KR listing MarCap ≈ AUM/NAV×주식수 프록시",
        }
        for p in by_aum[:3]
    ]

    return {
        "ticker": ticker,
        "name": st.get("name") or (st_day or {}).get("name"),
        "as_of": snap.get("as_of"),
        "spot": {
            "close": (st_day or {}).get("close") or st.get("close"),
            "day_return": st.get("day_return"),
            "market_cap_krw": mcap,
            "market_cap_usd_bn": _bn(mcap / fx) if mcap else None,
            "free_float_mcap_krw": ff,
            "adv_spot_krw": adv,
            "adv_spot_usd_bn": _bn(adv / fx) if adv else None,
            "adv_spot_jo": None if adv <= 0 else round(adv / 1e12, 3),
        },
        "kr_letf": {
            "aum_krw": aum,
            "aum_usd_bn": _bn(aum / fx),
            "aum_jo": round(aum / 1e12, 3),
            "notional_aum_x_L_krw": notional,
            "notional_usd_bn": _bn(notional / fx),
            "day_trading_value_krw": letf_tv,
            "day_trading_value_jo": round(letf_tv / 1e12, 3),
            "day_trading_value_usd_bn": _bn(letf_tv / fx),
            "top3_by_aum": top3_kr,
        },
        "youtube_impact_ko": {
            "metric_1_wag_the_dog": {
                "name": "LETF 일거래대금 / 현물 ADV",
                "value_pct": None
                if st.get("letf_turnover_ratio") is None
                else round(float(st["letf_turnover_ratio"]) * 100.0, 2),
                "band": tangle.get("wag_the_dog_band"),
                "formula": "Σ LETF trading_value / underlying ADV",
                "read_ko": "유튜브 '개가 꼬리를 흔든다' — 레버 ETF 거래가 현물 대비 얼마나 큰지. low<5% · watch~10% · high≥10%.",
            },
            "metric_2_size_vs_mcap": {
                "name": "LETF AUM / 하이닉스 시총",
                "value_pct": _pct(aum, mcap),
                "formula": "Σ AUM / market_cap",
            },
            "metric_3_size_vs_ff": {
                "name": "LETF AUM×|L| / 유동시총",
                "value_pct": _pct(notional, ff),
                "formula": "Σ AUM×|L| / free_float",
            },
            "metric_4_short_gamma_ir": {
                "name": "실현 IR (리밸런싱 압력)",
                "value_pct": tangle.get("realized_ir_pct"),
                "tr_krw": realized.get("tr_abs_sum"),
                "day_R": st.get("day_return"),
                "formula": "TR=Σ AUM×(L²−L)×R · IR=|TR|/ADV×100",
                "read_ko": "종가 리밸런싱이 현물 ADV의 몇 %인지. 하락일·인버스 공존 시 숏감마 압력.",
                "scenario_minus_5pct_ir": ((st.get("scenarios") or {}).get("r_minus_5pct") or {}).get(
                    "ir_pct"
                ),
            },
            "metric_5_inverse_tv_share": {
                "name": "인버스 ETF 거래대금 비중",
                "value_pct": None
                if tangle.get("inverse_tv_share") is None
                else round(float(tangle["inverse_tv_share"]) * 100.0, 2),
                "inverse_aum_share_pct": None
                if tangle.get("inverse_aum_share") is None
                else round(float(tangle["inverse_aum_share"]) * 100.0, 2),
                "read_ko": "AUM 대비 인버스 거래비중이 크면 하락일에 헤지/리밸런싱 비대칭.",
            },
        },
        "external_size_compare": {
            "hk_notional_usd_bn": _bn(ext.get("hk_notional_usd")),
            "hk_over_spot_adv": ext.get("hk_over_spot_adv"),
            "crypto_oi_usd_bn": _bn(ext.get("crypto_oi_usd")),
            "crypto_oi_over_spot_adv": ext.get("crypto_oi_over_spot_adv"),
            "note_ko": ext.get("note_ko")
            or "HK/crypto는 규모 비교용. KR 현물 wag-the-dog 공식에 합산 금지.",
        },
    }


def build_ai_casino_brief(snap: dict[str, Any], day: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble paper-style headline metrics + ranked product drill-down."""
    day = day or {}
    kospi = day.get("kospi") or {}
    fx = float(snap.get("fx_usdkrw") or 1400.0)
    c = snap["concentration"]
    m = snap["market_levered_etf"]
    f = snap["foreign_vs_retail"]
    g = snap.get("global_leverage_stack") or {}
    cal = {row["field"]: row for row in snap.get("paper_calibration") or []}

    mkt_ff = float(kospi.get("free_float_mcap_krw") or 0.0)
    mkt_tot = float(kospi.get("total_mcap_krw") or 0.0)
    if mkt_ff <= 0:
        # recover from paper-style aum/ff if day not passed
        aum_row = cal.get("leverage_exposure_pct_aum_over_ff") or {}
        if aum_row.get("model_value") and m["aum_krw"]:
            pct = float(aum_row["model_value"])
            if pct > 0:
                mkt_ff = float(m["aum_krw"]) / (pct / 100.0)

    ss_aum = float(m.get("single_stock_kr_aum_krw") or 0.0)

    ranked, crypto_ranked = rank_leverage_products(snap)
    largest = ranked[0] if ranked else None
    top3_etf = ranked[:3]
    hynix_impact = _stock_youtube_impact(snap, day, "000660", fx)

    stock_cards = []
    for s in snap.get("stocks") or []:
        t = s.get("flow_tangle") or {}
        stock_cards.append(
            {
                "ticker": s["ticker"],
                "name": s.get("name"),
                "day_return": s.get("day_return"),
                "letf_turnover_ratio": s.get("letf_turnover_ratio"),
                "leverage_exposure_pct_of_stock_ff": s.get("leverage_exposure_pct"),
                "wag_the_dog_band": t.get("wag_the_dog_band"),
                "realized_ir_pct": t.get("realized_ir_pct"),
                "long_aum_share": t.get("long_aum_share"),
                "inverse_aum_share": t.get("inverse_aum_share"),
                "inverse_tv_share": t.get("inverse_tv_share"),
                "retail_net_krw": (s.get("flows_krw") or {}).get("retail_net_krw"),
                "foreign_net_krw": (s.get("flows_krw") or {}).get("foreign_net_krw"),
                "external_vs_spot": s.get("external_vs_spot"),
            }
        )

    # Headline “AI Casino closing” style bullets
    headlines = [
        {
            "id": "concentration",
            "title_en": "Concentration matters",
            "title_ko": "집중도",
            "stat": f"Conc_top2 {c['conc_top2_samsung_hynix_pct']:.1f}%",
            "detail_ko": (
                f"삼성+하닉 {c['conc_top2_samsung_hynix_pct']:.1f}% · "
                f"Top5 {c['conc_top5_pct']:.1f}% · Top10 {c['conc_top10_pct']:.1f}% · "
                f"tickers Top5={c.get('top5_tickers')} "
                f"(분모=KOSPI 전체시총)"
            ),
            "paper_note": "elevated concentration amplifies idiosyncratic + leverage feedback",
        },
        {
            "id": "leverage_reset",
            "title_en": "Leverage reset",
            "title_ko": "레버리지 AUM",
            "stat": f"${_bn(m['aum_usd'])}bn KR levered ETF",
            "detail_ko": (
                f"KR 레버/인버스 ETF AUM ${_bn(m['aum_usd'])}bn "
                f"(paper anchor ${_bn((cal.get('levered_etf_aum_usd') or {}).get('paper_anchor'))}bn). "
                f"단일종목 LETF ${_bn(ss_aum/fx)}bn."
            ),
            "paper_note": "paper peak ~$53bn → recent ~$26bn; model is live KR listing sum",
        },
        {
            "id": "free_float_share",
            "title_en": "Leverage vs free float",
            "title_ko": "유동시총 대비 레버 비중",
            "stat": (
                f"{(cal.get('leverage_exposure_pct_aum_over_ff') or {}).get('model_value')}% "
                f"of KOSPI free float (AUM)"
            ),
            "detail_ko": (
                f"paper-style AUM/FF = {(cal.get('leverage_exposure_pct_aum_over_ff') or {}).get('model_value')}% "
                f"(paper 2.1%). "
                f"단일종목 LETF AUM/KOSPI FF = {_pct(ss_aum, mkt_ff)}%. "
                f"노셔널 ΣAUM×|L|/커버종목 FF = "
                f"{(cal.get('leverage_exposure_pct_notional') or {}).get('model_value')}%. "
                f"HK·crypto는 분모에 넣지 않음."
            ),
            "paper_note": "Soc Gen chart ≈ levered ETF AUM / free float (not always ×|L|)",
        },
        {
            "id": "foreign_vs_retail",
            "title_en": "Foreign vs retail",
            "title_ko": "외인 vs 개인",
            "stat": (
                f"foreign {None if f.get('foreign_net_krw') is None else round(float(f['foreign_net_krw'])/1e12, 2)}조 · "
                f"retail {None if f.get('retail_net_krw') is None else round(float(f['retail_net_krw'])/1e12, 2)}조"
            ),
            "detail_ko": f"scope={f.get('scope')} · quality={f.get('quality')}",
            "paper_note": "who absorbs the other side of leverage flows",
        },
        {
            "id": "largest_product",
            "title_en": "Largest leverage product",
            "title_ko": "최대 레버 상품",
            "stat": (
                None
                if not largest
                else f"{largest['ticker']} · ${_bn(largest['aum_usd'])}bn AUM"
            ),
            "detail_ko": (
                None
                if not largest
                else (
                    f"{largest['venue']} {largest['name']} · underlying {largest['underlying']} · "
                    f"L={largest['L']} · notional ${_bn(largest['notional_exposure_usd'])}bn · "
                    f"{largest['note_ko']} "
                    f"(참고: 하이닉스 HK 메인은 7709.HK. 7708은 현재 유니버스/Yahoo에 없음.)"
                )
            ),
            "paper_note": "drill-down: ranked product table",
        },
        {
            "id": "hynix_wag",
            "title_en": "Hynix wag-the-dog",
            "title_ko": "하이닉스 ETF 영향도",
            "stat": (
                None
                if not hynix_impact
                else (
                    f"LETF/ADV "
                    f"{hynix_impact['youtube_impact_ko']['metric_1_wag_the_dog']['value_pct']}% · "
                    f"IR {hynix_impact['youtube_impact_ko']['metric_4_short_gamma_ir']['value_pct']}%"
                )
            ),
            "detail_ko": (
                None
                if not hynix_impact
                else (
                    f"현물 ADV {hynix_impact['spot']['adv_spot_jo']}조 · "
                    f"LETF TV {hynix_impact['kr_letf']['day_trading_value_jo']}조 · "
                    f"AUM {hynix_impact['kr_letf']['aum_jo']}조"
                )
            ),
            "paper_note": "YouTube reverse: turnover ratio + short-gamma IR",
        },
    ]

    free_float_block = {
        "kospi_total_mcap_krw": mkt_tot or None,
        "kospi_free_float_mcap_krw": mkt_ff or None,
        "kospi_free_float_mcap_usd_bn": _bn(mkt_ff / fx) if mkt_ff else None,
        "kr_all_levered_etf_aum_over_kospi_ff_pct": (cal.get("leverage_exposure_pct_aum_over_ff") or {}).get(
            "model_value"
        ),
        "kr_single_stock_letf_aum_over_kospi_ff_pct": _pct(ss_aum, mkt_ff),
        "kr_single_stock_notional_over_covered_ff_pct": (cal.get("leverage_exposure_pct_notional") or {}).get(
            "model_value"
        ),
        "paper_anchor_pct": 2.1,
        "definition_ko": (
            "유동시총 대비 레버 = (정의1) KR 레버ETF AUM / KOSPI 유동시총 — paper 2.1% 대응. "
            "(정의2) Σ AUM×|L|×β / 커버 종목 유동시총. HK·crypto는 KR 유동시총 분모에 합산하지 않음."
        ),
    }

    # --- L=2 means ~2× underlying exposure (notional), not just price % ---
    leverage_notional = {
        "rule_ko": "2배 레버 ETF 1좌의 경제적 노출 ≈ 기초자산 2좌. 모델은 AUM이 아니라 AUM×|L|로 센다.",
        "formulas": {
            "notional_exposure": "Σ AUM × |L| × β",
            "daily_rebalance_TR": "Σ AUM × (L² − L) × R",
            "L2_example": "L=+2 → (L²−L)=2; L=-2 → (L²−L)=6 (인버스가 AUM 대비 리밸런싱 더 큼)",
        },
        "beginner_ko": (
            "레버리지 2배 ETF를 100만 원어치 사면, 하이닉스가 1% 움직일 때 "
            "그 상품은 대략 2%를 목표로 합니다. 그래서 ‘지갑의 100만 원’이 "
            "시장에서는 ‘약 200만 원짜리 베팅’처럼 움직입니다. "
            "우리가 쓰는 노셔널(AUM×2)이 그 의미입니다."
        ),
        "expert_ko": (
            "Price target ≈ L×R (daily reset). Exposure stock = AUM×|L|. "
            "End-of-day hedge/rebalance notional TR = AUM×(L²−L)×R; "
            "IR = |TR|/ADV_spot. Long and inverse TR computed separately then summed."
        ),
    }

    # Trading-share snapshot (optional; filled by caller or defaults from last live)
    ts = (day.get("trading_share") or {}) if day else {}
    trading_share = {
        "as_of": snap.get("as_of"),
        "kospi_cash_tv_jo": ts.get("kospi_jo"),
        "kosdaq_cash_tv_jo": ts.get("kosdaq_jo"),
        "all_etf_tv_jo": ts.get("etf_jo"),
        "levered_inverse_etf_tv_jo": ts.get("lev_jo"),
        "single_stock_letf_tv_jo": ts.get("ss_jo"),
        "lev_of_all_etf_pct": ts.get("lev_of_etf_pct"),
        "lev_of_kospi_pct": ts.get("lev_of_kospi_pct"),
        "lev_of_kospi_kosdaq_pct": ts.get("lev_of_cash_pct"),
        "single_stock_of_kospi_pct": ts.get("ss_of_kospi_pct"),
        "stock_letf_over_spot": [
            {
                "ticker": s["ticker"],
                "name": s.get("name"),
                "letf_over_spot_adv_pct": None
                if s.get("letf_turnover_ratio") is None
                else round(float(s["letf_turnover_ratio"]) * 100.0, 2),
            }
            for s in stock_cards
        ],
        "note_ko": "ETF Amount(FDR)=백만원 단위. 레버+인버스 이름 매칭.",
    }

    # Single-stock LETF catalog (KR has few — show all as candidates, not search-first)
    ss_catalog = []
    for r in ranked:
        if r.get("venue") != "KR":
            continue
        # only true single-stock universe products
        if r.get("underlying") in ("000660", "005930"):
            ss_catalog.append(
                {
                    "ticker": r["ticker"],
                    "name": r.get("name"),
                    "underlying": r["underlying"],
                    "L": r["L"],
                    "aum_usd_bn": _bn(r.get("aum_usd")),
                    "structure": r.get("structure"),
                }
            )
    product_ux = {
        "recommendation_ko": (
            "국내 단일종목 레버/인버스는 소수(삼전·하닉만)라 옆 후보 목록이 맞음. "
            "ELW·옵션·개별선물까지 보면 종목이 폭증하므로 그때는 검색/필터. "
            "하이브리드: LETF는 카탈로그, 기타 파생은 검색."
        ),
        "single_stock_letf_kr": ss_catalog,
        "nearby_candidates_ko": [
            "지수 레버: KODEX 레버리지 / 인버스 / 200선물인버스2X",
            "섹터 레버: 반도체레버리지, 2차전지레버리지 (바스켓 — 개별주 wag와 분모 다름)",
            "HK: 7709/7747/7347 (swap, KR 합산 금지)",
            "기타 파생(검색): ELW, 주식선물, 옵션 OI",
        ],
    }

    audience = {
        "beginner": {
            "title_ko": "초심자 — 직관 비율",
            "bullets_ko": [
                f"오늘 코스피 현금 거래 중, 레버·인버스 ETF 거래는 대략 "
                f"{trading_share.get('lev_of_kospi_pct')}% 수준"
                if trading_share.get("lev_of_kospi_pct") is not None
                else "레버·인버스 ETF가 코스피 현금 거래의 상당 부분을 차지할 수 있음",
                f"ETF 시장 안에서는 레버·인버스가 약 "
                f"{trading_share.get('lev_of_all_etf_pct')}%"
                if trading_share.get("lev_of_all_etf_pct") is not None
                else "ETF 중 레버·인버스 비중이 큼",
                f"‘한 종목’ 레버(삼전·하닉)만 보면 코스피 거래의 약 "
                f"{trading_share.get('single_stock_of_kospi_pct')}% — 나머지는 지수/섹터 레버"
                if trading_share.get("single_stock_of_kospi_pct") is not None
                else "단일종목 레버는 소수, 대부분은 지수형",
                "하닉: 현물 거래 100원이면 레버 ETF가 약 9원 같이 움직임(당일 기준)",
                "삼전: 현물 100원 대비 레버 ETF 약 4원",
                leverage_notional["beginner_ko"],
                f"시총 쏠림: 삼성+하닉만 코스피의 약 {c.get('conc_top2_samsung_hynix_pct')}%",
            ],
            "analogy_ko": (
                "비유: 주차장(코스피 거래)에 차 100대가 들어오면, "
                "그 중 약 25대가 ‘가속 페달 달린 특수차(레버·인버스 ETF)’입니다. "
                "특수차 1대는 일반차 2대 분량의 힘을 씁니다(2배 레버)."
            ),
        },
        "expert": {
            "title_ko": "전문가 — 상세",
            "fields": {
                "trading_share": trading_share,
                "leverage_notional": leverage_notional,
                "concentration": c,
                "hynix_youtube_impact": hynix_impact,
                "top3_etf_by_aum_nav": top3_etf[:3],
                "global_stack": g,
                "paper_calibration": snap.get("paper_calibration"),
                "product_ux": product_ux,
            },
            "formulas_ko": [
                "LETF_turnover = Σ LETF TV / underlying ADV",
                "notional = Σ AUM×|L|×β",
                "TR = Σ AUM×(L²−L)×R ; IR = |TR|/ADV×100",
                "Conc_topN = Σ Marcap TopN / KOSPI total",
                "venue: KR cash wag ≠ HK swap ≠ crypto OI",
            ],
        },
    }

    return {
        "schema_version": "ai-casino-brief-v1",
        "as_of": snap["as_of"],
        "style": "Market Ear / Soc Gen AI Casino closing — quantitative mirror, not advice",
        "disclaimer_ko": snap.get("disclaimer_ko"),
        "audience": audience,
        "leverage_notional": leverage_notional,
        "trading_share": trading_share,
        "product_ux": product_ux,
        "headlines": headlines,
        "free_float_leverage": free_float_block,
        "concentration": c,
        "market_levered_etf": m,
        "foreign_vs_retail": f,
        "flows_kospi_market": snap.get("flows_kospi_market"),
        "deposit_credit": snap.get("deposit_credit"),
        "letf_category_share": snap.get("letf_category_share"),
        "short_interest": snap.get("short_interest_meta"),
        "global_leverage_stack_usd_bn": {
            "kr_single_stock_letf_notional": _bn(g.get("kr_single_stock_letf_notional_usd")),
            "hk_swap_letf_notional": _bn(g.get("hk_swap_letf_notional_usd")),
            "crypto_perp_oi": _bn(g.get("crypto_perp_oi_notional_usd")),
            "stack_sum_reference": _bn(g.get("global_stack_usd")),
            "note_ko": g.get("note_ko"),
        },
        "stocks": stock_cards,
        "hynix_youtube_impact": hynix_impact,
        "top3_etf_by_aum_nav": [
            {
                **r,
                "aum_usd_bn": _bn(r.get("aum_usd")),
                "notional_usd_bn": _bn(r.get("notional_exposure_usd")),
                "nav_note_ko": "AUM≈NAV×발행좌수 프록시 (KR MarCap / HK Yahoo marketCap)",
            }
            for r in top3_etf
        ],
        "paper_calibration": snap.get("paper_calibration"),
        "ranked_etf_by_aum": ranked,
        "ranked_crypto_by_oi": crypto_ranked,
        "largest_etf": largest,
        "ticker_note_7708_vs_7709_ko": (
            "하이닉스 HK 2x 메인은 CSOP 7709.HK. "
            "7708.HK는 현재 파이프라인/Yahoo 유니버스에 없고, AUM 1위도 7709."
        ),
    }


def markdown_ai_casino_brief(brief: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# AI Casino brief — {brief['as_of']}")
    lines.append("")
    lines.append(f"_{brief.get('style')}_")
    lines.append("")
    lines.append(brief.get("disclaimer_ko") or "")
    lines.append("")

    aud = brief.get("audience") or {}
    if aud.get("beginner"):
        b = aud["beginner"]
        lines.append(f"## {b['title_ko']}")
        lines.append("")
        lines.append(b.get("analogy_ko") or "")
        lines.append("")
        for bullet in b.get("bullets_ko") or []:
            lines.append(f"- {bullet}")
        lines.append("")
    if aud.get("expert"):
        e = aud["expert"]
        lines.append(f"## {e['title_ko']}")
        lines.append("")
        for fml in e.get("formulas_ko") or []:
            lines.append(f"- `{fml}`")
        lines.append("")

    ln = brief.get("leverage_notional") or {}
    if ln:
        lines.append("## Leverage = notional (1주 ≈ |L|주)")
        lines.append("")
        lines.append(ln.get("rule_ko") or "")
        lines.append("")
        lines.append(f"- beginner: {ln.get('beginner_ko')}")
        lines.append(f"- expert: {ln.get('expert_ko')}")
        lines.append(f"- formulas: {ln.get('formulas')}")
        lines.append("")

    ts = brief.get("trading_share") or {}
    if ts.get("lev_of_kospi_pct") is not None:
        lines.append("## Trading share (당일 거래대금)")
        lines.append("")
        lines.append("| metric | value |")
        lines.append("|--------|------:|")
        lines.append(f"| 레버+인버스 / 전체 ETF % | {ts.get('lev_of_all_etf_pct')} |")
        lines.append(f"| 레버+인버스 / KOSPI % | {ts.get('lev_of_kospi_pct')} |")
        lines.append(f"| 단일종목 LETF / KOSPI % | {ts.get('single_stock_of_kospi_pct')} |")
        lines.append(f"| 레버 TV 조 | {ts.get('levered_inverse_etf_tv_jo')} |")
        lines.append(f"| KOSPI TV 조 | {ts.get('kospi_cash_tv_jo')} |")
        lines.append("")

    ux = brief.get("product_ux") or {}
    if ux:
        lines.append("## Product UX (목록 vs 검색)")
        lines.append("")
        lines.append(ux.get("recommendation_ko") or "")
        lines.append("")
        for c in ux.get("nearby_candidates_ko") or []:
            lines.append(f"- {c}")
        lines.append("")

    lines.append("## Headlines")
    lines.append("")
    for h in brief["headlines"]:
        lines.append(f"### {h['title_en']} / {h['title_ko']}")
        lines.append("")
        lines.append(f"**{h['stat']}**")
        lines.append("")
        lines.append(h.get("detail_ko") or "")
        lines.append("")
        lines.append(f"> paper: {h.get('paper_note')}")
        lines.append("")

    ff = brief["free_float_leverage"]
    lines.append("## Free float — how much is leverage ETF?")
    lines.append("")
    lines.append(ff["definition_ko"])
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|--------|------:|")
    lines.append(
        f"| KOSPI free float (USD bn, approx) | {ff.get('kospi_free_float_mcap_usd_bn')} |"
    )
    lines.append(
        f"| KR all levered ETF AUM / KOSPI FF % | {ff.get('kr_all_levered_etf_aum_over_kospi_ff_pct')} |"
    )
    lines.append(
        f"| KR single-stock LETF AUM / KOSPI FF % | {ff.get('kr_single_stock_letf_aum_over_kospi_ff_pct')} |"
    )
    lines.append(
        f"| KR single-stock notional / covered FF % | {ff.get('kr_single_stock_notional_over_covered_ff_pct')} |"
    )
    lines.append(f"| paper anchor % | {ff.get('paper_anchor_pct')} |")
    lines.append("")

    c = brief.get("concentration") or {}
    lines.append("## Concentration (시총 TopN → Conc)")
    lines.append("")
    lines.append(c.get("note_ko") or "")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|--------|------:|")
    lines.append(f"| Conc_top2 삼성+하닉 % | {c.get('conc_top2_samsung_hynix_pct')} |")
    lines.append(f"| Conc_top5 % | {c.get('conc_top5_pct')} |")
    lines.append(f"| Conc_top10 % | {c.get('conc_top10_pct')} |")
    lines.append(f"| Top5 tickers | {', '.join(c.get('top5_tickers') or [])} |")
    lines.append(f"| Top10 tickers | {', '.join(c.get('top10_tickers') or [])} |")
    lines.append("")

    lines.append("## Top 3 ETF by AUM/NAV")
    lines.append("")
    lines.append("| # | venue | ticker | name | AUM $bn | notional $bn |")
    lines.append("|--:|-------|--------|------|--------:|-------------:|")
    for r in brief.get("top3_etf_by_aum_nav") or []:
        lines.append(
            f"| {r.get('rank')} | {r.get('venue')} | {r.get('ticker')} | {r.get('name')} | "
            f"{r.get('aum_usd_bn')} | {r.get('notional_usd_bn')} |"
        )
    lines.append("")
    lines.append((brief.get("top3_etf_by_aum_nav") or [{}])[0].get("nav_note_ko") or "")
    lines.append("")

    hy = brief.get("hynix_youtube_impact")
    if hy:
        lines.append("## Hynix — YouTube wag-the-dog reverse")
        lines.append("")
        sp, kr, yi = hy["spot"], hy["kr_letf"], hy["youtube_impact_ko"]
        lines.append(
            f"현물 ADV **{sp.get('adv_spot_jo')}조** (${sp.get('adv_spot_usd_bn')}bn) · "
            f"시총 ${sp.get('market_cap_usd_bn')}bn · day R {sp.get('day_return')}"
        )
        lines.append("")
        lines.append(
            f"KR LETF AUM **{kr.get('aum_jo')}조** (${kr.get('aum_usd_bn')}bn) · "
            f"일거래 **{kr.get('day_trading_value_jo')}조** · "
            f"노셔널 ${kr.get('notional_usd_bn')}bn"
        )
        lines.append("")
        lines.append("| YouTube metric | value |")
        lines.append("|---------------|------:|")
        m1 = yi["metric_1_wag_the_dog"]
        lines.append(f"| {m1['name']} % | {m1['value_pct']} ({m1.get('band')}) |")
        m2 = yi["metric_2_size_vs_mcap"]
        lines.append(f"| {m2['name']} % | {m2['value_pct']} |")
        m3 = yi["metric_3_size_vs_ff"]
        lines.append(f"| {m3['name']} % | {m3['value_pct']} |")
        m4 = yi["metric_4_short_gamma_ir"]
        lines.append(f"| {m4['name']} % | {m4['value_pct']} |")
        m5 = yi["metric_5_inverse_tv_share"]
        lines.append(f"| {m5['name']} % | {m5['value_pct']} |")
        lines.append("")
        lines.append("### Hynix KR LETF Top3 AUM")
        lines.append("")
        lines.append("| ticker | name | L | AUM 조 | day TV 조 |")
        lines.append("|--------|------|--:|------:|----------:|")
        for p in kr.get("top3_by_aum") or []:
            lines.append(
                f"| {p['ticker']} | {p.get('name')} | {p['L']} | "
                f"{p['aum_krw']/1e12:.3f} | {p['trading_value_krw']/1e12:.3f} |"
            )
        lines.append("")
        ex = hy.get("external_size_compare") or {}
        lines.append(
            f"HK notional ${ex.get('hk_notional_usd_bn')}bn "
            f"({None if ex.get('hk_over_spot_adv') is None else round(100*float(ex['hk_over_spot_adv']),1)}% of spot ADV) · "
            f"crypto OI ${ex.get('crypto_oi_usd_bn')}bn — {ex.get('note_ko')}"
        )
        lines.append("")

    lines.append("## Ranked leverage ETFs (click / open detail)")
    lines.append("")
    lines.append(brief.get("ticker_note_7708_vs_7709_ko") or "")
    lines.append("")
    lines.append("| # | venue | ticker | name | und | L | AUM $bn | notional $bn | impact |")
    lines.append("|--:|-------|--------|------|-----|--:|--------:|-------------:|--------|")
    for r in brief["ranked_etf_by_aum"]:
        lines.append(
            f"| {r['rank']} | {r['venue']} | {r['ticker']} | {r.get('name') or ''} | "
            f"{r['underlying']} | {r['L']} | {_bn(r['aum_usd'])} | {_bn(r['notional_exposure_usd'])} | "
            f"{r.get('kr_spot_impact')} |"
        )
    lines.append("")

    if brief.get("ranked_crypto_by_oi"):
        lines.append("## Crypto perps (not ETFs — OI rank)")
        lines.append("")
        lines.append("| # | ticker | und | OI $bn | 24h vol $bn |")
        lines.append("|--:|--------|-----|-------:|------------:|")
        for r in brief["ranked_crypto_by_oi"]:
            lines.append(
                f"| {r['rank']} | {r['ticker']} | {r['underlying']} | "
                f"{_bn(r['open_interest_notional_usd'])} | {_bn(r['quote_volume_24h_usd'])} |"
            )
        lines.append("")

    lines.append("## Stock microstructure cards")
    lines.append("")
    lines.append("| ticker | day_R | LETF/ADV | lev% FF | wag | realized IR% |")
    lines.append("|--------|------:|---------:|--------:|-----|-------------:|")
    for s in brief["stocks"]:
        lines.append(
            f"| {s['ticker']} | {s.get('day_return')} | {s.get('letf_turnover_ratio')} | "
            f"{s.get('leverage_exposure_pct_of_stock_ff')} | {s.get('wag_the_dog_band')} | "
            f"{s.get('realized_ir_pct')} |"
        )
    lines.append("")
    return "\n".join(lines)

