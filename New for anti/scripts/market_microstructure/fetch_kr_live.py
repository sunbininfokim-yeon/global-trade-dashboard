"""Fetch Korea spot + single-stock LETF + investor flow day input.

Sources:
  - ``KRX_API`` (Cloudflare Variables and secrets / local env) → KRX OpenAPI
  - FinanceDataReader fallback when KRX_API unset or ``--source fdr``
  - Naver mobile integration for foreign/retail share nets (still needed)

Never hardcode API keys.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"

# FDR ETF listing units (empirically: MarCap=억원, Amount=백만원)
ETF_MARCAP_TO_KRW = 100_000_000  # 억원
ETF_AMOUNT_TO_KRW = 1_000_000  # 백만원


def _parse_signed_int(s: str | int | float | None) -> int | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    t = str(s).strip().replace(",", "").replace("+", "")
    if t in {"", "-", "N/A"}:
        return None
    return int(t)


def _parse_pct(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(s))
    return float(m.group(1)) if m else None


def _infer_L(name: str) -> float:
    n = name.upper()
    if "인버스2X" in name or "인버스 2X" in name or "INVERSE 2X" in n:
        return -2.0
    if "인버스" in name:
        return -1.0
    if "레버리지" in name or "LEVERAGE" in n:
        return 2.0
    return 2.0


def _infer_underlying(name: str) -> str | None:
    if "하이닉스" in name:
        return "000660"
    if "삼성전자" in name:
        return "005930"
    return None


def _infer_structure(name: str) -> str:
    return "futures" if "선물" in name else "cash"


def _infer_direction(L: float) -> str:
    return "inverse" if L < 0 else "long"


def load_universe() -> dict[str, Any]:
    return json.loads((CONFIG / "letf_universe.json").read_text(encoding="utf-8"))


def load_ff_ratios() -> dict[str, float]:
    path = CONFIG / "free_float_ratios.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"005930": 0.70, "000660": 0.72, "_default": 0.70}


def has_krx_api() -> bool:
    return bool(
        os.environ.get("KRX_API", "").strip()
        or os.environ.get("KRX_OPENAPI_KEY", "").strip()
    )


def fetch_etf_listing() -> Any:
    import FinanceDataReader as fdr

    return fdr.StockListing("ETF/KR")


def fetch_kospi_listing() -> Any:
    import FinanceDataReader as fdr

    return fdr.StockListing("KOSPI")


def fetch_naver_integration(ticker: str) -> dict[str, Any]:
    import requests

    url = f"https://m.stock.naver.com/api/stock/{ticker}/integration"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    return r.json()


def build_letf_products(etfs, *, underlyings: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Group single-stock leverage/inverse ETFs by underlying (FDR listing)."""
    out: dict[str, list[dict[str, Any]]] = {u: [] for u in underlyings}
    names = etfs["Name"].astype(str)
    mask = names.str.contains("하이닉스|삼성전자", na=False) & names.str.contains(
        "레버리지|인버스", na=False
    )
    for _, row in etfs.loc[mask].iterrows():
        name = str(row["Name"])
        und = _infer_underlying(name)
        if und not in underlyings:
            continue
        L = _infer_L(name)
        aum = float(row["MarCap"]) * ETF_MARCAP_TO_KRW
        tv = float(row["Amount"]) * ETF_AMOUNT_TO_KRW
        out[und].append(
            {
                "ticker": str(row["Symbol"]),
                "name": name,
                "L": L,
                "aum": aum,
                "trading_value": tv,
                "beta": 1.0,
                "structure": _infer_structure(name),
                "direction": _infer_direction(L),
                "nav": float(row["NAV"]) if row.get("NAV") == row.get("NAV") else None,
                "price": float(row["Price"]) if row.get("Price") == row.get("Price") else None,
            }
        )
    return out


