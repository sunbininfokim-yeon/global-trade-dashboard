"""Declarative wiring for free public series: one registry entry per card, no code per card.

The registry (config/free_cards_v1.json) names, for each card, the reader that fetches it, the
reader's parameters, a list of transforms, and the card's unit, format, label and note. The runner
(wire_free_cards.py) reads every enabled entry, builds the card with the same patch contract as the
hand-written country modules, attaches it (creating the card when the pack has none), and records
each entry's health in config/free_cards_status_v1.json. apply_hidden_flags.py then shows a card
once it is live and keeps a card that never read hidden -- so adding a source is adding an entry.

Entries with "enabled": false document a card that has no free source (or one that has not been
verified yet) and why; `wire_free_cards.py --probe` tries the ones that name a reader, so a source
that comes back (a server that was down, a site out of maintenance) is noticed.

Readers are either the shared fetchers in world_public_series.Fetch (fred, ecb, eurostat, bcb, boe,
statcan, boc, sidra, boi, ons, yahoo, imf, bis) or the small ones below. Every value is a published
observation or arithmetic on one; nothing is estimated.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Callable

from . import jp_public_series  # noqa: F401 -- registers the yen/signed display formats
from . import us_public_series as ups
from . import world_public_series as wps

Points = list[tuple[str, float]]

REGISTRY = Path(__file__).resolve().parent.parent / "config" / "free_cards_v1.json"
STATUS = Path(__file__).resolve().parent.parent / "config" / "free_cards_status_v1.json"

CADENCES = {"monthly", "quarterly", "annual", "weekly"}
CATEGORIES = {"liquidity", "rates", "fx", "equity", "growth", "inflation"}


# --------------------------------------------------------------------------
# Readers that the shared Fetch does not have
# --------------------------------------------------------------------------

def parse_sdmx_series(text: str, filters: dict[str, str]) -> Points:
    """One series out of an IMF SDMX 2.1 structure-specific answer, matched on its attributes."""
    found: list[Points] = []
    for m in re.finditer(r"<Series ([^>]*)>(.*?)</Series>", text, re.S):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        if any(attrs.get(k) != v for k, v in filters.items()):
            continue
        pts = []
        for per, val in re.findall(r'TIME_PERIOD="([^"]+)" OBS_VALUE="([^"]+)"', m.group(2)):
            d, v = wps.period_key(per.replace("-M", "-")), wps._num(val)
            if d and v is not None:
                pts.append((d, v))
        if pts:
            found.append(sorted(pts))
    if len(found) != 1:
        raise ValueError(f"SDMX {filters}: {len(found)} matching series")
    return found[0]


def read_imf_pcps(indicator: str, transformation: str = "USD", start: str = "2014") -> Points:
    """IMF Primary Commodity Prices (monthly, world). e.g. PURAN = uranium, USD per pound."""
    text = wps._get(f"https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS/G001.{indicator}.?startPeriod={start}",
                    timeout=240).decode("utf-8")
    return parse_sdmx_series(text, {"INDICATOR": indicator, "DATA_TRANSFORMATION": transformation, "FREQUENCY": "M"})


MOF_SECURITIES = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/{file}.csv"
_EN_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def parse_mof_securities(text: str, column: int) -> Points:
    """MOF 'International Transactions in Securities' monthly CSV: the year sits only on January's row
    (col 0), the English month in col 2, values with thousands separators (100 million yen)."""
    out: Points = []
    year = None
    for row in csv.reader(io.StringIO(text)):
        if len(row) <= column:
            continue
        m = re.match(r"\s*(\d{4})", row[0] or "")
        if m:
            year = int(m.group(1))
        mon = (row[2] or "").strip()[:3]
        if year is None or mon not in _EN_MONTHS:
            continue
        v = wps._num((row[column] or "").replace(",", ""))
        if v is not None:
            out.append((f"{year:04d}-{_EN_MONTHS.index(mon) + 1:02d}-01", v))
    if not out:
        raise ValueError("MOF securities CSV: no observations")
    return sorted(out)


def read_mof_securities(file: str, column: int) -> Points:
    raw = wps._get(MOF_SECURITIES.format(file=file))
    return parse_mof_securities(raw.decode("cp932", errors="replace"), column)


IFO_PAGE = "https://www.ifo.de/en/ifo-time-series"


def parse_ifo_rows(rows: list[tuple], column: int) -> Points:
    """ifo time-series workbook: data rows start with 'MM/YYYY'."""
    out: Points = []
    for r in rows:
        if not r or not isinstance(r[0], str):
            continue
        m = re.match(r"\s*(\d{2})/(\d{4})\s*$", r[0])
        if m and len(r) > column and isinstance(r[column], (int, float)):
            out.append((f"{m.group(2)}-{m.group(1)}-01", float(r[column])))
    if not out:
        raise ValueError("ifo workbook: no observations")
    return sorted(out)


def read_ifo(prefix: str, column: int) -> Points:
    """The workbook's name carries its month (gsk-e-YYYYMM.xlsx); take the link the page lists now."""
    import openpyxl
    page = wps._get(IFO_PAGE).decode("utf-8", errors="replace")
    m = re.search(rf'href="([^"]*/{re.escape(prefix)}-\d{{6}}\.xlsx)"', page)
    if not m:
        raise ValueError(f"ifo page lists no {prefix} workbook")
    data = wps._get("https://www.ifo.de" + m.group(1) if m.group(1).startswith("/") else m.group(1))
    ws = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True).worksheets[0]
    return parse_ifo_rows(list(ws.iter_rows(values_only=True)), column)


