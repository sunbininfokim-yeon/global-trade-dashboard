"""Shared machinery for the countries wired from official keyless APIs in one pass (wire_world_public_series.py).

A country module (can_public_series.py, gbr_public_series.py, ...) lists `CARDS`: each a Spec plus a
function that turns a `Fetch` into points. `Fetch` holds one reader per source, each cached, so two
cards on one series cost one request:

  fred(id)                  FRED CSV                                  (us_public_series.fetch_fred)
  boc(series)               Bank of Canada Valet                      www.bankofcanada.ca/valet
  statcan(vector)           Statistics Canada WDS (POST)              www150.statcan.gc.ca/t1/wds
  ecb(flow, key)            ECB Data Portal SDMX                      data-api.ecb.europa.eu
  eurostat(dataset, query)  Eurostat dissemination API (JSON-stat)    ec.europa.eu/eurostat/api
  bcb(code)                 Banco Central do Brasil SGS               api.bcb.gov.br
  sidra(path)               IBGE SIDRA values API                     apisidra.ibge.gov.br
  boi(flow, code)           Bank of Israel SDMX                       edge.boi.gov.il
  imf(flow, iso3, filters)  IMF data portal SDMX                      api.imf.org
  lpr(tenor)                China Loan Prime Rate (CFETS)             www.chinamoney.com.cn
  boe(code)                 Bank of England IADB CSV                  www.bankofengland.co.uk/boeapps/database
  ons(path)                 ONS time series JSON                      www.ons.gov.uk/<path>/data
  pink()                    World Bank Pink Sheet (monthly averages)  za_public_series.fetch_pink_sheet
  bis(key)                  BIS effective exchange rates (WS_EER)     sg_public_series.fetch_bis

Every reader returns ascending (ISO date, value) points; a daily series is shown as month-ends with the
running month dated by its last observation (`monthly_last`).
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

from . import kr_public_series as krs
from . import us_public_series as ups
from .us_public_series import Points, Spec

UA = "Mozilla/5.0 (compatible; macro-monitor/1.0; +https://github.com/sunbininfokim-yeon/global-trade-dashboard)"

ups._FORMATS.update({
    "pct1": lambda v: f"{v:.1f}%",
    "pct2": lambda v: f"{v:.2f}%",
    "pct0": lambda v: f"{v:.0f}%",
    "bp0": lambda v: f"{v:+.0f}bp" if v else "0bp",
    "k0s": lambda v: f"{v:+,.0f}K",
    "num0": lambda v: f"{v:,.0f}",
    "num1": lambda v: f"{v:,.1f}",
    "usd0": lambda v: f"${v:,.0f}",
    "usd1": lambda v: f"${v:,.1f}",
    "bn0usd": lambda v: f"${v:,.0f}B",
    "bn1usds": lambda v: f"+${v:,.1f}B" if v >= 0 else f"-${-v:,.1f}B",
})


def money(symbol: str, decimals: int = 1, signed: bool = True, suffix: str = "B") -> str:
    """Register (once) and return a format key such as 'bn1_C$' -> 'C$12.3B' / '-C$4.0B'."""
    key = f"{suffix.lower()}{decimals}_{symbol}{'s' if signed else ''}"
    if key not in ups._FORMATS:
        def fmt(v: float, s=symbol, d=decimals, sg=signed, sf=suffix) -> str:
            body = f"{s}{abs(v):,.{d}f}{sf}"
            return ("-" + body) if v < 0 else (("+" + body) if sg and v > 0 else body)
        ups._FORMATS[key] = fmt
    return key


def _get(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: int = 90,
         tries: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url.split('?')[0][:90]}: {last}")


def _num(s: Any) -> float | None:
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s in ("", ".", "NaN", "-", "..", "x", "F"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def period_key(p: str) -> str | None:
    """'2026-08' / '2026-08-15' / '2026-Q2' / '2026Q2' / '2026 AUG' / '2026 Q2' -> ISO date (1st of period)."""
    p = p.strip()
    months = {m: i + 1 for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"))}
    if len(p) == 10 and p[4] == "-" and p[7] == "-":
        return p
    if len(p) in (8, 9) and p[4] == "-" and p[5] == "W":                 # ISO week -> its Friday
        return date.fromisocalendar(int(p[:4]), int(p[6:]), 5).isoformat()
    if len(p) == 7 and p[4] == "-" and p[5] == "Q":
        return f"{p[:4]}-{(int(p[6]) - 1) * 3 + 1:02d}-01"
    if len(p) == 6 and p[4] == "Q":
        return f"{p[:4]}-{(int(p[5]) - 1) * 3 + 1:02d}-01"
    if len(p) == 7 and p[4] == "-":
        return p + "-01"
    parts = p.split()
    if len(parts) == 2 and parts[0].isdigit():
        if parts[1].upper()[:3] in months:
            return f"{parts[0]}-{months[parts[1].upper()[:3]]:02d}-01"
        if parts[1].upper().startswith("Q"):
            return f"{parts[0]}-{(int(parts[1][1]) - 1) * 3 + 1:02d}-01"
    return None


# --------------------------------------------------------------------------
# Readers
# --------------------------------------------------------------------------

def read_boc(series: str, start: str = "2014-01-01") -> Points:
    doc = json.loads(_get(f"https://www.bankofcanada.ca/valet/observations/{series}/json?start_date={start}"))
    out = []
    for o in doc.get("observations") or []:
        v = _num((o.get(series) or {}).get("v"))
        if v is not None:
            out.append((o["d"], v))
    if not out:
        raise ValueError(f"BoC {series}: no observations")
    return out


def read_statcan(vector: int, n: int = 160) -> Points:
    body = json.dumps([{"vectorId": vector, "latestN": n}]).encode()
    doc = json.loads(_get("https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods", data=body,
                          headers={"Content-Type": "application/json"}))[0]
    if doc.get("status") != "SUCCESS":
        raise ValueError(f"StatCan v{vector}: {doc.get('status')}")
    out = []
    for p in doc["object"]["vectorDataPoint"]:
        v = _num(p.get("value"))
        if v is not None:
            out.append((p["refPer"], v * 10 ** int(p.get("scalarFactorCode") or 0)))
    return sorted(out)


def read_ecb(flow: str, key: str, start: str = "2014-01") -> Points:
    text = _get(f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}?startPeriod={start}&format=csvdata").decode("utf-8-sig")
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        d, v = period_key(row.get("TIME_PERIOD", "")), _num(row.get("OBS_VALUE"))
        if d and v is not None:
            out.append((d, v))
    if not out:
        raise ValueError(f"ECB {flow}/{key}: no observations")
    return sorted(out)


def read_eurostat(dataset: str, query: str) -> Points:
    doc = json.loads(_get(f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}?{query}"))
    idx = doc["dimension"]["time"]["category"]["index"]                  # period -> position
    vals = doc.get("value") or {}
    size = 1
    for dim_id in doc["id"]:
        if dim_id != "time":
            if doc["size"][doc["id"].index(dim_id)] != 1:
                raise ValueError(f"Eurostat {dataset}: query is not one series ({dim_id})")
    out = []
    for per, pos in idx.items():
        v = vals.get(str(pos * size))
        d = period_key(per.replace("M", "-")) if "M" in per else period_key(per)
        if d and v is not None:
            out.append((d, float(v)))
    if not out:
        raise ValueError(f"Eurostat {dataset}: no observations")
    return sorted(out)


def read_bcb(code: int, start: str = "01/01/2014") -> Points:
    out: dict[str, float] = {}
    # SGS caps a daily series at ten years per request.
    y0 = int(start[-4:])
    today = date.today()
    while y0 <= today.year:
        y1 = min(y0 + 4, today.year)
        rows = None
        for attempt in range(4):                     # SGS now and then answers an HTML error page
            raw = _get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados?formato=json"
                       f"&dataInicial=01/01/{y0}&dataFinal=31/12/{y1}")
            try:
                rows = json.loads(raw)
                break
            except ValueError:
                time.sleep(3 * (attempt + 1))
        if rows is None:
            raise RuntimeError(f"BCB SGS {code} {y0}-{y1}: not JSON after retries")
        for o in rows:
            dd, mm, yy = o["data"].split("/")
            v = _num(o.get("valor"))
            if v is not None and f"{yy}-{mm}-{dd}" <= today.isoformat():   # the Selic target runs to the next meeting
                out[f"{yy}-{mm}-{dd}"] = v
        y0 = y1 + 1
    if not out:
        raise ValueError(f"BCB SGS {code}: no observations")
    return sorted(out.items())


def read_sidra(path: str) -> Points:
    """IBGE SIDRA values API; the period code is YYYYMM for months and YYYY0Q for quarters (D3C)."""
    rows = json.loads(_get(f"https://apisidra.ibge.gov.br/values/{path}"))
    head, out = rows[0], []
    col = next(k for k, v in head.items() if k.endswith("C") and v.split(" ")[0] in ("Mês", "Trimestre", "Trimestre móvel"))
    quarterly = head[col].startswith("Trimestre (")
    for r in rows[1:]:
        code, v = r[col], _num(r.get("V"))
        if v is None or len(code) != 6:
            continue
        y, n = code[:4], int(code[4:])
        month = (n - 1) * 3 + 1 if quarterly else n
        out.append((f"{y}-{month:02d}-01", v))
    if not out:
        raise ValueError(f"SIDRA {path}: no observations")
    return sorted(out)


def read_boi(flow: str, code: str, start: str = "2014-01") -> Points:
    """Bank of Israel SDMX (edge.boi.gov.il), one series by its SERIES_CODE."""
    url = (f"https://edge.boi.gov.il/FusionEdgeServer/sdmx/v2/data/dataflow/BOI.STATISTICS/{flow}/1.0"
           f"?c%5BSERIES_CODE%5D={code}&startPeriod={start}&format=csv")
    out = []
    for row in csv.DictReader(io.StringIO(_get(url, timeout=150).decode("utf-8-sig"))):
        d, v = period_key(row.get("TIME_PERIOD", "")), _num(row.get("OBS_VALUE"))
        if d and v is not None:
            out.append((d, v))
    if not out:
        raise ValueError(f"BOI {flow}/{code}: no observations")
    return sorted(out)


_IMF_TEXT: dict[tuple[str, str, str], str] = {}


def read_chinamoney_lpr(tenor: str, first_year: int = 2019) -> Points:
    """Loan Prime Rate history from CFETS (chinamoney.com.cn); the endpoint answers one year per request."""
    out: dict[str, float] = {}
    for y in range(first_year, date.today().year + 1):
        url = ("https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/LprHis?lang=CN"
               f"&strStartDate={y}-01-01&strEndDate={y}-12-31&pageNum=1&pageSize=50")
        doc = json.loads(_get(url, headers={"Referer": "https://www.chinamoney.com.cn/english/bmklpr/"}))
        for r in doc.get("records") or []:
            v = _num(r.get(tenor))
            if v is not None:
                out[r["showDateCN"]] = v
    if not out:
        raise ValueError(f"CFETS LPR {tenor}: no observations")
    return sorted(out.items())


def read_imf(flow: str, country: str, filters: tuple[tuple[str, str], ...], start: str = "2014") -> Points:
    """IMF data portal SDMX 2.1 (api.imf.org, keyless). Asks for one country's whole dataflow and keeps
    the single monthly/quarterly series whose attributes match `filters` (e.g. INDICATOR=TRGMV_REVS,
    UNIT=USD) -- the dimension order differs per dataflow, so matching on names is sturdier than a key."""
    import re
    if (flow, country, start) not in _IMF_TEXT:
        _IMF_TEXT[(flow, country, start)] = _get(
            f"https://api.imf.org/external/sdmx/2.1/data/IMF.STA,{flow}/{country}?startPeriod={start}",
            timeout=240).decode("utf-8")
    text = _IMF_TEXT[(flow, country, start)]
    want = dict(filters)
    found: list[Points] = []
    for m in re.finditer(r"<Series ([^>]*)>(.*?)</Series>", text, re.S):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        if any(attrs.get(k) != v for k, v in want.items()):
            continue
        pts = []
        for per, val in re.findall(r'TIME_PERIOD="([^"]+)" OBS_VALUE="([^"]+)"', m.group(2)):
            per = per.replace("-M", "-").replace("-Q", "-Q")
            d, v = period_key(per), _num(val)
            if d and v is not None:
                pts.append((d, v))
        if pts:
            found.append(sorted(pts))
    if len(found) != 1:
        raise ValueError(f"IMF {flow}/{country} {want}: {len(found)} matching series")
    return found[0]


def read_boe(code: str, start: str = "01/Jan/2014") -> Points:
    url = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes"
           f"&Datefrom={start}&Dateto=now&SeriesCodes={code}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
    text = _get(url, headers={"Accept": "text/csv"}).decode("utf-8-sig")
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2 or row[0] == "DATE":
            continue
        try:
            d = time.strftime("%Y-%m-%d", time.strptime(row[0].strip(), "%d %b %Y"))
        except ValueError:
            continue
        v = _num(row[1])
        if v is not None:
            out.append((d, v))
    if not out:
        raise ValueError(f"BoE {code}: no observations")
    return sorted(out)


def read_ons(path: str) -> Points:
    doc = json.loads(_get(f"https://www.ons.gov.uk/{path}/data"))
    rows = doc.get("months") or doc.get("quarters") or []
    out = []
    for r in rows:
        d, v = period_key(r.get("date", "")), _num(r.get("value"))
        if d and v is not None:
            out.append((d, v))
    if not out:
        raise ValueError(f"ONS {path}: no observations")
    return sorted(out)


# --------------------------------------------------------------------------
# Transforms
# --------------------------------------------------------------------------

def monthly_last(pts: Points) -> tuple[Points, str]:
    by: dict[str, float] = {}
    for d, v in sorted(pts):
        by[d[:7] + "-01"] = v
    return sorted(by.items()), max(pts)[0]


def monthly_mean(pts: Points) -> Points:
    acc: dict[str, list[float]] = {}
    for d, v in pts:
        acc.setdefault(d[:7] + "-01", []).append(v)
    return sorted((k, sum(v) / len(v)) for k, v in acc.items())


def spread_bp(a: Points, b: Points) -> Points:
    b_by = dict(b)
    return [(d, (v - b_by[d]) * 100) for d, v in a if d in b_by]


# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------

@dataclass
class Fetch:
    fred: Callable[[str], Points] = ups.fetch_fred
    boc: Callable[[str], Points] = read_boc
    statcan: Callable[[int], Points] = read_statcan
    ecb: Callable[[str, str], Points] = read_ecb
    eurostat: Callable[[str, str], Points] = read_eurostat
    bcb: Callable[[int], Points] = read_bcb
    boe: Callable[[str], Points] = read_boe
    sidra: Callable[[str], Points] = read_sidra
    boi: Callable[[str, str], Points] = read_boi
    imf: Callable[..., Points] = read_imf
    lpr: Callable[[str], Points] = read_chinamoney_lpr
    ons: Callable[[str], Points] = read_ons
    pink_sheet: Callable[[], dict[str, Points]] | None = None
    bis: Callable[[str], Points] | None = None
    _cache: dict[Any, Any] = field(default_factory=dict)

    def get(self, kind: str, *args: Any) -> Any:
        k = (kind, *args)
        if k not in self._cache:
            if kind == "pink":
                if self.pink_sheet is None:
                    from .za_public_series import fetch_pink_sheet
                    self.pink_sheet = fetch_pink_sheet
                self._cache[k] = self.pink_sheet()
            elif kind == "bis" and self.bis is None:
                from .sg_public_series import fetch_bis
                self.bis = fetch_bis
                self._cache[k] = self.bis(*args)
            else:
                self._cache[k] = getattr(self, kind)(*args)
        return self._cache[k]


# The result of a card's reader: points, or (points, last observation day) for a daily series shown monthly.
Read = Callable[[Fetch], "Points | tuple[Points, str]"]


@dataclass
class Card:
    spec: Spec
    read: Read
    category: str | None = None          # set for a card the pack does not have yet (ensure_card)
    yoy_line: bool = False
    rename_from: str | None = None       # an old fixture id this card replaces


def card(id_: str, cadence: str, unit: str, fmt: str, label: str, note: str, source: str, url: str, read: Read,
         *, chart: str = "line", category: str | None = None, yoy_line: bool = False,
         rename_from: str | None = None) -> Card:
    return Card(Spec(id_, cadence, unit, fmt, note, source, (url,), cadence, label_ko=label, chart_type=chart),
                read, category, yoy_line, rename_from)


def build_patch(c: Card, got: Any, *, retrieved_at: str) -> dict[str, Any]:
    from . import jp_public_series as jps
    from .za_public_series import with_gaps
    points, last_day = (got if isinstance(got, tuple) else (got, None))
    if not points:
        raise ValueError(f"{c.spec.id}: no observations")
    if c.spec.cadence in ("monthly", "quarterly"):
        points = with_gaps(points, 3 if c.spec.cadence == "quarterly" else 1)
    live = bool(last_day) and last_day[:7] == points[-1][0][:7]
    patch = ups.build_patch(c.spec, points, retrieved_at=retrieved_at, asof=last_day if live else None)
    if live:
        jps.pin_last_date(patch, last_day)
    if c.yoy_line:
        patch["yoy_line"] = True
    return patch


def apply_country(country: dict[str, Any], cards: list[Card], patches: dict[str, dict[str, Any]], *,
                  retrieved_at: str, gdp_source: str | None = None) -> dict[str, Any]:
    from . import jp_public_series as jps
    by_card = {c.spec.id: c for c in cards}
    for cid, c in by_card.items():
        if cid in patches and c.rename_from:
            krs.rename_indicator(country, c.rename_from, cid, {})
        if cid in patches and c.category:
            ups.ensure_card(country, cid, c.category, c.spec)
    by_id = {i["id"]: i for i in country["indicators"]}
    changed = [k for k, p in patches.items() if k in by_id and ups.apply_patch(by_id[k], p)]
    for k in changed:
        by_id[k].pop("analog_ko", None)
    if gdp_source and jps.apply_gdp_composite(by_id, retrieved_at, source=gdp_source):
        changed.append("gdp")
    ups.sync_chips(country, by_id, set(changed))
    units = krs.sync_chip_units(country, by_id, {k for k in patches if k in by_id})
    before = dict(country.get("data_status_summary") or {})
    ups.refresh_status_summary(country)
    return {"changed": changed, "summary_changed": units or before != country["data_status_summary"]}


def run_country(country: dict[str, Any], cards: list[Card], fetch: Fetch, *, retrieved_at: str,
                gdp_source: str | None = None) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    patches, failures = {}, []
    for c in cards:
        try:
            patches[c.spec.id] = build_patch(c, c.read(fetch), retrieved_at=retrieved_at)
        except Exception as exc:  # noqa: BLE001 -- one series failing must not block the others
            failures.append(f"{country['iso3']} {c.spec.id}: {str(exc)[:160]}")
    result = apply_country(country, cards, patches, retrieved_at=retrieved_at, gdp_source=gdp_source)
    return result, patches, failures


# --------------------------------------------------------------------------
# IMF helpers shared by the emerging-market modules
# --------------------------------------------------------------------------

IMF_CPI_YOY = (("INDEX_TYPE", "CPI"), ("COICOP_1999", "_T"), ("TYPE_OF_TRANSFORMATION", "YOY_PCH_PA_PT"), ("FREQUENCY", "M"))
IMF_RESERVES = (("INDICATOR", "TRGMV_REVS"), ("UNIT", "USD"), ("FREQUENCY", "M"))
IMF_BROAD_MONEY = (("INDICATOR", "DCORP_L_BM"), ("TYPE_OF_TRANSFORMATION", "SA_XDC"), ("FREQUENCY", "M"))
IMF_EXPORTS = (("INDICATOR", "XG"), ("TYPE_OF_TRANSFORMATION", "FOB_USD"), ("FREQUENCY", "M"))
IMF_IMPORTS = (("INDICATOR", "MG"), ("TYPE_OF_TRANSFORMATION", "CIF_USD"), ("FREQUENCY", "M"))
IMF_URL = "https://data.imf.org/"


def imf_trade_balance(f: "Fetch", iso3: str) -> Points:
    """Goods exports (FOB) minus imports (CIF), US$ billion, for the months both are published."""
    ex = dict(f.get("imf", "ITG", iso3, IMF_EXPORTS))
    return [(d, (ex[d] - v) * 1e-9) for d, v in f.get("imf", "ITG", iso3, IMF_IMPORTS) if d in ex]