def _attach_naver_flows(code: str, close: float) -> dict[str, Any]:
    integ = fetch_naver_integration(code)
    infos = {i["code"]: i.get("value") for i in integ.get("totalInfos") or []}
    trends = integ.get("dealTrendInfos") or []
    latest = trends[0] if trends else {}

    def net_krw(key: str) -> int | None:
        q = _parse_signed_int(latest.get(key))
        return None if q is None else int(q * close)

    return {
        "foreign_hold_ratio_pct": _parse_pct(
            infos.get("foreignRate") or latest.get("foreignerHoldRatio")
        ),
        "flows_shares": {
            "as_of": latest.get("bizdate"),
            "foreign_net": _parse_signed_int(latest.get("foreignerPureBuyQuant")),
            "institution_net": _parse_signed_int(latest.get("organPureBuyQuant")),
            "retail_net": _parse_signed_int(latest.get("individualPureBuyQuant")),
        },
        "flows_krw": {
            "foreign_net_krw": net_krw("foreignerPureBuyQuant"),
            "institution_net_krw": net_krw("organPureBuyQuant"),
            "retail_net_krw": net_krw("individualPureBuyQuant"),
        },
        "deal_trend_history": trends[:10],
        "bizdate": latest.get("bizdate"),
    }


def build_day_from_live(
    *,
    underlyings: list[str] | None = None,
    fx_usdkrw: float = 1400.0,
) -> dict[str, Any]:
    """FDR + Naver path (no KRX_API required)."""
    underlyings = underlyings or ["000660", "005930"]
    ff_ratios = load_ff_ratios()
    etfs = fetch_etf_listing()
    kospi = fetch_kospi_listing()
    products_by = build_letf_products(etfs, underlyings=set(underlyings))

    kospi_sorted = kospi.sort_values("Marcap", ascending=False)
    total_mcap = float(kospi_sorted["Marcap"].sum())
    top = kospi_sorted.head(30)
    constituent = {str(r["Code"]): float(r["Marcap"]) for _, r in top.iterrows()}

    lev_mask = etfs["Name"].astype(str).str.contains("레버리지|인버스", na=False)
    market_lev_aum = float(etfs.loc[lev_mask, "MarCap"].sum()) * ETF_MARCAP_TO_KRW

    stocks: list[dict[str, Any]] = []
    as_of = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")

    for code in underlyings:
        row = kospi[kospi["Code"] == code]
        if row.empty:
            raise RuntimeError(f"missing KOSPI listing row for {code}")
        r0 = row.iloc[0]
        mcap = float(r0["Marcap"])
        adv = float(r0["Amount"])
        ff_r = float(ff_ratios.get(code, ff_ratios.get("_default", 0.7)))
        close = float(r0["Close"])
        chg = float(r0["ChagesRatio"]) / 100.0
        nv = _attach_naver_flows(code, close)
        products = products_by.get(code, [])
        letf_tv = sum(float(p["trading_value"]) for p in products)
        stocks.append(
            {
                "ticker": code,
                "name": str(r0["Name"]),
                "market_cap_krw": mcap,
                "free_float_mcap_krw": mcap * ff_r,
                "free_float_ratio_assumed": ff_r,
                "adv_spot_krw": adv,
                "close": close,
                "day_return": chg,
                "letf_trading_value_krw": letf_tv,
                "foreign_hold_ratio_pct": nv["foreign_hold_ratio_pct"],
                "flows_shares": nv["flows_shares"],
                "flows_krw": nv["flows_krw"],
                "deal_trend_history": nv["deal_trend_history"],
                "short_interest_shares": None,
                "short_ratio_pct": None,
                "letf_products": products,
                "source": "FinanceDataReader ETF/KR + KOSPI + Naver integration",
                "quality": "observed",
            }
        )
        bd = nv.get("bizdate")
        if bd and len(str(bd)) == 8:
            b = str(bd)
            as_of = f"{b[:4]}-{b[4:6]}-{b[6:8]}"

    f_net = sum((s["flows_krw"]["foreign_net_krw"] or 0) for s in stocks)
    r_net = sum((s["flows_krw"]["retail_net_krw"] or 0) for s in stocks)
    i_net = sum((s["flows_krw"]["institution_net_krw"] or 0) for s in stocks)

    return {
        "as_of": as_of,
        "fx_usdkrw": fx_usdkrw,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_mode": "fdr",
        "note": "FDR+Naver day input. Free-float assumed. Short interest null.",
        "kospi": {
            "total_mcap_krw": total_mcap,
            "free_float_mcap_krw": total_mcap * float(ff_ratios.get("_kospi_default", 0.75)),
            "constituent_mcaps_krw": constituent,
            "source": "FinanceDataReader StockListing(KOSPI)",
            "quality": "observed",
        },
        "market_levered_etf": {
            "aum_krw": market_lev_aum,
            "source": "FinanceDataReader ETF/KR names matching 레버리지|인버스",
            "quality": "observed",
        },
        "flows": {
            "scope": "covered_underlyings_spot",
            "foreign_net_krw": f_net,
            "retail_net_krw": r_net,
            "institution_net_krw": i_net,
            "source": "Naver dealTrendInfos (share nets × close)",
            "quality": "estimated",
        },
        "stocks": stocks,
    }


