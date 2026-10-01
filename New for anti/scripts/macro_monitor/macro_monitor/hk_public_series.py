"""Hong Kong: the Census and Statistics Department's (C&SD) static CSVs. Keyless.

Every C&SD table (https://www.censtatd.gov.hk/en/web_table.html?id=...) is drawn from plain CSVs at
    https://www.censtatd.gov.hk/data/MDT_{theme}_{table}_{statvar}_{presentation}.csv
with a header naming its columns: the year (CCYY), a month (MM) or quarter (Q) -- blank on the annual
total rows that are interleaved with them --, any classification columns (MATURITY, BOP_COMPONENT, ...),
obs_value and sd_value. sd_value is a status code from
    https://www.censtatd.gov.hk/data/en/sd_lang.json
and many codes mean the figure is *not released* ("N.A.", "not applicable", confidential); those rows
carry obs_value 0.0000, which must not be read as a zero. They are skipped.

Cards (table in brackets):
  composite_cpi   composite CPI, YoY (510-60001)              monthly
  gdp_yoy/gdp_qoq real GDP YoY / seasonally adjusted QoQ (310-31001)   quarterly
  m2_yoy          money supply M2 (all currencies), YoY (340-45011)  quarterly
  m2_vs_2019      M2 against 2019Q4 (340-45011)                quarterly
  hibor_1m/_3m    HKD interest settlement rates, quarter end (340-45022)
  current_account BOP current account balance, HK$ (315-37001)  quarterly
  retail_sales_yoy value index of retail sales, YoY (620-67001) monthly
Money supply and HIBOR are only published by C&SD at quarter ends; the monthly/daily figures are the
HKMA's, whose API (api.hkma.gov.hk) could not be reached from here (connection refused behind its WAF).

  hibor_sofr_spread 3-month HIBOR (quarter end) minus the 90-day SOFR average (FRED) -- 3-month term SOFR is
                  not free, so the backward-looking average stands in, and the card says so
  hk_home_price   RVD private domestic price index, all classes, monthly (www.rvd.gov.hk/datagovhk/1.4M.csv);
                  replaces the Centa-City Leading index card (a private weekly index with no free source)

Not here, and why: aggregate balance, FX reserves, base rate (HKMA API, see above), CDS (paid).
Stock indices (HSI, HSCEI) are Yahoo series in live_catalog.py; total exports are in export_public_series.py.
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from . import jp_public_series as jps
from . import kr_public_series as krs
from . import us_public_series as ups
from .us_public_series import Points, Spec

CENSTATD_CSV = "https://www.censtatd.gov.hk/data/{name}.csv"
SD_LEGEND = "https://www.censtatd.gov.hk/data/en/sd_lang.json"
PAGE = "https://www.censtatd.gov.hk/en/web_table.html?id={table}"
UA = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"

# Snapshot of sd_lang.json (2026-09-29): codes whose figure is not released. Used when the legend
# itself cannot be read.
SUPPRESSED_FALLBACK = frozenset(
    [str(c) for c in (*range(1, 18), *range(21, 100), 125, 127, 128, 129, 130, 133, 222) if c not in (7, 18)])

ups._FORMATS.update({
    "pct2": lambda v: f"{v:.2f}%",
    "bn1hkd": lambda v: f"HK${v:,.1f}B",
    "idx1": lambda v: f"{v:,.1f}",
})


def _get(url: str, *, timeout: int = 60, tries: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"C&SD {url}: {last}")


def suppressed_codes(legend: dict[str, Any] | None) -> frozenset[str]:
    if not legend:
        return SUPPRESSED_FALLBACK
    return frozenset(k for k, v in legend.items() if str(v.get("obs_value_suppressed")) == "1")


def fetch_suppressed() -> frozenset[str]:
    try:
        return suppressed_codes(json.loads(_get(SD_LEGEND).decode("utf-8")))
    except Exception:  # noqa: BLE001 -- the snapshot is the same list
        return SUPPRESSED_FALLBACK


def parse_censtatd(text: str, *, where: dict[str, str] | None = None,
                   suppressed: frozenset[str] = SUPPRESSED_FALLBACK) -> Points:
    """Monthly rows -> YYYY-MM-01, quarterly rows -> the quarter's first month; the annual rows
    interleaved with them (period blank) and every suppressed figure are skipped."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows or "obs_value" not in rows[0] or "CCYY" not in rows[0]:
        raise ValueError(f"unexpected C&SD csv: {text[:80]!r}")
    col = {name: i for i, name in enumerate(rows[0])}
    period = "MM" if "MM" in col else "Q" if "Q" in col else None
    out: Points = []
    for r in rows[1:]:
        if len(r) < len(col):
            continue
        if any(r[col[k]] != v for k, v in (where or {}).items()):
            continue
        sd = r[col["sd_value"]].strip() if "sd_value" in col else ""
        if sd and sd in suppressed:
            continue
        p = r[col[period]].strip() if period else ""
        if period and not p:
            continue                                       # the year's total, not a period
        try:
            y, v = int(r[col["CCYY"]]), float(r[col["obs_value"]])
            m = int(p) if period == "MM" else (int(p) - 1) * 3 + 1 if period == "Q" else 1
        except ValueError:
            continue
        out.append((f"{y:04d}-{m:02d}-01", v))
    if not out:
        raise ValueError("C&SD csv has no usable rows")
    return sorted(out)


