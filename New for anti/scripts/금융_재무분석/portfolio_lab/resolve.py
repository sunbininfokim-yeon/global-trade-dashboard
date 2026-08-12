"""Map user queries (ticker / Korean name / code) → canonical instruments."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", str(text)).strip().lower()
    t = re.sub(r"[\s_\-]+", "", t)
    return t


# Yahoo-style tickers: AAPL, SPCX, BRK.B, 005930.KS, ^KS11, EURUSD=X, bare 6-digit KRX
_YAHOO_TICKER_RE = re.compile(
    r"""^
    (?:
        \^[A-Za-z0-9]{1,12}                 # ^KS11, ^GSPC
      | [A-Za-z]{2,12}=X                    # EURUSD=X, USDKRW=X
      | \d{6}\.(?:KS|KQ)                    # 005930.KS
      | \d{1,4}\.T                          # 1482.T
      | \d{6}                               # bare KRX code → .KS
      | [A-Za-z][A-Za-z0-9.\-]{0,14}        # AAPL, SPCX, BRK-B, BRK.B
    )
    $""",
    re.VERBOSE | re.IGNORECASE,
)


def looks_like_yahoo_ticker(query: str) -> bool:
    """True if stripped query resembles a Yahoo Finance symbol."""
    s = unicodedata.normalize("NFKC", str(query)).strip()
    if not s or " " in s:
        return False
    return bool(_YAHOO_TICKER_RE.fullmatch(s))


def canonicalize_yahoo_symbol(query: str) -> str:
    """Uppercase ticker while preserving ^, =X, and exchange suffixes."""
    s = unicodedata.normalize("NFKC", str(query)).strip()
    if re.fullmatch(r"\d{6}", s):
        return f"{s}.KS"
    upper = s.upper()
    if upper.endswith("=X"):
        return upper[:-2] + "=X"
    for suf in (".KS", ".KQ", ".T", ".L", ".HK"):
        if upper.endswith(suf):
            return upper[: -len(suf)] + suf
    if s.startswith("^"):
        return "^" + s[1:].upper()
    return upper


def currency_for_yahoo(yahoo: str) -> str:
    u = yahoo.upper()
    if u.endswith(".KS") or u.endswith(".KQ"):
        return "KRW"
    if u.endswith(".T"):
        return "JPY"
    # KR indices are point levels in KRW terms — never treat as USD (would * USDKRW).
    if u.startswith("^"):
        if u in {"^KS11", "^KQ11", "^KS200"} or u.startswith("^KS") or u.startswith("^KQ"):
            return "KRW"
        return "USD"
    if u.endswith("=X"):
        if "KRW" in u:
            return "KRW"
        if "JPY" in u and not u.startswith("JPY"):
            return "JPY"
        # Pair quotes (EURUSD=X, GBPUSD=X, …) are treated as USD-leg prices so
        # USD→KRW conversion yields base-currency units of the pair's base cash.
        return "USD"
    # Common non-US listings (dynamic passthrough). Missing FX path still fails loudly
    # in returns._to_base_price rather than silently treating them as USD.
    _SUFFIX_CCY = {
        ".DE": "EUR",
        ".PA": "EUR",
        ".AS": "EUR",
        ".BR": "EUR",
        ".MI": "EUR",
        ".MC": "EUR",
        ".L": "GBP",
        ".HK": "HKD",
        ".SS": "CNY",
        ".SZ": "CNY",
        ".AX": "AUD",
        ".TO": "CAD",
    }
    for suf, ccy in _SUFFIX_CCY.items():
        if u.endswith(suf):
            return ccy
    return "USD"


def asset_class_for_yahoo(yahoo: str) -> str:
    u = yahoo.upper()
    if u.endswith("=X"):
        return "fx"
    if u.startswith("^"):
        return "index"
    if u.endswith(".KS") or u.endswith(".KQ") or u.endswith(".T"):
        # exchange-listed: treat ETFs/stocks alike as equity unless known
        return "equity"
    return "equity"


@dataclass(frozen=True)
class Instrument:
    id: str
    asset_class: str
    currency: str
    yahoo: str | None
    name_ko: str
    leveraged: bool = False
    leverage_factor: float = 1.0
    max_weight: float | None = None
    proxy: bool = False
    synthetic: str | None = None
    synthetic_leverage: bool = False
    fx_as_asset: bool = False
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "asset_class": self.asset_class,
            "currency": self.currency,
            "yahoo": self.yahoo,
            "name_ko": self.name_ko,
            "leveraged": self.leveraged,
            "leverage_factor": self.leverage_factor,
            "max_weight": self.max_weight,
            "proxy": self.proxy,
            "synthetic": self.synthetic,
            "synthetic_leverage": self.synthetic_leverage,
            "fx_as_asset": self.fx_as_asset,
        }


def make_dynamic_yahoo_instrument(query: str) -> Instrument:
    yahoo = canonicalize_yahoo_symbol(query)
    ccy = currency_for_yahoo(yahoo)
    ac = asset_class_for_yahoo(yahoo)
    label = yahoo
    return Instrument(
        id=f"dyn:yahoo:{yahoo}",
        asset_class=ac,
        currency=ccy,
        yahoo=yahoo,
        name_ko=label,
        aliases=(),
    )


class InstrumentRegistry:
    def __init__(self, path: Path):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.instruments: list[Instrument] = []
        self._by_alias: dict[str, Instrument] = {}
        for row in raw.get("instruments", []):
            inst = Instrument(
                id=row["id"],
                asset_class=row["asset_class"],
                currency=row["currency"],
                yahoo=row.get("yahoo"),
                name_ko=row.get("name_ko") or row["id"],
                leveraged=bool(row.get("leveraged")),
                leverage_factor=float(row.get("leverage_factor") or (2.0 if row.get("leveraged") else 1.0)),
                max_weight=row.get("max_weight"),
                proxy=bool(row.get("proxy")),
                synthetic=row.get("synthetic"),
                synthetic_leverage=bool(row.get("synthetic_leverage")),
                fx_as_asset=bool(row.get("fx_as_asset")),
                aliases=tuple(row.get("aliases") or []),
            )
            self.instruments.append(inst)
            keys = list(inst.aliases) + [inst.id, inst.name_ko]
            if inst.yahoo:
                keys.append(inst.yahoo)
            for a in keys:
                self._by_alias[_norm(a)] = inst

    def resolve_one(self, query: str) -> Instrument | None:
        raw = unicodedata.normalize("NFKC", str(query)).strip()
        if not raw:
            return None
        q = _norm(raw)
        if q in self._by_alias:
            return self._by_alias[q]
        # bare KRX 6-digit → try .KS style ids / aliases
        if re.fullmatch(r"\d{6}", q):
            for cand in (q, f"{q}.ks", f"eq:kr:{q}", f"etf:kr:{q}"):
                if cand in self._by_alias:
                    return self._by_alias[cand]
        # direct yahoo-looking ticker in registry
        for inst in self.instruments:
            if inst.yahoo and _norm(inst.yahoo) == q:
                return inst
        # Yahoo passthrough: unknown but ticker-shaped → dynamic instrument
        if looks_like_yahoo_ticker(raw):
            return make_dynamic_yahoo_instrument(raw)
        return None


def resolve_portfolio(
    portfolio: dict[str, Any],
    registry: InstrumentRegistry,
    *,
    net_asset_value: float | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return resolved positions with signed weights.

    When a positive ``net_asset_value`` is supplied, values are divided by NAV rather
    than by gross exposure.  This preserves the risk of a credit-funded or long/short
    book (for example, a 130% long funded with 30% credit remains a 130% exposure).
    The gross-normalized fallback is retained for legacy callers and pure weight input.
    """
    positions_in = portfolio.get("positions") or []
    unresolved: list[str] = []
    resolved: list[dict[str, Any]] = []

    values: list[float] = []
    rows: list[tuple[Instrument, float]] = []
    for p in positions_in:
        query = str(p.get("query") or p.get("symbol") or "").strip()
        if not query:
            continue
        inst = registry.resolve_one(query)
        if inst is None:
            unresolved.append(query)
            continue
        side = str(p.get("side") or "long").strip().lower()
        if "value" in p and p["value"] is not None:
            val = abs(float(p["value"]))
            if side in {"short", "sell", "공매도"}:
                val = -val
        elif "weight" in p and p["weight"] is not None:
            val = float(p["weight"])  # temporary; renormalize later as weight-only
            if side in {"short", "sell", "공매도"} and val > 0:
                val = -val
            rows.append((inst, val))
            values.append(None)  # type: ignore[arg-type]
            continue
        else:
            unresolved.append(query)
            continue
        rows.append((inst, val))
        values.append(val)

    # weight-only portfolio — normalize by gross (|w|), same convention as value path.
    # Net-sum renormalization breaks with shorts (0.6/-0.4 → 3/-2; 0.5/-0.5 → 0/0).
    if rows and all(v is None for v in values):
        gross = sum(abs(v) for _, v in rows)
        for inst, w in rows:
            resolved.append(
                {
                    "query": inst.name_ko,
                    "instrument": inst.to_dict(),
                    "value": None,
                    "weight": (w / gross) if gross else 0.0,
                    "side": "short" if w < 0 else "long",
                }
            )
        return resolved, unresolved

    # drop weight-only mixed case; require values
    clean = [(inst, val) for (inst, val), marker in zip(rows, values) if marker is not None]
    gross = sum(abs(v) for _, v in clean)
    if gross <= 0:
        return [], unresolved

    # merge duplicate ids (signed notionals)
    merged: dict[str, dict[str, Any]] = {}
    for inst, val in clean:
        if inst.id in merged:
            merged[inst.id]["value"] += val
        else:
            merged[inst.id] = {
                "query": inst.name_ko,
                "instrument": inst.to_dict(),
                "value": val,
                "weight": 0.0,
                "side": "short" if val < 0 else "long",
            }
    gross = sum(abs(x["value"]) for x in merged.values())
    denom = float(net_asset_value) if net_asset_value is not None else gross
    if denom <= 0:
        raise ValueError("net_asset_value must be positive when resolving value positions")
    for row in merged.values():
        row["weight"] = row["value"] / denom  # NAV weights when supplied; shorts negative
        row["side"] = "short" if row["value"] < 0 else "long"
        resolved.append(row)
    return resolved, unresolved
