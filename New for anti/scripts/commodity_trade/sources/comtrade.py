"""UN Comtrade monthly adapters: key-backed API and bounded free Preview."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from hs_match import COMMODITY_HS_STEMS, normalize_hs


PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"


def fetch_monthly(
    *,
    hs: str,
    reporter_m49: str,
    periods: str,
    flow: str = "X",
    api_key: str | None = None,
    timeout: int = 90,
) -> dict[str, Any]:
    key = api_key or os.environ.get("COMTRADE_SUBSCRIPTION_KEY") or os.environ.get("COMTRADE_API_KEY")
    if not key:
        return {
            "available": False,
            "reason": "COMTRADE_SUBSCRIPTION_KEY not set",
            "hs": hs,
            "series": [],
        }
    params = {
        "reporterCode": reporter_m49,
        "period": periods,
        "partnerCode": "0",
        "cmdCode": normalize_hs(hs),
        "flowCode": flow,
        "fmt": "json",
    }
    url = "https://comtradeapi.un.org/data/v1/get/C/M/HS?" + urlencode(params)
    req = Request(
        url,
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "User-Agent": "commodity-trade/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = json.load(resp)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": str(exc), "hs": hs, "series": []}

    series = []
    for row in body.get("data") or []:
        period = str(row.get("period") or "")
        if len(period) == 6 and period.isdigit():
            month = f"{period[:4]}-{period[4:]}"
        else:
            month = period
        val = row.get("netWgt")
        if val is None:
            val = row.get("primaryValue")
        try:
            val_f = float(val) if val is not None else None
        except (TypeError, ValueError):
            val_f = None
        if val_f is None:
            continue
        series.append(
            {
                "month": month,
                "value": val_f,
                "unit": "kg" if row.get("netWgt") is not None else "usd",
                "source": "comtrade",
                "hs": normalize_hs(hs),
            }
        )
    return {"available": bool(series), "hs": hs, "series": series, "source": "comtrade"}


def _preview_cache_path(
    cache_dir: Path, *, reporter_m49: str, period: str, flow: str, hs_codes: list[str]
) -> Path:
    key = ",".join(sorted(hs_codes))
    digest = sha256(key.encode("utf-8")).hexdigest()[:12]
    return cache_dir / f"comtrade_preview_{reporter_m49}_{flow}_{period}_{digest}.json"


def fetch_preview_month(
    *,
    hs_codes: list[str],
    reporter_m49: str,
    period: str,
    flow: str,
    cache_dir: Path,
    allow_fetch: bool = True,
    timeout: int = 90,
) -> dict[str, Any]:
    """Fetch one reporter/flow/month from the no-key Preview endpoint.

    Preview is deliberately restricted to one period per request.  Callers must
    impose a request cap and cache responses; this helper never expands a
    period range on its own.
    """
    normalized_codes = sorted({normalize_hs(code) for code in hs_codes if normalize_hs(code)})
    if not normalized_codes:
        return {"available": False, "reason": "no valid HS codes", "series_by_hs": {}}
    if len(period) != 6 or not period.isdigit():
        return {"available": False, "reason": "period must be YYYYMM", "series_by_hs": {}}
    if flow not in {"X", "M"}:
        return {"available": False, "reason": "flow must be X or M", "series_by_hs": {}}

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _preview_cache_path(
        cache_dir,
        reporter_m49=reporter_m49,
        period=period,
        flow=flow,
        hs_codes=normalized_codes,
    )
    from_cache = cache_path.exists()
    if from_cache:
        try:
            body = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"available": False, "reason": f"invalid preview cache: {exc}", "series_by_hs": {}}
    elif not allow_fetch:
        return {"available": False, "reason": "preview cache miss with fetch disabled", "series_by_hs": {}}
    else:
        params = {
            "reporterCode": reporter_m49,
            "period": period,
            "partnerCode": "0",
            "cmdCode": ",".join(normalized_codes),
            "flowCode": flow,
            "maxRecords": "500",
        }
        req = Request(
            PREVIEW_URL + "?" + urlencode(params),
            headers={"User-Agent": "commodity-trade-preview/1.0", "Accept": "application/json"},
        )
        try:
            with urlopen(req, timeout=timeout) as response:
                body = json.load(response)
        except HTTPError as exc:
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            return {
                "available": False,
                "reason": str(exc),
                "rate_limited": exc.code == 429,
                "retry_after_seconds": retry_after,
                "series_by_hs": {},
            }
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"available": False, "reason": str(exc), "series_by_hs": {}}
        cache_path.write_text(json.dumps(body, ensure_ascii=False) + "\n", encoding="utf-8")

    series_by_hs: dict[str, list[dict[str, Any]]] = {code: [] for code in normalized_codes}
    for row in body.get("data") or []:
        hs = normalize_hs(row.get("cmdCode"))
        if hs not in series_by_hs:
            continue
        raw_weight = row.get("netWgt")
        raw_value = raw_weight if raw_weight is not None else row.get("primaryValue")
        try:
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            value = None
        if value is None:
            continue
        observed_period = str(row.get("period") or period)
        month = f"{observed_period[:4]}-{observed_period[4:]}" if len(observed_period) == 6 else observed_period
        series_by_hs[hs].append(
            {
                "month": month,
                "value": value,
                "unit": "kg" if raw_weight is not None else "usd",
                "source": "comtrade_preview",
                "source_access": "free_preview",
                "hs": hs,
                "flow": flow,
                "partner_m49": "0",
                "primary_value_usd": row.get("primaryValue"),
                "quality": {
                    "is_reported": row.get("isReported"),
                    "is_quantity_estimated": row.get("isQtyEstimated"),
                    "is_aggregate": row.get("isAggregate"),
                    "legacy_estimation_flag": row.get("legacyEstimationFlag"),
                },
            }
        )
    return {
        "available": any(series_by_hs.values()),
        "source": "comtrade_preview",
        "reporter_m49": reporter_m49,
        "period": period,
        "flow": flow,
        "series_by_hs": series_by_hs,
        "response_count": len(body.get("data") or []),
        "cache": {"path": str(cache_path), "hit": from_cache},
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "error": body.get("error") or None,
    }