@dataclass(frozen=True)
class HkSpec:
    spec: Spec
    file: str
    where: tuple[tuple[str, str], ...] = ()
    transform: str | None = None        # "vs_2019q4" | "bn" (HK$ million -> billion)
    gap_months: int = 1


def _s(id_: str, cadence: str, unit: str, fmt: str, label: str, note: str, table: str) -> Spec:
    return Spec(id_, cadence, unit, fmt, note, f"censtatd:{table}", (PAGE.format(table=table),), cadence, label_ko=label)


SPECS: dict[str, HkSpec] = {h.spec.id: h for h in [
    HkSpec(_s("composite_cpi", "monthly", "%", "pct1", "종합 CPI YoY",
              "종합 소비자물가지수(2019/20=100) 전년 동월 대비입니다. 통계처 표 510-60001.", "510-60001"),
           "MDT_54_510-60001_CC_CM_1920_YoY_1dp_percent_s"),
    HkSpec(_s("gdp_yoy", "quarterly", "%", "pct1", "실질GDP YoY",
              "실질GDP(연쇄 2024년 가격) 전년 동기 대비입니다. 통계처 표 310-31001.", "310-31001"),
           "MDT_69_310-31001_CON_YoY_1dp_percent_s", gap_months=3),
    HkSpec(_s("gdp_qoq", "quarterly", "%", "pct1", "실질GDP QoQ",
              "계절조정 실질GDP 전기 대비(연율 아님)입니다. 통계처 표 310-31001.", "310-31001"),
           "MDT_69_310-31001_SA1_QoQ_1dp_percent_s", gap_months=3),
    HkSpec(_s("m2_yoy", "quarterly", "%", "pct1", "M2 YoY",
              "통화량 M2(전체 통화) 전년 동기 대비, 분기말입니다. 통계처 표 340-45011(원자료 HKMA). 월별 수치는 HKMA API에 있지만 여기서 접속되지 않아 분기로 싣습니다.", "340-45011"),
           "MDT_96_340-45011_M2_YoY_1dp_percent_s", gap_months=3),
    HkSpec(_s("m2_vs_2019", "quarterly", "%", "pct1", "M2 vs 2019말",
              "통화량 M2(전체 통화) 2019년 4분기 말 대비 증가율입니다. 통계처 표 340-45011.", "340-45011"),
           "MDT_96_340-45011_M2_Raw_M_hkd_d", transform="vs_2019q4", gap_months=3),
    HkSpec(_s("hibor_1m", "quarterly", "%", "pct2", "HIBOR 1M(분기말)",
              "홍콩달러 은행간 금리(HIBOR) 1개월물, 분기말 고시값입니다. 통계처 표 340-45022(원자료 HKMA). 일별 값은 HKMA API라 여기서는 분기말만 싣습니다.", "340-45022"),
           "MDT_96_340-45022_SET_RATE_Rate_2dp_percent_n", where=(("MATURITY", "1M"),), gap_months=3),
    HkSpec(_s("hibor_3m", "quarterly", "%", "pct2", "HIBOR 3M(분기말)",
              "홍콩달러 은행간 금리(HIBOR) 3개월물, 분기말 고시값입니다. 통계처 표 340-45022(원자료 HKMA).", "340-45022"),
           "MDT_96_340-45022_SET_RATE_Rate_2dp_percent_n", where=(("MATURITY", "3M"),), gap_months=3),
    HkSpec(_s("current_account", "quarterly", "bn_hkd", "bn1hkd", "경상수지",
              "국제수지 경상수지(분기, 십억 홍콩달러)입니다. 통계처 표 315-37001. 달러가 아니라 홍콩달러 기준입니다.", "315-37001"),
           "MDT_64_315-37001_BOP_Raw_M_hkd_d", where=(("BOP_COMPONENT", "CRA"),), transform="bn", gap_months=3),
    HkSpec(_s("retail_sales_yoy", "monthly", "%", "pct1", "소매판매 YoY",
              "소매판매액 지수(금액 기준) 전년 동월 대비입니다. 통계처 표 620-67001.", "620-67001"),
           "MDT_75_620-67001_VAL_IDX_RS_YoY_1dp_percent_s"),
    HkSpec(Spec("hibor_sofr_spread", "quarterly", "bp", "bp0",
                "HIBOR 3개월물(분기말 고시, 통계처 표 340-45022)에서 SOFR 90일 평균(같은 날, FRED SOFR90DAYAVG)을 뺀 값입니다. 3개월 기간물 SOFR는 무료 출처가 없어 90일 평균으로 맞췄습니다. 마이너스 → 캐리 유출 · 환율 7.85 압력.",
                "censtatd:340-45022+fred:SOFR90DAYAVG", (PAGE.format(table="340-45022"), "https://fred.stlouisfed.org/series/SOFR90DAYAVG"),
                "quarterly", label_ko="HIBOR 3M − SOFR"),
           "MDT_96_340-45022_SET_RATE_Rate_2dp_percent_n", where=(("MATURITY", "3M"),), gap_months=3),
    HkSpec(Spec("hk_home_price", "monthly", "index", "idx1",
                "민간 주택 가격지수(전 등급, 1999=100, 월)입니다 — 정부 평가처(RVD) 공식 지수. 예전 카드는 민간 'Centa-City Leading' 주간 지수였는데 무료 출처가 없어 공식 월간 지수로 바꿨습니다. 최근 몇 달은 잠정치(P).",
                "rvd:1.4M", ("https://www.rvd.gov.hk/en/publications/property_market_statistics.html",), "monthly",
                label_ko="주택가격지수(RVD)"),
           ""),
]}

