"""China Foreign Exchange Trade System (www.chinamoney.com.cn) series, kept month by month in
config/cn_cfets_cache_v1.json: the endpoints answer one year (fixing, CFETS index) or one day (the
government bond curve) per request, so each month-end is asked for once and kept.

  fixing   USD/CNY central parity (PBOC fixing), last fixing of each month
  rmbidx   CFETS RMB index (basket), last weekly print of each month
  cgb10    ChinaBond government yield curve, 10-year point, last business day of each month
"""

from __future__ import annotations

import calendar
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from .us_public_series import Points
from .world_public_series import _get

CACHE = Path(__file__).resolve().parent.parent / "config" / "cn_cfets_cache_v1.json"
BASE = "https://www.chinamoney.com.cn/ags/ms/"
FIRST_YEAR = 2016


def _post(path: str) -> dict[str, Any]:
    raw = _get(BASE + path, data=b"", headers={"Referer": "https://www.chinamoney.com.cn/english/"})
    return json.loads(raw)


def fetch_fixing_year(y: int, today: date) -> dict[str, float]:
    end = min(date(y, 12, 31), today)
    out: dict[str, float] = {}
    page = 1
    while True:
        doc = _post(f"cm-u-bk-ccpr/CcprHisNew?startDate={y}-01-01&endDate={end}&currency=USD/CNY&pageNum={page}&pageSize=50")
        recs = doc.get("records") or []
        for r in recs:
            out[r["date"]] = float(r["values"][0])
        total = (doc.get("data") or {}).get("total") or 0
        if not recs or page * 50 >= int(total):
            return out
        page += 1


def fetch_rmbidx_year(y: int, today: date) -> dict[str, float]:
    end = min(date(y, 12, 31), today)
    doc = _post(f"cm-u-bk-fx/RmbIdxHis?lang=CN&startDate={y}-01-01&endDate={end}")
    return {r["showDate"]: float(r["cfetsIndexRate"]) for r in doc.get("records") or [] if r.get("cfetsIndexRate")}


def fetch_cgb10_day(d: date) -> float | None:
    doc = _post(f"cm-u-bk-currency/ClsYldCurvHis?lang=CN&reference=1&bondType=CYCC000&startDate={d}&endDate={d}"
                f"&termId=10&pageNum=1&pageSize=50")
    for r in doc.get("records") or []:
        if r.get("yearTermStr") in ("10", "10.0"):
            return float(r["maturityYieldStr"])
    return None


def _month_last(daily: dict[str, float]) -> dict[str, list]:
    by: dict[str, list] = {}
    for d in sorted(daily):
        by[d[:7]] = [d, daily[d]]
    return by


def load_cache(path: Path = CACHE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_cache(cache: dict[str, Any], path: Path = CACHE) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def refresh(cache: dict[str, Any], today: date,
            fixing: Callable[[int, date], dict[str, float]] = fetch_fixing_year,
            rmbidx: Callable[[int, date], dict[str, float]] = fetch_rmbidx_year,
            cgb10: Callable[[date], float | None] = fetch_cgb10_day) -> bool:
    """Fill what is missing: whole years on the first run, then this year (and last, in January)."""
    before = json.dumps(cache, sort_keys=True)
    for name, reader in (("fixing", fixing), ("rmbidx", rmbidx)):
        series = cache.setdefault(name, {})
        years = range(FIRST_YEAR, today.year + 1) if not series else sorted({today.year, (today - timedelta(days=40)).year})
        for y in years:
            series.update(_month_last(reader(y, today)))
    series = cache.setdefault("cgb10", {})
    y, m = FIRST_YEAR, 1
    while (y, m) <= (today.year, today.month):
        key = f"{y:04d}-{m:02d}"
        current = (y, m) == (today.year, today.month)
        if key not in series or current:
            last = min(date(y, m, calendar.monthrange(y, m)[1]), today)
            for back in range(0, 8):                    # step back over weekends and holidays
                v = cgb10(last - timedelta(days=back))
                if v is not None:
                    series[key] = [(last - timedelta(days=back)).isoformat(), v]
                    break
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return json.dumps(cache, sort_keys=True) != before


def points(cache: dict[str, Any], name: str) -> tuple[Points, str]:
    rows = sorted((cache.get(name) or {}).items())
    if not rows:
        raise ValueError(f"CFETS {name}: nothing cached")
    return [(f"{k}-01", v[1]) for k, v in rows], rows[-1][1][0]
