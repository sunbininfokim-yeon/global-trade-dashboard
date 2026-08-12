"""Align prices into base-currency log returns."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .prices import load_price_series, synthetic_flat


def _to_base_price(
    local: pd.Series,
    *,
    local_ccy: str,
    base_ccy: str,
    fx_usdkrw: pd.Series | None,
    fx_usdjpy: pd.Series | None = None,
    fx_eurusd: pd.Series | None = None,
) -> pd.Series:
    """Convert local-currency price series into base currency units."""
    if local_ccy == base_ccy:
        return local
    if local_ccy == "USD" and base_ccy == "KRW":
        if fx_usdkrw is None:
            raise ValueError("FX USDKRW required")
        aligned = pd.concat([local, fx_usdkrw], axis=1, join="inner").dropna()
        if aligned.empty:
            raise ValueError("no overlap for FX conversion")
        return aligned.iloc[:, 0] * aligned.iloc[:, 1]
    if local_ccy == "KRW" and base_ccy == "USD":
        if fx_usdkrw is None:
            raise ValueError("FX USDKRW required")
        aligned = pd.concat([local, fx_usdkrw], axis=1, join="inner").dropna()
        if aligned.empty:
            raise ValueError("no overlap for FX conversion")
        return aligned.iloc[:, 0] / aligned.iloc[:, 1]
    if local_ccy == "JPY" and base_ccy == "KRW":
        if fx_usdkrw is None or fx_usdjpy is None:
            raise ValueError("FX USDKRW and USDJPY required for JPY")
        # KRW per JPY ≈ USDKRW / USDJPY
        aligned = pd.concat([local, fx_usdkrw, fx_usdjpy], axis=1, join="inner").dropna()
        if aligned.empty:
            raise ValueError("no overlap for JPY conversion")
        px, usdkrw, usdjpy = aligned.iloc[:, 0], aligned.iloc[:, 1], aligned.iloc[:, 2]
        return px * (usdkrw / usdjpy)
    if local_ccy == "EUR" and base_ccy == "KRW":
        if fx_usdkrw is None or fx_eurusd is None:
            raise ValueError("FX USDKRW and EURUSD required for EUR")
        # KRW per EUR ≈ EURUSD * USDKRW
        aligned = pd.concat([local, fx_eurusd, fx_usdkrw], axis=1, join="inner").dropna()
        if aligned.empty:
            raise ValueError("no overlap for EUR conversion")
        px, eurusd, usdkrw = aligned.iloc[:, 0], aligned.iloc[:, 1], aligned.iloc[:, 2]
        return px * eurusd * usdkrw
    raise ValueError(f"unsupported conversion {local_ccy}->{base_ccy}")


def aligned_returns(
    positions: list[dict[str, Any]],
    cache_dir,
    *,
    base_currency: str = "KRW",
    years: float = 5.0,
    cache_only: bool = False,
) -> tuple[pd.DataFrame, pd.Series, dict[str, Any]]:
    """
    Returns
    -------
    rets : DataFrame (date x asset_id) log returns in base currency
    weights : Series indexed by asset_id
    meta : quality notes
    """
    meta: dict[str, Any] = {"proxies": [], "errors": [], "price_sources": {}}
    need_fx = any(
        (p["instrument"]["currency"] != base_currency)
        or p["instrument"].get("fx_as_asset")
        or p["instrument"]["id"] == "cash:usd"
        for p in positions
    )
    need_jpy = any(p["instrument"]["currency"] == "JPY" for p in positions)
    need_eur = any(p["instrument"]["currency"] == "EUR" for p in positions)
    fx = None
    fx_jpy = None
    fx_eur = None
    if need_fx or base_currency == "KRW":
        try:
            fx = load_price_series(
                "USDKRW=X",
                cache_dir,
                years=years,
                cache_only=cache_only,
            )
            meta["price_sources"]["fx:USDKRW=X"] = str(fx.attrs.get("source") or "unknown")
        except Exception as e:  # noqa: BLE001
            meta["errors"].append(f"USDKRW=X: {e}")
            if need_fx:
                raise
    if need_jpy:
        fx_jpy = load_price_series(
            "USDJPY=X",
            cache_dir,
            years=years,
            cache_only=cache_only,
        )
        meta["price_sources"]["fx:USDJPY=X"] = str(fx_jpy.attrs.get("source") or "unknown")
    if need_eur:
        fx_eur = load_price_series(
            "EURUSD=X",
            cache_dir,
            years=years,
            cache_only=cache_only,
        )
        meta["price_sources"]["fx:EURUSD=X"] = str(fx_eur.attrs.get("source") or "unknown")

    calendar_src = fx
    price_cols: dict[str, pd.Series] = {}
    weights = {}

    for p in positions:
        inst = p["instrument"]
        iid = inst["id"]
        weights[iid] = float(p["weight"])
        try:
            if inst.get("synthetic") == "flat":
                if calendar_src is None:
                    calendar_src = load_price_series(
                        "005930.KS",
                        cache_dir,
                        years=years,
                        cache_only=cache_only,
                    )
                s = synthetic_flat(calendar_src.index, name=iid)
                meta["price_sources"][iid] = "synthetic"
            elif inst.get("fx_as_asset") and inst["currency"] == "USD" and base_currency == "KRW":
                if fx is None:
                    raise RuntimeError("FX missing for USD cash")
                s = fx.rename(iid)
                meta["price_sources"][iid] = str(fx.attrs.get("source") or "unknown")
            else:
                ysym = inst.get("yahoo")
                if not ysym:
                    raise RuntimeError(f"no yahoo symbol for {iid}")
                local = load_price_series(
                    ysym,
                    cache_dir,
                    years=years,
                    cache_only=cache_only,
                )
                meta["price_sources"][iid] = str(local.attrs.get("source") or "unknown")
                if inst.get("proxy"):
                    meta["proxies"].append(iid)
                s = _to_base_price(
                    local,
                    local_ccy=inst["currency"],
                    base_ccy=base_currency,
                    fx_usdkrw=fx,
                    fx_usdjpy=fx_jpy,
                    fx_eurusd=fx_eur,
                ).rename(iid)
            price_cols[iid] = s
            if calendar_src is None:
                calendar_src = s
        except Exception as e:  # noqa: BLE001
            meta["errors"].append(f"{iid}: {e}")

    if not price_cols:
        raise RuntimeError(f"no price series loaded: {meta['errors']}")

    # Union index + ffill bridges exchange holidays; Yahoo FX also has weekend prints.
    # Keep Mon–Fri only so weekend FX moves are not paired with zero equity returns.
    prices = pd.DataFrame(price_cols).sort_index().ffill().dropna(how="any")
    prices = prices[prices.index.dayofweek < 5]
    rets = np.log(prices / prices.shift(1)).dropna(how="any")
    # Drop residual weekend rows if any slipped through before the filter.
    rets = rets[rets.index.dayofweek < 5]
    for p in positions:
        inst = p["instrument"]
        iid = inst["id"]
        if iid not in rets.columns:
            continue
        if inst.get("synthetic_leverage"):
            # Daily leverage is defined on *simple* returns (like a 2x ETF),
            # not on log returns. 2 * log(1+r) ≠ log(1+2r).
            lf = float(inst.get("leverage_factor") or 2.0)
            simple = np.expm1(rets[iid])
            levered_simple = (lf * simple).clip(lower=-0.999999)
            rets[iid] = np.log1p(levered_simple)
            meta.setdefault("synthetic_leverage", {})[iid] = lf
    w = pd.Series(weights, dtype="float64")
    w = w.reindex(rets.columns).fillna(0.0)
    if w.abs().sum() <= 0:
        raise RuntimeError("weights sum to 0")
    return rets, w, meta
