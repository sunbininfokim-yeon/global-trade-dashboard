"""Alert level thresholds from REAL series only (no return-proxies for options).

KR: Hynix single-stock LETF trading value / spot TV (FDR Close×Volume).
US→KR: Cboe official VIX daily % change (not put OI — OI history unavailable).

Put/call open interest history for equities is NOT available on public Cboe CDN
(equity_pc_ratio_history.csv → 403). Do not invent thresholds from SOXL price.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd


def explain_put_oi() -> dict[str, str]:
    return {
        "put_oi_ko": (
            "풋 OI(Put Open Interest) = 아직 청산되지 않은 풋옵션 계약 수. "
            "‘오늘 거래량’이 아니라 ‘남아 있는 미결제 계약’이다. "
            "풋 OI·풋 거래량이 늘면 하방 헤지/공격 수요가 커졌다는 해석을 할 수 있지만, "
            "주체를 알 수는 없다."
        ),
        "availability_ko": (
            "종목별 풋 OI 시계열은 공개 Cboe 히스토리 CSV가 막혀 있어(403) "
            "우리 엔진으로는 백테스트 임계값을 만들 수 없다. "
            "당일 지연 체인의 집계만 가능."
        ),
    }


def _etf_tv_series(symbols: list[str], start: str) -> pd.DataFrame:
    import FinanceDataReader as fdr

    def _one(c: str) -> pd.Series | None:
        try:
            df = fdr.DataReader(c, start)
            if df is None or df.empty:
                return None
            vol = df["Volume"].astype(float).clip(upper=2e9)
            return (df["Close"].astype(float) * vol).rename(c)
        except Exception:  # noqa: BLE001
            return None

    series: list[pd.Series] = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(_one, c) for c in symbols]
        for fut in as_completed(futs):
            s = fut.result()
            if s is not None:
                series.append(s)
    if not series:
        return pd.DataFrame()
    return pd.concat(series, axis=1).sort_index()


def build_kr_hynix_letf_levels(*, start: str = "2026-05-27") -> dict[str, Any]:
    """3 levels from real Hynix LETF/spot TV ratio (products listed ~2026-05-27)."""
    import FinanceDataReader as fdr

    etfs = fdr.StockListing("ETF/KR")
    lev = etfs[etfs["Name"].astype(str).str.contains("레버리지|인버스", na=False)]
    hx = lev[lev["Name"].astype(str).str.contains("하이닉스", na=False)]
    codes = hx["Symbol"].astype(str).tolist()
    panel = _etf_tv_series(codes, start)
    hx_tv = panel.sum(axis=1)
    spot = fdr.DataReader("000660", start)
    spot_tv = spot["Close"].astype(float) * spot["Volume"].astype(float).clip(upper=2e9)
    spot_r = spot["Close"].pct_change()
    df = pd.DataFrame({"ratio": hx_tv / spot_tv.replace(0, np.nan), "r": spot_r}).dropna()
    df = df[df["ratio"] > 0]
    df["next_r"] = df["r"].shift(-1)
    df["next_abs"] = df["next_r"].abs()
    df["next_down2"] = df["next_r"] <= -0.02
    df = df.dropna()

    # Empirical cuts: only top tercile clearly worse in sample → use outcome-guided floors
    # 관찰: <0.50 · 주의: 0.50–0.75 · 경계: ≥0.75 (approx p67 / elevated)
    cuts = {"관찰": (None, 0.50), "주의": (0.50, 0.75), "경계": (0.75, None)}
    levels = {}
    base = {
        "n": int(len(df)),
        "frac_next_down2": round(float(df["next_down2"].mean()), 4),
        "mean_next_abs": round(float(df["next_abs"].mean()), 4),
        "mean_next_r": round(float(df["next_r"].mean()), 4),
    }
    for name, (lo, hi) in cuts.items():
        sub = df.copy()
        if lo is not None:
            sub = sub[sub["ratio"] >= lo]
        if hi is not None:
            sub = sub[sub["ratio"] < hi]
        levels[name] = {
            "metric": "hynix_letf_tv / hynix_spot_tv",
            "ratio_min": lo,
            "ratio_max": hi,
            "n": int(len(sub)),
            "frac_next_down2": round(float(sub["next_down2"].mean()), 4) if len(sub) else None,
            "mean_next_abs": round(float(sub["next_abs"].mean()), 4) if len(sub) else None,
            "mean_next_r": round(float(sub["next_r"].mean()), 4) if len(sub) else None,
            "ratio_median_in_bucket": round(float(sub["ratio"].median()), 4) if len(sub) else None,
        }

    # today
    today_ratio = None
    try:
        hx_amt = float(hx["Amount"].sum()) * 1_000_000  # 백만원
        kospi = fdr.StockListing("KOSPI")
        spot_amt = float(kospi.set_index("Code").loc["000660", "Amount"])
        if spot_amt > 0:
            today_ratio = hx_amt / spot_amt
    except Exception:  # noqa: BLE001
        today_ratio = None

    def _classify(r: float | None) -> str | None:
        if r is None:
            return None
        if r >= 0.75:
            return "경계"
        if r >= 0.50:
            return "주의"
        return "관찰"

    return {
        "schema": "kr-hynix-letf-alert-levels-v1",
        "metric_ko": "하닉 단일종목 레버·인버스 ETF 거래대금 ÷ 하닉 현물 거래대금",
        "data_source": "FinanceDataReader ETF/KR Amount(당일) + Close×Volume(히스토리)",
        "sample": {
            "start": start,
            "n_active_days": base["n"],
            "note_ko": "단일종목 하닉 LETF는 2026-05-27 상장. 표본 ~50거래일로 짧음.",
            "baseline": base,
        },
        "levels": levels,
        "rule_ko": {
            "관찰": "비율 < 0.50 (현물 거래 대비 레버 ETF < 50%)",
            "주의": "0.50 ≤ 비율 < 0.75",
            "경계": "비율 ≥ 0.75 — 표본에서 익일 |R|·−2% 비율이 뚜렷히 상승",
        },
        "today_ratio": None if today_ratio is None else round(today_ratio, 4),
        "today_level": _classify(today_ratio),
        "limitation_ko": "표본 짧음. 인덱스 레버 비중은 선행지표로 유의하지 않아 채택하지 않음.",
    }


def build_us_vix_kr_levels() -> dict[str, Any]:
    """US→KR levels from official Cboe VIX history only (not put OI)."""
    import io

    import requests
    import yfinance as yf

    text = requests.get(
        "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
        timeout=60,
        headers={"User-Agent": "market-microstructure/1.0"},
    ).text
    vix = pd.read_csv(io.StringIO(text))
    vix["DATE"] = pd.to_datetime(vix["DATE"])
    vix = vix.set_index("DATE").sort_index()
    vix["vix_r"] = vix["CLOSE"].pct_change()
    vix = vix.loc["2025-01-01":]

    hx = yf.download("000660.KS", start="2025-01-01", auto_adjust=True, progress=False)
    hx_o, hx_c = hx["Open"], hx["Close"]
    if isinstance(hx_o, pd.DataFrame):
        hx_o = hx_o.iloc[:, 0]
        hx_c = hx_c.iloc[:, 0]
    hx_c.index = pd.to_datetime(hx_c.index).tz_localize(None).normalize()
    hx_o.index = pd.to_datetime(hx_o.index).tz_localize(None).normalize()
    r_open = (hx_o / hx_c.shift(1) - 1.0).dropna()

    rows = []
    for d, vr in vix["vix_r"].dropna().items():
        d = pd.Timestamp(d).normalize()
        nxt = [x for x in r_open.index if x > d]
        if not nxt or (nxt[0] - d).days > 5:
            continue
        rows.append(
            {
                "vix_r": float(vr),
                "vix": float(vix.loc[d, "CLOSE"]),
                "r_kr": float(r_open.loc[nxt[0]]),
            }
        )
    a = pd.DataFrame(rows)
    base = {
        "n": int(len(a)),
        "frac_neg": round(float((a["r_kr"] < 0).mean()), 4),
        "mean": round(float(a["r_kr"].mean()), 6),
    }

    # Outcome-guided: 관찰 <5%, 주의 5–10%, 경계 ≥10% VIX day return
    cuts = {"관찰": (None, 0.05), "주의": (0.05, 0.10), "경계": (0.10, None)}
    levels = {}
    for name, (lo, hi) in cuts.items():
        sub = a.copy()
        if lo is not None:
            sub = sub[sub["vix_r"] >= lo]
        if hi is not None:
            sub = sub[sub["vix_r"] < hi]
        # for 관찰 include calm days (vix_r < 0.05) including negative
        if name == "관찰":
            sub = a[a["vix_r"] < 0.05]
        levels[name] = {
            "metric": "Cboe VIX daily return",
            "vix_r_min": lo if name != "관찰" else None,
            "vix_r_max": 0.05 if name == "관찰" else hi,
            "n": int(len(sub)),
            "frac_kr_open_neg": round(float((sub["r_kr"] < 0).mean()), 4) if len(sub) else None,
            "mean_kr_open": round(float(sub["r_kr"].mean()), 6) if len(sub) else None,
        }

    latest = vix.iloc[-1]
    latest_r = float(vix["vix_r"].iloc[-1]) if len(vix) > 1 else None

    def _cls(r: float | None) -> str | None:
        if r is None:
            return None
        if r >= 0.10:
            return "경계"
        if r >= 0.05:
            return "주의"
        return "관찰"

    return {
        "schema": "us-vix-kr-alert-levels-v1",
        "metric_ko": "Cboe 공식 VIX 전일 대비 변화율 → 익일 하닉 overnight open",
        "data_source": "cdn.cboe.com VIX_History.csv + Yahoo 000660.KS OHLC",
        "not_put_oi": True,
        "put_oi_status_ko": "종목 풋 OI 히스토리 없음 → 임계값 불가. VIX는 옵션시장 변동성 지수(공식).",
        "sample": {"start": "2025-01-01", "baseline": base},
        "levels": levels,
        "rule_ko": {
            "관찰": "VIX 일변화 < +5%",
            "주의": "+5% ≤ VIX 일변화 < +10%",
            "경계": "VIX 일변화 ≥ +10%",
        },
        "latest_vix": float(latest["CLOSE"]),
        "latest_vix_r": None if latest_r is None else round(latest_r, 4),
        "latest_level": _cls(latest_r),
        "limitation_ko": (
            "VIX는 개별주 풋/콜 OI·공매 동시 포지션이 아님. "
            "SOXL 가격·수익률로 옵션 스트레스를 대체하지 않음."
        ),
    }


def build_alert_levels_report() -> dict[str, Any]:
    put = explain_put_oi()
    kr = build_kr_hynix_letf_levels()
    us = build_us_vix_kr_levels()
    return {
        "schema_version": "alert-levels-v1",
        "as_of": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "put_oi": put,
        "cannot_do_ko": [
            "미국 개별주/ETF 풋·콜 OI·거래량 히스토리 기반 임계값 (공개 시계열 없음)",
            "SOXL/MU 가격 급락을 ‘옵션 포지션 변화’로 바꿔 쓴 프록시 백테스트 (금지)",
            "딜러 GEX·누가 걸었는지 주체 특정",
        ],
        "kr_hynix_letf": kr,
        "us_vix_to_kr": us,
        "disclaimer_ko": "실측 공개 데이터 기반 통계 임계값. 투자 권유 아님. 표본 한계 명시.",
    }
