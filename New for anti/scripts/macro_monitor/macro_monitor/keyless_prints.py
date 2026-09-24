"""Graft CPI and policy prints that do not need KOSIS or e-Stat.

Korea and Japan stay on their previous cards until those keys exist.
A fetch that fails, is older than the series allows, or is dated after
today leaves the previous card untouched. asof is the source's own
observation date: the first day of the CPI reference month, or the
business day of a policy rate. It is not moved onto the chart's month-end.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from .live_overlay import _pin_latest, _sync_chips

# (iso3, indicator, source label, max age in days, fetcher key)
CATALOG: tuple[tuple[str, str, str, int, str], ...] = (
    ("GBR", "cpi_yoy", "ons:D7G7", 80, "gbr_cpi"),
    ("GBR", "core_cpi_yoy", "ons:DKO8", 80, "gbr_core"),
    ("GBR", "bank_rate", "boe:IUDBEDR", 21, "gbr_bank_rate"),
    ("CAN", "cpi_yoy", "statcan:v41690973", 80, "can_cpi"),
    ("CAN", "boc_overnight", "boc:V39079", 21, "can_overnight"),
    ("BRA", "ipca", "bcb:13522", 80, "bra_ipca"),
    ("BRA", "selic_rate", "bcb:432", 21, "bra_selic"),
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

Fetch = Callable[[], tuple[date, float]]


def apply_keyless_prints(
    universe: dict[str, Any],
    *,
    today: date,
    retrieved_at: str,
    fetchers: dict[str, Fetch] | None = None,
) -> dict[str, list[str]]:
    """Overlay catalog series in place. Failures leave the previous card."""
    stats: dict[str, list[str]] = {"ok": [], "fail": [], "skip": []}
    loaders = fetchers if fetchers is not None else default_fetchers(today)
    by_country = {c.get("iso3"): c for c in universe.get("countries") or []}

    for iso3, sid, source, max_age, key in CATALOG:
        label = f"{iso3}:{sid}"
        pack = by_country.get(iso3)
        if not pack:
            stats["skip"].append(f"{label}:no-country")
            continue
        ind = next((i for i in pack.get("indicators") or [] if i.get("id") == sid), None)
        if ind is None:
            stats["skip"].append(f"{label}:no-indicator")
            continue
        if str(ind.get("quality") or "") == "live":
            stats["skip"].append(f"{label}:already-live")
            continue
        loader = loaders.get(key)
        if loader is None:
            stats["skip"].append(f"{label}:no-fetcher")
            continue
        try:
            observed, value = loader()
        except Exception as exc:  # noqa: BLE001 — one series must not wipe the others
            stats["fail"].append(f"{label}:{exc}")
            continue
        if observed is None or value is None:
            stats["fail"].append(f"{label}:empty")
            continue
        if observed > today + timedelta(days=2):
            stats["fail"].append(f"{label}:future {observed.isoformat()}")
            continue
        if observed < today - timedelta(days=max_age):
            stats["fail"].append(f"{label}:stale {observed.isoformat()}")
            continue
        _pin_latest(ind, float(value), source, observed.isoformat())
        ind["observed_at"] = observed.isoformat()
        ind["retrieved_at"] = retrieved_at
        ind["data_status"] = "live_latest"
        _sync_chips(pack, ind)
        stats["ok"].append(label)
    return stats


def default_fetchers(today: date) -> dict[str, Fetch]:
    return {
        "gbr_cpi": lambda: fetch_ons("d7g7", ("ANNUAL RATE", "ALL ITEMS")),
        "gbr_core": lambda: fetch_ons("dko8", ("EXCLUDING ENERGY",)),
        "gbr_bank_rate": lambda: fetch_boe_bank_rate(today),
        "can_cpi": fetch_statcan_cpi_yoy,
        "can_overnight": lambda: fetch_boc_overnight(today),
        "bra_ipca": lambda: fetch_bcb(13522, today, lookback_days=120),
        "bra_selic": lambda: fetch_bcb(432, today, lookback_days=40),
    }


def _get(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: int = 35) -> bytes:
    base = {"User-Agent": "macro-monitor/keyless", "Accept": "application/json,text/csv"}
    if headers:
        base.update(headers)
    req = urllib.request.Request(url, data=data, headers=base)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _month_number(name: str) -> int:
    key = name.strip().lower().rstrip(".")
    if key not in _MONTHS:
        raise RuntimeError(f"unknown month {name}")
    return _MONTHS[key]


def parse_ons_latest(doc: dict[str, Any], title_needs: tuple[str, ...]) -> tuple[date, float]:
    desc = doc.get("description")
    title = str(desc.get("title") if isinstance(desc, dict) else desc or "")
    folded = title.upper()
    missing = [part for part in title_needs if part.upper() not in folded]
    if missing:
        raise RuntimeError(f"ons title {title!r} missing {missing}")
    for row in reversed(doc.get("months") or []):
        raw = str(row.get("value") or "").strip()
        if not raw or raw in {"-", "."}:
            continue
        observed = date(int(row["year"]), _month_number(str(row["month"])), 1)
        return observed, float(raw)
    raise RuntimeError("ons empty")


def fetch_ons(cdid: str, title_needs: tuple[str, ...]) -> tuple[date, float]:
    uri = f"/economy/inflationandpriceindices/timeseries/{cdid}/mm23"
    url = "https://api.beta.ons.gov.uk/v1/data?" + urllib.parse.urlencode({"uri": uri})
    return parse_ons_latest(json.loads(_get(url).decode("utf-8")), title_needs)


def parse_boe_csv(text: str, *, today: date) -> tuple[date, float]:
    last: tuple[date, float] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.upper().startswith("DATE"):
            continue
        day_s, _, value_s = line.partition(",")
        parts = day_s.split()
        if len(parts) != 3 or not value_s.strip():
            continue
        try:
            observed = date(int(parts[2]), _month_number(parts[1]), int(parts[0]))
            value = float(value_s.strip())
        except ValueError:
            continue
        if observed <= today + timedelta(days=2):
            last = (observed, value)
    if last is None:
        raise RuntimeError("boe empty")
    return last


def fetch_boe_bank_rate(today: date) -> tuple[date, float]:
    start = today - timedelta(days=40)
    url = (
        "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
        "?csv.x=yes&SeriesCodes=IUDBEDR&UsingCodes=Y&CSVF=TN&Datefrom="
        + urllib.parse.quote(start.strftime("%d/%b/%Y"))
    )
    return parse_boe_csv(_get(url).decode("latin-1", "replace"), today=today)


def parse_boc_overnight(doc: dict[str, Any], *, today: date) -> tuple[date, float]:
    latest: tuple[date, float] | None = None
    for row in doc.get("observations") or []:
        raw = (row.get("V39079") or {}).get("v")
        if raw in (None, "", "."):
            continue
        observed = date.fromisoformat(str(row["d"])[:10])
        if observed > today + timedelta(days=2):
            continue
        if latest is None or observed > latest[0]:
            latest = (observed, float(raw))
    if latest is None:
        raise RuntimeError("boc empty")
    return latest


def fetch_boc_overnight(today: date) -> tuple[date, float]:
    url = "https://www.bankofcanada.ca/valet/observations/V39079/json?recent=8"
    return parse_boc_overnight(json.loads(_get(url).decode("utf-8")), today=today)


def parse_bcb_latest(rows: list[dict[str, Any]], *, today: date) -> tuple[date, float]:
    latest: tuple[date, float] | None = None
    for row in rows:
        observed = datetime.strptime(str(row["data"]), "%d/%m/%Y").date()
        if observed > today:
            continue
        latest = (observed, float(str(row["valor"]).replace(",", ".")))
    if latest is None:
        raise RuntimeError("bcb empty")
    return latest


def fetch_bcb(series: int, today: date, *, lookback_days: int) -> tuple[date, float]:
    start = today - timedelta(days=lookback_days)
    query = urllib.parse.urlencode({
        "formato": "json",
        "dataInicial": start.strftime("%d/%m/%Y"),
        "dataFinal": today.strftime("%d/%m/%Y"),
    })
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados?{query}"
    return parse_bcb_latest(json.loads(_get(url).decode("utf-8")), today=today)


def all_items_cpi_title(title: str) -> bool:
    """StatCan labels the headline as ``Canada;All-items`` on table 18-10-0004."""
    folded = title.strip().lower()
    if "excluding" in folded:
        return False
    if folded == "canada;all-items":
        return True
    return "consumer price index" in folded and "all-items" in folded


def yoy_from_month_index(points: list[tuple[date, float]]) -> tuple[date, float]:
    """12-month percent change of a published price index. Not a forecast."""
    by = {item[0]: item[1] for item in points}
    if not by:
        raise RuntimeError("statcan empty")
    latest = max(by)
    prev = date(latest.year - 1, latest.month, latest.day)
    if prev not in by or by[prev] == 0:
        raise RuntimeError(f"statcan missing {prev.isoformat()}")
    return latest, round((by[latest] / by[prev] - 1.0) * 100.0, 1)


def fetch_statcan_cpi_yoy() -> tuple[date, float]:
    info_body = json.dumps([{"vectorId": 41690973}]).encode()
    info = json.loads(_get(
        "https://www150.statcan.gc.ca/t1/wds/rest/getSeriesInfoFromVector",
        data=info_body,
        headers={"Content-Type": "application/json"},
    ).decode("utf-8"))
    obj = (info[0] or {}).get("object") or {}
    title = str(obj.get("SeriesTitleEn") or "")
    if not all_items_cpi_title(title):
        raise RuntimeError(f"statcan title not all-items: {title!r}")
    data_body = json.dumps([{"vectorId": 41690973, "latestN": 14}]).encode()
    data = json.loads(_get(
        "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods",
        data=data_body,
        headers={"Content-Type": "application/json"},
    ).decode("utf-8"))
    pts = ((data[0] or {}).get("object") or {}).get("vectorDataPoint") or []
    points = [
        (date.fromisoformat(str(p["refPer"])[:10]), float(p["value"]))
        for p in pts
        if p.get("refPer") and p.get("value") is not None
    ]
    return yoy_from_month_index(points)


def retrieved_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
