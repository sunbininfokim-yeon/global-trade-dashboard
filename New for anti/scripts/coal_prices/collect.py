#!/usr/bin/env python3
"""Coal reference prices. Standard library only; nothing is estimated.

Two official, free series, kept apart because they are different things:

  HBA     Indonesia's government reference price (Harga Batubara Acuan), set by
          a ministerial decision twice a month. The decision itself (a PDF on
          the ministry's legal portal, JDIH) carries the four grades (HBA 6,322
          GAR; HBA I 5,300; HBA II 4,100; HBA III 3,400) in its annex II, which
          is what is read here. The ministry's news archive was tried first: it
          has no search or feed and carried only some announcements.
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

# The ministry's legal portal: its decisions (Keputusan Menteri), newest first, 5 a page.
JDIH_LIST = "https://jdih.esdm.go.id/dokumen/peraturan?DokumenSearch%5Bjenis_peraturan%5D=176"
HBA_KEEP_PERIODS = 48   # two years of half-months
HBA_PAUSE = 1.0
HBA_MAX_PAGES = 8       # 5 decisions a page, an HBA decision about every two weeks
HBA_FIRST_RUN_DECREES = 4

# Stale thresholds the panel applies (days since the data's own end date).
HBA_STALE_DAYS = 24
WB_STALE_DAYS = 80


def note(msg: str) -> None:
    """Diagnostics for the CI log only; never written to the public snapshot."""
    print(msg, file=sys.stderr)


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


def read_xlsx_sheet(blob: bytes, sheet_name: str, prefix: bool = False) -> List[List[Any]]:
    """Rows of one sheet as lists (None for blanks). Numbers come back as float.

    `prefix` matches a sheet whose name merely starts with `sheet_name`."""
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
    sheets_el = wb.find("m:sheets", _NS)
    for sh in (sheets_el if sheets_el is not None else []):
        name = (sh.get("name") or "").strip().lower()
        if name == sheet_name.lower() or (prefix and name.startswith(sheet_name.lower())):
            rid = sh.get(f"{{{_NS['r']}}}id")
            break
    if rid is None:
        note("xlsx sheets: " + repr([sh.get("name") for sh in (sheets_el if sheets_el is not None else [])]))
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

def header_name(cell: Any) -> str:
    """A column title without its footnote marks: 'Coal, South African **' -> 'coal, south african'."""
    return re.sub(r"[\s*\u2020\u2021\u00b9\u00b2\u00b3]+$", "", str(cell)).strip().lower() if isinstance(cell, str) else ""


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
        names = {header_name(c) for c in row}
        if all(col.lower() in names for _, col, _ in WB_SERIES):
            header_at = i
            break
    if header_at is None:
        note(f"monthly sheet: {len(rows)} rows")
        for i, row in enumerate(rows[:12]):
            note(f"  row {i}: {[c for c in row if c is not None][:8]!r}")
        for i, row in enumerate(rows[:40]):
            for j, c in enumerate(row):
                if isinstance(c, str) and "coal" in c.lower():
                    note(f"  coal cell r{i} c{j}: {c!r}")
        raise SourceError("coal_columns_missing")
    header = rows[header_at]
    cols = {}
    for sid, col, _ in WB_SERIES:
        cols[sid] = next(j for j, c in enumerate(header) if header_name(c) == col.lower())
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


def worldbank_definitions(blob: bytes) -> Dict[str, str]:
    """The workbook's own wording for each coal series, if its Description sheet has one.

    Shown verbatim next to the price; nothing is written here from memory."""
    try:
        rows = read_xlsx_sheet(blob, "Description", prefix=True)
    except SourceError:
        return {}
    out: Dict[str, str] = {}
    for row in rows:
        texts = [c.strip() for c in row if isinstance(c, str) and c.strip()]
        for sid, col, _ in WB_SERIES:
            if texts and header_name(texts[0]).startswith(col.lower()) and len(texts) > 1:
                out[sid] = " ".join(texts[1:])[:400]
    note(f"worldbank definitions: {out!r}")
    return out


def fetch_worldbank(get: Callable[[str], bytes] = get_bytes) -> Dict[str, Any]:
    page = get(WB_PAGE).decode("utf-8", "replace")
    m = WB_FILE_RE.search(page)
    if not m:
        raise SourceError("workbook_link_missing")
    file_url = m.group(0)
    blob = get(file_url)
    parsed = parse_worldbank_monthly(read_xlsx_sheet(blob, WB_SHEET))
    defs = worldbank_definitions(blob)
    for series in parsed["series"]:
        if series["id"] in defs:
            series["definition"] = defs[series["id"]]
    latest = max(s["points"][-1][0] for s in parsed["series"])
    return {"status": "ok", "source": "World Bank Commodity Price Data (The Pink Sheet)", "license": "CC BY 4.0",
            "source_url": WB_PAGE, "file_url": file_url, "latest_period": latest, **parsed}


# ---- Indonesia HBA (ministerial decision, annex II) ------------------------------------

_MONTHS_ID = {"januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6, "juli": 7,
              "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12}
_HBA_ORDER = ("HBA", "HBA I", "HBA II", "HBA III")
_HBA_GARS = {"HBA": 6322, "HBA I": 5300, "HBA II": 4100, "HBA III": 3400}
# The annex heading names the period; the decision's own "mulai berlaku" date confirms it.
_DECREE_PERIOD_RE = re.compile(r"HARGA\s+BATUBARA\s+ACUAN\s+PERIODE\s+(PERTAMA|KEDUA)\s+BULAN\s+([A-Z]+)\s+TAHUN\s+(\d{4})", re.I)
_DECREE_NUMBER_RE = re.compile(r"NOMOR\s*:?\s*(\d+\.K/MB\.\d+/MEM\.B/\d{4})", re.I)
_EFFECTIVE_RE = re.compile(r"mulai\s+berlaku\s+pada\s+tanggal\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.I)
_DECREE_GRADE_RE = re.compile(r"Batubara(?:\s+(III|II|I))?\s*\(\s*([\d.]+)\s*GAR\s*\)\s*USD\s*/\s*ton\s*([\d.,]+)", re.I)
_ANCHOR_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def id_number(text: str, decimals: bool) -> float:
    """Indonesian digits: '.' groups thousands and ',' is the decimal mark."""
    s = text.strip()
    s = s.replace(".", "").replace(",", ".") if decimals else s.replace(".", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        raise SourceError("bad_number") from None


def _last_day(year: int, month: int) -> int:
    return (date(year + (month == 12), month % 12 + 1, 1) - date(year, month, 1)).days


def parse_hba_decree(text: str, url: str) -> Dict[str, Any]:
    """One half-month's HBA grades from the text of a decision's annex II.

    Strict by design: the four grades must be the four known calorific classes,
    in falling order of price. The PDF is a scan with a text layer, and a
    misread digit is far worse than a missing row, so anything that does not
    look exactly like the annex is refused and named."""
    m = _DECREE_PERIOD_RE.search(text)
    if not m or m.group(2).lower() not in _MONTHS_ID:
        raise SourceError("period_unreadable")
    month, year = _MONTHS_ID[m.group(2).lower()], int(m.group(3))
    first_half = m.group(1).lower() == "pertama"
    start = date(year, month, 1 if first_half else 15)
    end = date(year, month, 14 if first_half else _last_day(year, month))
    eff = _EFFECTIVE_RE.search(text)
    if eff and eff.group(2).lower() in _MONTHS_ID:
        if (int(eff.group(3)), _MONTHS_ID[eff.group(2).lower()], int(eff.group(1))) != (start.year, start.month, start.day):
            raise SourceError("period_mismatch")

    grades: Dict[str, Dict[str, Any]] = {}
    for g in _DECREE_GRADE_RE.finditer(text):
        name = "HBA" + (f" {g.group(1).upper()}" if g.group(1) else "")
        if name in grades:
            continue
        grades[name] = {"name": name, "gar": int(id_number(g.group(2), False)), "usd_per_t": id_number(g.group(3), True)}
    if set(grades) != set(_HBA_ORDER):
        raise SourceError("grades_missing")
    ordered = [grades[n] for n in _HBA_ORDER]
    prices = [g["usd_per_t"] for g in ordered]
    if any(g["gar"] != _HBA_GARS[g["name"]] for g in ordered):
        raise SourceError("grades_changed")
    if not (all(5 < p < 600 for p in prices) and prices == sorted(prices, reverse=True)):
        raise SourceError("grades_inconsistent")
    out = {"start": start.isoformat(), "end": end.isoformat(), "grades": ordered, "url": url}
    num = _DECREE_NUMBER_RE.search(text)
    if num:
        out["decree"] = num.group(1)
    return out


def pdf_text(blob: bytes) -> str:
    """The text layer of a PDF (needs pypdf, which the workflow installs)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SourceError("pypdf_missing") from None
    try:
        reader = PdfReader(io.BytesIO(blob))
        return " ".join((page.extract_text() or "") for page in reader.pages)
    except Exception:  # noqa: BLE001 -- a broken PDF is an unreadable decision, nothing more
        raise SourceError("pdf_unreadable") from None