def build_day_from_krx(
    *,
    underlyings: list[str] | None = None,
    fx_usdkrw: float = 1400.0,
    bas_dd: str | None = None,
    include_naver_flows: bool = True,
) -> dict[str, Any]:
    """KRX OpenAPI day input, with optional current-only Naver investor flows.

    Historical LETF backfills must not ask Naver for a past investor snapshot:
    the KRX stock/ETF EOD fields are sufficient for AUM, turnover and the
    modelled rebalance proxy.  ``include_naver_flows=False`` keeps that
    backfill reproducible and avoids presenting current investor data as past.
    """
    from market_microstructure.krx_client import (
        etf_metrics,
        fetch_etf_daily,
        fetch_stock_daily,
        index_by_code,
        recent_bas_dd,
        stock_metrics,
    )

    underlyings = underlyings or ["000660", "005930"]
    ff_ratios = load_ff_ratios()
    day = bas_dd or recent_bas_dd()
    stock_rows = fetch_stock_daily(day)
    etf_rows = fetch_etf_daily(day)
    stocks_ix = index_by_code(stock_rows)
    etfs_ix = index_by_code(etf_rows)

    mcaps: dict[str, float] = {}
    for code, row in stocks_ix.items():
        m = stock_metrics(row)["market_cap_krw"]
        if m is not None:
            mcaps[code] = m
    if not mcaps:
        raise RuntimeError(f"KRX stk_bydd_trd empty/unusable for {day}")
    total_mcap = float(sum(mcaps.values()))
    top_codes = sorted(mcaps, key=mcaps.get, reverse=True)[:30]  # type: ignore[arg-type]
    constituent = {c: mcaps[c] for c in top_codes}

    universe = load_universe()
    univ_products = universe.get("venues", {}).get("kr", {}).get("products", [])
    products_by: dict[str, list[dict[str, Any]]] = {u: [] for u in underlyings}
    market_lev_aum = 0.0
    stock_source = (
        "KRX OpenAPI stk_bydd_trd + etf_bydd_trd (KRX_API) + Naver flows"
        if include_naver_flows
        else "KRX OpenAPI stk_bydd_trd + etf_bydd_trd (KRX_API)"
    )

    for row in etf_rows:
        name = str(row.get("ISU_NM") or row.get("ISU_ABBRV") or "")
        em = etf_metrics(row)
        aum = em["aum_krw"] or 0.0
        if "레버리지" in name or "인버스" in name:
            market_lev_aum += aum

    for p in univ_products:
        und = p.get("underlying")
        if und not in products_by:
            continue
        t = str(p["ticker"])
        row = etfs_ix.get(t)
        if not row:
            continue
        em = etf_metrics(row)
        if em["aum_krw"] is None and em["trading_value_krw"] is None:
            continue
        products_by[und].append(
            {
                "ticker": t,
                "name": p.get("name") or str(row.get("ISU_NM") or t),
                "L": float(p["L"]),
                "aum": float(em["aum_krw"] or 0.0),
                "trading_value": float(em["trading_value_krw"] or 0.0),
                "beta": float(p.get("beta", 1.0)),
                "structure": p.get("structure") or _infer_structure(str(p.get("name") or "")),
                "direction": p.get("direction") or _infer_direction(float(p["L"])),
                "nav": em["nav"],
                "price": em["close"],
            }
        )

    for und in underlyings:
        if products_by[und]:
            continue
        for row in etf_rows:
            name = str(row.get("ISU_NM") or "")
            if _infer_underlying(name) != und:
                continue
            if not (("레버리지" in name) or ("인버스" in name)):
                continue
            code = str(row.get("ISU_SRT_CD") or row.get("ISU_CD") or "").strip()
            em = etf_metrics(row)
            L = _infer_L(name)
            products_by[und].append(
                {
                    "ticker": code,
                    "name": name,
                    "L": L,
                    "aum": float(em["aum_krw"] or 0.0),
                    "trading_value": float(em["trading_value_krw"] or 0.0),
                    "beta": 1.0,
                    "structure": _infer_structure(name),
                    "direction": _infer_direction(L),
                    "nav": em["nav"],
                    "price": em["close"],
                }
            )

    stocks: list[dict[str, Any]] = []
    as_of = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
    for code in underlyings:
        row = stocks_ix.get(code)
        if not row:
            raise RuntimeError(f"KRX missing stock {code} on {day}")
        sm = stock_metrics(row)
        mcap = float(sm["market_cap_krw"] or 0.0)
        adv = float(sm["adv_spot_krw"] or 0.0)
        close = float(sm["close"] or 0.0)
        ff_r = float(ff_ratios.get(code, ff_ratios.get("_default", 0.7)))
        nv = (
            _attach_naver_flows(code, close)
            if include_naver_flows
            else {
                "foreign_hold_ratio_pct": None,
                "flows_shares": {"as_of": None, "foreign_net": None, "institution_net": None, "retail_net": None},
                "flows_krw": {"foreign_net_krw": None, "institution_net_krw": None, "retail_net_krw": None},
                "deal_trend_history": [],
            }
        )
        products = products_by.get(code, [])
        letf_tv = sum(float(p["trading_value"]) for p in products)
        stocks.append(
            {
                "ticker": code,
                "name": str(row.get("ISU_ABBRV") or row.get("ISU_NM") or code),
                "market_cap_krw": mcap,
                "free_float_mcap_krw": mcap * ff_r,
                "free_float_ratio_assumed": ff_r,
                "adv_spot_krw": adv,
                "close": close,
                "day_return": sm["day_return"],
                "letf_trading_value_krw": letf_tv,
                "foreign_hold_ratio_pct": nv["foreign_hold_ratio_pct"],
                "flows_shares": nv["flows_shares"],
                "flows_krw": nv["flows_krw"],
                "deal_trend_history": nv["deal_trend_history"],
                "short_interest_shares": None,
                "short_ratio_pct": None,
                "letf_products": products,
                "source": stock_source,
                "quality": "observed",
            }
        )

    f_net = sum((s["flows_krw"]["foreign_net_krw"] or 0) for s in stocks)
    r_net = sum((s["flows_krw"]["retail_net_krw"] or 0) for s in stocks)
    i_net = sum((s["flows_krw"]["institution_net_krw"] or 0) for s in stocks)

    return {
        "as_of": as_of,
        "bas_dd": day,
        "fx_usdkrw": fx_usdkrw,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_mode": "krx",
        "note": (
            "KRX_API OpenAPI day input. Free-float assumed. Flows from Naver."
            if include_naver_flows
            else "KRX_API OpenAPI historical day input. Naver investor flows intentionally omitted."
        ),
        "kospi": {
            "total_mcap_krw": total_mcap,
            "free_float_mcap_krw": total_mcap * float(ff_ratios.get("_kospi_default", 0.75)),
            "constituent_mcaps_krw": constituent,
            "source": f"KRX OpenAPI sto/stk_bydd_trd basDd={day}",
            "quality": "observed",
        },
        "market_levered_etf": {
            "aum_krw": market_lev_aum,
            "source": f"KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd={day}",
            "quality": "observed",
        },
        "flows": {
            "scope": "covered_underlyings_spot",
            "foreign_net_krw": f_net if include_naver_flows else None,
            "retail_net_krw": r_net if include_naver_flows else None,
            "institution_net_krw": i_net if include_naver_flows else None,
            "source": "Naver dealTrendInfos (share nets × close)" if include_naver_flows else "not requested for historical LETF backfill",
            "quality": "estimated" if include_naver_flows else "missing",
        },
        "stocks": stocks,
    }


