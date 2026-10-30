"""Switzerland: the Swiss National Bank's data portal (data.snb.ch) and FRED. Keyless.

  snb_policy_rate      SNB policy rate, daily                    cube snbgwdzid (LZ)
  bond_10y             Confederation bond yield, 10y, daily      warehouse SNB1A.SNB.NSS.KZS.EID (J10M0)
  ch_bund_10y_spread   CH 10y minus German 10y, monthly averages SNB (above) and FRED IRLTLT01DEM156N
  cpi_yoy              CPI YoY (FSO figures as the SNB carries them)   cube plkopr (VVP)
  m3_yoy, m3_vs_2019   M3                                        cube snbmonagg (VV/B, GM3)
  snb_total_assets     SNB balance sheet total, month-end        cube snbbipo (T0)
  snb_fx_reserves      foreign currency investments, month-end   cube snbbipo (D)
  sight_deposits       sight deposits at the SNB, weekly total   cube snbgwdchfsgw (TG)
  current_account      current account balance, quarterly        cube bopoverq (S0)
  fx_intervention      SNB foreign currency purchases, quarterly cube snbfxtr (T0)
  chf_reer             real (CPI-based) trade-weighted CHF index cube devwkieffim (K, G, I)
  gdp_qoq, gdp_yoy     real GDP, chain-linked, s.a.              FRED CLVMNACSCAB1GQCH (Eurostat)

Terms. The SNB allows its data to be saved, transmitted and used "for non-commercial purposes" with a
reference to the source (www.snb.ch/en/srv/disclaimer_copyright). The source line is shown under the
panel (config/source_notices_v1.json).

Not here, and why: the KOF barometer (datenservice.kof.ethz.ch refuses connections), procure.ch PMI
(press release only), CDS, a Swiss bank-share index (no free series). EUR/CHF and the SMI are Yahoo
quotes (live_catalog.py).

GDP: the SNB's own GDP cube does not say whether it is real or nominal, so the Eurostat chain-linked
real series on FRED is used for both rates; its QoQ matches the OECD real QoQ.
"""

from __future__ import annotations

import csv
import io
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from . import kr_public_series as krs
from . import us_public_series as ups
from .us_public_series import Points, Spec

UA = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"
CUBE = "https://data.snb.ch/api/cube/{cube}/data/csv/en?fromDate={start}"
WAREHOUSE = ("https://data.snb.ch/api/warehouse/cube/{cube}/data/csv/en"
             "?dimSel={dims}&fromDate={start}")
YIELD_CUBE = "SNB1A.SNB.NSS.KZS.EID"
YIELD_DIMS = "LAUFZEIT(J10M0),ZEITPUNKT(A1100),frequency(P1D_L),AGGREGATIONSMETHODE(ZZ)"
PORTAL = "https://data.snb.ch/en/topics/{topic}/cube/{cube}"

ups._FORMATS.update({
    "pct2": lambda v: f"{v:.2f}%",
    "bn0chf": lambda v: f"CHF {v:,.0f}B",
    "bn1chf": lambda v: f"CHF {v:,.1f}B" if v >= 0 else f"-CHF {-v:,.1f}B",
    "idx1": lambda v: f"{v:,.1f}",
})


def _get(url: str, *, timeout: int = 60, tries: int = 3) -> str:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8-sig")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url[:70]}: {last}")


def period_key(p: str) -> str | None:
    """'2026-08' -> 2026-08-01, '2026-Q2' -> 2026-04-01, '2026-09-25' as is; a bare year -> None."""
    if len(p) == 10:
        return p
    if len(p) == 7 and p[4] == "-" and p[5] == "Q":
        return f"{p[:4]}-{(int(p[6]) - 1) * 3 + 1:02d}-01"
    if len(p) == 7 and p[4] == "-":
        return p + "-01"
    return None


def parse_cube(text: str, *key: str) -> Points:
    """Rows of an SNB cube CSV whose dimension columns equal `key`, in date order. The file opens with a
    few ';'-separated header lines ahead of the "Date";"D0";...;"Value" row; empty values are gaps."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith('"Date"')), None)
    if start is None:
        raise ValueError(f"not an SNB cube csv: {text[:80]!r}")
    out: Points = []
    for row in csv.reader(io.StringIO("\n".join(lines[start + 1:])), delimiter=";"):
        if len(row) < 2 or tuple(row[1:-1]) != key or row[-1] == "":
            continue
        d = period_key(row[0])
        if d:
            out.append((d, float(row[-1])))
    if not out:
        raise ValueError(f"no observations for {key}")
    return sorted(out)


def fetch_cube(cube: str, start: str = "2014-01") -> str:
    return _get(CUBE.format(cube=cube, start=start))


def fetch_yield_10y(start: str = "2014-01-01") -> Points:
    text = _get(WAREHOUSE.format(cube=YIELD_CUBE, dims=YIELD_DIMS, start=start))
    return parse_cube(text, "J10M0", "A1100", "P1D_L", "ZZ")


def month_last(pts: Points) -> Points:
    """Daily -> the last observation of each month, dated the 1st."""
    by: dict[str, float] = {}
    for d, v in sorted(pts):
        by[d[:7] + "-01"] = v
    return sorted(by.items())


def month_mean(pts: Points) -> Points:
    sums: dict[str, list[float]] = {}
    for d, v in pts:
        sums.setdefault(d[:7] + "-01", []).append(v)
    return sorted((k, sum(v) / len(v)) for k, v in sums.items())


def spread_bp(ch: Points, de: Points) -> Points:
    """Monthly average CH 10y minus Germany's monthly (OECD) 10y, only for months both have."""
    de_by = dict(de)
    return [(d, (v - de_by[d]) * 100) for d, v in ch if d in de_by]


