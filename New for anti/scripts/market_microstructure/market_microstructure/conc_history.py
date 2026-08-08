"""KOSPI concentration history (Conc_top2 / top5 / top10).

Builds a daily series for charts. Method:
  mcap_{i,t} = Close_{i,t} × Stocks_i
  Close from FinanceDataReader (KRX), Stocks from latest FDR listing
  Conc_top2 = (005930 + 000660) / Σ mcap
  Conc_top5/10 = daily top-N / Σ mcap

Today's point uses listing Marcap directly (quality=observed).
Backfill quality=estimated (shares pinned to latest listing).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from market_microstructure.formulas import conc_named, concentration


def _listing_kospi() -> pd.DataFrame:
    import FinanceDataReader as fdr

    df = fdr.StockListing("KOSPI")
    df["Code"] = df["Code"].astype(str)
    return df


def observed_point_from_listing(listing: pd.DataFrame | None = None) -> dict[str, Any]:
    listing = listing if listing is not None else _listing_kospi()
    mcaps = {str(r.Code): float(r.Marcap) for r in listing.itertuples() if float(r.Marcap) > 0}
    univ = float(sum(mcaps.values()))
    return {
        "date": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "conc_top2_samsung_hynix_pct": round(
            conc_named(mcaps, ["005930", "000660"], univ) or 0.0, 4
        ),
        "conc_top5_pct": round(concentration(mcaps, univ, 5) or 0.0, 4),
        "conc_top10_pct": round(concentration(mcaps, univ, 10) or 0.0, 4),
        "universe_mcap_krw": univ,
        "n_names": len(mcaps),
        "quality": "observed",
        "source": "FinanceDataReader StockListing(KOSPI) Marcap",
    }


def _fdr_close_panel(codes: list[str], start: str, *, workers: int = 24) -> pd.DataFrame:
    import FinanceDataReader as fdr

    def _one(code: str) -> tuple[str, pd.Series | None]:
        try:
            s = fdr.DataReader(code, start)["Close"]
            s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
            return code, s
        except Exception:  # noqa: BLE001
            return code, None

    series: list[pd.Series] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_one, c) for c in codes]
        for fut in as_completed(futs):
            code, s = fut.result()
            if s is not None and len(s):
                series.append(s.rename(code))
    if not series:
        return pd.DataFrame()
    return pd.concat(series, axis=1).sort_index()


def build_concentration_history(
    *,
    months: int = 6,
    include_observed_today: bool = True,
    workers: int = 24,
) -> dict[str, Any]:
    listing = _listing_kospi()
    codes = listing["Code"].astype(str).tolist()
    shares = listing.set_index("Code")["Stocks"].astype(float)
    start = (datetime.now() - timedelta(days=int(months * 31))).strftime("%Y-%m-%d")

    px = _fdr_close_panel(codes, start, workers=workers)
    points: list[dict[str, Any]] = []
    for day, row in px.iterrows():
        mcaps: dict[str, float] = {}
        for c, price in row.dropna().items():
            sh = shares.get(str(c))
            if sh is None or sh <= 0 or float(price) <= 0:
                continue
            mcaps[str(c)] = float(price) * float(sh)
        if len(mcaps) < 100:
            continue
        univ = float(sum(mcaps.values()))
        top = sorted(mcaps.values(), reverse=True)
        points.append(
            {
                "date": pd.Timestamp(day).strftime("%Y-%m-%d"),
                "conc_top2_samsung_hynix_pct": round(
                    (mcaps.get("005930", 0.0) + mcaps.get("000660", 0.0)) / univ * 100.0, 4
                ),
                "conc_top5_pct": round(sum(top[:5]) / univ * 100.0, 4),
                "conc_top10_pct": round(sum(top[:10]) / univ * 100.0, 4),
                "universe_mcap_krw": univ,
                "n_names": len(mcaps),
                "quality": "estimated",
                "source": "FDR Close×FDR Stocks (shares pinned)",
            }
        )

    if include_observed_today:
        obs = observed_point_from_listing(listing)
        points = [p for p in points if p["date"] != obs["date"]]
        points.append(obs)
        points.sort(key=lambda p: p["date"])

    series_top2 = [p["conc_top2_samsung_hynix_pct"] for p in points]
    return {
        "schema_version": "kospi-concentration-history-v1",
        "as_of": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "months": months,
        "n_points": len(points),
        "latest": points[-1] if points else None,
        "stats": {
            "conc_top2_min": None if not series_top2 else round(float(np.min(series_top2)), 4),
            "conc_top2_max": None if not series_top2 else round(float(np.max(series_top2)), 4),
            "conc_top2_last": None if not series_top2 else series_top2[-1],
            "conc_top2_chg_60d": None
            if len(series_top2) < 60
            else round(series_top2[-1] - series_top2[-60], 4),
        },
        "points": points,
        "note_ko": (
            "백필: 최신 상장주식수 고정 × FDR 종가. "
            "당일은 listing Marcap(observed). 차트용."
        ),
        "disclaimer_ko": "추정 시계열 포함. 투자 권유 아님.",
    }


def append_observed(history: dict[str, Any], point: dict[str, Any] | None = None) -> dict[str, Any]:
    point = point or observed_point_from_listing()
    pts = [p for p in (history.get("points") or []) if p.get("date") != point["date"]]
    pts.append(point)
    pts.sort(key=lambda p: p["date"])
    out = dict(history)
    out["points"] = pts
    out["n_points"] = len(pts)
    out["latest"] = pts[-1]
    out["as_of"] = point["date"]
    out["fetched_at"] = datetime.now(timezone.utc).isoformat()
    s = [p["conc_top2_samsung_hynix_pct"] for p in pts]
    out["stats"] = {
        "conc_top2_min": round(float(np.min(s)), 4),
        "conc_top2_max": round(float(np.max(s)), 4),
        "conc_top2_last": s[-1],
        "conc_top2_chg_60d": None if len(s) < 60 else round(s[-1] - s[-60], 4),
    }
    return out