RENAMES = {"ccl_index": "hk_home_price"}
RVD_CSV = "https://www.rvd.gov.hk/datagovhk/1.4M.csv"


def parse_rvd(text: str, column: str = "All Classes") -> Points:
    """RVD 'Month,Class A,Class A - Remarks,...' with months 'MM-YYYY'; the title line above the header is skipped."""
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    hi = next((i for i, r in enumerate(rows) if r and r[0].strip() == "Month"), None)
    if hi is None or column not in rows[hi]:
        raise ValueError(f"RVD csv has no {column!r} column")
    j = rows[hi].index(column)
    out: Points = []
    for r in rows[hi + 1:]:
        if len(r) <= j or len(r[0]) != 7 or r[0][2] != "-":
            continue
        try:
            out.append((f"{r[0][3:]}-{r[0][:2]}-01", float(r[j])))
        except ValueError:
            continue
    if not out:
        raise ValueError("RVD csv has no monthly rows")
    return sorted(out)


def quarter_spread(hibor: Points, sofr: Points) -> Points:
    """HIBOR at each quarter end minus SOFR on the last day at or before that quarter end, in bp."""
    out: Points = []
    for d, h in hibor:
        end = ups.quarter_end(d)
        s = [v for sd, v in sofr if sd <= end]
        if s and sofr[0][0] <= end:
            out.append((d, (h - s[-1]) * 100))
    return out


def series_for(spec_id: str, get: Callable[[str], str], suppressed: frozenset[str],
               fred: Callable[[str], Points] = ups.fetch_fred,
               rvd: Callable[[], str] = lambda: _get(RVD_CSV).decode("utf-8-sig")) -> Points:
    h = SPECS[spec_id]
    if spec_id == "hk_home_price":
        return parse_rvd(rvd())
    pts = parse_censtatd(get(h.file), where=dict(h.where), suppressed=suppressed)
    if spec_id == "hibor_sofr_spread":
        return quarter_spread(pts, fred("SOFR90DAYAVG"))
    if h.transform == "vs_2019q4":
        pts = ups.vs_base(pts, "2019-10-01")
    elif h.transform == "bn":
        pts = ups.scale(pts, 1e-3)
    return pts


def fetch_file(name: str) -> str:
    return _get(CENSTATD_CSV.format(name=name)).decode("utf-8")


def build_patch(spec_id: str, points: Points, *, retrieved_at: str) -> dict[str, Any]:
    from .za_public_series import with_gaps
    return ups.build_patch(SPECS[spec_id].spec, with_gaps(points, SPECS[spec_id].gap_months), retrieved_at=retrieved_at)


def apply_all(hkg: dict[str, Any], patches: dict[str, dict[str, Any]], *, retrieved_at: str) -> dict[str, Any]:
    for old, new in RENAMES.items():
        if new in patches:
            krs.rename_indicator(hkg, old, new, {})
    by_id = {i["id"]: i for i in hkg["indicators"]}
    changed = [k for k, p in patches.items() if k in by_id and ups.apply_patch(by_id[k], p)]
    if jps.apply_gdp_composite(by_id, retrieved_at, source="censtatd:310-31001"):
        changed.append("gdp")
    ups.sync_chips(hkg, by_id, set(changed))
    units = krs.sync_chip_units(hkg, by_id, {k for k in patches if k in by_id})
    before = dict(hkg.get("data_status_summary") or {})
    ups.refresh_status_summary(hkg)
    return {"changed": changed, "summary_changed": units or before != hkg["data_status_summary"]}
