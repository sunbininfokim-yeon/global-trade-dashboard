"""EIA Short-Term Energy Outlook workbooks (keyless): the current STEO_m.xlsx and the December archives.

Each workbook carries 72 months (four years of history, two of forecast). Rows are found by their series
codes in the first column, which have stayed the same since 2007 even where the table moved (OPEC spare
capacity, cops_opec, was table 3c until 2022 and is 3d now), so every numbered table is read and a code's
first appearance wins; month columns come from the year row above the month-name row.
"""

from __future__ import annotations

import io
import re
import subprocess
from typing import Any

CURRENT = "https://www.eia.gov/outlooks/steo/xls/STEO_m.xlsx"
ARCHIVE = "https://www.eia.gov/outlooks/steo/archives/dec{yy:02d}_base.{ext}"
CODES = {"pasc_oecd_t3": "oecd_stocks_mb", "patc_oecd": "oecd_demand_mbd", "patc_world": "world_demand_mbd",
         "papr_world": "world_supply_mbd", "brepuus": "brent_steo", "t3_stchange_world": "world_stock_draw_mbd",
         "patc_ch": "china_demand_mbd", "papr_opec": "opec_supply_mbd", "papr_nonopec": "nonopec_supply_mbd",
         "cops_opec": "opec_spare_mbd"}
# What a December vintage forecast for the following year, kept for the back-test.
VINTAGE_FIELDS = ("oecd_stocks_mb", "oecd_demand_mbd", "opec_spare_mbd", "brent_steo")
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def fetch(url: str, timeout: int = 120) -> bytes:
    proc = subprocess.run(["curl", "-sS", "-L", "-m", str(timeout), "-A", "Mozilla/5.0", url], check=False, capture_output=True)
    if proc.returncode != 0 or len(proc.stdout) < 10000:
        raise RuntimeError(f"{url}: curl rc={proc.returncode}, {len(proc.stdout)} bytes")
    return proc.stdout


def _sheets(data: bytes, xls: bool):
    """(name, rows) for every numbered table sheet ('2tab', '3atab', ...), in workbook order."""
    if xls:
        import xlrd
        wb = xlrd.open_workbook(file_contents=data)
        for n in wb.sheet_names():
            if re.match(r"\d", n.strip()):
                ws = wb.sheet_by_name(n)
                yield n, [ws.row_values(i) for i in range(ws.nrows)]
        return
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    for n in wb.sheetnames:
        if re.match(r"\d", n.strip()):
            yield n, [list(r) for r in wb[n].iter_rows(values_only=True)]


def _rows(data: bytes, xls: bool, sheet: str) -> list[list[Any]]:
    if xls:
        import xlrd
        wb = xlrd.open_workbook(file_contents=data)
        name = next(n for n in wb.sheet_names() if n.lower().replace(" ", "") == sheet)
        ws = wb.sheet_by_name(name)
        return [ws.row_values(i) for i in range(ws.nrows)]
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    name = next(n for n in wb.sheetnames if n.lower().replace(" ", "") == sheet)
    return [list(r) for r in wb[name].iter_rows(values_only=True)]


def vintage_date(data: bytes, xls: bool) -> str | None:
    """'Thursday, November 5, 2026' in table 3a's header -> '2026-11-05'."""
    from datetime import datetime
    for r in _rows(data, xls, "3atab")[:6]:
        for c in r:
            if isinstance(c, str):
                m = re.search(r"([A-Z][a-z]+ \d{1,2}, 20\d\d)", c)
                if m:
                    return datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
    return None


def parse(data: bytes, xls: bool = False) -> dict[str, dict[str, float]]:
    """{field: {'YYYY-MM': value}} for the CODES rows (a code's first appearance across the tables)."""
    out: dict[str, dict[str, float]] = {}
    for _, rows in _sheets(data, xls):
        mi = next((i for i, r in enumerate(rows[:12])
                   if sum(1 for c in r if isinstance(c, str) and c.strip().lower()[:3] in MON) >= 12), None)
        if mi is None or mi == 0:
            continue
        cols: dict[int, str] = {}
        y = None
        for j, (yc, mc) in enumerate(zip(rows[mi - 1], rows[mi])):
            if isinstance(yc, (int, float)) and 1990 < yc < 2100:
                y = int(yc)
            elif isinstance(yc, str) and re.fullmatch(r"\s*(19|20)\d\d\s*", yc):
                y = int(yc)
            if y and isinstance(mc, str) and mc.strip().lower()[:3] in MON:
                cols[j] = f"{y}-{MON[mc.strip().lower()[:3]]:02d}"
        for r in rows:
            field = CODES.get(str((r[0] if r else "") or "").strip().lower())
            if field and field not in out:
                out[field] = {cols[j]: float(r[j]) for j in cols if j < len(r) and isinstance(r[j], (int, float))}
    return out


def archive(yy: int, local_dir: str | None = None) -> dict[str, dict[str, float]]:
    xls = yy <= 12
    ext = "xls" if xls else "xlsx"
    if local_dir:
        from pathlib import Path
        f = Path(local_dir) / f"dec{yy:02d}.{ext}"
        if f.exists():
            return parse(f.read_bytes(), xls)
    return parse(fetch(ARCHIVE.format(yy=yy, ext=ext)), xls)


def history_from_archives(first: int = 2007, last: int = 2022, vintages_to: int = 2025,
                          local_dir: str | None = None) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, dict[str, float]]]]:
    """History: year Y from the December Y+1 vintage (Y fully reported and revised by then); before the
    first vintage's year, everything it carries. Vintages: what each December vintage (up to `vintages_to`)
    said about itself and the following year -- the latest history month and twelve forecast months, the
    inputs a forecast made that December would have had."""
    hist: dict[str, dict[str, float]] = {}
    vint: dict[str, dict[str, dict[str, float]]] = {}
    for yy in range(first % 100, max(last, vintages_to) % 100 + 1):
        d = archive(yy, local_dir)
        y0 = 2000 + yy
        if y0 <= last:
            for field, series in d.items():
                for k, v in series.items():
                    y = int(k[:4])
                    if y == y0 - 1 or (yy == first % 100 and y < y0 - 1):
                        hist.setdefault(field, {})[k] = v
        vint[f"{y0}-12"] = {f: {k: v for k, v in d.get(f, {}).items() if f"{y0}-01" <= k <= f"{y0 + 1}-12"}
                           for f in VINTAGE_FIELDS}
    return {f: dict(sorted(s.items())) for f, s in hist.items()}, vint
