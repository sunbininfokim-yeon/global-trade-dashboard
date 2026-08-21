"""US options/short regime classification + KR transmission alerts.

Display language: scenario/channel names only (no event nicknames).
"""

from __future__ import annotations

from typing import Any


def _f(x: Any, default: float | None = None) -> float | None:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def classify_name(row: dict[str, Any]) -> dict[str, Any]:
    """Assign regime + channel stress for one US name."""
    spot = row.get("spot") or {}
    opt = row.get("options") or {}
    sh = row.get("finra_short") or {}

    day_r = _f(spot.get("day_return"))
    gap = _f(spot.get("premarket_gap"))
    pc_vol = _f(opt.get("put_call_volume"))
    pc_oi = _f(opt.get("put_call_oi"))
    call_v = _f(opt.get("call_volume"))
    put_v = _f(opt.get("put_volume"))
    total_v = None if call_v is None or put_v is None else call_v + put_v
    iv_change = _f(opt.get("atm_call_iv_change"))
    short_chg = _f(sh.get("short_chg_pct"))
    dtc = _f(sh.get("days_to_cover"))

    # Heuristic thresholds (v1; recalibrate monthly)
    put_heavy = pc_vol is not None and pc_vol >= 1.1
    call_heavy = pc_vol is not None and pc_vol <= 0.7
    both_active = total_v is not None and total_v >= 50_000  # absolute; weak for small names
    short_up = short_chg is not None and short_chg >= 8.0
    short_down = short_chg is not None and short_chg <= -8.0
    down_day = day_r is not None and day_r <= -0.02
    up_day = day_r is not None and day_r >= 0.02
    gap_down = gap is not None and gap <= -0.015

    regimes: list[str] = []
    scores = {
        "downside": 0.0,
        "upside": 0.0,
        "vol_up": 0.0,
        "vol_down": 0.0,
    }

    if put_heavy and (down_day or (pc_oi or 0) >= 1.0):
        regimes.append("downside_put_bid")
        scores["downside"] += 1.0 + min(0.5, max(0.0, (pc_vol or 1) - 1.0))
    if call_heavy and up_day:
        regimes.append("upside_call_bid")
        scores["upside"] += 1.0 + min(0.5, max(0.0, 0.7 - (pc_vol or 0.7)))
    # A single IV level plus call/put volume cannot distinguish long-vol from
    # short-vol.  Only fire those regimes when a comparable-session IV change
    # is explicitly supplied; today's public snapshot does not yet supply it.
    neutral_pc = pc_vol is not None and 0.85 <= pc_vol <= 1.15
    spot_quiet = day_r is not None and abs(day_r) < 0.01
    if both_active and neutral_pc and spot_quiet and iv_change is not None:
        if iv_change >= 0.05:
            regimes.append("vol_long_straddle")
            scores["vol_up"] += 0.8
        elif iv_change <= -0.05:
            regimes.append("vol_short_strangle")
            scores["vol_down"] += 0.6
    if short_up and call_heavy and up_day:
        regimes.append("short_cover_squeeze")
        scores["upside"] += 0.9
    if gap_down or (down_day and put_heavy):
        regimes.append("gap_down_stress")
        scores["downside"] += 1.2
    if short_up and down_day:
        scores["downside"] += 0.5
    if short_down and up_day:
        scores["upside"] += 0.3

    if not regimes:
        regimes = ["quiet"]

    # downside emphasis
    scores["downside"] *= 1.25

    primary = max(scores.items(), key=lambda kv: kv[1])
    level = "quiet"
    if primary[1] >= 2.0:
        level = "high"
    elif primary[1] >= 1.0:
        level = "watch"

    return {
        "symbol": row.get("symbol"),
        "regimes": regimes,
        "channel_scores": {k: round(v, 3) for k, v in scores.items()},
        "primary_channel": primary[0] if primary[1] > 0 else "quiet",
        "stress_level": level if primary[1] > 0 else "quiet",
        "inputs": {
            "day_return": day_r,
            "premarket_gap": gap,
            "premarket_gap_quality": spot.get("premarket_gap_quality"),
            "put_call_volume": pc_vol,
            "put_call_oi": pc_oi,
            "atm_call_iv": _f(opt.get("atm_call_iv")),
            "atm_call_iv_change": iv_change,
            "short_chg_pct": short_chg,
            "days_to_cover": dtc,
            "options_total_volume": total_v,
        },
    }