_SNB = "https://data.snb.ch/"


def _s(id_: str, cadence: str, unit: str, fmt: str, label: str, note: str, source: str, url: str,
       chart: str = "line") -> Spec:
    return Spec(id_, cadence, unit, fmt, note, source, (url,), cadence, label_ko=label, chart_type=chart)


SPECS: dict[str, Spec] = {s.id: s for s in [
    _s("snb_policy_rate", "monthly", "%", "pct2", "SNB 정책금리",
       "스위스 국립은행(SNB) 정책금리입니다. 차트는 각 달 말 금리, 최신 점은 최근 고시일입니다. SNB 데이터 포털 snbgwdzid.",
       "snb:snbgwdzid", PORTAL.format(topic="ziredev", cube="snbgwdzid")),
    _s("bond_10y", "monthly", "%", "pct2", "연방채 10년",
       "스위스 연방채 10년 만기 현물 수익률입니다. 차트는 각 달 마지막 영업일 값, 최신 점은 최근 영업일입니다. SNB 데이터 포털.",
       "snb:SNB1A.KZS.EID", _SNB + "en/warehouse/SNB1A/cube/SNB1A@SNB.NSS.KZS.EID"),
    _s("ch_bund_10y_spread", "monthly", "bp", "bp0", "CH−Bund 10Y",
       "스위스 연방채 10년 월평균(SNB) − 독일 국채 10년 월평균(OECD, FRED IRLTLT01DEM156N), bp입니다. 음수 폭이 클수록 CHF 안전자산 프리미엄이 큽니다.",
       "snb+fred:IRLTLT01DEM156N", "https://fred.stlouisfed.org/series/IRLTLT01DEM156N"),
    _s("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
       "소비자물가 전년 동월 대비입니다(연방통계청 FSO 발표치, SNB 데이터 포털 plkopr).",
       "snb:plkopr", PORTAL.format(topic="uvo", cube="plkopr")),
    _s("m3_yoy", "monthly", "%", "pct1", "M3 전년비",
       "통화량 M3 전년 동월 대비입니다. SNB 데이터 포털 snbmonagg.",
       "snb:snbmonagg", PORTAL.format(topic="snb", cube="snbmonagg")),
    _s("m3_vs_2019", "monthly", "%", "pct1", "M3 vs 2019-12",
       "(현재 M3 − 2019-12 M3) / 2019-12 M3 × 100. SNB 데이터 포털 snbmonagg.",
       "snb:snbmonagg", PORTAL.format(topic="snb", cube="snbmonagg")),
    _s("snb_total_assets", "monthly", "bn_chf", "bn0chf", "SNB 총자산",
       "SNB 대차대조표 총자산(월말, 십억 스위스프랑)입니다. SNB 데이터 포털 snbbipo.",
       "snb:snbbipo", PORTAL.format(topic="snb", cube="snbbipo")),
    _s("snb_fx_reserves", "monthly", "bn_chf", "bn0chf", "SNB 외화자산",
       "SNB 대차대조표의 외화 투자(Foreign currency investments, 월말, 십억 스위스프랑)입니다. 환율 방어 개입의 누적 결과입니다.",
       "snb:snbbipo", PORTAL.format(topic="snb", cube="snbbipo")),
    _s("sight_deposits", "weekly", "bn_chf", "bn0chf", "요구불예금(SNB)",
       "SNB에 예치된 요구불예금 합계(주간, 십억 스위스프랑)입니다. 은행 유동성과 SNB 개입의 흔적이 같이 보입니다. SNB 데이터 포털 snbgwdchfsgw.",
       "snb:snbgwdchfsgw", PORTAL.format(topic="snb", cube="snbgwdchfsgw")),
    _s("current_account", "quarterly", "bn_chf", "bn1chf", "경상수지",
       "경상수지(분기, 십억 스위스프랑)입니다. SNB 국제수지 bopoverq.",
       "snb:bopoverq", PORTAL.format(topic="aube", cube="bopoverq")),
    _s("fx_intervention", "quarterly", "bn_chf", "bn1chf", "외환거래(분기)",
       "SNB의 외환 순매입(분기, 십억 스위스프랑)입니다. 양수는 외화 매입(프랑 약세 유도), 음수는 매도입니다. SNB는 분기 합계만 사후 공개합니다.",
       "snb:snbfxtr", PORTAL.format(topic="snb", cube="snbfxtr"), chart="bar"),
    _s("chf_reer", "monthly", "index", "idx1", "CHF REER",
       "스위스프랑 실질실효환율(소비자물가 기준, 전체 교역국)입니다. 오르면 프랑 강세입니다. SNB 데이터 포털 devwkieffim.",
       "snb:devwkieffim", PORTAL.format(topic="ziredev", cube="devwkieffim")),
    _s("gdp_qoq", "quarterly", "%", "pct1", "실질GDP QoQ",
       "실질GDP(연쇄가격, 계절조정) 전기 대비 %입니다(연율 아님). Eurostat 계열, FRED CLVMNACSCAB1GQCH.",
       "fred:CLVMNACSCAB1GQCH", "https://fred.stlouisfed.org/series/CLVMNACSCAB1GQCH"),
    _s("gdp_yoy", "quarterly", "%", "pct1", "실질GDP YoY",
       "실질GDP(연쇄가격, 계절조정) 전년 동기 대비입니다. Eurostat 계열, FRED CLVMNACSCAB1GQCH.",
       "fred:CLVMNACSCAB1GQCH", "https://fred.stlouisfed.org/series/CLVMNACSCAB1GQCH"),
]}


