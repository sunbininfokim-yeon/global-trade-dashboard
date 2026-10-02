"""Bank of Korea ECOS OpenAPI client (ecos.bok.or.kr).

The key comes from ECOS_API_KEY and is never written anywhere: it is kept out of every exception
message. ECOS answers a problem with HTTP 200 and {"RESULT": {"CODE": ..., "MESSAGE": ...}}; the
data itself sits under "StatisticSearch". Period strings by cycle: D YYYYMMDD, M YYYYMM, Q YYYYQn.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date
from typing import Any

BASE = "https://ecos.bok.or.kr/api"
USER_AGENT = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"

Points = list[tuple[str, float]]


class MissingKey(RuntimeError):
    """ECOS_API_KEY is not set: the run falls back to the cache instead of failing."""


class EcosError(RuntimeError):
    pass


def api_key() -> str:
    key = os.environ.get("ECOS_API_KEY", "").strip()
    if not key:
        raise MissingKey("ECOS_API_KEY is not set")
    return key


def _scrub(text: str) -> str:
    key = os.environ.get("ECOS_API_KEY", "").strip()
    return text.replace(key, "***") if key else text


def _get(path: str, *, timeout: int = 90, tries: int = 3) -> Any:
    url = f"{BASE}/{path.replace('@KEY', api_key())}"
    last: Exception | None = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise EcosError(_scrub(f"ECOS request failed: {last}"))


def period_to_date(time_s: str, cycle: str) -> str:
    """ECOS period -> series date: a day as itself, a month as its first day, a quarter as the first day
    of its first month (the convention the FRED-fed cards use)."""
    if cycle == "D" and len(time_s) == 8:
        return f"{time_s[:4]}-{time_s[4:6]}-{time_s[6:]}"
    if cycle == "M" and len(time_s) == 6:
        return f"{time_s[:4]}-{time_s[4:]}-01"
    if cycle == "Q" and len(time_s) == 6 and time_s[4] == "Q":
        return f"{time_s[:4]}-{(int(time_s[5]) - 1) * 3 + 1:02d}-01"
    raise ValueError(f"unsupported {cycle} period {time_s!r}")


def window(cycle: str, today: date, years: int = 11) -> tuple[str, str]:
    y0 = today.year - years
    if cycle == "D":
        return f"{y0}0101", today.strftime("%Y%m%d")
    if cycle == "M":
        return f"{y0}01", today.strftime("%Y%m")
    if cycle == "Q":
        return f"{y0}Q1", f"{today.year}Q{(today.month - 1) // 3 + 1}"
    raise ValueError(cycle)


def parse_rows(doc: Any, cycle: str) -> tuple[Points, str | None]:
    """(points, unit name) from a StatisticSearch answer; a value that is not a number is skipped."""
    body = doc.get("StatisticSearch") if isinstance(doc, dict) else None
    if body is None:
        res = (doc or {}).get("RESULT") or {}
        raise EcosError(f"ECOS: {res.get('CODE')} {res.get('MESSAGE')}")
    out: Points = []
    unit = None
    for r in body.get("row") or []:
        v = str(r.get("DATA_VALUE") or "").replace(",", "").strip()
        if v in ("", "-"):
            continue
        try:
            out.append((period_to_date(str(r["TIME"]), cycle), float(v)))
        except (ValueError, KeyError):
            continue
        unit = unit or r.get("UNIT_NAME")
    if not out:
        raise EcosError("ECOS series has no observations")
    return sorted(out), unit


def series(stat: str, cycle: str, items: tuple[str, ...], *, today: date | None = None) -> tuple[Points, str | None]:
    """One ECOS series over the last ~11 years: (points, unit name)."""
    today = today or date.today()
    a, b = window(cycle, today)
    path = f"StatisticSearch/@KEY/json/kr/1/100000/{stat}/{cycle}/{a}/{b}/" + "/".join(items) + "/"
    return parse_rows(_get(path), cycle)