def hba_decree_links(html: str, base: str) -> List[Tuple[str, str]]:
    """(pdf url, title) of the HBA decisions on one list page.

    Each row is a title link (dokumen/view) followed by a 'Dokumen' link
    (dokumen/download); the pair is what identifies a decision's PDF."""
    out: List[Tuple[str, str]] = []
    title = ""
    for href, inner in _ANCHOR_RE.findall(html):
        url = urljoin(base, unescape(href))
        text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", inner))).strip()
        if "/dokumen/view" in url:
            title = text
        elif "/dokumen/download" in url and title:
            if re.search(r"harga\s+batubara\s+acuan", title, re.I):
                out.append((url, title))
            title = ""
    return out


def merge_periods(old: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """History accumulates: the portal's list only reaches back a few weeks."""
    by_start = {p["start"]: p for p in old}
    for p in new:
        by_start[p["start"]] = p
    return [by_start[k] for k in sorted(by_start)][-HBA_KEEP_PERIODS:]


def with_changes(periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Each grade's move since the previous half-month, computed here from two
    published values (never copied from a news article)."""
    prev = None
    for p in periods:
        if prev is not None and (date.fromisoformat(p["start"]) - date.fromisoformat(prev["end"])).days <= 3:
            before = {g["name"]: g["usd_per_t"] for g in prev["grades"]}
            for g in p["grades"]:
                if "change_pct" not in g and before.get(g["name"]):
                    g["change_pct"] = round((g["usd_per_t"] / before[g["name"]] - 1) * 100, 2)
        prev = p
    return periods


def fetch_hba(previous: Optional[Dict[str, Any]] = None, get: Callable[[str], bytes] = get_bytes,
              extract: Callable[[bytes], str] = pdf_text, pause: float = HBA_PAUSE,
              max_pages: int = HBA_MAX_PAGES) -> Dict[str, Any]:
    """New HBA decisions, found by paging the ministry's decision list.

    Newest first; paging stops at the first decision already held. A decision
    appears on the portal a few days after it takes effect, so the newest
    half-month can be missing for a while -- the panel says so."""
    prior = (previous or {}).get("periods", [])
    known = {p["url"] for p in prior}
    links: List[Tuple[str, str]] = []
    errors: List[str] = []
    for n in range(1, max_pages + 1):
        if n > 1:
            time.sleep(pause)
        page = JDIH_LIST if n == 1 else f"{JDIH_LIST}&page={n}"
        try:
            page_links = hba_decree_links(get(page).decode("utf-8", "replace"), page)
        except SourceError as exc:
            if n == 1:
                raise
            errors.append(f"page{n}:{exc}")
            break
        links += [l for l in page_links if l[0] not in {u for u, _ in links}]
        if any(u in known for u, _ in page_links):
            break
        if not known and len(links) >= HBA_FIRST_RUN_DECREES:
            break

    found: List[Dict[str, Any]] = []
    for url, title in links:
        if url in known:
            continue
        time.sleep(pause)
        try:
            found.append(parse_hba_decree(extract(get(url)), url))
        except SourceError as exc:
            errors.append(f"{url.rsplit('=', 1)[-1][:40]}:{exc}")
    periods = with_changes(merge_periods(prior, found))
    if not periods:
        raise SourceError(errors[-1].split(":")[-1] if errors else "no_decisions_found")
    out = {"status": "ok", "source": "인도네시아 에너지광물자원부(ESDM) 장관결정문 · JDIH", "source_url": JDIH_LIST,
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
