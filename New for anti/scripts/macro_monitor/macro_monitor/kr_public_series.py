"""Korean indicators from official statistics instead of the fixture generator.

Almost everything comes from the Bank of Korea's ECOS (which republishes Statistics Korea's CPI and
production index, the Customs Service's exports and the KRX's market data): CPI, core CPI, industrial
production, GDP, the current account, reserves, CCSI, BSI, household credit, M2, the BOK balance sheet,
market rates and the credit spreads, and foreign net buying. The Fed's target rate (for the rate
gap) and the monthly average KRW/USD (for exports in won) come from FRED, keyless.

Same contract as the other public-series modules: every value is a published observation or arithmetic
on one, a series that cannot be read leaves the previous card, nothing is estimated. Exports are shown in
won: the Customs Service publishes dollars, so the won figure is dollars x the month's average KRW/USD
(a conversion, and the card says so); a month whose average rate is not out yet is left out.

The ECOS key stays on the machine that has it. What it reads is written to a small cache file, and a
run without the key (the scheduled one, if the secret is not set) reads that cache.

Not grafted: the BOK base rate. The live overlay already pins its latest value (from the BOK key
statistics) on every run; a second writer would flip the card between the two. Semiconductor exports come from KOSIS (the MSIT's monthly IT-industry export table, class "반도체":
memory, system chips, discrete devices, optoelectronics, wafers, parts), converted to won the same way.
Left as demo, and why: VKOSPI (no free source found), real-estate PF balance and delinquency (the
Financial Supervisory Service publishes them, not ECOS), sovereign CDS (licensed), the FX intervention
(the authorities publish it with a lag that cannot be told from "none").
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import ecos
from . import jp_public_series as jps
from . import kosis
from . import us_public_series as ups
from .us_public_series import Points, Spec

ups._FORMATS.update({
    "pct2": lambda v: f"{v:.2f}%", "tn1": lambda v: f"{v:.1f}T", "tn2": lambda v: f"{v:.2f}T", "bn0u": lambda v: f"{v:,.0f}B",
    "bn1s": lambda v: f"{v:+,.1f}B", "bp0": lambda v: f"{v:+.0f}bp" if v else "0bp", "n0": lambda v: f"{v:.0f}", "n1": lambda v: f"{v:.1f}",
    "krw_tn1": lambda v: f"{v:,.1f}조원",
})

_USD_UNITS = {"달러": 1.0, "천달러": 1e3, "백만달러": 1e6, "억달러": 1e8, "십억달러": 1e9,
              "불": 1.0, "천불": 1e3, "백만불": 1e6, "억불": 1e8}


def usd_multiplier(unit_nm: str) -> float:
    """Dollars per printed unit ("천불" = thousand dollars). An unknown unit raises: guessing the
    unit of a money series is off by a factor of a thousand or a million."""
    key = "".join(str(unit_nm or "").split())
    if key not in _USD_UNITS:
        raise ValueError(f"unrecognised money unit {unit_nm!r}")
    return _USD_UNITS[key]


def export_krw_tn(usd_rows_unit: str, usd_points: Points, krw_per_usd: Points) -> Points:
    """Monthly exports in trillions of won: dollars x that month's average KRW per USD. Only months
    that have both an export figure and an average rate."""
    mult = usd_multiplier(usd_rows_unit)
    fx = dict(krw_per_usd)
    return [(d, v * mult * fx[d] / 1e12) for d, v in usd_points if d in fx]


def month_sums(points: Points, today: date) -> Points:
    """Monthly totals of a daily flow, complete months only: the running month's partial sum would read as
    a small month."""
    tot: dict[str, float] = {}
    for d, v in points:
        tot[d[:7]] = tot.get(d[:7], 0.0) + v
    return [(f"{k}-01", v) for k, v in sorted(tot.items()) if k < f"{today.year:04d}-{today.month:02d}"]


def month_join(a: Points, b: Points, op: Callable[[float, float], float]) -> Points:
    """op(a, b) for each month both have, dated by the older of the two month-end observations (the value is
    only as fresh as its oldest input)."""
    bm = {d[:7]: (d, v) for d, v in b}
    return [(min(d, bm[d[:7]][0]), op(v, bm[d[:7]][1])) for d, v in a if d[:7] in bm]


def rename_indicator(country: dict[str, Any], old_id: str, new_id: str, patch: dict[str, Any]) -> bool:
    """Replace one indicator (and its chip and headline) by another id with a new definition -- the
    card changes what it is (a YoY rate -> an amount in won), not just its value."""
    changed = False
    for ind in country["indicators"]:
        if ind["id"] in (old_id, new_id):
            before = dict(ind)
            ind["id"] = new_id
            ind.update({k: v for k, v in patch.items() if k != "retrieved_at"})
            if ind != before:
                ind["retrieved_at"] = patch.get("retrieved_at")
                changed = True
    for chips in (country.get("categories") or {}).values():
        for chip in chips:
            if chip.get("id") in (old_id, new_id):
                chip["id"] = new_id
    for h in country.get("headlines") or []:
        if h.get("id") == old_id:
            h["id"] = new_id
    return changed


# --------------------------------------------------------------------------
# Reading ECOS (live with the key, cached without it)
# --------------------------------------------------------------------------

ECOS_CACHE = Path(__file__).resolve().parent.parent / "config" / "kr_ecos_series_v1.json"
CACHE_FROM = "2014-01-01"


def load_cache(path: Path = ECOS_CACHE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": "kr-ecos-series-v1", "series": {}}


def save_cache(cache: dict[str, Any], updates: dict[str, dict[str, Any]], now_iso: str, path: Path = ECOS_CACHE) -> bool:
    """Merge fresh reads into the cache; rewritten (and stamped) only when something changed."""
    series = dict(cache.get("series") or {})
    for key, v in updates.items():
        series[key] = {"unit": v["unit"], "points": [[d, round(x, 6)] for d, x in v["points"] if d >= CACHE_FROM]}
    if series == (cache.get("series") or {}):
        return False
    path.write_text(json.dumps({"schema_version": "kr-ecos-series-v1", "retrieved_at": now_iso, "series": series},
                               ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    return True


def ecos_reader(cache: dict[str, Any], updates: dict[str, dict[str, Any]], today: date | None = None):
    """read(stat, cycle, items, mode) -> (points, unit). mode: raw | last (last observation of each month,
    for daily series) | sum (monthly totals of a daily flow). Live when the key is set, else the cache."""
    today = today or date.today()

    def read(stat: str, cycle: str, items: tuple[str, ...], mode: str = "raw") -> tuple[Points, str | None]:
        key = f"{stat}/{cycle}/{'/'.join(items)}/{mode}"
        try:
            pts, unit = ecos.series(stat, cycle, items, today=today)
        except ecos.MissingKey:
            cached = (cache.get("series") or {}).get(key)
            if not cached:
                raise
            return [(d, float(v)) for d, v in cached["points"]], cached["unit"]
        pts = jps.month_last(pts) if mode == "last" else month_sums(pts, today) if mode == "sum" else pts
        updates[key] = {"points": pts, "unit": unit}
        return pts, unit
    return read


def kosis_reader(cache: dict[str, Any], updates: dict[str, dict[str, Any]], today: date | None = None):
    """read(org, tbl, c1_code, c1_name) -> (points, unit): a monthly KOSIS series for one first-level
    classification value, chosen by code and checked by name. Live with the key, else the cache."""
    today = today or date.today()

    def read(org: str, tbl: str, c1: str, c1_nm: str) -> tuple[Points, str | None]:
        key = f"kosis/{org}/{tbl}/{c1}"
        try:
            rows = kosis.data(org, tbl, prd_se="M", start=f"{today.year - 11}01", end=today.strftime("%Y%m"), obj_l1=c1)
        except kosis.MissingKey:
            cached = (cache.get("series") or {}).get(key)
            if not cached:
                raise
            return [(d, float(v)) for d, v in cached["points"]], cached["unit"]
        pts = kosis.series(rows, prd_se="M", c1=c1, c1_nm=c1_nm)
        unit = next((r.get("UNIT_NM") for r in rows if r.get("UNIT_NM")), None)
        updates[key] = {"points": pts, "unit": unit}
        return pts, unit
    return read


class Sources:
    def __init__(self, *, ecos_read, kosis_read=None, fred=ups.fetch_fred):
        self._read, self._kosis_read, self._fred = ecos_read, kosis_read, fred
        self._cache: dict[Any, Any] = {}

    def _memo(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def ecos(self, stat: str, cycle: str, items: tuple[str, ...], mode: str = "raw") -> tuple[Points, str | None]:
        return self._memo((stat, cycle, items, mode), lambda: self._read(stat, cycle, items, mode))

    def kosis(self, org: str, tbl: str, c1: str, c1_nm: str) -> tuple[Points, str | None]:
        return self._memo(("kosis", org, tbl, c1), lambda: self._kosis_read(org, tbl, c1, c1_nm))

    def pts(self, *a, **kw) -> Points:
        return self.ecos(*a, **kw)[0]

    def fred(self, sid: str) -> Points:
        return self._memo(("fred", sid), lambda: self._fred(sid))


# --------------------------------------------------------------------------
# What each indicator is made of
# --------------------------------------------------------------------------

_ECOS_PAGE = "https://ecos.bok.or.kr/"


def _u(*u: str) -> tuple[str, ...]:
    return u


SPECS: dict[str, Spec] = {s.id: s for s in [
    Spec("cpi_yoy", "monthly", "%", "pct1", "소비자물가지수(총지수, 2020=100)의 전년 같은 달 대비 상승률입니다. 통계청 발표를 한국은행 ECOS(901Y009)에서 받아 계산했습니다.",
         "ecos:901Y009", _u(_ECOS_PAGE), "monthly"),
    Spec("core_cpi_yoy", "monthly", "%", "pct1", "'농산물 및 석유류 제외 지수'(근원 CPI)의 전년 같은 달 대비 상승률입니다. ECOS 901Y010.",
         "ecos:901Y010", _u(_ECOS_PAGE), "monthly"),
    Spec("ip_yoy", "monthly", "%", "pct1", "전산업생산지수(농림어업 제외, 2020=100, 원지수)의 전년 같은 달 대비 증가율입니다. ECOS 901Y033.",
         "ecos:901Y033", _u(_ECOS_PAGE), "monthly"),
    Spec("gdp_yoy", "quarterly", "%", "pct1", "실질 GDP(원계열)의 전년 같은 분기 대비 증가율입니다. ECOS 200Y106.",
         "ecos:200Y106", _u(_ECOS_PAGE), "quarterly"),
    Spec("gdp_qoq", "quarterly", "%", "pct1", "실질 GDP(계절조정)의 직전 분기 대비 증가율입니다(연율 환산 아님). ECOS 200Y104.",
         "ecos:200Y104", _u(_ECOS_PAGE), "quarterly"),
    Spec("current_account", "monthly", "bn_usd", "bn1s", "월별 경상수지(십억 달러)입니다. ECOS 301Y013(국제수지).",
         "ecos:301Y013", _u(_ECOS_PAGE), "monthly"),
    Spec("fx_reserves", "monthly", "bn_usd", "bn0u", "외환보유액 합계(십억 달러)입니다. ECOS 732Y001.",
         "ecos:732Y001", _u(_ECOS_PAGE), "monthly"),
    Spec("ccsi", "monthly", "index", "n1", "소비자심리지수(CCSI)입니다. 한국은행 소비자동향조사, ECOS 511Y002.",
         "ecos:511Y002", _u(_ECOS_PAGE), "monthly"),
    Spec("bsi", "monthly", "index", "n0", "전산업 업황실적 BSI입니다. 한국은행 기업경기조사, ECOS 512Y013.",
         "ecos:512Y013", _u(_ECOS_PAGE), "monthly"),
    Spec("household_credit", "quarterly", "tn_krw", "tn1", "가계신용 잔액(조원)입니다. ECOS 151Y001.",
         "ecos:151Y001", _u(_ECOS_PAGE), "quarterly"),
    Spec("household_credit_yoy", "quarterly", "%", "pct1", "가계신용 잔액의 전년 같은 분기 대비 증가율입니다. 위 잔액에서 계산했습니다.",
         "ecos:151Y001", _u(_ECOS_PAGE), "quarterly"),
    Spec("m2_yoy", "monthly", "%", "pct1", "M2(평잔, 원계열)의 전년 같은 달 대비 증가율입니다. ECOS 161Y006.",
         "ecos:161Y006", _u(_ECOS_PAGE), "monthly"),
    Spec("m2_vs_2019", "monthly", "%", "pct1", "(현재 M2 − 2019-12 M2) / 2019-12 M2 × 100. M2(평잔, 원계열) 기준입니다. ECOS 161Y006.",
         "ecos:161Y006", _u(_ECOS_PAGE), "monthly"),
    Spec("bok_total_assets", "monthly", "tn_krw", "tn1", "한국은행 자산 합계(월말 잔액, 조원)입니다. ECOS 103Y002(한국은행 주요계정).",
         "ecos:103Y002", _u(_ECOS_PAGE), "monthly"),
    Spec("ktb_3y", "monthly", "%", "pct2", "국고채 3년물 수익률(월말 마지막 거래일; 이번 달은 최신일). ECOS 817Y002.",
         "ecos:817Y002", _u(_ECOS_PAGE), "daily"),
    Spec("bond_10y", "monthly", "%", "pct2", "국고채 10년물 수익률(월말 마지막 거래일; 이번 달은 최신일). ECOS 817Y002.",
         "ecos:817Y002", _u(_ECOS_PAGE), "daily"),
    Spec("corp_spread_aa", "monthly", "bp", "bp0", "회사채(3년, AA−) 수익률 − 국고채 3년물 수익률(bp). ECOS 817Y002에서 같은 달 마지막 값끼리 뺐습니다.",
         "ecos:817Y002", _u(_ECOS_PAGE), "daily"),
    Spec("cp_spread", "monthly", "bp", "bp0", "CP(91일) 수익률 − 통안증권(91일) 수익률(bp). ECOS 817Y002.",
         "ecos:817Y002", _u(_ECOS_PAGE), "daily"),
    Spec("us_kr_rate_gap", "monthly", "bp", "bp0", "연준 정책금리 상단(FRED DFEDTARU) − 한국은행 기준금리(bp). 양수면 미국이 더 높습니다(자본유출·환율 압력).",
         "fred:DFEDTARU+ecos:722Y001", _u("https://fred.stlouisfed.org/series/DFEDTARU", _ECOS_PAGE), "daily"),
    Spec("foreign_equity_kr", "monthly", "tn_krw", "tn2", "외국인 주식 순매수(유가증권시장 + 코스닥, 조원)의 월 합계입니다. ECOS 802Y001의 일별 값을 더했고, 진행 중인 달은 부분 합이라 싣지 않습니다.",
         "ecos:802Y001", _u(_ECOS_PAGE), "monthly"),
    Spec("semi_export_krw", "monthly", "tn_krw", "krw_tn1", "반도체 월별 수출액의 원화 환산입니다 = 과기정통부 'IT산업별/월별 수출 현황'의 '반도체'(메모리·시스템반도체·개별소자·광전자·웨이퍼·부품 포함) 달러 수출액(KOSIS) × 그 달 평균 원/달러(FRED EXKOUS). 환산값이며 원화로 결제된 금액이 아닙니다. 평균 환율이 아직 안 나온 달은 싣지 않습니다.",
         "kosis:127/DT_092_115_2009_S023+fred:EXKOUS", _u("https://kosis.kr/", "https://fred.stlouisfed.org/series/EXKOUS"), "monthly", label_ko="반도체 수출(원화 환산)"),
    Spec("export_krw", "monthly", "tn_krw", "krw_tn1", "월별 수출액(통관 기준)의 원화 환산입니다 = 관세청 달러 수출액(ECOS 901Y118) × 그 달 평균 원/달러(FRED EXKOUS). 환산값이며 원화로 결제된 금액이 아닙니다. 평균 환율이 아직 안 나온 달은 싣지 않습니다.",
         "ecos:901Y118+fred:EXKOUS", _u(_ECOS_PAGE, "https://fred.stlouisfed.org/series/EXKOUS"), "monthly", label_ko="수출(원화 환산)"),
]}
DAILY_SOURCED = {"ktb_3y", "bond_10y", "corp_spread_aa", "cp_spread", "us_kr_rate_gap"}


def series_for(spec_id: str, s: Sources, today: date | None = None) -> Points:
    today = today or date.today()
    if spec_id == "cpi_yoy":
        return ups.pct_change(s.pts("901Y009", "M", ("0",)), 12)
    if spec_id == "core_cpi_yoy":
        return ups.pct_change(s.pts("901Y010", "M", ("QB",)), 12)
    if spec_id == "ip_yoy":
        return ups.pct_change(s.pts("901Y033", "M", ("A00",)), 12)
    if spec_id == "gdp_yoy":
        return ups.pct_change(s.pts("200Y106", "Q", ("1400",)), 4)
    if spec_id == "gdp_qoq":
        return ups.pct_change(s.pts("200Y104", "Q", ("1400",)), 1)
    if spec_id == "current_account":
        return ups.scale(s.pts("301Y013", "M", ("000000",)), 1e-3)                   # million USD -> billion USD
    if spec_id == "fx_reserves":
        return ups.scale(s.pts("732Y001", "M", ("99",)), 1e-6)                       # thousand USD -> billion USD
    if spec_id == "ccsi":
        return s.pts("511Y002", "M", ("FME",))
    if spec_id == "bsi":
        return s.pts("512Y013", "M", ("99988", "AA"))
    if spec_id == "household_credit":
        return ups.scale(s.pts("151Y001", "Q", ("1000000",)), 1e-3)                  # billion won -> trillion won
    if spec_id == "household_credit_yoy":
        return ups.pct_change(s.pts("151Y001", "Q", ("1000000",)), 4)
    if spec_id == "m2_yoy":
        return ups.pct_change(s.pts("161Y006", "M", ("BBHA00",)), 12)
    if spec_id == "m2_vs_2019":
        return ups.vs_base(s.pts("161Y006", "M", ("BBHA00",)), "2019-12-01")
    if spec_id == "bok_total_assets":
        return ups.scale(s.pts("103Y002", "M", ("BCAA1",)), 1e-3)
    if spec_id == "ktb_3y":
        return s.pts("817Y002", "D", ("010200000",), "last")
    if spec_id == "bond_10y":
        return s.pts("817Y002", "D", ("010210000",), "last")
    if spec_id == "corp_spread_aa":
        return jps.spread_bp(s.pts("817Y002", "D", ("010300000",), "last"), s.pts("817Y002", "D", ("010200000",), "last"))
    if spec_id == "cp_spread":
        return jps.spread_bp(s.pts("817Y002", "D", ("010503000",), "last"), s.pts("817Y002", "D", ("010400000",), "last"))
    if spec_id == "us_kr_rate_gap":
        return month_join(jps.month_last(s.fred("DFEDTARU")), s.pts("722Y001", "D", ("0101000",), "last"), lambda us, kr: (us - kr) * 100)
    if spec_id == "foreign_equity_kr":
        kospi, kosdaq = s.pts("802Y001", "D", ("0030000",), "sum"), s.pts("802Y001", "D", ("0113000",), "sum")
        return ups.scale(month_join(kospi, kosdaq, lambda a, b: a + b), 1e-4)      # 100 million won -> trillion won
    if spec_id == "semi_export_krw":
        usd, unit = s.kosis("127", "DT_092_115_2009_S023", "13102131003A.AF11100000", "반도체")
        return export_krw_tn(unit or "", usd, s.fred("EXKOUS"))
    if spec_id == "export_krw":
        usd, unit = s.ecos("901Y118", "M", ("T002",))
        return export_krw_tn(unit or "", usd, s.fred("EXKOUS"))
    raise KeyError(spec_id)


def build_patch(spec_id: str, points: Points, *, retrieved_at: str, today: date | None = None) -> dict[str, Any]:
    """A monthly figure is dated by its month end -- except the running month (the consumer survey of this
    month is out before the month is), which is dated by the run date, never by a day that has not happened."""
    spec = SPECS[spec_id]
    today_s = (today or date.today()).isoformat()
    daily = spec_id in DAILY_SOURCED
    patch = ups.build_patch(spec, points, retrieved_at=retrieved_at, asof=points[-1][0] if daily else None)
    if patch["asof"] > today_s:
        patch["asof"] = patch["observed_at"] = today_s
    if daily or patch["asof"] == today_s:
        jps.pin_last_date(patch, patch["asof"])
    return patch


def apply_all(kor: dict[str, Any], patches: dict[str, dict[str, Any]], *, retrieved_at: str) -> dict[str, Any]:
    """Apply the patches to the Korea block: rename the exports card first (a YoY rate becomes an amount
    in won), then the indicators, the GDP composite, chips, and the status counts."""
    for old, new in (("export_yoy_kr", "export_krw"), ("semi_export_yoy", "semi_export_krw")):
        if new in patches:
            rename_indicator(kor, old, new, {})
    by_id = {i["id"]: i for i in kor["indicators"]}
    changed = [k for k, p in patches.items() if k in by_id and ups.apply_patch(by_id[k], p)]
    if jps.apply_gdp_composite(by_id, retrieved_at, source="ecos:200Y106+200Y104"):
        changed.append("gdp")
    ups.sync_chips(kor, by_id, set(changed))
    before = dict(kor.get("data_status_summary") or {})
    ups.refresh_status_summary(kor)
    return {"changed": changed, "summary_changed": before != kor["data_status_summary"]}
