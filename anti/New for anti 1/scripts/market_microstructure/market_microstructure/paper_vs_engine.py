"""Paper-anchor calibration + US stress → KR event-study backtest.

1) Compare Market Ear / paper anchors to current engine snapshot.
2) On recent US semis derivatives stress days (SOXL/MU/SMH large downs),
   measure next KR overnight open for 000660/005930 and whether our
   downside proxy alert would have fired.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from market_microstructure.us_kr_discovery import (
    _align_us_to_next_kr,
    _series_close,
    download_daily,
)


def _f(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _sim(model: float | None, anchor: float | None) -> dict[str, Any]:
    if model is None or anchor is None or anchor == 0:
        return {"similarity": None, "delta_pct": None, "band": "n/a"}
    delta = (model - anchor) / abs(anchor) * 100.0
    ad = abs(delta)
    if ad <= 15:
        band = "close"  # within ~15%
    elif ad <= 40:
        band = "same_order"
    else:
        band = "diverged"
    return {
        "similarity": round(max(0.0, 100.0 - ad), 1),
        "delta_pct": round(delta, 2),
        "band": band,
    }


def compare_paper_vs_engine(
    snap: dict[str, Any],
    anchors: dict[str, Any],
    *,
    path_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build calibration table from snapshot + price-path anchors."""
    rows: list[dict[str, Any]] = []
    fx = float(snap.get("fx_usdkrw") or 1400)

    # From engine paper_calibration
    for cal in snap.get("paper_calibration") or []:
        sim = _sim(_f(cal.get("model_value")), _f(cal.get("paper_anchor")))
        rows.append(
            {
                "field": cal.get("field"),
                "paper_anchor": cal.get("paper_anchor"),
                "model_value": cal.get("model_value"),
                "delta_pct": cal.get("delta_pct")
                if cal.get("delta_pct") is not None
                else sim["delta_pct"],
                "band": sim["band"],
                "similarity_score": sim["similarity"],
                "note": cal.get("note"),
                "quality": cal.get("quality"),
                "source": "engine.paper_calibration",
            }
        )

    # Concentration — paper says elevated; we report level
    c = snap.get("concentration") or {}
    top2 = _f(c.get("conc_top2_samsung_hynix_pct"))
    rows.append(
        {
            "field": "conc_top2_samsung_hynix_pct",
            "paper_anchor": "elevated (~50% discussed)",
            "model_value": top2,
            "delta_pct": None,
            "band": "qualitative_match" if top2 and top2 >= 40 else "low",
            "similarity_score": None if not top2 else round(min(100.0, top2), 1),
            "note": "paper: concentration elevated; engine observes level",
            "quality": c.get("quality"),
            "source": "engine.concentration",
        }
    )

    # Global stack AUM (KR + note HK/US not in paper Korea chart)
    m = snap.get("market_levered_etf") or {}
    aum_usd = _f(m.get("aum_usd"))
    peak = 53e9
    recent = 26e9
    rows.append(
        {
            "field": "levered_etf_aum_vs_paper_peak",
            "paper_anchor": peak,
            "model_value": aum_usd,
            "delta_pct": None if aum_usd is None else round((aum_usd - peak) / peak * 100, 2),
            "band": "reset_confirmed" if aum_usd and aum_usd < peak * 0.7 else "n/a",
            "similarity_score": None,
            "note": "paper peak $53bn → reset; model is KR-only current",
            "quality": m.get("quality"),
            "source": "engine.market_levered_etf",
        }
    )

    # Price path anchors from yfinance (SOXL/KORU/KOSPI)
    if path_stats:
        for field, anchor_key, model_key in (
            ("soxl_path_peak", "soxl_peak_paper", "soxl_peak_1y"),
            ("soxl_path_recent", "soxl_recent_paper", "soxl_last"),
            ("koru_path_peak", "koru_peak_paper", "koru_peak_1y"),
            ("koru_path_recent", "koru_recent_paper", "koru_last"),
        ):
            a = path_stats.get(anchor_key)
            mv = path_stats.get(model_key)
            sim = _sim(mv, a)
            rows.append(
                {
                    "field": field,
                    "paper_anchor": a,
                    "model_value": None if mv is None else round(mv, 2),
                    "delta_pct": sim["delta_pct"],
                    "band": sim["band"],
                    "similarity_score": sim["similarity"],
                    "note": path_stats.get("note"),
                    "quality": "observed",
                    "source": "yfinance_path",
                }
            )
        for field, a_key, m_key in (
            ("kospi_drawdown_from_peak_pct", "kospi_dd_paper", "kospi_dd_1y"),
        ):
            a = path_stats.get(a_key)
            mv = path_stats.get(m_key)
            # drawdowns: compare magnitude
            sim = _sim(mv, a) if a and mv else {"similarity": None, "delta_pct": None, "band": "n/a"}
            rows.append(
                {
                    "field": field,
                    "paper_anchor": a,
                    "model_value": None if mv is None else round(mv, 2),
                    "delta_pct": sim["delta_pct"],
                    "band": sim["band"],
                    "similarity_score": sim["similarity"],
                    "note": "paper canary ~−35% / next-china ~−25%; model = peak→trough or peak→last",
                    "quality": "observed",
                    "source": "yfinance_KS11",
                }
            )

    # Summary scores
    scored = [r for r in rows if r.get("similarity_score") is not None and r.get("band") in (
        "close", "same_order", "diverged", "qualitative_match"
    )]
    close_n = sum(1 for r in rows if r.get("band") == "close")
    same_n = sum(1 for r in rows if r.get("band") in ("close", "same_order", "qualitative_match", "reset_confirmed"))

    return {
        "as_of": snap.get("as_of"),
        "fx_usdkrw": fx,
        "n_rows": len(rows),
        "n_close_band": close_n,
        "n_directionally_ok": same_n,
        "rows": rows,
        "verdict_ko": (
            f"정량 근접(≤15%): {close_n}개 · 방향/오더일치 포함: {same_n}/{len(rows)}. "
            "레버 AUM·2.1%는 페이퍼 시점·분모 정의 차이로 현재 엔진이 낮게 나오는 편."
        ),
    }


