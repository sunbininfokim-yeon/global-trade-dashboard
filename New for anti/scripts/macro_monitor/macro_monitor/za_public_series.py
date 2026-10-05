"""South Africa: the SARB's own web API for the newest observations, FRED (OECD / IMF series) and the
World Bank Pink Sheet for the history behind them. All keyless.

SARB web API (the one its own site calls for the rates ticker):
  https://custom.resbank.co.za/SarbWebApi/WebIndicators/Shared/GetTimeseriesObservations/{code}
returns the latest 25 observations of a series -- 25 months of CPI, 25 quarters of GDP, but only 25
*days* of a daily rate. So:
  - every SARB answer is kept in config/za_sarb_series_v1.json and merged with what was kept before,
    which makes the short daily windows grow into a history over time, and keeps the cards when the
    site cannot be reached (its bot defence cuts off a client that asks too often; one run a day asks
    for about a dozen series, with a pause between them);
  - the history before those 25 points comes from FRED (OECD main economic indicators, IMF WEO) and
    the World Bank Pink Sheet.

How the two are joined, per card:
  - "override": the SARB number replaces FRED's for the same month (same published concept: CPI YoY,
    M3 YoY, the policy rate rebuilt from the dates it was changed);
  - "extend": FRED/Pink Sheet keep every month they have (monthly averages), SARB only adds the months
    after them -- its newest daily value, dated by its own day (10-year yield, gold).
A month that neither source has is left empty (None), never filled in.

Not here, and why: core CPI, SARB total assets, M3 level (only its growth rate is published in the API),
5-year CDS (paid), load shedding hours (EskomSePush needs a key), Absa PMI (proprietary), foreign
bond/equity flows (JSE / Treasury, no API found).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from . import jp_public_series as jps
from . import kr_public_series as krs
from . import us_public_series as ups
from .us_public_series import Points, Spec

SARB_OBS = "https://custom.resbank.co.za/SarbWebApi/WebIndicators/Shared/GetTimeseriesObservations/{code}"
WB_COMMODITY_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
UA = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"
SARB_CACHE = Path(__file__).resolve().parent.parent / "config" / "za_sarb_series_v1.json"
SARB_PAUSE_S = 2.0

ups._FORMATS.update({
    "pct2": lambda v: f"{v:.2f}%",
    "bn1zar": lambda v: f"-R{abs(v):,.1f}B" if v < 0 else f"R{v:,.1f}B",
    "usd0": lambda v: f"${v:,.0f}",
    "usd1": lambda v: f"${v:,.1f}",
    "hrs0": lambda v: f"{v:,.0f}시간",
})


class SarbUnavailable(RuntimeError):
    """SARB could not be read and nothing is cached for that series."""


# --------------------------------------------------------------------------
# Readers
# --------------------------------------------------------------------------

def parse_sarb(doc: Any) -> Points:
    """[{'Period': '2026-08-31T00:00:00', 'Value': 4.4, ...}, ...] (newest first) -> ascending points."""
    if not isinstance(doc, list):
        raise ValueError(f"unexpected SARB answer: {str(doc)[:80]!r}")
    out: Points = []
    for row in doc:
        v = row.get("Value")
        p = str(row.get("Period") or "")[:10]
        if v is None or len(p) != 10:
            continue
        out.append((p, float(v)))
    if not out:
        raise ValueError("SARB answer has no observations")
    return sorted(out)


def fetch_sarb(code: str, tries: int = 2) -> Points:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(SARB_OBS.format(code=code), headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                return parse_sarb(json.loads(resp.read().decode("utf-8")))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"SARB {code}: {last}")


def load_cache(path: Path = SARB_CACHE) -> dict[str, Any]:
    if not path.exists():
        return {"series": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def merge_points(old: Points, new: Points) -> Points:
    """Union by date; the newer answer wins a date both have (a revision)."""
    by = dict(old)
    by.update(new)
    return sorted(by.items())


def sarb_reader(cache: dict[str, Any], updates: dict[str, Points], fetch: Callable[[str], Points] = fetch_sarb,
                pause: float = SARB_PAUSE_S) -> Callable[[str], Points]:
    """Live answer merged into the cache; the cache alone when SARB cannot be reached."""
    series = cache.setdefault("series", {})
    first = [True]

    def read(code: str) -> Points:
        kept = [tuple(p) for p in series.get(code, [])]
        if not first[0]:
            time.sleep(pause)
        first[0] = False
        try:
            live = fetch(code)
        except Exception as exc:  # noqa: BLE001 -- fall back to what was kept
            if kept:
                return kept
            raise SarbUnavailable(f"SARB {code}: {exc}") from exc
        merged = merge_points(kept, live)
        if merged != kept:
            updates[code] = merged
        return merged
    return read


def save_cache(cache: dict[str, Any], updates: dict[str, Points], retrieved_at: str, path: Path = SARB_CACHE,
               force: bool = False) -> bool:
    if not updates and not force:
        return False
    for code, pts in updates.items():
        cache.setdefault("series", {})[code] = [[d, v] for d, v in pts]
    cache["source"] = "SARB web API (GetTimeseriesObservations), accumulated; see za_public_series.py"
    cache["retrieved_at"] = retrieved_at
    cache["series"] = dict(sorted(cache.setdefault("series", {}).items()))
    if "eskom_mlr_days" in cache:
        cache["eskom_mlr_days"] = dict(sorted(cache["eskom_mlr_days"].items()))
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


def pink_sheet_url(page_html: str) -> str:
    """The monthly-prices workbook changes address every month; take the one the page links today."""
    m = re.findall(r'https?://[^"\'\s]*CMO-Historical-Data-Monthly[^"\'\s]*\.xlsx', page_html)
    if not m:
        raise ValueError("World Bank commodity page has no CMO-Historical-Data-Monthly.xlsx link")
    return m[0]


def parse_pink_sheet(xlsx: bytes) -> dict[str, Points]:
    """{column title: [(YYYY-MM-01, $)]} from the 'Monthly Prices' sheet (rows '2026M08'; '…' = none)."""
    import openpyxl  # only this reader needs it; installed in the refresh workflow

    ws = openpyxl.load_workbook(BytesIO(xlsx), read_only=True, data_only=True)["Monthly Prices"]
    rows = list(ws.iter_rows(values_only=True))
    header = next((r for r in rows if r and any(isinstance(c, str) and c.strip() == "Gold" for c in r)), None)
    if header is None:
        raise ValueError("Pink Sheet has no header row with 'Gold'")
    out: dict[str, Points] = {}
    for r in rows:
        k = r[0] if r else None
        if not (isinstance(k, str) and re.fullmatch(r"\d{4}M\d{2}", k)):
            continue
        d = f"{k[:4]}-{k[5:7]}-01"
        for j, title in enumerate(header):
            if isinstance(title, str) and isinstance(r[j], (int, float)):
                out.setdefault(title.strip(), []).append((d, float(r[j])))
    return out


def fetch_pink_sheet() -> dict[str, Points]:
    page = jps._get(WB_COMMODITY_PAGE).decode("utf-8", "replace")
    return parse_pink_sheet(jps._get(pink_sheet_url(page), timeout=120))


# --------------------------------------------------------------------------
# Joining and transforms
# --------------------------------------------------------------------------

def month_key(iso: str) -> str:
    return f"{iso[:7]}-01"


def to_monthly(points: Points) -> tuple[Points, str | None]:
    """One point per month (the month's last observation, keyed YYYY-MM-01) and the date of the
    newest observation itself."""
    by: dict[str, float] = {}
    for d, v in sorted(points):
        by[month_key(d)] = v
    return sorted(by.items()), (max(points)[0] if points else None)


def to_quarterly(points: Points) -> Points:
    """Quarter-end dated points -> keyed by the quarter's first month (the FRED convention)."""
    out = []
    for d, v in points:
        m = (int(d[5:7]) - 1) // 3 * 3 + 1
        out.append((f"{d[:4]}-{m:02d}-01", v))
    return sorted(out)


def to_annual(points: Points) -> Points:
    return sorted((f"{d[:4]}-01-01", v) for d, v in points)


def join(history: Points, recent: Points, mode: str) -> Points:
    """'override': recent replaces history on the dates both have; 'extend': recent only adds dates
    after the last history date."""
    if mode == "override":
        return merge_points(history, recent)
    if mode == "extend":
        cut = history[-1][0] if history else ""
        return sorted(history + [(d, v) for d, v in recent if d > cut])
    raise ValueError(mode)


def _step(y: int, m: int, months: int) -> tuple[int, int]:
    t = y * 12 + (m - 1) + months
    return t // 12, t % 12 + 1


def with_gaps(points: Points, months: int = 1) -> list[tuple[str, float | None]]:
    """Insert None for every missing month (quarter: months=3, year: 12) between the first and the last
    point, so a chart shows the hole instead of closing it."""
    if not points:
        return []
    by = dict(points)
    y, m = int(points[0][0][:4]), int(points[0][0][5:7])
    end = points[-1][0]
    out: list[tuple[str, float | None]] = []
    while True:
        d = f"{y:04d}-{m:02d}-01"
        if d > end:
            break
        out.append((d, by.get(d)))
        y, m = _step(y, m, months)
    return out


def step_monthly(changes: Points, today: date) -> Points:
    """A rate that is set on decision days: its level at each month end (the running month: today),
    from the month of the first decision on."""
    if not changes:
        return []
    changes = sorted(changes)
    y, m = int(changes[0][0][:4]), int(changes[0][0][5:7])
    out: Points = []
    while (y, m) <= (today.year, today.month):
        edge = today.isoformat() if (y, m) == (today.year, today.month) else ups.month_end(f"{y:04d}-{m:02d}-01")
        in_force = [v for d, v in changes if d <= edge]
        if in_force:
            out.append((f"{y:04d}-{m:02d}-01", in_force[-1]))
        y, m = _step(y, m, 1)
    return out


def chain_yoy(qoq: Points) -> Points:
    """Four consecutive quarter-on-quarter changes compounded = the change on the same quarter a year
    earlier (exact for the same seasonally adjusted level). A quarter without its three predecessors
    gets no value."""
    by = dict(qoq)
    out: Points = []
    for d, _ in qoq:
        y, m = int(d[:4]), int(d[5:7])
        quarters = [f"{yy:04d}-{mm:02d}-01" for yy, mm in (_step(y, m, -3 * k) for k in range(4))]
        if all(q in by for q in quarters):
            f = 1.0
            for q in quarters:
                f *= 1 + by[q] / 100
            out.append((d, (f - 1) * 100))
    return out


# --------------------------------------------------------------------------
# Eskom: hours of manual load reduction (load shedding)
# --------------------------------------------------------------------------

ESKOM_CSV = ("https://www.eskom.co.za/dataportal/wp-content/uploads/{y:04d}/{m:02d}/"
             "Pumped_storage_gen_hours_gas_generation_and_manual_load_reduction.csv")


def fetch_eskom_csv(today: date) -> str:
    """The portal re-uploads the rolling file into the current month's folder (and its page can link an
    older one that is gone): try this month's folder, then the three before it."""
    y, m = today.year, today.month
    last: Exception | None = None
    for _ in range(4):
        try:
            return jps._get(ESKOM_CSV.format(y=y, m=m), tries=1).decode("utf-8-sig")
        except Exception as exc:  # noqa: BLE001
            last = exc
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    raise RuntimeError(f"Eskom MLR csv: {last}")


def parse_eskom_mlr(text: str) -> list[tuple[str, float]]:
    """Hourly rows 'YYYY-MM-DD HH:MM:SS, ..., Manual Load Reduction(MLR), ...' -> [(hour, MW)]."""
    import csv
    import io

    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows or "Date" not in rows[0]:
        raise ValueError(f"unexpected Eskom csv: {text[:60]!r}")
    col = next((i for i, h in enumerate(rows[0]) if h.strip().startswith("Manual Load Reduction")), None)
    if col is None:
        raise ValueError("Eskom csv has no Manual Load Reduction column")
    out = []
    for r in rows[1:]:
        if len(r) <= col or len(r[0]) < 13:
            continue
        try:
            out.append((r[0][:13], float(r[col] or 0)))
        except ValueError:
            continue
    if not out:
        raise ValueError("Eskom csv has no hourly rows")
    return out


def merge_mlr(cache: dict[str, Any], hourly: list[tuple[str, float]]) -> bool:
    """Per day two 24-character masks: hours observed, hours with load shedding (MLR > 0). A later file
    that covers the same hours only adds what was not seen; nothing is counted twice."""
    days: dict[str, list[str]] = cache.setdefault("eskom_mlr_days", {})
    changed = False
    for stamp, mw in hourly:
        day, hour = stamp[:10], int(stamp[11:13])
        seen, shed = days.get(day, ["0" * 24, "0" * 24])
        new_seen = seen[:hour] + "1" + seen[hour + 1:]
        new_shed = shed[:hour] + ("1" if mw > 0 or shed[hour] == "1" else "0") + shed[hour + 1:]
        if [new_seen, new_shed] != [seen, shed]:
            days[day] = [new_seen, new_shed]
            changed = True
    return changed


def mlr_monthly(cache: dict[str, Any]) -> tuple[Points, str | None]:
    """Load-shedding hours per month over the hours observed, and the last day observed."""
    days = cache.get("eskom_mlr_days") or {}
    if not days:
        raise ValueError("no Eskom hours kept yet")
    by: dict[str, float] = {}
    for day, (seen, shed) in sorted(days.items()):
        key = day[:7] + "-01"
        by[key] = by.get(key, 0) + shed.count("1")
    return sorted(by.items()), max(days)


def mlr_coverage(cache: dict[str, Any], month: str) -> int:
    """Days of `month` (YYYY-MM) with at least one hour observed."""
    return sum(1 for d, (seen, _) in (cache.get("eskom_mlr_days") or {}).items() if d.startswith(month) and "1" in seen)


# --------------------------------------------------------------------------
# What each card is made of
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ZaSpec:
    spec: Spec
    sarb_codes: tuple[str, ...] = ()
    fred_ids: tuple[str, ...] = ()
    pink: str | None = None
    gap_months: int = 1
    daily_latest: bool = False           # the newest point is a daily observation: dated by its own day
    extra: dict[str, Any] = field(default_factory=dict)


SARB_PAGE = "https://www.resbank.co.za/en/home/what-we-do/statistics/key-statistics/current-market-rates"
_FRED = "https://fred.stlouisfed.org/series/"


def _s(id_: str, cadence: str, unit: str, fmt: str, label: str, note: str, source: str, urls: tuple[str, ...],
       tier: str = "monthly") -> Spec:
    return Spec(id_, cadence, unit, fmt, note, source, urls, tier, label_ko=label)


SPECS: dict[str, ZaSpec] = {z.spec.id: z for z in [
    ZaSpec(_s("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
              "소비자물가(전 도시) 전년 동월 대비입니다. 최근 25개월은 SARB 웹 API(CPI1000F, 통계청 발표치), 그 이전은 OECD 소비자물가지수(FRED ZAFCPIALLMINMEI)로 계산했습니다. 인플레 목표 3~6%.",
              "sarb:CPI1000F+fred:ZAFCPIALLMINMEI", (SARB_PAGE, _FRED + "ZAFCPIALLMINMEI")),
           sarb_codes=("CPI1000F",), fred_ids=("ZAFCPIALLMINMEI",)),
    ZaSpec(_s("sarb_repo", "monthly", "%", "pct2", "SARB 정책금리",
              "SARB 정책금리(월말 기준)입니다. 2018-11 이후는 SARB가 공개하는 금리 변경일 이력(MRDREPOR)으로 각 달 말 적용 금리를 그대로 옮겼고, 그 이전은 OECD 중앙은행 금리(FRED IRSTCB01ZAM156N)입니다. 최신값은 SARB 일별(MMRD002A). 인플레 타겟 3–6% · 자본유출 방어.",
              "sarb:MRDREPOR+MMRD002A+fred:IRSTCB01ZAM156N", (SARB_PAGE, _FRED + "IRSTCB01ZAM156N")),
           sarb_codes=("MRDREPOR", "MMRD002A"), fred_ids=("IRSTCB01ZAM156N",), daily_latest=True),
    ZaSpec(_s("sagb_10y", "monthly", "%", "pct2", "SAGB 10년",
              "10년 국채 수익률입니다. 과거는 OECD 장기국채 수익률 월평균(FRED IRLTLT01ZAM156N), 그 뒤 달은 SARB의 '만기 10년 이상 국채 일평균 수익률'(CMJD004A) 최신 일자 값입니다(월평균 아님). 장기 조달비용 · 재정건전성 평가.",
              "fred:IRLTLT01ZAM156N+sarb:CMJD004A", (_FRED + "IRLTLT01ZAM156N", SARB_PAGE)),
           sarb_codes=("CMJD004A",), fred_ids=("IRLTLT01ZAM156N",), daily_latest=True),
    ZaSpec(_s("unemployment", "quarterly", "%", "pct1", "실업률",
              "15~64세 실업률(분기, 계절조정; 통계청 QLFS 공식 정의)입니다. OECD(FRED LRUN64TTZAQ156S). 구조적 장기실업(~30%대) — 미국식 완전고용 프레임은 거의 무의미합니다.",
              "fred:LRUN64TTZAQ156S", (_FRED + "LRUN64TTZAQ156S",), "quarterly"),
           fred_ids=("LRUN64TTZAQ156S",), gap_months=3),
    ZaSpec(_s("gdp_qoq", "quarterly", "%", "pct1", "실질GDP QoQ",
              "실질GDP 전기 대비(계절조정, 연율 아님)입니다. OECD(FRED NAEXKP01ZAQ657S).",
              "fred:NAEXKP01ZAQ657S", (_FRED + "NAEXKP01ZAQ657S",), "quarterly"),
           fred_ids=("NAEXKP01ZAQ657S",), gap_months=3),
    ZaSpec(_s("gdp_yoy", "quarterly", "%", "pct1", "실질GDP YoY",
              "실질GDP 전년 동기 대비입니다. 같은 계절조정 시계열의 전기 대비 4분기를 누적해 계산했습니다(OECD, FRED NAEXKP01ZAQ657S) — 원계열 기준 통계청 발표치와 소수점 차이가 날 수 있습니다.",
              "fred:NAEXKP01ZAQ657S(4Q)", (_FRED + "NAEXKP01ZAQ657S",), "quarterly"),
           fred_ids=("NAEXKP01ZAQ657S",), gap_months=3, extra={"chain_yoy": True}),
    ZaSpec(_s("m3_yoy_za", "monthly", "%", "pct1", "M3 전년비",
              "광의통화 M3 전년 동월 대비입니다. 최근 25개월은 SARB(MON0300P), 그 이전은 OECD M3(FRED MABMM301ZAM189S)로 계산했습니다. OECD 시계열이 2023-11에서 끊겨 그 사이 달은 비워 둡니다.",
              "sarb:MON0300P+fred:MABMM301ZAM189S", (SARB_PAGE, _FRED + "MABMM301ZAM189S")),
           sarb_codes=("MON0300P",), fred_ids=("MABMM301ZAM189S",)),
    ZaSpec(_s("fiscal_deficit_gdp", "annual", "%", "pct1", "재정수지/GDP",
              "중앙정부 재정수지/GDP(%, 회계연도)입니다. 적자면 음수. SARB(KBP4420J).",
              "sarb:KBP4420J", (SARB_PAGE,), "annual"),
           sarb_codes=("KBP4420J",), gap_months=12),
    ZaSpec(_s("debt_to_gdp", "annual", "%", "pct1", "국가부채/GDP",
              "일반정부 총부채/GDP(%)입니다. IMF 세계경제전망(FRED GGGDTAZAA188N). 신용등급 핵심 변수.",
              "fred:GGGDTAZAA188N", (_FRED + "GGGDTAZAA188N",), "annual"),
           fred_ids=("GGGDTAZAA188N",), gap_months=12),
    ZaSpec(_s("current_account", "quarterly", "bn_zar", "bn1zar", "경상수지(연율)",
              "경상수지(계절조정·연율, 십억 랜드)입니다. SARB(KBP5007L, 최근 25분기). 달러가 아니라 랜드 기준입니다.",
              "sarb:KBP5007L", (SARB_PAGE,), "quarterly"),
           sarb_codes=("KBP5007L",), gap_months=3),
    ZaSpec(_s("trade_balance", "monthly", "bn_zar", "bn1zar", "무역수지",
              "상품 무역수지(월, 계절조정, 십억 랜드)입니다. OECD(FRED XTNTVA01ZAM664S). 원자재 수출 − 에너지 수입.",
              "fred:XTNTVA01ZAM664S", (_FRED + "XTNTVA01ZAM664S",)),
           fred_ids=("XTNTVA01ZAM664S",)),
    ZaSpec(_s("gold_price", "monthly", "usd_oz", "usd0", "금 가격",
              "금 가격(달러/온스)입니다. 과거는 세계은행 Pink Sheet 월평균, 그 뒤 달은 SARB의 런던 금 가격(GDPL201D) 최신 일자 값입니다. 남아공의 주력 수출 원자재.",
              "worldbank:pinksheet+sarb:GDPL201D", ("https://www.worldbank.org/en/research/commodity-markets", SARB_PAGE)),
           sarb_codes=("GDPL201D",), pink="Gold", daily_latest=True),
    ZaSpec(_s("platinum_price", "monthly", "usd_oz", "usd0", "백금 가격",
              "백금 가격(달러/온스, 월평균)입니다. 세계은행 Pink Sheet. 남아공이 세계 공급 대부분을 차지하는 수출 원자재.",
              "worldbank:pinksheet", ("https://www.worldbank.org/en/research/commodity-markets",)),
           pink="Platinum"),
    ZaSpec(_s("foreign_equity_flow_za", "monthly", "bn_zar", "bn1zar", "외국인 주식순매수",
              "비거주자의 JSE 주식 순매수(월, 십억 랜드; 음수는 순매도)입니다. SARB 월간 자본시장 통계(CAPM311A). SARB가 최근 25개월만 공개해 그 이전 이력은 매일 쌓아 가며 늘어납니다.",
              "sarb:CAPM311A", (SARB_PAGE,)),
           sarb_codes=("CAPM311A",)),
    ZaSpec(_s("load_shedding_hours", "monthly", "hours", "hrs0", "Load Shedding",
              "Eskom 데이터 포털의 '수동 부하 감축(MLR)'이 0보다 큰 시간 수(월)입니다 — 순환정전이 실제로 시행된 시간. 포털이 최근 약 9일치만 공개해 2026-09-14부터 매일 쌓고 있고, 그 이전 이력은 Eskom 데이터 요청 양식으로만 받을 수 있어 싣지 않았습니다.",
              "eskom:dataportal:MLR", ("https://www.eskom.co.za/dataportal/supply-side/pumped-storage-generating-hours-gas-generation-and-manual-load-reduction/",)),
           ),
    ZaSpec(_s("coal_price", "monthly", "usd_t", "usd1", "석탄 가격",
              "남아공 석탄(리처즈베이 FOB, 달러/톤, 월평균)입니다. 세계은행 Pink Sheet 'Coal, South African'.",
              "worldbank:pinksheet", ("https://www.worldbank.org/en/research/commodity-markets",)),
           pink="Coal, South African **"),
]}

JOIN = {"cpi_yoy": "override", "sarb_repo": "override", "m3_yoy_za": "override",
        "sagb_10y": "extend", "gold_price": "extend"}
SCALE = {"current_account": 1e-3, "trade_balance": 1e-9, "foreign_equity_flow_za": 1e-3}   # R million -> R bn; Rand -> R bn


@dataclass
class Sources:
    sarb: Callable[[str], Points]
    fred: Callable[[str], Points] = ups.fetch_fred
    pink: Callable[[], dict[str, Points]] = lambda: fetch_pink_sheet()
    today: date = field(default_factory=date.today)
    cache: dict[str, Any] = field(default_factory=dict)       # the SARB cache; the Eskom hours are kept in it too
    eskom: Callable[[date], str] = lambda today: fetch_eskom_csv(today)
    eskom_changed: bool = False
    _pink: dict[str, Points] | None = None

    def pink_series(self, title: str) -> Points:
        if self._pink is None:
            self._pink = self.pink()
        return self._pink[title]


def series_for(spec_id: str, src: Sources) -> tuple[list[tuple[str, float | None]], str | None]:
    """(points with gaps as None, date of the newest observation when it is a day inside the month)."""
    z = SPECS[spec_id]
    last_day: str | None = None
    if spec_id == "cpi_yoy":
        pts = join(ups.pct_change(src.fred("ZAFCPIALLMINMEI"), 12), to_monthly(src.sarb("CPI1000F"))[0], "override")
    elif spec_id == "sarb_repo":
        before = src.fred("IRSTCB01ZAM156N")
        decided = step_monthly(src.sarb("MRDREPOR"), src.today)
        pts = join(before, decided, "override")
        daily = src.sarb("MMRD002A")
        last_day = daily[-1][0]
        if pts and last_day[:7] == pts[-1][0][:7]:
            pts[-1] = (pts[-1][0], daily[-1][1])
    elif spec_id == "sagb_10y":
        monthly, last_day = to_monthly(src.sarb("CMJD004A"))
        pts = join(src.fred("IRLTLT01ZAM156N"), monthly, "extend")
        if pts[-1][0][:7] != last_day[:7]:
            last_day = None
    elif spec_id == "gold_price":
        monthly, last_day = to_monthly(src.sarb("GDPL201D"))
        pts = join(src.pink_series("Gold"), monthly, "extend")
        if pts[-1][0][:7] != last_day[:7]:
            last_day = None
    elif spec_id == "m3_yoy_za":
        pts = join(ups.pct_change(src.fred("MABMM301ZAM189S"), 12), to_monthly(src.sarb("MON0300P"))[0], "override")
    elif spec_id == "gdp_yoy":
        pts = chain_yoy(src.fred("NAEXKP01ZAQ657S"))
    elif spec_id == "fiscal_deficit_gdp":
        pts = to_annual(src.sarb("KBP4420J"))
    elif spec_id == "current_account":
        pts = to_quarterly(src.sarb("KBP5007L"))
    elif spec_id == "foreign_equity_flow_za":
        pts = to_monthly(src.sarb("CAPM311A"))[0]
    elif spec_id == "load_shedding_hours":
        src.eskom_changed |= merge_mlr(src.cache, parse_eskom_mlr(src.eskom(src.today)))
        pts, last_day = mlr_monthly(src.cache)
    elif z.pink:
        pts = src.pink_series(z.pink)
    elif z.fred_ids:
        pts = src.fred(z.fred_ids[0])
    else:
        raise KeyError(spec_id)
    if spec_id in SCALE:
        pts = ups.scale(pts, SCALE[spec_id])
    return with_gaps(pts, z.gap_months), last_day


def build_patch(spec_id: str, points: list[tuple[str, float | None]], last_day: str | None, *,
                retrieved_at: str, cache: dict[str, Any] | None = None) -> dict[str, Any]:
    patch = ups.build_patch(SPECS[spec_id].spec, points, retrieved_at=retrieved_at, asof=last_day)
    if last_day:
        jps.pin_last_date(patch, last_day)
    if spec_id == "load_shedding_hours" and cache is not None and last_day:
        month = last_day[:7]
        patch["note_ko"] += f" 이번 달({month})은 관측된 {mlr_coverage(cache, month)}일 기준입니다."
    return patch


def apply_all(zaf: dict[str, Any], patches: dict[str, dict[str, Any]], *, retrieved_at: str) -> dict[str, Any]:
    by_id = {i["id"]: i for i in zaf["indicators"]}
    changed = [k for k, p in patches.items() if k in by_id and ups.apply_patch(by_id[k], p)]
    for k in changed:
        by_id[k].pop("analog_ko", None)
    if jps.apply_gdp_composite(by_id, retrieved_at, source="fred:NAEXKP01ZAQ657S"):
        changed.append("gdp")
    ups.sync_chips(zaf, by_id, set(changed))
    units = krs.sync_chip_units(zaf, by_id, {k for k in patches if k in by_id})
    before = dict(zaf.get("data_status_summary") or {})
    ups.refresh_status_summary(zaf)
    return {"changed": changed, "summary_changed": units or before != zaf["data_status_summary"]}
