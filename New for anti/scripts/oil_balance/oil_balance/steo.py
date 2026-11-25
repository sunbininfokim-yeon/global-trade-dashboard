"""EIA Short-Term Energy Outlook workbooks (keyless): the current STEO_m.xlsx and the December archives.

Each workbook carries 72 months (four years of history, two of forecast). The world balance (table 3a)
and Brent (table 2) rows are found by their series codes in the first column, which have stayed the same
since 2007; month columns come from the year row above the month-name row.
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
         "patc_ch": "china_demand_mbd", "papr_opec": "opec_supply_mbd", "papr_nonopec": "nonopec_supply_mbd"}
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def fetch(url: str, timeout: int = 120) -> bytes:
    proc = subprocess.run(["curl", "-sS", "-L", "-m", str(timeout), "-A", "Mozilla/5.0", url], check=False, capture_output=True)
    if proc.returncode != 0 or len(proc.stdout) < 10000:
        raise RuntimeError(f"{url}: curl rc={proc.returncode}, {len(proc.stdout)} bytes")
    return proc.stdout


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
    """{field: {'YYYY-MM': value}} for the CODES rows."""
    out: dict[str, dict[str, float]] = {}
    for sheet in ("3atab", "2tab"):
        rows = _rows(data, xls, sheet)
        mi = next(i for i, r in enumerate(rows[:12])
                  if sum(1 for c in r if isinstance(c, str) and c.strip().lower()[:3] in MON) >= 12)
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
            field = CODES.get(str(r[0] or "").strip().lower())
            if field:
                out.setdefault(field, {}).update(
                    {cols[j]: float(r[j]) for j in cols if j < len(r) and isinstance(r[j], (int, float))})
    return out


def history_from_archives(first: int = 2007, last: int = 2022) -> dict[str, dict[str, float]]:
    """Year Y from the December Y+1 vintage (Y fully reported and revised by then); before the first
    vintage's year, everything it carries."""
    out: dict[str, dict[str, float]] = {}
    for yy in range(first % 100, last % 100 + 1):
        xls = yy <= 12
        d = parse(fetch(ARCHIVE.format(yy=yy, ext="xls" if xls else "xlsx")), xls)
        for field, series in d.items():
            for k, v in series.items():
                y = int(k[:4])
                if y == 2000 + yy - 1 or (yy == first % 100 and y < 2000 + yy - 1):
                    out.setdefault(field, {})[k] = v
    return {f: dict(sorted(s.items())) for f, s in out.items()}
