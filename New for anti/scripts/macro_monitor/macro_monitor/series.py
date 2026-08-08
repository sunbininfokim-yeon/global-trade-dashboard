"""Deterministic synthetic + derived series for Macro Monitor."""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from typing import Any


def month_ends(end: date, n_months: int) -> list[str]:
    y, m = end.year, end.month
    cur = date(y, 12, 31) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)
    out: list[date] = []
    for _ in range(n_months):
        out.append(cur)
        first = date(cur.year, cur.month, 1)
        cur = first - timedelta(days=1)
    out.reverse()
    return [d.isoformat() for d in out]


def finite_or_none(value: float | None) -> float | None:
    """JSON-safe scalar: non-finite floats become None (→ null)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def synth_path(
    *,
    base: float,
    vol: float,
    drift: float,
    n: int,
    seed: int,
    multiplicative: bool,
    floor: float | None = None,
) -> list[float | None]:
    """Walk backward from `base` (latest). Never emits non-finite floats."""
    rng = random.Random(seed)
    xs: list[float | None] = [None] * n
    level = float(base)
    for i in range(n - 1, -1, -1):
        if not math.isfinite(level):
            xs[i] = None
            # Recover toward base so the rest of the path can continue.
            level = float(base)
            continue
        xs[i] = round(level, 6)
        shock = rng.gauss(0.0, vol)
        if multiplicative:
            factor = 1.0 + drift + shock
            # Near-zero / non-positive factors explode when inverted (→ Inf).
            # Fall back to an additive step instead of clamping to 1e-9.
            if factor > 1e-6:
                level = level / factor
            else:
                level = level - drift - shock
        else:
            level = level - drift - shock
        if floor is not None and math.isfinite(level):
            level = max(floor, level)
    return xs


def delta_vs(history: list[float | None], lookback: int) -> float | None:
    if len(history) <= lookback or lookback < 1:
        return None
    a, b = history[-1], history[-1 - lookback]
    a_f, b_f = finite_or_none(a), finite_or_none(b)
    if a_f is None or b_f is None or b_f == 0:
        return None
    return round((a_f / b_f - 1.0) * 100.0, 2)


def format_value(value: float | None, fmt: str) -> str:
    v = finite_or_none(value)
    if v is None:
        return "—"
    value = v
    if fmt == "flag":
        return "가동" if value >= 0.5 else "미가동"
    if fmt == "usd1":
        return f"${value:+.1f}" if value != 0 else "$0.0"
    if fmt == "pct0":
        return f"{value:.0f}%"
    if fmt == "pct1":
        return f"{value:.1f}%"
    if fmt == "pct2":
        return f"{value:.2f}%"
    if fmt == "pp2":
        return f"{value:.2f}%p"
    if fmt == "bp0":
        return f"{value:+.0f}bp" if value != 0 else "0bp"
    if fmt == "tn1":
        return f"{value:.1f}T"
    if fmt == "tn2":
        return f"{value:.2f}T"
    if fmt == "bn0":
        return f"{value:,.0f}B"
    if fmt == "bn1":
        return f"{value:,.1f}B"
    if fmt == "k0":
        return f"{value:,.0f}K"
    if fmt == "number0":
        return f"{value:,.0f}"
    if fmt == "number1":
        return f"{value:.1f}"
    if fmt == "number2":
        return f"{value:.2f}"
    if fmt == "fx":
        if abs(value) >= 100:
            return f"{value:,.1f}"
        if abs(value) >= 10:
            return f"{value:.2f}"
        return f"{value:.3f}"
    if fmt == "fx4":
        return f"{value:.4f}"
    return f"{value}"


def _multiplicative_for(series_id: str, fmt: str, unit: str) -> bool:
    """Geometric walk only for strictly-positive stock/price-like series.

    Do NOT infer from bn0/bn1/number0: trade balances, net flows, OMO, and
    hours-at-zero cross or hit 0 — multiplicative backfill then overflows to Inf
    on the long (10y) window while the short (5y) window still looks fine.
    """
    multi_ids = {
        "dxy",
        "eurusd",
        "usdjpy",
        "eurjpy",
        "yen_reer",
        "spx",
        "ndx",
        "rut",
        "vix",
        "nikkei",
        "topix",
        "nikkei_vi",
        "fed_total_assets",
        "fed_ust_le_1y",
        "fed_ust_1_5y",
        "fed_ust_5_10y",
        "fed_ust_gt_10y",
        "fed_mbs",
        "on_rrp",
        "fima_repo",
        "discount_window",
        "tga",
        "qra_coupon_bn",
        "qra_bill_bn",
        "net_liquidity",
        "boj_total_assets",
        "boj_etf",
        "boj_jreit",
        "boj_current_account",
        "boj_jgb_purchase_target",
        "boj_jgb_purchase_actual",
        "fx_reserves",
        "boe_total_assets",
        "apf_balance",
        "boe_emergency_facility",
        "gbpusd",
        "eurgbp",
        "gbp_reer",
        "ftse100",
        "ftse250",
        "usdcny",
        "usdcnh",
        "pboc_fixing",
        "cfets_rmb",
        "sse_composite",
        "csi300",
        "hscei",
        "ecb_total_assets",
        "app_balance",
        "pepp_balance",
        "euro_stoxx50",
        "dax40",
        "cac40",
        "stoxx_banks",
        "eur_eer",
        "nwf_liquid",
        "cbr_total_assets",
        "fx_reserves_total",
        "fx_reserves_usable",
        "cnyrub",
        "usdrub",
        "moex_index",
        "rtsi",
        "aggregate_balance",
        "hk_fx_reserves",
        "usdhkd",
        "hsi",
        "hstech",
        "ccl_index",
        "sgd_neer",
        "usdsgd",
        "mas_ofr",
        "sg_total_liquidity",
        "fx_deposits",
        "sti",
        "sreit_index",
        "sg_private_home",
        "sarb_total_assets",
        "usdzar",
        "gold_price",
        "platinum_price",
        "coal_price",
        "jse_top40",
        "usdinr",
        "nifty50",
        "sensex",
        "bok_total_assets",
        "household_credit",
        "pf_loan_balance",
        "usdkrw",
        "kospi",
        "kosdaq",
        "vkospi",
        "boc_total_assets",
        "usdcad",
        "wcs_oil",
        "tsx",
        "teranet_hpi",
        "rba_total_assets",
        "audusd",
        "iron_ore",
        "coking_coal",
        "asx200",
        "asx_vix",
        "corelogic_hpi",
        "snb_total_assets",
        "snb_fx_reserves",
        "sight_deposits",
        "eurchf",
        "usdchf",
        "chf_reer",
        "smi",
        "swiss_banks",
        "kof_barometer",
        "usdbrl",
        "soybeans",
        "crude_oil",
        "ibovespa",
        "ibc_br",
        "usdvnd",
        "vnindex",
        "fdi_registered",
        "fdi_disbursed",
        "nfrk_assets",
        "usdkzt",
        "uranium",
        "cpc_blend",
        "kase_index",
        "usdtwd",
        "life_fx_assets",
        "taiex",
    }
    if series_id in multi_ids:
        return True
    # FX formats are positive price levels; never bn*/number0 (signed / zeroable).
    if fmt in ("fx", "fx4"):
        return True
    if unit in ("index", "tn_jpy", "bn_jpy", "bn_usd", "tn_usd") and series_id.startswith(
        ("spx", "ndx", "rut", "dxy", "ism", "vix", "nikkei", "topix", "boj_", "fx_")
    ):
        return True
    return False


def _sanitize_values(values: list[float | None]) -> list[float | None]:
    return [finite_or_none(v) for v in values]


def build_indicator(
    *,
    series_id: str,
    spec: dict[str, Any],
    country_cfg: dict[str, Any],
    dates: list[str],
    seed: int,
    values_override: list[float | None] | None = None,
) -> dict[str, Any]:
    label = country_cfg.get("label_ko") or spec["label_ko"]
    fmt = spec.get("format", "number1")
    unit = spec.get("unit", "")

    if values_override is not None:
        values = _sanitize_values(
            [round(v, 6) if finite_or_none(v) is not None else None for v in values_override]
        )
        latest = values[-1] if values else None
    else:
        base = float(country_cfg["base"])
        vol = float(country_cfg.get("vol", 0.02))
        drift = float(country_cfg.get("drift", 0.0))
        floor = country_cfg.get("floor")
        floor_f = float(floor) if floor is not None else None
        multiplicative = _multiplicative_for(series_id, fmt, unit)
        values = _sanitize_values(
            synth_path(
                base=base,
                vol=vol,
                drift=drift,
                n=len(dates),
                seed=seed,
                multiplicative=multiplicative,
                floor=floor_f,
            )
        )
        values[-1] = finite_or_none(round(base, 6))
        latest = values[-1]

    hist_years = list(spec.get("history_years") or [5, 10])
    histories: dict[str, dict[str, Any]] = {}
    for y in hist_years:
        months = y * 12
        histories[f"{y}y"] = {
            "dates": dates[-months:] if months <= len(dates) else dates,
            "values": values[-months:] if months <= len(values) else values,
        }

    out: dict[str, Any] = {
        "id": series_id,
        "category": spec["category"],
        "label_ko": label,
        "unit": unit,
        "format": fmt,
        "value": finite_or_none(latest),
        "display": format_value(latest, fmt),
        "change_1m_pct": delta_vs(values, 1),
        "change_1y_pct": delta_vs(values, 12),
        "asof": dates[-1],
        "history": histories,
        "source": "fixture_synth",
        "quality": "demo",
    }
    if spec.get("note_ko"):
        out["note_ko"] = spec["note_ko"]
    if spec.get("fred_hint"):
        out["fred_hint"] = spec["fred_hint"]
    if spec.get("derived") or country_cfg.get("derived"):
        out["derived"] = spec.get("derived") or True
        out["source"] = "derived"
    return out
