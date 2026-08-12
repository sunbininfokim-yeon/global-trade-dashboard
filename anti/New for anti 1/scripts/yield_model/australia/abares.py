"""
Read state crop area and production from the ABARES Australian Crop Report.

The state workbook is deliberately parsed with the Python standard library.
The project runtime does not otherwise require openpyxl, and adding a large
spreadsheet dependency just for two rows in each state sheet would make the
weekly pipeline more fragile than it needs to be.

ABARES names seasons by Australian financial year.  That label has two crop-
specific meanings which must not be collapsed:

* winter wheat in ``2025-26`` is harvested in late 2025 -> model year 2025;
* summer cotton in ``2025-26`` is harvested in 2026      -> model year 2026.

Rows marked ``f`` are ABARES forecasts and are never used as training labels.
Rows marked ``s`` are current ABARES estimates; they are kept but their status
is carried into the training table because they can be revised later.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
import zipfile
from xml.etree import ElementTree as ET

import pandas as pd


HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
CACHE_FILE = os.path.join(CACHE, "abares_state_crop_data.xlsx")

LANDING_URL = (
    "https://www.agriculture.gov.au/abares/research-topics/"
    "agricultural-outlook/australian-crop-report"
)
UA = {"User-Agent": "yield-model/1.0 (ABARES public-data client)"}
CACHE_DAYS = 30


def _fetch(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _links(page: bytes, base: str) -> list[tuple[str, str]]:
    text = page.decode("utf-8", "replace")
    found = []
    for href, label in re.findall(
            r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
            text, flags=re.I | re.S):
        clean_label = re.sub(r"<[^>]+>", " ", html.unescape(label))
        clean_label = " ".join(clean_label.split())
        found.append((urllib.parse.urljoin(base, html.unescape(href)), clean_label))
    return found


def resolve_state_workbook_url() -> str:
    """Resolve the newest public state-data workbook without pinning an asset id."""
    override = os.environ.get("ABARES_STATE_XLSX_URL")
    if override:
        return override

    landing = _fetch(LANDING_URL)
    links = _links(landing, LANDING_URL)

    # Some page versions expose the workbook directly.
    for url, label in links:
        if url.lower().endswith(".xlsx") and "state" in (url + label).lower():
            return url

    # Others point to the latest quarterly release, which contains the asset.
    release_candidates = [
        url for url, label in links
        if "australian crop report" in label.lower()
        and re.search(r"/(march|june|september|december)-\d{4}", url, re.I)
    ]
    if not release_candidates:
        raise RuntimeError("ABARES landing page did not expose a quarterly release")

    release_url = release_candidates[0]
    release_links = _links(_fetch(release_url), release_url)
    for url, label in release_links:
        marker = (url + " " + label).lower()
        if url.lower().endswith(".xlsx") and "state" in marker:
            return url
    raise RuntimeError("ABARES release page did not expose a state-data workbook")


def workbook_path(force: bool = False) -> str:
    """Return a local workbook, downloading/caching it when necessary."""
    local = os.environ.get("ABARES_STATE_XLSX")
    if local:
        if not os.path.exists(local):
            raise FileNotFoundError(f"ABARES_STATE_XLSX does not exist: {local}")
        return local

    if (not force and os.path.exists(CACHE_FILE)
            and time.time() - os.path.getmtime(CACHE_FILE) < CACHE_DAYS * 86400):
        return CACHE_FILE

    os.makedirs(CACHE, exist_ok=True)
    url = resolve_state_workbook_url()
    tmp = CACHE_FILE + ".part"
    with open(tmp, "wb") as handle:
        handle.write(_fetch(url, timeout=180))
    if not zipfile.is_zipfile(tmp):
        os.remove(tmp)
        raise RuntimeError(f"ABARES response was not an xlsx workbook: {url}")
    shutil.move(tmp, CACHE_FILE)
    return CACHE_FILE


def _column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref.upper())
    if not letters:
        raise ValueError(f"invalid xlsx cell reference: {cell_ref}")
    value = 0
    for char in letters.group(0):
        value = value * 26 + ord(char) - ord("A") + 1
    return value - 1


def _shared_strings(book: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values = []
    for item in root:
        values.append("".join(node.text or "" for node in item.iter()
                              if node.tag.endswith("}t")))
    return values


def _sheet_path(book: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    rel_id = None
    for sheet in workbook.iter():
        if sheet.tag.endswith("}sheet") and sheet.attrib.get("name") == sheet_name:
            rel_id = next((v for k, v in sheet.attrib.items()
                           if k.endswith("}id")), None)
            break
    if not rel_id:
        raise KeyError(f"sheet not found in ABARES workbook: {sheet_name}")

    relationships = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    target = None
    for rel in relationships:
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib.get("Target")
            break
    if not target:
        raise KeyError(f"worksheet relationship missing: {sheet_name}")
    target = target.lstrip("/")
    return target if target.startswith("xl/") else "xl/" + target


def read_sheet(path: str, sheet_name: str) -> list[list[object]]:
    """Return an xlsx worksheet as a rectangular list of Python values."""
    with zipfile.ZipFile(path) as book:
        shared = _shared_strings(book)
        root = ET.fromstring(book.read(_sheet_path(book, sheet_name)))

    rows: list[list[object]] = []
    for row in root.iter():
        if not row.tag.endswith("}row"):
            continue
        values: dict[int, object] = {}
        for cell in row:
            if not cell.tag.endswith("}c"):
                continue
            col = _column_index(cell.attrib["r"])
            kind = cell.attrib.get("t")
            value_node = next((n for n in cell if n.tag.endswith("}v")), None)
            if kind == "inlineStr":
                value = "".join(n.text or "" for n in cell.iter()
                                if n.tag.endswith("}t"))
            elif value_node is None:
                value = None
            elif kind == "s":
                value = shared[int(value_node.text)]
            elif kind in {"str", "e", "b"}:
                value = value_node.text
            else:
                try:
                    value = float(value_node.text)
                except (TypeError, ValueError):
                    value = value_node.text
            values[col] = value
        if values:
            width = max(values) + 1
            rows.append([values.get(i) for i in range(width)])
        else:
            rows.append([])
    width = max((len(row) for row in rows), default=0)
    return [row + [None] * (width - len(row)) for row in rows]


def _season(label: object, harvest_rule: str) -> tuple[int, str] | None:
    if not isinstance(label, str):
        return None
    match = re.search(r"(\d{4})\s*[–-]\s*(\d{2})(?:\s+([sf]))?", label.strip(), re.I)
    if not match:
        return None
    first = int(match.group(1))
    second = (first // 100) * 100 + int(match.group(2))
    if second < first:
        second += 100
    year = first if harvest_rule == "winter" else second
    return year, (match.group(3) or "actual").lower()


def state_crop_series(state_sheet: str, crop_label: str, harvest_rule: str,
                      path: str | None = None,
                      include_forecast: bool = False) -> pd.DataFrame:
    """Extract area, production and derived yield for one state-crop series."""
    path = path or workbook_path()
    rows = read_sheet(path, state_sheet)

    header_i = next((i for i, row in enumerate(rows)
                     if len(row) > 2 and str(row[2]).strip() == "Crops"), None)
    if header_i is None:
        raise ValueError(f"season header not found in sheet {state_sheet}")

    crop_i = next((i for i, row in enumerate(rows)
                   if len(row) > 2
                   and str(row[2]).strip().lower() == crop_label.lower()), None)
    if crop_i is None:
        raise ValueError(f"crop {crop_label!r} not found in sheet {state_sheet}")
    if crop_i + 2 >= len(rows):
        raise ValueError(f"area/production rows missing after {crop_label}")
    if str(rows[crop_i + 1][2]).strip() != "Area" \
            or str(rows[crop_i + 2][2]).strip() != "Production":
        raise ValueError(f"unexpected ABARES row layout after {crop_label}")

    out = []
    for col, label in enumerate(rows[header_i]):
        parsed = _season(label, harvest_rule)
        if not parsed or col >= len(rows[crop_i + 2]):
            continue
        year, status = parsed
        if status == "f" and not include_forecast:
            continue
        try:
            area_thousand_ha = float(rows[crop_i + 1][col])
            production_kt = float(rows[crop_i + 2][col])
        except (TypeError, ValueError):
            continue
        if area_thousand_ha <= 0:
            continue
        out.append({
            "year": year,
            "area_ha": area_thousand_ha * 1000.0,
            "production_t": production_kt * 1000.0,
            "yield_kg_ha": production_kt / area_thousand_ha * 1000.0,
            "target_status": ("forecast" if status == "f" else
                              "estimate" if status == "s" else "actual"),
            "source_season": str(label),
        })
    if not out:
        raise ValueError(f"no usable ABARES observations for {state_sheet}/{crop_label}")
    return pd.DataFrame(out).sort_values("year").reset_index(drop=True)
