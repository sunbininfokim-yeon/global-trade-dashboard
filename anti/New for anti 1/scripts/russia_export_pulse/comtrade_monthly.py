"""Optional UN Comtrade monthly exports (needs COMTRADE_SUBSCRIPTION_KEY)."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Russia M49 = 643. Partner World = 0. Flow export = X.
RUSSIA_M49 = "643"
WORLD_PARTNER = "0"

# HS headings we care about for this pulse.
HS_SERIES = {
    "wheat": "1001",
    "petroleum_products": "2710",
}


def log(msg: str) -> None:
    print(f"[comtrade_monthly] {msg}", flush=True)


def fetch_monthly_exports(
    hs: str,
    *,
    periods: str,
    api_key: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """
    Fetch monthly Russia exports for one HS code.

    `periods` is Comtrade period list, e.g. "202301,202302,...,202412"
    or a range if the API accepts it — we pass an explicit comma list.
    """
    key = api_key or os.environ.get("COMTRADE_SUBSCRIPTION_KEY") or os.environ.get("COMTRADE_API_KEY")
    if not key:
        return {
            "available": False,
            "reason": "COMTRADE_SUBSCRIPTION_KEY not set — monthly series skipped",
            "hs": hs,
            "series": [],
        }

    params = {
        "reporterCode": RUSSIA_M49,
        "period": periods,
        "partnerCode": WORLD_PARTNER,
        "cmdCode": hs,
        "flowCode": "X",
        "fmt": "json",
    }
    url = "https://comtradeapi.un.org/data/v1/get/C/M/HS?" + urlencode(params)
    req = Request(url, headers={
        "Ocp-Apim-Subscription-Key": key,
        "User-Agent": "russia-export-pulse/1.0",
        "Accept": "application/json",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = json.load(resp)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        log(f"HS {hs} failed: {exc}")
        return {
            "available": False,
            "reason": str(exc),
            "hs": hs,
            "series": [],
        }

    rows = body.get("data") or []
    series = []
    for row in rows:
        period = str(row.get("period") or row.get("periodDesc") or "")
        # Prefer net weight tonnes when present
        val = row.get("netWgt")
        unit = "kg"
        if val is None:
            val = row.get("primaryValue")
            unit = str(row.get("qtyUnitAbbr") or row.get("cmdCode") or "value")
        if val is None:
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        # Convert kg → 1000 MT when netWgt
        if unit == "kg" or row.get("netWgt") is not None:
            num = num / 1_000_000.0  # kg → thousand metric tons
            unit = "1000 MT"
        series.append({"period": period, "value": round(num, 3), "unit": unit})

    series.sort(key=lambda x: x["period"])
    return {
        "available": True,
        "hs": hs,
        "frequency": "monthly",
        "source": {
            "name": "UN Comtrade (monthly HS)",
            "url": "https://comtradeplus.un.org/",
        },
        "series": series,
        "note_ko": "월별은 구독 키가 있을 때만. 다크십·미신고는 포함되지 않음.",
    }


def default_recent_periods(n_months: int = 24) -> str:
    """Build YYYYMM list for the last n_months (UTC-naive calendar)."""
    from datetime import date

    today = date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n_months):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return ",".join(reversed(out))