def fetch_path_stats() -> dict[str, Any]:
    import yfinance as yf

    def _ser(sym: str) -> pd.Series:
        d = yf.download(sym, period="1y", auto_adjust=True, progress=False)
        s = d["Close"].dropna()
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        return s

    soxl = _ser("SOXL")
    koru = _ser("KORU")
    ks11 = _ser("^KS11")
    peak_ks = float(ks11.max())
    last_ks = float(ks11.iloc[-1])
    trough_ks = float(ks11.min())
    return {
        "soxl_peak_paper": 300.0,
        "soxl_recent_paper": 120.0,
        "soxl_peak_1y": float(soxl.max()),
        "soxl_last": float(soxl.iloc[-1]),
        "soxl_min_1y": float(soxl.min()),
        "koru_peak_paper": 64.0,
        "koru_recent_paper": 17.0,
        "koru_peak_1y": float(koru.max()),
        "koru_last": float(koru.iloc[-1]),
        "kospi_dd_paper": -35.0,  # canary
        "kospi_dd_1y": (last_ks / peak_ks - 1.0) * 100.0,
        "kospi_max_dd_1y": (trough_ks / peak_ks - 1.0) * 100.0,
        "kospi_peak": peak_ks,
        "kospi_last": last_ks,
        "note": "1y Yahoo path vs paper approximate levels",
    }