def read_kof(key: str) -> Points:
    """KOF data service (ETH Zurich), keyless JSON: {key: [{"date": "YYYY-MM", "value": x}, ...]}."""
    doc = json.loads(wps._get(f"https://datenservice.kof.ethz.ch/api/v1/public/ts?keys={key}&mime=json"))
    rows = doc.get(key) if isinstance(doc, dict) else None
    if not rows:
        raise ValueError(f"KOF {key}: no observations")
    return sorted((r["date"][:7] + "-01", float(r["value"])) for r in rows if r.get("value") is not None)


CUSTOM_READERS: dict[str, Callable[..., Points]] = {
    "imf_pcps": read_imf_pcps,
    "mof_securities": read_mof_securities,
    "ifo": read_ifo,
    "kof": read_kof,
}
FETCH_READERS = {"fred", "boc", "statcan", "ecb", "eurostat", "bcb", "boe", "sidra", "boi", "ons", "yahoo", "imf", "bis"}


def read(fetch: wps.Fetch, spec: dict[str, Any]) -> Points:
    name, params = spec["reader"], spec.get("params") or {}
    if name in CUSTOM_READERS:
        return CUSTOM_READERS[name](**params)
    if name in FETCH_READERS:
        args = params.get("args") or []
        if name == "imf":
            args = [args[0], args[1], tuple(tuple(x) for x in args[2])]
        return fetch.get(name, *args)
    raise KeyError(f"unknown reader {name!r}")


# --------------------------------------------------------------------------
# Transforms
# --------------------------------------------------------------------------

def apply_ops(points: Points, ops: list[list[Any]], fetch: wps.Fetch) -> Any:
    """Each op is [name, *args]. A daily series turned monthly by monthly_last keeps its last day so the
    card shows the true observation date."""
    last_day = None
    for op in ops:
        name, args = op[0], op[1:]
        if name == "scale":
            points = ups.scale(points, float(args[0]))
        elif name == "pct_change":
            points = ups.pct_change(points, int(args[0]))
        elif name == "diff":
            points = ups.diff(points)
        elif name == "vs_base":
            points = ups.vs_base(points, str(args[0]))
        elif name == "monthly_mean":
            points = wps.monthly_mean(points)
        elif name == "monthly_last":
            points, last_day = wps.monthly_last(points)
        elif name in ("minus", "spread_bp"):
            other = read(fetch, args[0])
            points = wps.spread_bp(points, other) if name == "spread_bp" else \
                [(d, v - o) for d, v in points for o in [dict(other).get(d)] if o is not None]
        elif name == "ratio_pct":
            other = dict(read(fetch, args[0]))
            points = [(d, v / other[d] * 100.0) for d, v in points if other.get(d)]
        else:
            raise KeyError(f"unknown transform {name!r}")
    return (points, last_day) if last_day else points


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

REQUIRED = ("iso3", "id", "label_ko", "category", "cadence", "unit", "format", "note_ko", "source", "url")


def validate(entry: dict[str, Any]) -> list[str]:
    """Problems with one entry ([] when it is fine). A disabled entry needs only an id and a reason."""
    errs = []
    if not entry.get("enabled", True):
        if not entry.get("reason_ko"):
            errs.append("disabled entry without reason_ko")
        return errs
    errs += [f"missing {k}" for k in REQUIRED if not entry.get(k)]
    if entry.get("cadence") not in CADENCES:
        errs.append(f"cadence {entry.get('cadence')!r}")
    if entry.get("category") not in CATEGORIES:
        errs.append(f"category {entry.get('category')!r}")
    if entry.get("format") not in ups._FORMATS:
        errs.append(f"format {entry.get('format')!r}")
    r = (entry.get("read") or {}).get("reader")
    if r not in CUSTOM_READERS and r not in FETCH_READERS:
        errs.append(f"reader {r!r}")
    return errs


def load_registry(path: Path = REGISTRY) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc["cards"]


def to_card(entry: dict[str, Any]) -> wps.Card:
    return wps.card(entry["id"], entry["cadence"], entry["unit"], entry["format"], entry["label_ko"], entry["note_ko"],
                    entry["source"], entry["url"],
                    lambda f, e=entry: apply_ops(read(f, e["read"]), e.get("ops") or [], f),
                    category=entry["category"], chart=entry.get("chart_type") or "line")


def enabled_by_country(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        if e.get("enabled", True):
            out.setdefault(e["iso3"], []).append(e)
    return out


def update_status(status: dict[str, Any], key: str, *, ok: bool, now: str, patch: dict[str, Any] | None = None,
                  error: str | None = None) -> None:
    """Changes only when something did (a new value, a failure), so a quiet day commits nothing."""
    s = status.setdefault(key, {"consecutive_failures": 0})
    if ok and patch:
        shown = (patch.get("display"), patch.get("reference_period"))
        if shown != (s.get("display"), s.get("reference_period")):
            s.update({"display": shown[0], "reference_period": shown[1], "changed_at": now[:10]})
        s.update({"consecutive_failures": 0, "last_error": None})
    else:
        s["consecutive_failures"] = int(s.get("consecutive_failures") or 0) + 1
        s["last_error"] = (error or "")[:200]
        s["last_failed"] = now[:10]
