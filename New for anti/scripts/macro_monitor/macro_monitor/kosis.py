"""KOSIS OpenAPI client (Statistics Korea and the agencies that publish through it).

The key comes from the KOSIS_API_KEY environment variable and is never written anywhere: it is
kept out of every exception message and every printed URL.

KOSIS answers a bad request with HTTP 200 and {"err": "<code>", "errMsg": "..."}, so an error is
recognised by the body, not the status. A table that needs more classification levels than were
passed answers err 20 ("required variable missing"); `data()` adds levels until it fits.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://kosis.kr/openapi"
USER_AGENT = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"


class KosisError(RuntimeError):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


class MissingKey(KosisError):
    """KOSIS_API_KEY is not set: a run falls back to its cache instead of failing."""


def api_key() -> str:
    key = os.environ.get("KOSIS_API_KEY", "").strip()
    if not key:
        raise MissingKey("KOSIS_API_KEY is not set")
    return key


def _scrub(text: str) -> str:
    key = os.environ.get("KOSIS_API_KEY", "").strip()
    return text.replace(key, "***") if key else text


def _get(path: str, params: dict[str, Any], *, timeout: int = 60, tries: int = 3) -> Any:
    query = urllib.parse.urlencode({**params, "apiKey": api_key(), "format": "json", "jsonVD": "Y"})
    url = f"{BASE}/{path}?{query}"
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            if isinstance(data, dict) and "err" in data:
                raise KosisError(f"KOSIS err {data.get('err')}: {data.get('errMsg')}", code=str(data.get("err")))
            return data
        except KosisError:
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise KosisError(_scrub(f"KOSIS request failed: {last}"))


def data(org_id: str, tbl_id: str, *, prd_se: str = "M", newest: int | None = None,
         start: str | None = None, end: str | None = None, itm_id: str = "ALL", obj_l1: str = "ALL") -> list[dict[str, Any]]:
    """Rows of a statistics table: every classification value and item by default ("ALL"), or the given
    first-level classification code. Either the newest `newest` periods or a start/end range (YYYYMM
    for monthly). KOSIS refuses more than 40,000 cells, so a long range needs `obj_l1`."""
    base: dict[str, Any] = {"method": "getList", "orgId": org_id, "tblId": tbl_id, "prdSe": prd_se, "itmId": itm_id}
    if newest:
        base["newEstPrdCnt"] = newest
    else:
        base["startPrdDe"], base["endPrdDe"] = start, end
    last: KosisError | None = None
    for levels in range(1, 5):
        params = {**base, "objL1": obj_l1, **{f"objL{i}": "ALL" for i in range(2, levels + 1)}}
        try:
            return _get("Param/statisticsParameterData.do", params)
        except KosisError as exc:
            last = exc
            if exc.code != "20":            # only "a required classification is missing" is worth another level
                raise
    raise last or KosisError("no result")


def search(keyword: str, *, org_id: str | None = None, count: int = 10) -> list[dict[str, Any]]:
    """Statistics tables matching a keyword (KOSIS integrated search)."""
    params: dict[str, Any] = {"method": "getList", "searchNm": keyword, "sort": "RANK", "startCount": 1, "resultCount": count}
    if org_id:
        params["orgId"] = org_id
    out = _get("statisticsSearch.do", params)
    return out if isinstance(out, list) else []


# --------------------------------------------------------------------------
# Rows -> series
# --------------------------------------------------------------------------

def period_to_date(prd_de: str, prd_se: str) -> str:
    """KOSIS spells a monthly period YYYYMM and a quarterly one YYYYQQ ('202402' = 2024 Q2); the
    series date is the first day of the month (monthly) or of the quarter's last month (quarterly)."""
    if prd_se == "Q":
        y, q = int(prd_de[:4]), int(prd_de[4:6])
        return f"{y:04d}-{q * 3:02d}-01"
    if prd_se == "M":
        return f"{prd_de[:4]}-{prd_de[4:6]}-01"
    if prd_se == "Y":
        return f"{prd_de[:4]}-12-01"
    raise ValueError(f"unsupported period type {prd_se}")


def series(rows: list[dict[str, Any]], *, prd_se: str, c1_nm: str | None = None, itm_nm: str | None = None,
           c1: str | None = None, itm_id: str | None = None) -> list[tuple[str, float]]:
    """One series out of a table's rows, chosen by the NAME of the classification value and item
    (or by code). Names are what the table prints, and they survive a re-coding of the table;
    a name that matches nothing, or matches two different classification values, raises."""
    picked = [r for r in rows
              if (c1_nm is None or _norm(r.get("C1_NM")) == _norm(c1_nm))
              and (c1 is None or r.get("C1") == c1)
              and (itm_nm is None or _norm(r.get("ITM_NM")) == _norm(itm_nm))
              and (itm_id is None or r.get("ITM_ID") == itm_id)]
    if not picked:
        raise KosisError(f"no rows for C1_NM={c1_nm!r} ITM_NM={itm_nm!r}")
    keys = {(r.get("C1"), r.get("ITM_ID")) for r in picked}
    if len(keys) > 1:
        raise KosisError(f"{len(keys)} different series match C1_NM={c1_nm!r} ITM_NM={itm_nm!r}: {sorted(keys)[:4]}")
    out: dict[str, float] = {}
    for r in picked:
        v = str(r.get("DT", "")).replace(",", "").strip()
        if v in ("", "-", "..."):
            continue
        out[period_to_date(str(r["PRD_DE"]), prd_se)] = float(v)
    if not out:
        raise KosisError("series has no numeric observations")
    return sorted(out.items())


def _norm(text: Any) -> str:
    return "".join(str(text or "").split())