@dataclass
class Sources:
    cube: Callable[[str], str] = fetch_cube
    yield_10y: Callable[[], Points] = fetch_yield_10y
    fred: Callable[[str], Points] = ups.fetch_fred
    _cubes: dict[str, str] = field(default_factory=dict)
    _y10: Points | None = None

    def rows(self, cube: str, *key: str) -> Points:
        if cube not in self._cubes:
            self._cubes[cube] = self.cube(cube)
        return parse_cube(self._cubes[cube], *key)

    def y10(self) -> Points:
        if self._y10 is None:
            self._y10 = self.yield_10y()
        return self._y10


def series_for(spec_id: str, src: Sources) -> tuple[Points, str | None]:
    """(points, the day of the newest observation when a daily series is shown monthly)."""
    if spec_id == "snb_policy_rate":
        daily = src.rows("snbgwdzid", "LZ")
        return month_last(daily), daily[-1][0]
    if spec_id == "bond_10y":
        daily = src.y10()
        return month_last(daily), daily[-1][0]
    if spec_id == "ch_bund_10y_spread":
        return spread_bp(month_mean(src.y10()), src.fred("IRLTLT01DEM156N")), None
    if spec_id == "cpi_yoy":
        return src.rows("plkopr", "VVP"), None
    if spec_id == "m3_yoy":
        return src.rows("snbmonagg", "VV", "GM3"), None
    if spec_id == "m3_vs_2019":
        return ups.vs_base(src.rows("snbmonagg", "B", "GM3"), "2019-12-01"), None
    if spec_id == "snb_total_assets":
        return ups.scale(src.rows("snbbipo", "T0"), 1e-3), None
    if spec_id == "snb_fx_reserves":
        return ups.scale(src.rows("snbbipo", "D"), 1e-3), None
    if spec_id == "sight_deposits":
        return ups.scale(src.rows("snbgwdchfsgw", "TG"), 1e-3), None
    if spec_id == "current_account":
        return ups.scale(src.rows("bopoverq", "S0"), 1e-3), None
    if spec_id == "fx_intervention":
        return ups.scale(src.rows("snbfxtr", "T0"), 1e-3), None
    if spec_id == "chf_reer":
        return src.rows("devwkieffim", "K", "G", "I"), None
    if spec_id in ("gdp_qoq", "gdp_yoy"):
        level = src.fred("CLVMNACSCAB1GQCH")
        return ups.pct_change(level, 1 if spec_id == "gdp_qoq" else 4), None
    raise KeyError(spec_id)


def build_patch(spec_id: str, points: Points, last_day: str | None, *, retrieved_at: str) -> dict[str, Any]:
    from . import jp_public_series as jps
    from .za_public_series import with_gaps
    spec = SPECS[spec_id]
    if spec.cadence == "monthly":
        points = with_gaps(points)
    elif spec.cadence == "quarterly":
        points = with_gaps(points, 3)
    live_month = last_day and points and last_day[:7] == points[-1][0][:7]
    patch = ups.build_patch(spec, points, retrieved_at=retrieved_at, asof=last_day if live_month else None)
    if live_month:
        jps.pin_last_date(patch, last_day)
    return patch


def apply_all(che: dict[str, Any], patches: dict[str, dict[str, Any]], *, retrieved_at: str) -> dict[str, Any]:
    from . import jp_public_series as jps
    by_id = {i["id"]: i for i in che["indicators"]}
    changed = [k for k, p in patches.items() if k in by_id and ups.apply_patch(by_id[k], p)]
    for k in changed:
        by_id[k].pop("analog_ko", None)
    if jps.apply_gdp_composite(by_id, retrieved_at, source="fred:CLVMNACSCAB1GQCH"):
        changed.append("gdp")
    ups.sync_chips(che, by_id, set(changed))
    units = krs.sync_chip_units(che, by_id, {k for k in patches if k in by_id})
    before = dict(che.get("data_status_summary") or {})
    ups.refresh_status_summary(che)
    return {"changed": changed, "summary_changed": units or before != che["data_status_summary"]}
