"""Graft verified non-US macro prints onto an existing macro pack.

The daily overlay already refreshes FX and a few equity indices. CPI, policy
rates, local bonds, and the remaining equity/commodity cards for other
countries were still ``fixture_synth`` with ``asof`` pinned to a month-end
grid (2026-08-31), which reads as fresh even when nobody has fetched them.

This module only writes a series after a live observation comes back, and it
labels ``asof`` / ``observed_at`` with that observation's own date. It does
not shift the date to the chart's month-end, and it does not replace a card
with null or with a synthetic value when the fetch fails.

Series below were checked on 2026-09-23 against the worker FRED proxy or
Yahoo chart metadata. OECD CPI and immediate-rate mirrors on FRED were still
on 2023–2025 prints, so they are not in this catalog: grafting them would
replace a card with a number that is not a current release. National CPI and
policy-rate adapters stay out until a source whose latest period is actually
current is verified.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from .live_overlay import _pin_latest, _sync_chips, fetch_fred_worker_latest

# (iso3, indicator id, FRED series, max age). Long-term rates are monthly
# OECD MEI prints; ECB policy rates are daily. Age is measured from the
# observation date, not from when we downloaded it.
FRED_SERIES: tuple[tuple[str, str, str, int], ...] = (
    ("ZAF", "sagb_10y", "IRLTLT01ZAM156N", 450),
    ("KOR", "bond_10y", "IRLTLT01KRM156N", 450),
    ("JPN", "bond_10y", "IRLTLT01JPM156N", 450),
    ("GBR", "bond_10y", "IRLTLT01GBM156N", 450),
    ("GBR", "unemployment", "LRHUTTTTGBM156S", 450),
    ("CAN", "bond_10y", "IRLTLT01CAM156N", 450),
    ("AUS", "bond_10y", "IRLTLT01AUM156N", 450),
    ("CHE", "bond_10y", "IRLTLT01CHM156N", 450),
    ("EMU", "bund_10y", "IRLTLT01DEM156N", 450),
    ("EMU", "btp_10y", "IRLTLT01ITM156N", 450),
    ("EMU", "deposit_facility", "ECBDFR", 21),
    ("EMU", "mro_rate", "ECBMRRFR", 21),
    ("EMU", "mlf_rate", "ECBMLFR", 21),
    ("ISR", "bond_10y", "IRLTLT01ILM156N", 450),
)

# Market cards still on fixture_synth. Symbol checked 2026-09-23; the asof
# is the session timestamp Yahoo returns, not the monthly grid.
YAHOO_SERIES: tuple[tuple[str, str, str, int], ...] = (
    ("ZAF", "jse_top40", "^J200.JO", 14),
    ("ZAF", "gold_price", "GC=F", 14),
    ("ZAF", "platinum_price", "PL=F", 14),
    ("CHN", "sse_composite", "000001.SS", 14),
    ("CHN", "csi300", "000300.SS", 14),
    ("EMU", "cac40", "^FCHI", 14),
    ("HKG", "hsi", "^HSI", 14),
    ("AUS", "asx200", "^AXJO", 14),
    ("CHE", "smi", "^SSMI", 14),
    ("BRA", "ibovespa", "^BVSP", 14),
    ("IND", "nifty50", "^NSEI", 14),
    ("IND", "sensex", "^BSESN", 14),
    ("ISR", "ta125", "^TA125.TA", 14),
    ("TWN", "taiex", "^TWII", 14),
    ("VNM", "vnindex", "^VNINDEX.VN", 14),
)

FredFetch = Callable[[str], tuple[date, float]]
YahooFetch = Callable[[str], tuple[date, float]]


def fetch_yahoo_latest(symbol: str) -> tuple[date, float]:
    enc = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}?interval=1d&range=10d"
    req = urllib.request.Request(url, headers={"User-Agent": "macro-monitor/peer"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    result = ((doc.get("chart") or {}).get("result") or [None])[0]
    if not result:
        err = ((doc.get("chart") or {}).get("error") or {})
        raise RuntimeError(f"yahoo empty {symbol}: {err}")
    meta = result.get("meta") or {}
    px = meta.get("regularMarketPrice")
    ts = meta.get("regularMarketTime")
    if px is None or ts is None:
        raise RuntimeError(f"yahoo missing price {symbol}")
    observed = datetime.fromtimestamp(int(ts), timezone.utc).date()
    return observed, float(px)


def apply_peer_macro(
    universe: dict[str, Any],
    *,
    today: date,
    retrieved_at: str,
    fred: FredFetch = fetch_fred_worker_latest,
    yahoo: YahooFetch = fetch_yahoo_latest,
) -> dict[str, list[str]]:
    """Overlay catalog series in place. Failures leave the previous card."""
    stats: dict[str, list[str]] = {"ok": [], "fail": [], "skip": []}
    by_country = {c.get("iso3"): c for c in universe.get("countries") or []}

    for iso3, sid, series_id, max_age in FRED_SERIES:
        _apply_one(
            by_country, stats,
            iso3=iso3, sid=sid, source=f"fred:{series_id}", max_age=max_age,
            today=today, retrieved_at=retrieved_at,
            load=lambda series_id=series_id: fred(series_id),
        )
    for iso3, sid, symbol, max_age in YAHOO_SERIES:
        _apply_one(
            by_country, stats,
            iso3=iso3, sid=sid, source=f"yahoo:{symbol}", max_age=max_age,
            today=today, retrieved_at=retrieved_at,
            load=lambda symbol=symbol: yahoo(symbol),
        )
    return stats


def _apply_one(
    by_country: dict[str, Any],
    stats: dict[str, list[str]],
    *,
    iso3: str,
    sid: str,
    source: str,
    max_age: int,
    today: date,
    retrieved_at: str,
    load: Callable[[], tuple[date, float]],
) -> None:
    key = f"{iso3}:{sid}"
    pack = by_country.get(iso3)
    if not pack:
        stats["skip"].append(f"{key}:no-country")
        return
    ind = next((i for i in pack.get("indicators") or [] if i.get("id") == sid), None)
    if ind is None:
        stats["skip"].append(f"{key}:no-indicator")
        return
    if str(ind.get("quality") or "") == "live":
        stats["skip"].append(f"{key}:already-live")
        return
    try:
        observed, value = load()
    except Exception as exc:  # noqa: BLE001 — one series must not wipe the others
        stats["fail"].append(f"{key}:{exc}")
        return
    if observed is None or value is None:
        stats["fail"].append(f"{key}:empty")
        return
    if observed > today + timedelta(days=2):
        stats["fail"].append(f"{key}:future {observed.isoformat()}")
        return
    if observed < today - timedelta(days=max_age):
        stats["fail"].append(f"{key}:stale {observed.isoformat()}")
        return
    _pin_latest(ind, float(value), source, observed.isoformat())
    ind["observed_at"] = observed.isoformat()
    ind["retrieved_at"] = retrieved_at
    ind["data_status"] = "live_latest"
    _sync_chips(pack, ind)
    stats["ok"].append(key)
