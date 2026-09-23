"""Chile Cochilco monthly copper physical exports (HTML bulletin table 21).

xlsx links on site return 404; parse public bulletin HTML instead.
Unit: thousand metric tons copper content (kMT). TOTAL column = refined+blister+bulk.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

MONTH_MAP = {
    "ENE": "01", "JAN": "01", "FEB": "02", "MAR": "03", "ABR": "04", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AGO": "08", "AUG": "08", "SEP": "09",
    "OCT": "10", "NOV": "11", "DIC": "12", "DEC": "12",
}


def _fetch(url: str, timeout: int = 45) -> str:
    req = Request(url, headers={"User-Agent": "commodity-trade-cochilco/1.0"})
    return urlopen(req, timeout=timeout).read().decode("latin-1", errors="replace")


def _cells(html: str) -> list[str]:
    out = []
    for c in re.findall(r"<td[^>]*>(.*?)</td>", html, re.I | re.S):
        t = re.sub(r"<[^>]+>", " ", c)
        t = re.sub(r"&[a-zA-Z]+;", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        out.append(t)
    return out


def _parse_eu_numbers(blob: str) -> list[float]:
    """'438,6 498,9' or '525,2 453,2' -> floats (European decimal comma)."""
    vals = []
    for tok in blob.replace("\xa0", " ").split():
        tok = tok.strip().replace(".", "").replace(",", ".")
        if not tok or tok in ("-", "—"):
            continue
        try:
            vals.append(float(tok))
        except ValueError:
            continue
    return vals


def _month_labels_from_header(header: str) -> list[str]:
    """ENE/JAN 2025 FEB MAR ... -> list of MM for that year context.

    Header starts with ENE/JAN YYYY then month abbreviations without year.
    """
    m = re.search(r"(ENE|JAN)\s*/?\s*(JAN|ENE)?\s*(\d{4})", header, re.I)
    if not m:
        return []
    year = m.group(3)
    # collect month tokens in order
    tokens = re.findall(
        r"\b(ENE|JAN|FEB|MAR|ABR|APR|MAY|JUN|JUL|AGO|AUG|SEP|OCT|NOV|DIC|DEC)\b",
        header,
        re.I,
    )
    # first is ENE/JAN pair sometimes duplicated — normalize
    months = []
    seen_first = False
    for t in tokens:
        key = t.upper()[:3]
        if key in ("ENE", "JAN"):
            if seen_first and months:
                continue
            seen_first = True
            mm = "01"
        else:
            # map 3-letter
            mm = None
            for k, v in MONTH_MAP.items():
                if key.startswith(k[:3]) or k.startswith(key):
                    mm = v
                    break
            if mm is None:
                continue
        months.append(f"{year}-{mm}")
    # unique preserve order, max 12
    out = []
    for x in months:
        if x not in out:
            out.append(x)
    return out[:12]


def parse_bulletin(html: str) -> list[dict]:
    cells = _cells(html)
    points = []
    i = 0
    while i < len(cells):
        c = cells[i]
        if re.search(r"ENE\s*/\s*JAN\s+\d{4}", c, re.I) or re.search(
            r"ENE/JAN\s+\d{4}", c, re.I
        ):
            if "ENE-FEB" in c.upper() or "JAN-FEB" in c.upper():
                i += 1
                continue
            labels = _month_labels_from_header(c)
            # next 4 numeric rows: refined, blister, bulk, TOTAL (then mo)
            # find TOTAL row: 4th numeric blob after header
            numeric_rows = []
            j = i + 1
            while j < len(cells) and len(numeric_rows) < 5:
                if re.search(r"\d+,\d+", cells[j]) or re.search(
                    r"\d+\s+\d+", cells[j]
                ):
                    nums = _parse_eu_numbers(cells[j])
                    if len(nums) >= 1:
                        numeric_rows.append(nums)
                j += 1
            if len(numeric_rows) >= 4 and labels:
                total = numeric_rows[3]  # TOTAL copper kMT
                for k, val in enumerate(total):
                    if k >= len(labels):
                        break
                    points.append(
                        {
                            "month": labels[k],
                            "value": val,
                            "unit": "kMT_cu_content",
                            "product_code": "copper_total_shipments",
                            "source": "cochilco_bulletin",
                            "hs_bridge": "2603",
                            "hs_relation": "alias_physical_copper",
                            "code_system": "COCHILCO",
                        }
                    )
            i = j
            continue
        i += 1
    # de-dupe by month keep last
    by_m = {p["month"]: p for p in points}
    return [by_m[m] for m in sorted(by_m.keys())]


def load_copper_exports(*, cache_dir: Path | None = None) -> dict[str, Any]:
    # March 2026 bulletin has 2023-2026 history
    url = "https://boletin.cochilco.cl/productos/boletin.asp?anio=2026&mes=03&tabla=tabla26"
    try:
        html = _fetch(url)
    except Exception as exc:
        return {"available": False, "reason": str(exc), "series": {}}
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "cochilco_tabla26.html").write_text(html, encoding="utf-8")
    pts = parse_bulletin(html)
    return {
        "available": bool(pts),
        "source": "cochilco_bulletin",
        "source_url": url,
        "series": {"copper": {"CHL": pts}},
        "note_ko": "칠레 Cochilco 월보 표21 구리 선적 TOTAL(천톤 Cu). xlsx 404이라 HTML 파싱. HS2603 별칭.",
    }