def _downside_rules_ko(regime: dict[str, Any]) -> list[str]:
    """Explain only the downside conditions that actually fired."""
    regimes = set(regime.get("regimes") or [])
    inputs = regime.get("inputs") or {}
    rules: list[str] = []
    if "downside_put_bid" in regimes:
        rules.append(
            "풋/콜 거래량비 ≥1.1 그리고 (당일 수익률 ≤-2% 또는 풋/콜 OI ≥1.0)"
        )
    if "gap_down_stress" in regimes:
        gap = inputs.get("premarket_gap")
        if gap is not None and float(gap) <= -0.015:
            rules.append("프리마켓 갭 ≤-1.5%")
        else:
            rules.append("당일 수익률 ≤-2% 그리고 풋/콜 거래량비 ≥1.1")
    short_chg = inputs.get("short_chg_pct")
    day_return = inputs.get("day_return")
    if (
        short_chg is not None
        and day_return is not None
        and float(short_chg) >= 8.0
        and float(day_return) <= -0.02
    ):
        rules.append("공매도 잔고 증감 ≥8% 그리고 당일 수익률 ≤-2% (보조 점수)")
    return rules


def classify_universe(us_snap: dict[str, Any]) -> dict[str, Any]:
    out = []
    for row in us_snap.get("names") or []:
        out.append(classify_name(row))
    return {
        "schema_version": "us-regime-v1",
        "as_of": us_snap.get("as_of"),
        "names": out,
    }


def _iter_edges(
    link_graph: dict[str, Any],
    discovered: dict[str, Any] | None,
    *,
    tier_b_scale: float = 0.55,
    tier_b_top_n: int = 12,
) -> list[dict[str, Any]]:
    """Tier A fixed edges + optional Tier B discoveries (down-weighted)."""
    edges: list[dict[str, Any]] = []
    for edge in link_graph.get("edges") or []:
        e = dict(edge)
        e.setdefault("tier", "A")
        e.setdefault("quality", "structural")
        edges.append(e)

    if discovered:
        # Prefer KR cash anchors; skip pure KOSPI duplicates unless strong
        ranked = sorted(
            discovered.get("discovered_edges") or [],
            key=lambda x: float(x.get("score") or 0),
            reverse=True,
        )
        seen = {(e["us"], e["kr"]) for e in edges}
        added = 0
        for raw in ranked:
            if added >= tier_b_top_n:
                break
            us, kr = raw.get("us"), raw.get("kr")
            if not us or not kr or kr == "KOSPI":
                continue
            if (us, kr) in seen:
                continue
            # only promote if down-day or overall corr is meaningful
            pack = raw.get("corr_us_close_kr_open") or {}
            if abs(float(pack.get("corr") or 0)) < 0.35 and abs(
                float(pack.get("corr_us_down") or 0)
            ) < 0.30:
                continue
            w = float(raw.get("weight") or 0.4) * tier_b_scale
            edges.append(
                {
                    "id": raw.get("id"),
                    "us": us,
                    "kr": kr,
                    "edge_type": raw.get("edge_type") or "discovered_corr",
                    "weight": round(w, 3),
                    "tier": "B",
                    "quality": "estimated",
                    "score": raw.get("score"),
                }
            )
            seen.add((us, kr))
            added += 1
    return edges


def open30m_prior_from_backtest(bt: dict[str, Any] | None) -> dict[str, Any] | None:
    """Attach conditioned open priors to alerts (schema alert_v1 field)."""
    if not bt:
        return None
    ch = bt.get("channel_summary") or {}
    # Prefer first driver's overnight us_down / us_up buckets for 000660
    prior: dict[str, Any] = {
        "kr": bt.get("kr"),
        "proxy": "US close ±2% buckets (options history not used)",
        "channels": {},
    }
    for driver in bt.get("per_driver") or []:
        if driver.get("us") not in ("SOXL", "MU", "SMH"):
            continue
        oo = driver.get("open_overnight") or {}
        o30 = driver.get("open30m") or {}
        prior["channels"][driver["us"]] = {
            "overnight_us_down": oo.get("us_down"),
            "overnight_us_up": oo.get("us_up"),
            "overnight_baseline": oo.get("baseline"),
            "open30m_us_down": o30.get("us_down"),
            "open30m_baseline": o30.get("baseline"),
        }
    prior["downside_summary"] = ch.get("downside")
    prior["upside_summary"] = ch.get("upside")
    prior["vol_up"] = ch.get("vol_up")
    return prior


