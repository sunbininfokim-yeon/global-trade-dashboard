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

    day_r = _f(spot.get("day_return"), 0.0) or 0.0
    gap = _f(spot.get("premarket_gap"))
    pc_vol = _f(opt.get("put_call_volume"))
    pc_oi = _f(opt.get("put_call_oi"))
    call_v = _f(opt.get("call_volume"), 0.0) or 0.0
    put_v = _f(opt.get("put_volume"), 0.0) or 0.0
    total_v = call_v + put_v
    short_chg = _f(sh.get("short_chg_pct"), 0.0) or 0.0
    dtc = _f(sh.get("days_to_cover"), 0.0) or 0.0

    # Heuristic thresholds (v1; recalibrate monthly)
    put_heavy = pc_vol is not None and pc_vol >= 1.1
    call_heavy = pc_vol is not None and pc_vol <= 0.7
    both_active = total_v >= 50_000  # absolute; weak for small names
    short_up = short_chg >= 8.0
    short_down = short_chg <= -8.0
    down_day = day_r <= -0.02
    up_day = day_r >= 0.02
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
    if both_active and put_v > 0 and call_v > 0 and abs(day_r) < 0.01:
        # straddlish: both sides busy, spot quiet
        if put_heavy or call_heavy:
            pass
        else:
            regimes.append("vol_long_straddle")
            scores["vol_up"] += 0.8
    if both_active and abs(day_r) < 0.005 and pc_vol is not None and 0.85 <= pc_vol <= 1.15:
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
            "put_call_volume": pc_vol,
            "put_call_oi": pc_oi,
            "short_chg_pct": short_chg,
            "days_to_cover": dtc,
            "options_total_volume": total_v,
        },
    }


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

    # overall: emphasize downside for headline
    headline = "quiet"
    for ch in ("downside", "vol_up", "upside", "vol_down"):
        if channels_out[ch]["level"] == "high":
            headline = f"high:{ch}"
            break
        if channels_out[ch]["level"] == "watch" and headline == "quiet":
            headline = f"watch:{ch}"

    prior = open30m_prior_from_backtest(open30m_backtest)

    return {
        "schema_version": "us-kr-transmission-v1",
        "as_of": us_snap.get("as_of"),
        "model_version": "uskr-scenario-2026-08",
        "headline": headline,
        "channels": channels_out,
        "edges_active": sorted(edges_active, key=lambda e: -e["heat"])[:40],
        "tier_b_edges_fired": tier_b_n,
        "kospi_open30m_prior": prior,
        "source_priority_used": us_snap.get("source_priority_used"),
        "disclaimer_ko": us_snap.get("disclaimer_ko"),
        "note_ko": (
            "Tier A 고정 링크 (+ Tier B corr 발견, 하향 가중). "
            "주체 특정 없음. 하방 채널 강조. open30m_prior는 수익률 버킷 프록시."
        ),
    }
