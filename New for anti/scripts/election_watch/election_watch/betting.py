"""US prediction-market snapshots (Polymarket public Gamma API).

During election cycles these markets give a useful probabilistic view.
Not for gambling UX — fold into elections_board as reference odds only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


DEFAULT_UA = "GTradeElectionWatch/1.0 (+research; markets snapshot)"
GAMMA_SEARCH = "https://gamma-api.polymarket.com/public-search"
GAMMA_MARKETS = "https://gamma-api.polymarket.com/markets"


def _http_get_json(url: str, *, timeout: float = 20.0, ua: str = DEFAULT_UA) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _parse_prices(outcome_prices: Any) -> List[float]:
    if outcome_prices is None:
        return []
    if isinstance(outcome_prices, str):
        try:
            outcome_prices = json.loads(outcome_prices)
        except json.JSONDecodeError:
            return []
    out: List[float] = []
    for p in outcome_prices or []:
        try:
            out.append(float(p))
        except (TypeError, ValueError):
            continue
    return out


def _parse_outcomes(outcomes: Any) -> List[str]:
    if outcomes is None:
        return []
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except json.JSONDecodeError:
            return [outcomes]
    return [str(x) for x in (outcomes or [])]


def market_row(m: Dict[str, Any], *, query: str) -> Dict[str, Any]:
    prices = _parse_prices(m.get("outcomePrices"))
    outcomes = _parse_outcomes(m.get("outcomes"))
    pairs = []
    for i, name in enumerate(outcomes):
        pairs.append(
            {
                "outcome": name,
                "price": prices[i] if i < len(prices) else None,
            }
        )
    return {
        "id": m.get("id") or m.get("conditionId") or m.get("slug"),
        "question": m.get("question") or m.get("title") or m.get("slug"),
        "slug": m.get("slug"),
        "query": query,
        "closed": bool(m.get("closed")),
        "volume": m.get("volume") or m.get("volumeNum"),
        "liquidity": m.get("liquidity") or m.get("liquidityNum"),
        "end_date": m.get("endDate") or m.get("end_date_iso"),
        "outcomes": pairs,
        "url": (
            f"https://polymarket.com/event/{m['slug']}"
            if m.get("slug")
            else m.get("url")
        ),
        "source": "polymarket",
    }


def search_polymarket(
    query: str,
    *,
    max_markets: int = 8,
    timeout: float = 20.0,
) -> List[Dict[str, Any]]:
    """Search public markets; fall back to /markets text filter if search fails."""
    q = (query or "").strip()
    if not q:
        return []
    rows: List[Dict[str, Any]] = []
    try:
        url = f"{GAMMA_SEARCH}?{urllib.parse.urlencode({'q': q, 'limit_per_type': max_markets})}"
        data = _http_get_json(url, timeout=timeout)
        markets = []
        if isinstance(data, dict):
            markets = data.get("markets") or data.get("events") or []
            if not markets and data.get("events"):
                for ev in data["events"]:
                    markets.extend(ev.get("markets") or [])
        elif isinstance(data, list):
            markets = data
        for m in markets:
            if not isinstance(m, dict):
                continue
            # event shell may nest markets
            if m.get("markets") and not m.get("question") and not m.get("outcomePrices"):
                for nested in m.get("markets") or []:
                    if isinstance(nested, dict):
                        rows.append(market_row(nested, query=q))
            else:
                rows.append(market_row(m, query=q))
            if len(rows) >= max_markets:
                break
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        rows = []

    if rows:
        return rows[:max_markets]

    # Fallback: list open markets and filter by keyword tokens
    try:
        url = f"{GAMMA_MARKETS}?{urllib.parse.urlencode({'limit': 80, 'active': 'true', 'closed': 'false'})}"
        data = _http_get_json(url, timeout=timeout)
        if not isinstance(data, list):
            return []
        tokens = [t.lower() for t in q.split() if len(t) > 2]
        for m in data:
            if not isinstance(m, dict):
                continue
            blob = " ".join(
                str(m.get(k) or "")
                for k in ("question", "description", "slug", "groupItemTitle")
            ).lower()
            if tokens and not any(t in blob for t in tokens):
                continue
            rows.append(market_row(m, query=q))
            if len(rows) >= max_markets:
                break
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []
    return rows


def fetch_us_election_markets(
    *,
    queries: Optional[List[str]] = None,
    max_markets: int = 12,
    timeout: float = 20.0,
    enabled: bool = True,
) -> Dict[str, Any]:
    """Aggregate US election-cycle markets from Polymarket."""
    generated_at = datetime.now(timezone.utc).isoformat()
    if not enabled:
        return {
            "enabled": False,
            "generated_at": generated_at,
            "source": "polymarket",
            "markets": [],
            "errors": [],
            "note": "betting disabled in config",
        }

    queries = queries or [
        "US presidential",
        "US election",
        "president",
        "control of congress",
        "senate",
    ]
    seen = set()
    markets: List[Dict[str, Any]] = []
    errors: List[str] = []
    per_q = max(2, max_markets // max(1, len(queries)))

    for q in queries:
        try:
            batch = search_polymarket(q, max_markets=per_q, timeout=timeout)
            for m in batch:
                mid = str(m.get("id") or m.get("slug") or m.get("question"))
                if mid in seen:
                    continue
                seen.add(mid)
                markets.append(m)
                if len(markets) >= max_markets:
                    break
        except Exception as exc:  # noqa: BLE001 — surface in payload, keep board building
            errors.append(f"{q}: {exc}")
        if len(markets) >= max_markets:
            break

    # Sort open markets by volume when available
    def vol_key(m: Dict[str, Any]) -> float:
        try:
            return float(m.get("volume") or 0)
        except (TypeError, ValueError):
            return 0.0

    markets.sort(key=vol_key, reverse=True)
    return {
        "enabled": True,
        "generated_at": generated_at,
        "source": "polymarket",
        "queries": queries,
        "markets": markets[:max_markets],
        "errors": errors,
        "note_ko": "선거 사이클 중 참고 확률. 도박 UX 아님.",
    }