def _attach_public_extras(day: dict[str, Any]) -> dict[str, Any]:
    """Mutate day with Naver deposit/credit, KOSPI flows, LETF categories, shorts."""
    from fetch_kr_public_extras import build_public_extras

    tickers = [s["ticker"] for s in day.get("stocks") or []]
    extras = build_public_extras(tickers=tickers or ["000660", "005930"])
    day["public_extras"] = extras

    shorts = (extras.get("short_interest") or {}).get("by_ticker") or {}
    for st in day.get("stocks") or []:
        hit = shorts.get(st["ticker"])
        if not hit:
            continue
        if hit.get("short_interest_shares") is not None:
            st["short_interest_shares"] = hit["short_interest_shares"]
        if hit.get("short_ratio_pct") is not None:
            st["short_ratio_pct"] = hit["short_ratio_pct"]
        st["short_source"] = (extras.get("short_interest") or {}).get("source")
        st["short_quality"] = (extras.get("short_interest") or {}).get("quality")

    # Prefer market-wide Naver flows when available (still keep covered-stock flows)
    mkt = (extras.get("kospi_investor_flows") or {}).get("latest")
    if mkt:
        day["flows_kospi_market"] = {
            "scope": "kospi_cash",
            "foreign_net_krw": mkt.get("foreign_net_krw"),
            "retail_net_krw": mkt.get("retail_net_krw"),
            "institution_net_krw": mkt.get("institution_net_krw"),
            "source": (extras.get("kospi_investor_flows") or {}).get("source"),
            "quality": "observed",
            "date_raw": mkt.get("date_raw"),
        }
    return day


