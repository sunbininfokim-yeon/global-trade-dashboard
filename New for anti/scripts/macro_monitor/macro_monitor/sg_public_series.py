"""Singapore: SingStat Table Builder (keyless; needs a User-Agent *and* Accept: application/json, or it
answers 403 -- see export_public_series.fetch_singstat).

Cards (table / row in brackets):
  cpi_yoy        CPI all items, YoY from the index (M213751 / 1)                 monthly
  mas_core_infl  MAS core inflation measure, YoY from the index (M213891 / 1)    monthly
  gdp_yoy        real GDP (chained 2015$), YoY from the level (M014811 / 1)      quarterly
  gdp_qoq        real GDP, seasonally adjusted, QoQ from the level (M014812 / 1) quarterly
  m2_yoy         money supply M2, end of period, YoY, each table on its own: M920281 / 2 to 2021-06,
                 M701111 / 1.1 from 2022-07 (a year into the new table)            monthly
  current_account BOP current account balance, S$ (M060171 / 1.1)              quarterly
  sgs_2y/sgs_10y SGS 2- and 10-year yields, end of month (M700071 / 13, 15)     monthly
  sg_private_home URA private residential price index (M212261 / 1)             quarterly
M2 changed definition on 2021-07-01 (MAS Notices 610/1003: from the DBU book, mostly SGD, to SGD-only
activity; the first new-basis month is 2.7% below the last old one). A year-on-year change that compares
a new-basis month with an old-basis one would mix the two, so 2021-07..2022-06 is left empty, and "M2
against 2019-12" is not published here at all: its base is on the old basis.

Not here, and why: SORA and the SORA-SOFR spread (MAS publishes SORA through its API gateway, which
needs a registered key -- 401 without one -- or an ASP.NET page), the S$NEER level, slope and band
(MAS does not publish them as numbers), MAS/total liquidity and FX deposits (no table found), the
S-REIT index and the SIPMM PMI (no free source), CDS (paid). STI is a Yahoo series in live_catalog.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from . import export_public_series as eps
from . import jp_public_series as jps
from . import kr_public_series as krs
from . import us_public_series as ups
from .us_public_series import Points, Spec

PAGE = "https://tablebuilder.singstat.gov.sg/table/TS/{table}"
_MONTHS = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

ups._FORMATS.update({
    "pct2": lambda v: f"{v:.2f}%",
    "bn1sgd": lambda v: f"S${v:,.1f}B",
    "idx1": lambda v: f"{v:,.1f}",
})


def period_key(key: str) -> str | None:
    """'2026 Aug' -> 2026-08-01, '2026 2Q' -> 2026-04-01, anything else (an annual '2026') -> None."""
    parts = str(key).split()
    if len(parts) != 2 or not parts[0].isdigit():
        return None
    y, p = int(parts[0]), parts[1]
    if p in _MONTHS:
        return f"{y:04d}-{_MONTHS[p]:02d}-01"
    m = re.fullmatch(r"([1-4])Q", p)
    if m:
        return f"{y:04d}-{(int(m.group(1)) - 1) * 3 + 1:02d}-01"
    return None


def parse_row(doc: dict[str, Any], row_no: str) -> tuple[Points, str | None]:
    rows = (doc.get("Data") or {}).get("row") or []
    row = next((r for r in rows if str(r.get("seriesNo")) == row_no), None)
    if row is None:
        raise ValueError(f"SingStat answer has no row {row_no!r}")
    out: Points = []
    for c in row.get("columns") or []:
        d = period_key(c.get("key", ""))
        if not d:
            continue
        try:
            out.append((d, float(str(c["value"]).replace(",", ""))))
        except (ValueError, KeyError):
            continue
    if not out:
        raise ValueError(f"SingStat row {row_no!r} has no observations")
    return sorted(out), row.get("uoM")


def fetch_row(table: str, row_no: str) -> tuple[Points, str | None]:
    import json
    import urllib.parse
    import urllib.request

    url = eps.SINGSTAT.format(table=urllib.parse.quote(table), row=urllib.parse.quote(row_no, safe=","))
    req = urllib.request.Request(url, headers={"User-Agent": eps.UA, "Accept": "application/json"})
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return parse_row(json.loads(resp.read().decode("utf-8")), row_no)
        except Exception as exc:  # noqa: BLE001
            last = exc
            import time
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"SingStat {table}/{row_no}: {last}")


def splice(old: Points, new: Points) -> Points:
    """Two pieces of one series: the old one up to where the new one starts."""
    start = new[0][0]
    return sorted([p for p in old if p[0] < start] + new)


@dataclass(frozen=True)
class SgSpec:
    spec: Spec
    gap_months: int = 1


def _s(id_: str, cadence: str, unit: str, fmt: str, label: str, note: str, tables: tuple[str, ...]) -> Spec:
    return Spec(id_, cadence, unit, fmt, note, "singstat:" + "+".join(tables), tuple(PAGE.format(table=t) for t in tables),
                cadence, label_ko=label)


SPECS: dict[str, SgSpec] = {s.spec.id: s for s in [
    SgSpec(_s("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
              "소비자물가지수(2024=100, 전 품목) 전년 동월 대비입니다. 통계청 Table Builder M213751.", ("M213751",))),
    SgSpec(_s("mas_core_infl", "monthly", "%", "pct1", "MAS 근원물가",
              "MAS 근원인플레이션(숙박·민간 교통 제외) 전년 동월 대비입니다. 통계청 Table Builder M213891.", ("M213891",))),
    SgSpec(_s("gdp_yoy", "quarterly", "%", "pct1", "실질GDP YoY",
              "실질GDP(연쇄 2015년 가격) 전년 동기 대비입니다. 통계청 M014811(원계열 수준에서 계산).", ("M014811",)), 3),
    SgSpec(_s("gdp_qoq", "quarterly", "%", "pct1", "실질GDP QoQ",
              "계절조정 실질GDP 전기 대비(연율 아님)입니다. 통계청 M014812(계절조정 수준에서 계산).", ("M014812",)), 3),
    SgSpec(_s("m2_yoy", "monthly", "%", "pct1", "M2 YoY",
              "통화량 M2(기말) 전년 동월 대비입니다. 통계청 M920281(과거 계열, ~2021-06)·M701111(2021-07~). MAS가 2021-07에 집계 기준을 바꿔(DBU → 싱가포르달러 표시분만) 두 기준이 섞이는 2021-07~2022-06은 비워 둡니다.", ("M920281", "M701111"))),
    SgSpec(_s("current_account", "quarterly", "bn_sgd", "bn1sgd", "경상수지",
              "국제수지 경상수지(분기, 십억 싱가포르달러)입니다. 통계청 M060171. 달러가 아니라 싱가포르달러 기준입니다.", ("M060171",)), 3),
    SgSpec(_s("sgs_2y", "monthly", "%", "pct2", "SGS 2년",
              "싱가포르 국채 2년 수익률(월말, 프라이머리 딜러 호가 평균)입니다. 통계청 M700071(MAS 자료).", ("M700071",))),
    SgSpec(_s("sgs_10y", "monthly", "%", "pct2", "SGS 10년",
              "싱가포르 국채 10년 수익률(월말)입니다. 통계청 M700071(MAS 자료).", ("M700071",))),
    SgSpec(_s("sg_private_home", "quarterly", "index", "idx1", "민간주택가격지수",
              "민간 주거용 부동산 가격지수(2009년 1분기=100, 전체)입니다. 통계청 M212261(URA 자료).", ("M212261",)), 3),
]}

ROWS: dict[str, tuple[str, str]] = {
    "cpi_yoy": ("M213751", "1"), "mas_core_infl": ("M213891", "1"),
    "gdp_yoy": ("M014811", "1"), "gdp_qoq": ("M014812", "1"),
    "current_account": ("M060171", "1.1"),
    "sgs_2y": ("M700071", "13"), "sgs_10y": ("M700071", "15"),
    "sg_private_home": ("M212261", "1"),
}


def m2_yoy(fetch: Callable[[str, str], tuple[Points, str | None]]) -> Points:
    """YoY within each basis only; nothing across the 2021-07 change of definition."""
    old, _ = fetch("M920281", "2")
    new, _ = fetch("M701111", "1.1")
    return splice(ups.pct_change(old, 12), ups.pct_change(new, 12))


def series_for(spec_id: str, fetch: Callable[[str, str], tuple[Points, str | None]] = fetch_row) -> Points:
    if spec_id == "m2_yoy":
        return m2_yoy(fetch)
    table, row = ROWS[spec_id]
    pts, unit = fetch(table, row)
    if spec_id in ("cpi_yoy", "mas_core_infl"):
        return ups.pct_change(pts, 12)
    if spec_id == "gdp_yoy":
        return ups.pct_change(pts, 4)
    if spec_id == "gdp_qoq":
        return ups.pct_change(pts, 1)
    if spec_id == "current_account":
        if "million" not in (unit or "").lower():
            raise ValueError(f"unexpected SingStat unit {unit!r}")
        return ups.scale(pts, 1e-3)
    return pts


def build_patch(spec_id: str, points: Points, *, retrieved_at: str) -> dict[str, Any]:
    from .za_public_series import with_gaps
    s = SPECS[spec_id]
    return ups.build_patch(s.spec, with_gaps(points, s.gap_months), retrieved_at=retrieved_at)


def apply_all(sgp: dict[str, Any], patches: dict[str, dict[str, Any]], *, retrieved_at: str) -> dict[str, Any]:
    by_id = {i["id"]: i for i in sgp["indicators"]}
    changed = [k for k, p in patches.items() if k in by_id and ups.apply_patch(by_id[k], p)]
    if jps.apply_gdp_composite(by_id, retrieved_at, source="singstat:M014811+M014812"):
        changed.append("gdp")
    ups.sync_chips(sgp, by_id, set(changed))
    units = krs.sync_chip_units(sgp, by_id, {k for k in patches if k in by_id})
    before = dict(sgp.get("data_status_summary") or {})
    ups.refresh_status_summary(sgp)
    return {"changed": changed, "summary_changed": units or before != sgp["data_status_summary"]}