def event_study_us_stress(
    *,
    period: str = "1y",
    soxl_thr: float = -0.10,
    drivers: list[str] | None = None,
) -> dict[str, Any]:
    """US semis stress days → next KR open for Hynix/Samsung."""
    drivers = list(drivers or ["SOXL", "SMH", "MU", "NVDA"])
    kr_map = {"000660.KS": "000660", "005930.KS": "005930"}
    tickers = drivers + list(kr_map.keys()) + ["^VIX"]
    daily = download_daily(tickers, period=period)

    us_rets = {}
    for u in drivers:
        us_rets[u] = _series_close(daily, u).dropna().pct_change().dropna()

    try:
        vix = _series_close(daily, "^VIX").dropna().pct_change()
    except Exception:  # noqa: BLE001
        vix = pd.Series(dtype=float)

    # Stress day = SOXL <= thr OR (MU<=-5% and SMH<=-3%)
    soxl = us_rets["SOXL"]
    stress_days = sorted(set(soxl[soxl <= soxl_thr].index.tolist()))
    # add composite
    if "MU" in us_rets and "SMH" in us_rets:
        for d in us_rets["MU"].index:
            if us_rets["MU"].get(d, 0) <= -0.05 and us_rets["SMH"].get(d, 0) <= -0.03:
                if d not in stress_days:
                    stress_days.append(d)
        stress_days = sorted(stress_days)

    events: list[dict[str, Any]] = []
    for kr_y, kr_id in kr_map.items():
        close = _series_close(daily, kr_y).dropna()
        if isinstance(daily.columns, pd.MultiIndex) and kr_y in daily.columns.get_level_values(0):
            open_ = daily[kr_y]["Open"].dropna()
        else:
            open_ = daily["Open"]
        open_.index = pd.to_datetime(open_.index).tz_localize(None).normalize()
        close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
        r_open = ((open_ / close.shift(1)) - 1.0).dropna()

        # also align each driver for alert proxy
        for us_day in stress_days:
            us_day = pd.Timestamp(us_day).tz_localize(None).normalize()
            # next KR day
            nxt = [d for d in r_open.index if d > us_day]
            if not nxt or (nxt[0] - us_day).days > 5:
                continue
            kd = nxt[0]
            r_kr = float(r_open.loc[kd])
            driver_rs = {u: float(us_rets[u].loc[us_day]) for u in drivers if us_day in us_rets[u].index}
            # Would our downside proxy fire? any linked driver <= -2%
            alert = any(r <= -0.02 for r in driver_rs.values())
            # stronger: SOXL <= -10% → high downside
            level = "quiet"
            if driver_rs.get("SOXL", 0) <= -0.15 or driver_rs.get("MU", 0) <= -0.05:
                level = "high"
            elif alert:
                level = "watch"
            vr = float(vix.loc[us_day]) if us_day in vix.index else None
            events.append(
                {
                    "us_day": us_day.strftime("%Y-%m-%d"),
                    "kr_day": kd.strftime("%Y-%m-%d"),
                    "kr": kr_id,
                    "r_kr_open": round(r_kr, 6),
                    "driver_returns": {k: round(v, 4) for k, v in driver_rs.items()},
                    "vix_day_return": None if vr is None else round(vr, 4),
                    "alert_would_fire": alert,
                    "proxy_stress_level": level,
                    "hit_down": r_kr < 0,
                }
            )

    # Aggregate by KR
    summary = {}
    for kr_id in ("000660", "005930"):
        ev = [e for e in events if e["kr"] == kr_id]
        if not ev:
            summary[kr_id] = {"n": 0}
            continue
        rs = np.array([e["r_kr_open"] for e in ev])
        fired = [e for e in ev if e["alert_would_fire"]]
        high = [e for e in ev if e["proxy_stress_level"] == "high"]
        summary[kr_id] = {
            "n_stress_events": len(ev),
            "frac_kr_open_neg": round(float((rs < 0).mean()), 4),
            "mean_kr_open": round(float(rs.mean()), 6),
            "median_kr_open": round(float(np.median(rs)), 6),
            "p10": round(float(np.quantile(rs, 0.1)), 6),
            "p90": round(float(np.quantile(rs, 0.9)), 6),
            "when_alert_fires": {
                "n": len(fired),
                "frac_neg": round(float(np.mean([e["r_kr_open"] < 0 for e in fired])), 4)
                if fired
                else None,
                "mean": round(float(np.mean([e["r_kr_open"] for e in fired])), 6)
                if fired
                else None,
            },
            "when_high": {
                "n": len(high),
                "frac_neg": round(float(np.mean([e["r_kr_open"] < 0 for e in high])), 4)
                if high
                else None,
                "mean": round(float(np.mean([e["r_kr_open"] for e in high])), 6)
                if high
                else None,
            },
        }

    # baseline: all days
    baseline = {}
    for kr_y, kr_id in kr_map.items():
        close = _series_close(daily, kr_y).dropna()
        if isinstance(daily.columns, pd.MultiIndex) and kr_y in daily.columns.get_level_values(0):
            open_ = daily[kr_y]["Open"].dropna()
        else:
            open_ = daily["Open"]
        open_.index = pd.to_datetime(open_.index).tz_localize(None).normalize()
        close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
        r_open = ((open_ / close.shift(1)) - 1.0).dropna()
        arr = r_open.to_numpy()
        baseline[kr_id] = {
            "n": int(len(arr)),
            "frac_neg": round(float((arr < 0).mean()), 4),
            "mean": round(float(arr.mean()), 6),
        }

    # top events for hynix
    hynix = sorted(
        [e for e in events if e["kr"] == "000660"],
        key=lambda e: e["driver_returns"].get("SOXL", 0),
    )[:12]

    return {
        "schema_version": "us-kr-event-study-v1",
        "as_of": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "soxl_thr": soxl_thr,
        "definition_ko": (
            f"스트레스일 = SOXL≤{soxl_thr:.0%} 또는 (MU≤−5% & SMH≤−3%). "
            "익일 KR overnight open. 알림 프록시 = 드라이버 중 하나 ≤−2%."
        ),
        "baseline_overnight": baseline,
        "summary": summary,
        "top_soxl_stress_hynix": hynix,
        "n_events_total": len(events),
        "disclaimer_ko": "옵션 체인 히스토리 없이 수익률 프록시. 투자 권유 아님.",
    }