def build_day(
    *,
    source: str = "auto",
    fx_usdkrw: float = 1400.0,
    bas_dd: str | None = None,
    skip_extras: bool = False,
) -> dict[str, Any]:
    """source: auto|krx|fdr — auto uses KRX when ``KRX_API`` is set."""
    mode = source
    if mode == "auto":
        mode = "krx" if has_krx_api() else "fdr"
    if mode == "krx":
        day = build_day_from_krx(fx_usdkrw=fx_usdkrw, bas_dd=bas_dd)
    elif mode == "fdr":
        day = build_day_from_live(fx_usdkrw=fx_usdkrw)
    else:
        raise ValueError(f"unknown source={source}")
    if not skip_extras:
        _attach_public_extras(day)
    return day


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=ROOT / "tests/fixtures/live_day.json")
    p.add_argument("--fx", type=float, default=1400.0)
    p.add_argument("--source", choices=["auto", "krx", "fdr"], default="auto")
    p.add_argument("--bas-dd", default=None, help="YYYYMMDD for KRX (optional)")
    args = p.parse_args()
    day = build_day(source=args.source, fx_usdkrw=args.fx, bas_dd=args.bas_dd)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(day, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.out} mode={day.get('source_mode')} as_of={day['as_of']} "
        f"stocks={len(day['stocks'])}"
    )
    for s in day["stocks"]:
        n = len(s["letf_products"])
        aum = sum(p["aum"] for p in s["letf_products"])
        print(
            f"  {s['ticker']} LETFs={n} AUM={aum/1e12:.2f}조 "
            f"ADV={s['adv_spot_krw']/1e12:.2f}조"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
