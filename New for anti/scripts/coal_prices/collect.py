#!/usr/bin/env python3
"""Coal reference prices. Standard library only; nothing is estimated.

Two official, free series, kept apart because they are different things:

  HBA     Indonesia's government reference price (Harga Batubara Acuan), set by
          a ministerial decision twice a month. The ministry's press release
          carries the four grades (HBA 6,322 GAR; HBA I 5,300; HBA II 4,100;
          HBA III 3,400) in one paragraph; that paragraph is what is read here.
          It is a policy price for Indonesian exports, not a market quote.
  WB      The World Bank's Pink Sheet: monthly average Australian (Newcastle)
          and South African (Richards Bay) thermal coal, $/mt, from the
          CMO-Historical-Data-Monthly workbook (CC BY 4.0). Published about a
          month behind.

Neither is a futures price and the panel says so. A number is written only if
it was read from the source and passed the checks below; a source that fails
keeps its last good data and is marked, never filled in.

Run: python3 collect.py --out ../../public/data/coal_prices_v1.json
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

SCHEMA = "coal_prices_v1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
LIMIT = 40 * 1024 * 1024

WB_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
WB_FILE_RE = re.compile(r"https?://thedocs\.worldbank\.org/[^\"'\s<>]+/related/CMO-Historical-Data-Monthly\.xlsx")
WB_SHEET = "Monthly Prices"
WB_SERIES = (
    # (id, the workbook's own column name, Korean label)
    ("coal_australian", "Coal, Australian", "호주산 석탄"),
    ("coal_south_african", "Coal, South African", "남아공산 석탄"),
)
WB_KEEP_MONTHS = 120   # ten years: a long series is what this source is for

ESDM_LIST = "https://www.esdm.go.id/id/media-center/arsip-berita"
HBA_KEEP_PERIODS = 48  # two years of half-months
HBA_PAUSE = 2.0        # the ministry's firewall rejects bursts; go one page at a time
HBA_MAX_PAGES = 14     # ~15 items a page, ~7 a day: two weeks back reaches the previous announcement
HBA_FIRST_RUN_LINKS = 3

# Stale thresholds the panel applies (days since the data's own end date).
HBA_STALE_DAYS = 24
WB_STALE_DAYS = 80


class SourceError(Exception):
    """Only short, categorical reasons are written to the public output."""


# ---- fetching ---------------------------------------------------------------------------

def get_bytes(url: str, timeout: float = 40.0) -> bytes:
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "id,en;q=0.8"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- fixed https hosts
            body = resp.read(LIMIT + 1)
    except HTTPError as exc:
        raise SourceError(f"http_{exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise SourceError("unreachable") from None
    if len(body) > LIMIT:
        raise SourceError("too_large")
    return body


def get_text(url: str) -> str:
    return get_bytes(url).decode("utf-8", "replace")


# ---- xlsx (stdlib reader: shared strings, inline strings, numbers) -------------------------

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
_MAX_XLSX_PART = 120 * 1024 * 1024


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "")
    if not letters:
        raise SourceError("bad_cell_ref")
    n = 0
    for ch in letters.group(0):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_xlsx_sheet(blob: bytes, sheet_name: str) -> List[List[Any]]:
    """Rows of one sheet as lists (None for blanks). Numbers come back as float."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        raise SourceError("not_xlsx") from None
    if any(i.file_size > _MAX_XLSX_PART for i in zf.infolist()):
        raise SourceError("xlsx_too_large")

    def parse(name: str) -> ET.Element:
        try:
            return ET.fromstring(zf.read(name))
        except KeyError:
            raise SourceError("xlsx_part_missing") from None
        except ET.ParseError:
            raise SourceError("xlsx_parse") from None

    shared: List[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        for si in parse("xl/sharedStrings.xml").findall("m:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))

    wb = parse("xl/workbook.xml")
    rid = None
    for sh in wb.find("m:sheets", _NS) or []:
        if (sh.get("name") or "").strip().lower() == sheet_name.lower():
            rid = sh.get(f"{{{_NS['r']}}}id")
            break
    if rid is None:
        raise SourceError("sheet_missing")
    target = None
    for rel in parse("xl/_rels/workbook.xml.rels").findall("rel:Relationship", _NS):
        if rel.get("Id") == rid:
            target = rel.get("Target") or ""
            break
    if not target:
        raise SourceError("sheet_missing")
    path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"

    rows: List[List[Any]] = []
    for row in parse(path).iter(f"{{{_NS['m']}}}row"):
        cells: Dict[int, Any] = {}
        for c in row.findall("m:c", _NS):
            kind = c.get("t")
            v = c.find("m:v", _NS)
            if kind == "inlineStr":
                value: Any = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
            elif v is None or v.text is None:
                continue
            elif kind == "s":
                idx = int(v.text)
                value = shared[idx] if 0 <= idx < len(shared) else None
            elif kind in ("str", "e"):
                value = v.text
            elif kind == "b":
                value = bool(int(v.text))
            else:
                try:
                    value = float(v.text)
                except ValueError:
                    value = v.text
            cells[_col_index(c.get("r", ""))] = value
        if cells:
            width = max(cells) + 1
            line = [cells.get(i) for i in range(width)]
        else:
            line = []
        # keep row positions: pad up to the declared row number
        want = int(row.get("r", len(rows) + 1))
        while len(rows) < want - 1:
            rows.append([])
        rows.append(line)
    return rows


# ---- World Bank ------------------------------------------------------------------------------

def finite(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            f = float(value.replace(",", "").strip())
        except ValueError:
            return None  # "…", "..", "n/a": a gap, not a zero
        return f if math.isfinite(f) else None
    return None


_MONTH_RE = re.compile(r"^\s*(\d{4})\s*M\s*(\d{1,2})\s*$")


def parse_worldbank_monthly(rows: List[List[Any]]) -> Dict[str, Any]:
    """Pull the coal columns out of the Pink Sheet's Monthly Prices sheet.

    The header row is found by name (the sheet has title rows above it and the
    column order moves between editions), and the unit row under it must still
    say $/mt, otherwise the series is refused rather than shown in a wrong unit.
    """
    header_at = None
    for i, row in enumerate(rows[:30]):
        names = {str(c).strip().lower() for c in row if isinstance(c, str)}
        if all(col.lower() in names for _, col, _ in WB_SERIES):
            header_at = i
            break
    if header_at is None:
        raise SourceError("coal_columns_missing")
    header = rows[header_at]
    cols = {}
    for sid, col, _ in WB_SERIES:
        cols[sid] = next(j for j, c in enumerate(header) if isinstance(c, str) and c.strip().lower() == col.lower())
    units_row = rows[header_at + 1] if header_at + 1 < len(rows) else []
    for sid, j in cols.items():
        unit = str(units_row[j]).strip() if j < len(units_row) and units_row[j] is not None else ""
        if "$/mt" not in unit.replace(" ", ""):
            raise SourceError("unit_changed")

    points: Dict[str, List[List[Any]]] = {sid: [] for sid in cols}
    for row in rows[header_at + 2:]:
        m = _MONTH_RE.match(str(row[0])) if row and row[0] is not None else None
        if not m:
            continue
        period = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
        for sid, j in cols.items():
            val = finite(row[j]) if j < len(row) else None
            if val is not None and 0 < val < 2000:
                points[sid].append([period, round(val, 2)])
    out = []
    for sid, col, label in WB_SERIES:
        pts = points[sid][-WB_KEEP_MONTHS:]
        if not pts:
            raise SourceError("coal_series_empty")
        out.append({"id": sid, "source_name": col, "label_ko": label, "unit": "$/mt", "points": pts})
    return {"series": out}


def fetch_worldbank(get: Callable[[str], bytes] = get_bytes) -> Dict[str, Any]:
    page = get(WB_PAGE).decode("utf-8", "replace")
    m = WB_FILE_RE.search(page)
    if not m:
        raise SourceError("workbook_link_missing")
    file_url = m.group(0)
    parsed = parse_worldbank_monthly(read_xlsx_sheet(get(file_url), WB_SHEET))
    latest = max(s["points"][-1][0] for s in parsed["series"])
    return {"status": "ok", "source": "World Bank Commodity Price Data (The Pink Sheet)", "license": "CC BY 4.0",
            "source_url": WB_PAGE, "file_url": file_url, "latest_period": latest, **parsed}


# ---- Indonesia HBA --------------------------------------------------------------------------------

_MONTHS_ID = {"januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6, "juli": 7,
              "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12}
_PERIOD_RE = re.compile(r"masa\s+berlaku\s+(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.I)
_TITLE_PERIOD_RE = re.compile(r"periode\s+(pertama|kedua|i{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.I)
_PRICE_RE = re.compile(
    r"\b(HBA(?:\s+(?:III|II|I))?)\s+untuk\s+([\d.]+)\s*GAR\s+sebesar\s+(?:USD|US\$)\s*([\d.,]+)\s+per\s+ton"
    r"(?:,\s*(naik|turun)\s+([\d.,]+)\s+persen)?", re.I)
_HBA_ORDER = ("HBA", "HBA I", "HBA II", "HBA III")


def id_number(text: str, decimals: bool) -> float:
    """Indonesian digits: '.' groups thousands and ',' is the decimal mark."""
    s = text.strip()
    s = s.replace(".", "").replace(",", ".") if decimals else s.replace(".", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        raise SourceError("bad_number") from None


def visible_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def _last_day(year: int, month: int) -> int:
    return (date(year + (month == 12), month % 12 + 1, 1) - date(year, month, 1)).days


def parse_hba_announcement(text: str, url: str, title: str = "") -> Dict[str, Any]:
    """One half-month's HBA grades from a ministry press release's text."""
    start = end = None
    m = _PERIOD_RE.search(text)
    if m and m.group(3).lower() in _MONTHS_ID:
        d1, d2, month, year = int(m.group(1)), int(m.group(2)), _MONTHS_ID[m.group(3).lower()], int(m.group(4))
        try:
            start, end = date(year, month, d1), date(year, month, d2)
        except ValueError:
            raise SourceError("bad_period") from None
    else:
        # Only the headline names this release's own period; the body also says
        # "compared with the second period of July", which is not it.
        t = _TITLE_PERIOD_RE.search(title or "")
        if t and t.group(2).lower() in _MONTHS_ID:
            month, year = _MONTHS_ID[t.group(2).lower()], int(t.group(3))
            first_half = t.group(1).lower() in ("pertama", "i")
            start = date(year, month, 1 if first_half else 15)
            end = date(year, month, 14 if first_half else _last_day(year, month))
    if start is None or end is None or end < start or (end - start).days > 20:
        raise SourceError("period_unreadable")

    grades: Dict[str, Dict[str, Any]] = {}
    for g in _PRICE_RE.finditer(text):
        name = re.sub(r"\s+", " ", g.group(1).upper())
        if name in grades:
            continue
        grades[name] = {
            "name": name,
            "gar": int(id_number(g.group(2), False)),
            "usd_per_t": id_number(g.group(3), True),
        }
        if g.group(4) and g.group(5):
            pct = id_number(g.group(5), True)
            grades[name]["change_pct"] = round(-pct if g.group(4).lower() == "turun" else pct, 2)
    if set(grades) != set(_HBA_ORDER):
        raise SourceError("grades_missing")
    ordered = [grades[n] for n in _HBA_ORDER]
    prices = [g["usd_per_t"] for g in ordered]
    gars = [g["gar"] for g in ordered]
    # A thinner coal sells for less: the grades must fall with calorific value.
    if not (all(5 < p < 600 for p in prices) and prices == sorted(prices, reverse=True) and gars == sorted(gars, reverse=True)):
        raise SourceError("grades_inconsistent")
    return {"start": start.isoformat(), "end": end.isoformat(), "grades": ordered, "url": url}


_ANCHOR_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def hba_links(html: str, base: str) -> List[Tuple[str, str]]:
    """(url, title) of the ministry's HBA announcements on a list page."""
    out: List[Tuple[str, str]] = []
    seen = set()
    for href, inner in _ANCHOR_RE.findall(html):
        title = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", inner))).strip()
        url = urljoin(base, unescape(href))
        slug = url.rsplit("/", 1)[-1].lower()
        if "/arsip-berita/" in url and re.search(r"(^|-)hba(-|$)", slug) and url not in seen:
            seen.add(url)
            out.append((url, title))
    return out


def merge_periods(old: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """History accumulates: the list page only reaches back a few weeks."""
    by_start = {p["start"]: p for p in old}
    for p in new:
        by_start[p["start"]] = p
    return [by_start[k] for k in sorted(by_start)][-HBA_KEEP_PERIODS:]


def fetch_hba(previous: Optional[Dict[str, Any]] = None, get: Callable[[str], bytes] = get_bytes,
              pause: float = HBA_PAUSE, max_pages: int = HBA_MAX_PAGES) -> Dict[str, Any]:
    """New HBA announcements, found by paging the ministry's news archive.

    The archive has no search and no feed; it lists ~15 items a page, newest
    first, and an announcement comes only twice a month, so the newest one can
    be a few pages down. Paging stops at the first announcement already held
    (everything below it is older). The firewall in front of the site rejects
    bursts, so this is strictly one request at a time with a pause.
    """
    prior = (previous or {}).get("periods", [])
    known = {p["url"] for p in prior}
    links: List[Tuple[str, str]] = []
    errors: List[str] = []
    for n in range(1, max_pages + 1):
        if n > 1:
            time.sleep(pause)
        page = ESDM_LIST if n == 1 else f"{ESDM_LIST}?page={n}"
        try:
            page_links = hba_links(get(page).decode("utf-8", "replace"), page)
        except SourceError as exc:
            if n == 1:
                raise
            errors.append(f"page{n}:{exc}")
            break
        links += [l for l in page_links if l[0] not in {u for u, _ in links}]
        if any(u in known for u, _ in page_links):
            break
        if not known and len(links) >= HBA_FIRST_RUN_LINKS:
            break

    found: List[Dict[str, Any]] = []
    for url, title in links:
        if url in known:
            continue
        time.sleep(pause)
        try:
            found.append(parse_hba_announcement(visible_text(get(url).decode("utf-8", "replace")), url, title))
        except SourceError as exc:
            # One unreadable announcement is skipped and named; it never becomes a guess.
            errors.append(f"{url.rsplit('/', 1)[-1][:60]}:{exc}")
    periods = merge_periods(prior, found)
    if not periods:
        raise SourceError(errors[-1].split(":")[-1] if errors else "no_announcements_found")
    out = {"status": "ok", "source": "인도네시아 에너지광물자원부(ESDM) 보도자료 · HBA 고시", "source_url": ESDM_LIST,
           "periods": periods, "latest_end": periods[-1]["end"]}
    if errors:
        out["skipped"] = errors[:6]
    return out


# ---- assemble ------------------------------------------------------------------------------------------

def collect(previous: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None,
            get: Callable[[str], bytes] = get_bytes, pause: float = HBA_PAUSE) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    previous = previous or {}
    out: Dict[str, Any] = {"schema_version": SCHEMA, "generated_at": now.replace(microsecond=0).isoformat(),
                           "stale_after_days": {"hba": HBA_STALE_DAYS, "worldbank": WB_STALE_DAYS}}
    for key, fn in (("hba", lambda: fetch_hba(previous.get("hba"), get=get, pause=pause)),
                    ("worldbank", lambda: fetch_worldbank(get))):
        try:
            out[key] = fn()
        except SourceError as exc:
            # The last good data stays, marked: an old number with its date is
            # honest, an empty card is not more so.
            was = previous.get(key) or {}
            kept = dict(was)
            kept["status"] = "error"
            kept["error"] = str(exc)
            # Same failure as last time keeps its first timestamp, so an outage
            # does not rewrite the file (and commit) every day.
            same = was.get("status") == "error" and was.get("error") == str(exc) and was.get("error_at")
            kept["error_at"] = was["error_at"] if same else now.replace(microsecond=0).isoformat()
            out[key] = kept
    return out


def atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    default_out = Path(__file__).resolve().parents[2] / "public" / "data" / "coal_prices_v1.json"
    ap.add_argument("--out", default=str(default_out))
    ap.add_argument("--require-all", action="store_true", help="exit 1 if either source failed")
    args = ap.parse_args()
    out_path = Path(args.out)
    previous = None
    if out_path.exists():
        try:
            previous = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = None
    doc = collect(previous)
    # Nothing but the run time changed: leave the file (and the repo) alone.
    if previous and {k: v for k, v in previous.items() if k != "generated_at"} == {k: v for k, v in doc.items() if k != "generated_at"}:
        doc = previous
    else:
        atomic_write(out_path, doc)
    hba, wb = doc["hba"], doc["worldbank"]
    last = hba.get("periods", [{}])[-1] if hba.get("periods") else {}
    print(f"hba: {hba['status']} {hba.get('error', '')} periods={len(hba.get('periods', []))} "
          f"latest={last.get('start')}..{last.get('end')} "
          f"{[(g['name'], g['usd_per_t']) for g in last.get('grades', [])]}")
    print(f"worldbank: {wb['status']} {wb.get('error', '')} latest={wb.get('latest_period')} "
          f"{[(s['id'], s['points'][-1]) for s in wb.get('series', [])]}")
    bad = [k for k in ("hba", "worldbank") if doc[k]["status"] != "ok"]
    return 1 if (bad and args.require_all) else 0


if __name__ == "__main__":
    sys.exit(main())