def build_transmission(
    us_snap: dict[str, Any],
    regimes: dict[str, Any],
    link_graph: dict[str, Any],
    *,
    discovered: dict[str, Any] | None = None,
    open30m_backtest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Join US regimes to KR anchors via Tier A (+ optional Tier B) edges."""
    by_sym = {r["symbol"]: r for r in regimes.get("names") or []}
    channels = {
        c: {"level": "quiet", "heat": 0.0, "drivers": [], "kr_tickers": set()}
        for c in ("downside", "upside", "vol_up", "vol_down")
    }
    edges_active = []
    tier_b_n = 0

    for edge in _iter_edges(link_graph, discovered):
        us = edge["us"]
        kr = edge["kr"]
        w = float(edge.get("weight") or 0.0)
        reg = by_sym.get(us)
        if not reg:
            continue
        for ch, score in (reg.get("channel_scores") or {}).items():
            if score <= 0:
                continue
            heat = w * float(score)
            if heat < 0.15:
                continue
            if edge.get("tier") == "B":
                tier_b_n += 1
            edges_active.append(
                {
                    "edge_id": edge.get("id"),
                    "us": us,
                    "kr": kr,
                    "edge_type": edge.get("edge_type"),
                    "tier": edge.get("tier", "A"),
                    "quality": edge.get("quality"),
                    "channel": ch,
                    "weight": w,
                    "us_score": score,
                    "heat": round(heat, 4),
                    "us_regimes": reg.get("regimes"),
                    "us_stress_level": reg.get("stress_level"),
                }
            )
            bucket = channels[ch]
            bucket["heat"] += heat
            bucket["kr_tickers"].add(kr)
            bucket["drivers"].append(
                {
                    "us": us,
                    "kr": kr,
                    "heat": round(heat, 4),
                    "edge_type": edge.get("edge_type"),
                    "tier": edge.get("tier", "A"),
                    "regimes": reg.get("regimes"),
                }
            )

    def _level(heat: float) -> str:
        if heat >= 2.5:
            return "high"
        if heat >= 1.0:
            return "watch"
        return "quiet"

    channels_out = {}
    for ch, b in channels.items():
        drivers = sorted(b["drivers"], key=lambda d: -d["heat"])[:12]
        channels_out[ch] = {
            "level": _level(b["heat"]),
            "heat": round(b["heat"], 4),
            "kr_tickers": sorted(b["kr_tickers"]),
            "drivers": drivers,
        }

    iv_change_observations = sum(
        1
        for name in regimes.get("names") or []
        if (name.get("inputs") or {}).get("atm_call_iv_change") is not None
    )
    for channel in ("vol_up", "vol_down"):
        channels_out[channel]["observable"] = iv_change_observations > 0
        channels_out[channel]["iv_change_observations"] = iv_change_observations
        if iv_change_observations == 0:
            channels_out[channel]["unavailable_reason_ko"] = (
                "비교 가능한 ATM IV 변화 시계열이 없어 거래량만으로 "
                "변동성 매수·매도를 판정하지 않음"
            )

    # overall: emphasize downside for headline
    headline = "quiet"
    for ch in ("downside", "vol_up", "upside", "vol_down"):
        if channels_out[ch]["level"] == "high":
            headline = f"high:{ch}"
            break
        if channels_out[ch]["level"] == "watch" and headline == "quiet":
            headline = f"watch:{ch}"

    prior = open30m_prior_from_backtest(open30m_backtest)

    # Human-readable "why" for UI (실측 inputs — not advice)
    evidence_us: list[dict[str, Any]] = []
    for n in regimes.get("names") or []:
        rules_ko = _downside_rules_ko(n)
        if not rules_ko:
            continue
        inp = n.get("inputs") or {}
        evidence_us.append(
            {
                "symbol": n.get("symbol"),
                "regimes": n.get("regimes"),
                "stress_level": n.get("stress_level"),
                "put_call_volume": inp.get("put_call_volume"),
                "put_call_oi": inp.get("put_call_oi"),
                "options_total_volume": inp.get("options_total_volume"),
                "short_chg_pct": inp.get("short_chg_pct"),
                "day_return": inp.get("day_return"),
                "premarket_gap": inp.get("premarket_gap"),
                "premarket_gap_quality": inp.get("premarket_gap_quality"),
                "downside_score": (n.get("channel_scores") or {}).get("downside"),
                "rules_ko": rules_ko,
                "rule_ko": " · ".join(rules_ko),
            }
        )
    evidence_us.sort(
        key=lambda r: float(r.get("downside_score") or 0), reverse=True
    )

    down = channels_out.get("downside") or {}
    top_drv = (down.get("drivers") or [])[:5]
    why_bits = []
    for e in evidence_us[:4]:
        why_bits.append(
            f"{e['symbol']} P/C거래량={e.get('put_call_volume')} "
            f"P/C OI={e.get('put_call_oi')} 프리마켓갭={e.get('premarket_gap')} "
            f"공매증감%={e.get('short_chg_pct')} [{e.get('rule_ko')}]"
        )
    link_bits = [
        f"{d['us']}→{d['kr']}(heat {d['heat']}, {d.get('edge_type')})" for d in top_drv
    ]
    headline_ko_map = {
        "high:downside": "높음 · 하방",
        "watch:downside": "주의 · 하방",
        "high:vol_up": "높음 · 변동성 확대",
        "watch:vol_up": "주의 · 변동성 확대",
        "high:upside": "높음 · 상방",
        "watch:upside": "주의 · 상방",
        "quiet": "조용",
    }
    why_ko = (
        "하방 heat는 공개 옵션의 풋 우위 조건 또는 큰 음의 프리마켓 갭 등 "
        "실제로 충족된 규칙을 한국 반도체·대형주 링크(Tier A/B)에 가중한 값이다. "
        + ("근거: " + " · ".join(why_bits) if why_bits else "")
        + ((" · 전이: " + ", ".join(link_bits)) if link_bits else "")
    )
    meaning_ko = {
        "headline": "오늘 US 레짐×KR 링크 heat의 최강 채널 요약. 투자 권유 아님.",
        "channels": "채널별 heat 합. 카드 클릭 시 drivers·US 옵션/숏 실측값 표를 열 것.",
        "drivers": "어느 미국 심볼→어느 한국 종목으로 heat가 전달되는지.",
        "edge_type": "etf_beta=수익률 링크(옵션 포지션 아님). discovered_corr=통계 발견.",
        "not_price_crash": (
            "당일 수익률이 작아도 P/C 조건이나 프리마켓 갭 조건으로 하방 레짐이 뜰 수 있음. "
            "각 evidence_us.rule_ko가 실제 발화 조건임."
        ),
    }

    return {
        "schema_version": "us-kr-transmission-v1",
        "as_of": us_snap.get("as_of"),
        "model_version": "uskr-scenario-2026-08",
        "headline": headline,
        "headline_ko": headline_ko_map.get(headline, headline),
        "why_ko": why_ko,
        "meaning_ko": meaning_ko,
        "evidence_us": evidence_us,
        "channels": channels_out,
        "edges_active": sorted(edges_active, key=lambda e: -e["heat"])[:40],
        "tier_b_edges_fired": tier_b_n,
        "kospi_open30m_prior": prior,
        "source_priority_used": us_snap.get("source_priority_used"),
        "ui_hint_ko": (
            "조기경보 박스/채널 카드/표 행을 클릭하면 evidence_us + drivers + "
            "us_regime_v1.inputs(P/C·숏) 상세 표를 모달로 표시."
        ),
        "disclaimer_ko": us_snap.get("disclaimer_ko"),
        "note_ko": (
            "Tier A 고정 링크 (+ Tier B corr 발견, 하향 가중). "
            "주체 특정 없음. 하방=실제 발화한 풋 우위/갭 스트레스×KR 링크 heat. "
            "IV 변화가 없으면 거래량만으로 vol-long/vol-short를 판정하지 않음. "
            "open30m_prior는 수익률 버킷 프록시(옵션 히스토리 아님)."
        ),
    }
