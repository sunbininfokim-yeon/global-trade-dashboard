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
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from market_microstructure.formulas import conc_named, concentration


def _listing_kospi() -> pd.DataFrame:
    import FinanceDataReader as fdr

    df = fdr.StockListing("KOSPI")
    df["Code"] = df["Code"].astype(str)
    return df


_CONC_FIELDS = (
    "conc_top2_samsung_hynix_pct",
    "conc_top5_pct",
    "conc_top10_pct",
    "universe_mcap_krw",
)
_KST = timezone(timedelta(hours=9))
# Confirmed closures in the legacy series. Equality of prices alone is not
# proof of a holiday: a real session may legitimately repeat a prior value.
_LEGACY_CLOSURES = {date(2026, 8, 17), date(2026, 9, 24), date(2026, 9, 25)}


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _is_fixed_krx_holiday(day: date) -> bool:
    """Fixed KRX holidays; lunar holidays are caught by the price-date guard."""
    return (day.month, day.day) in {
        (1, 1), (3, 1), (5, 5), (6, 6), (8, 15), (10, 3), (10, 9), (12, 25)
    }


def _latest_kospi_price_date(target: date) -> date | None:
    """Return the latest available KOSPI close, failing closed on lookup errors."""
    import FinanceDataReader as fdr

    try:
        panel = fdr.DataReader("KS11", (target - timedelta(days=14)).isoformat())
    except Exception:  # noqa: BLE001
        return None
    if panel.empty:
        return None
    return pd.Timestamp(panel.index.max()).tz_localize(None).date()


def observed_point_from_listing(
    listing: pd.DataFrame | None = None,
    *,
    as_of: date | datetime | str | None = None,
    latest_price_date: date | datetime | str | None = None,
) -> dict[str, Any] | None:
    """Build an observed point only for a confirmed KRX trading day.

    StockListing can repeat the preceding snapshot on weekends and holidays.  A
    listing alone is therefore not evidence for an observed session.
    """
    target = _as_date(as_of or datetime.now(_KST).date())
    if target.weekday() >= 5 or _is_fixed_krx_holiday(target):
        return None
    latest = (
        _as_date(latest_price_date)
        if latest_price_date is not None
        else _latest_kospi_price_date(target)
    )
    if latest != target:
        return None
    listing = listing if listing is not None else _listing_kospi()
    if listing.empty or not {"Code", "Marcap"}.issubset(listing.columns):
        return None
    caps = pd.to_numeric(listing["Marcap"], errors="coerce")
    if caps.isna().any() or not np.isfinite(caps).all():
        return None
    mcaps = dict(zip(listing["Code"].astype(str), caps))
    mcaps = {code: float(cap) for code, cap in mcaps.items() if cap > 0}
    univ = float(sum(mcaps.values()))
    if len(mcaps) < 100 or univ <= 0 or not all(code in mcaps for code in ("005930", "000660")):
        return None
    return {
        "date": target.isoformat(),
        "conc_top2_samsung_hynix_pct": round(
            conc_named(mcaps, ["005930", "000660"], univ), 4
        ),
        "conc_top5_pct": round(concentration(mcaps, univ, 5), 4),
        "conc_top10_pct": round(concentration(mcaps, univ, 10), 4),
        "universe_mcap_krw": univ,
        "n_names": len(mcaps),
        "quality": "observed",
        "source": "FinanceDataReader StockListing(KOSPI) Marcap",
    }


def _valid_point(point: dict[str, Any]) -> bool:
    """Reject hollow and known non-trading-day points from persisted history."""
    try:
        day = _as_date(point["date"])
        values = [float(point[field]) for field in _CONC_FIELDS]
        return (
            day.weekday() < 5
            and not _is_fixed_krx_holiday(day)
            and day not in _LEGACY_CLOSURES
            and int(point.get("n_names") or 0) > 0
            and all(np.isfinite(value) and value > 0 for value in values)
        )
    except (KeyError, TypeError, ValueError):
        return False


def clean_history(history: dict[str, Any]) -> dict[str, Any]:
    """Drop hollow/confirmed non-session rows and recompute summary fields."""
    points: list[dict[str, Any]] = []
    for point in sorted(history.get("points") or [], key=lambda value: value.get("date", "")):
        if not _valid_point(point):
            continue
        points.append(point)

    out = dict(history)
    out["points"] = points
    out["n_points"] = len(points)
    out["latest"] = points[-1] if points else None
    out["as_of"] = points[-1]["date"] if points else None
    series_top2 = [point["conc_top2_samsung_hynix_pct"] for point in points]
    out["stats"] = {
        "conc_top2_min": None if not series_top2 else round(float(np.min(series_top2)), 4),
        "conc_top2_max": None if not series_top2 else round(float(np.max(series_top2)), 4),
        "conc_top2_last": None if not series_top2 else series_top2[-1],
        "conc_top2_chg_60d": None
        if len(series_top2) < 60
        else round(series_top2[-1] - series_top2[-60], 4),
    }
    return out


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
        if obs is not None:
            points = [p for p in points if p["date"] != obs["date"]]
            points.append(obs)
            points.sort(key=lambda p: p["date"])

    series_top2 = [p["conc_top2_samsung_hynix_pct"] for p in points]
    return clean_history({
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
    })


def append_observed(history: dict[str, Any], point: dict[str, Any] | None = None) -> dict[str, Any]:
    point = point or observed_point_from_listing()
    pts = list(history.get("points") or [])
    if point is not None and _valid_point(point):
        pts = [p for p in pts if p.get("date") != point["date"]]
        pts.append(point)
    out = clean_history({**history, "points": pts})
    out["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return out
