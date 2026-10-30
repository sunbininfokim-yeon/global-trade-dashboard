"""Hormuz unobserved-flow reconstruction: an identifiability engine.

Implements HORMUZ_UNOBSERVED_FLOW_RESEARCH.md. It publishes only what free
inputs actually identify, and hold/null plus the blocking terms for the rest:

- Candidate A, Gulf of Oman maritime control-zone mass balance. The interval
  arithmetic is real, but it runs only when every term comes from a
  same-commodity, same-period, same-boundary cumulative-barrel input. Each
  term's free candidates are evaluated and the reason they do not qualify is
  published.
- Candidate B, delayed monthly external verification: producer crude exports
  (JODI-Oil) and importer crude receipts (UN Comtrade monthly, keyless
  preview). An origin is grouped only if its seaborne crude cannot leave the
  Gulf without transiting Hormuz, and a group is summed only when every
  member reported.
- Copernicus Sentinel-1 acquisition metadata over the strait: imaging
  coverage evidence only. No image download, ship detection or AIS matching.

Never computed here: a 62% dark-share correction (Q_visible / 0.38), an
IEA-minus-EIA "unobserved" volume, tonnes-to-barrels conversion, a zero for a
country that did not report, or a monthly value copied onto days.
"""

from __future__ import annotations

import calendar
import copy
import csv
import io
import json
import math
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable


CONTRACT_VERSION = "hormuz-reconstruction-v1"
METHOD_DOCUMENT = "New for anti/scripts/shipping_capacity/HORMUZ_UNOBSERVED_FLOW_RESEARCH.md"
USER_AGENT = "Chokemonitor/1.0 public-reference-collector"

JODI_DOWNLOADS_URL = "https://www.jodidata.org/oil/database/data-downloads.aspx"
JODI_TERMS_URL = "https://www.jodidata.org/terms-of-use.aspx"
JODI_ASSESSMENT_URL = "https://www.jodidata.org/oil/support/user-guide/assessments.aspx"
COMTRADE_PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
COMTRADE_TERMS_URL = "https://comtrade.un.org/licenseagreement.html"
STAC_SEARCH_URL = "https://stac.dataspace.copernicus.eu/v1/search"
SENTINEL_TERMS_URL = "https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice"

# Same reproducible box as the research note: the strait between Musandam and
# the Iranian coast. It is not the whole Gulf of Oman control zone.
SAR_BBOX = (55.8, 25.9, 57.4, 27.0)
SAR_WINDOW_DAYS = 30
SAR_GRID_STEP_DEG = 0.05
SAR_FULL_COVERAGE = 0.9
JODI_MONTHS = 6
COMTRADE_MONTHS = 6

# Route class is geography, not a share estimate: it only says whether an
# origin's seaborne crude *can* leave the Gulf without transiting the strait.
PRODUCERS: dict[str, dict[str, Any]] = {
    "KW": {"name_ko": "쿠웨이트", "comtrade_code": 414, "route_class": "hormuz_only_seaborne",
           "route_note_ko": "원유 선적항이 모두 페르시아만 안쪽이고, 해협을 피하는 수출 파이프라인이 없다."},
    "QA": {"name_ko": "카타르", "comtrade_code": 634, "route_class": "hormuz_only_seaborne",
           "route_note_ko": "원유·콘덴세이트 선적항(라스라판·메사이드)이 만 안쪽이고 우회 파이프라인이 없다."},
    "BH": {"name_ko": "바레인", "comtrade_code": 48, "route_class": "hormuz_only_seaborne",
           "route_note_ko": "선적항(시트라)이 만 안쪽이다. 생산 일부는 사우디와 공유하는 유전에서 나온다."},
    "IQ": {"name_ko": "이라크", "comtrade_code": 368, "route_class": "bypass_capable",
           "route_note_ko": "남부 바스라 선적은 해협을 지나지만, 북부 키르쿠크–제이한 파이프라인은 지중해로 나간다."},
    "IR": {"name_ko": "이란", "comtrade_code": 364, "route_class": "bypass_capable",
           "route_note_ko": "하르그 등 만 안쪽 선적 외에, 고레–자스크 파이프라인으로 오만만 자스크에서 선적할 수 있다."},
    "SA": {"name_ko": "사우디아라비아", "comtrade_code": 682, "route_class": "bypass_capable",
           "route_note_ko": "라스타누라·주아이마(만 안쪽) 외에, 동서 파이프라인으로 홍해 얀부에서 선적한다."},
    "AE": {"name_ko": "아랍에미리트", "comtrade_code": 784, "route_class": "bypass_capable",
           "route_note_ko": "만 안쪽 선적 외에, ADCOP 파이프라인으로 오만만 푸자이라에서 선적한다."},
    "OM": {"name_ko": "오만", "comtrade_code": 512, "route_class": "outside_strait",
           "route_note_ko": "주 선적항(미나 알파할)이 오만만에 있어 해협을 지나지 않는다. 두쿰 등 아라비아해 터미널도 있다."},
}
ROUTE_CLASS_LABELS_KO = {
    "hormuz_only_seaborne": "해협 외 수출로 없음",
    "bypass_capable": "우회 수출로 있음 · 원산지만으로 통과 판정 불가",
    "outside_strait": "해협 밖 선적",
}
IMPORTERS: dict[str, dict[str, Any]] = {
    "JP": {"name_ko": "일본", "comtrade_code": 392},
    "IN": {"name_ko": "인도", "comtrade_code": 699},
    "KR": {"name_ko": "한국", "comtrade_code": 410},
    "CN": {"name_ko": "중국", "comtrade_code": 156},
}
JODI_ASSESSMENT_KO = {
    "1": "JODI 평가: 다른 출처와 비교 가능 수준",
    "2": "JODI 평가: 메타데이터 확인 필요",
    "3": "JODI 평가: 미평가",
}

# Candidate A terms, signed as in the research note:
#   hormuz inflow = departures + local discharge + inventory increase
#                   - local loading (ex bypass) - bypass loading - other inflow
LEDGER_TERMS: tuple[dict[str, Any], ...] = (
    {"id": "open_sea_departures", "sign": 1, "role": "outflow",
     "label_ko": "외해 출항 (오만만 → 아라비아해)",
     "required_ko": "통제 구역 외곽 경계를 넘는 원유 적재 선박의 기간 누적 배럴(항차·적재량 기반)",
     "unlock_ko": "외곽 경계 통과 항차별 적재량. 무료 공개 자료에는 없고 PortWatch에도 이 경계의 게이트가 없다."},
    {"id": "local_discharge_consumption", "sign": 1, "role": "outflow",
     "label_ko": "구역 내 하역·소비",
     "required_ko": "구역 안 항만에서 하역된 원유의 기간 누적 배럴",
     "unlock_ko": "오만·UAE 동해안 정유소의 월간 원유 투입·입항 하역 실적."},
    {"id": "zone_inventory_change", "sign": 1, "role": "outflow",
     "label_ko": "구역 내 적재 선박 재고 증가",
     "required_ko": "기간 말과 기간 초 구역 안 적재 선박 화물량의 차(장기 정박 포함)",
     "unlock_ko": "구역 내 부유 저장·대기 선박 재고. 무료 시계열 없음."},
    {"id": "local_loading_excluding_bypass", "sign": -1, "role": "other_inflow",
     "label_ko": "현지 항만 선적 (우회분 제외)",
     "required_ko": "구역 안 항만에서 선적된, 해협을 지나지 않은 원유의 기간 누적 배럴",
     "unlock_ko": "미나 알파할 등 오만만 터미널별 월간 선적량. 국가 총수출은 아라비아해 터미널을 섞는다."},
    {"id": "bypass_port_loading", "sign": -1, "role": "other_inflow",
     "label_ko": "우회항 선적 (푸자이라·자스크)",
     "required_ko": "ADCOP·고레–자스크 파이프라인으로 와 선적된 원유의 기간 누적 배럴(현지 선적과 중복 없음)",
     "unlock_ko": "푸자이라·자스크 터미널 실제 선적량. 파이프라인 정격 용량은 실제 유량이 아니라 쓰지 않는다."},
    {"id": "other_maritime_inflow", "sign": -1, "role": "other_inflow",
     "label_ko": "다른 해상 유입 (아라비아해 → 구역)",
     "required_ko": "외해에서 구역으로 들어온 원유 적재 선박의 기간 누적 배럴",
     "unlock_ko": "외곽 경계 유입 항차별 적재량. 출항 항과 같은 자료가 필요하다."},
)
CONFIRMED_TERM: dict[str, Any] = {
    "id": "confirmed_transit_cargo", "label_ko": "확인된 해협 통과 화물 (같은 경계·기간·품목)",
    "required_ko": "해협 통과가 항차 단위로 확인된 원유의 기간 누적 배럴",
    "unlock_ko": "항차별 확인 화물량. PortWatch 일별 값은 선종별 톤이고 AIS 송신 선박만 센다.",
}

IDENTIFIABILITY = {
    "formula": "Q_total = Q_visible × (1 + p × r / (1 − p))",
    "terms": [
        {"id": "p_dark_vessel_share", "label_ko": "AIS 미포착 선박 비율 p", "value": None, "status": "unverified",
         "note_ko": "‘탱커 62% AIS 미송신’ 주장은 원출처의 표본·기간·분모(척수/화물량)를 확인하지 못해 쓰지 않는다."},
        {"id": "r_cargo_ratio", "label_ko": "미포착/포착 선박 평균 화물량 비 r", "value": None, "status": "no_source",
         "note_ko": "p가 검증돼도 r이 없으면 화물량은 식별되지 않는다."},
        {"id": "q_visible", "label_ko": "포착 화물량 Q_visible", "value": None, "status": "unit_mismatch",
         "note_ko": "PortWatch 값은 선종별 추정 톤이며 원유 배럴이 아니다."},
    ],
    "result": None,
    "status": "not_identified",
    "note_ko": "설명용 식이다. p와 r이 없으므로 계산하지 않는다.",
}
REJECTED_SHORTCUTS = [
    {"id": "dark_share_62pct", "label_ko": "관측 배럴 ÷ 0.38 (62% 미송신 보정)",
     "reason_ko": "원출처의 표본·기간·분모를 확인하지 못했다."},
    {"id": "portwatch_over_eia", "label_ko": "PortWatch 변화율 ÷ EIA 정상 수준",
     "reason_ko": "선종 톤과 석유 배럴, 일별과 분기 평균이 달라 식별되지 않는다."},
    {"id": "iea_minus_eia", "label_ko": "IEA 8월 값 − EIA 2분기 값 = 미포착",
     "reason_ko": "다른 기관·기간·방법의 차이다. 미포착 물량이 아니다."},
    {"id": "pipeline_capacity", "label_ko": "우회 파이프라인 정격 용량 차감",
     "reason_ko": "정격 용량은 실제 수출 유량이 아니다."},
    {"id": "price_insurance_inverse", "label_ko": "유가·보험료·용선료로 통항량 역산",
     "reason_ko": "다른 원인이 섞여 단독 역산이 불가능하다. 맥락 자료로만 쓴다."},
    {"id": "official_as_bound", "label_ko": "공식 발표 = 상한, AIS = 하한 자동 구간",
     "reason_ko": "정의·기간이 같은지 검증하기 전에는 서로 다른 참고값일 뿐이다."},
]

Fetcher = Callable[[str], bytes]


# ----------------------------------------------------------------- fetching

def _limits_for(url: str) -> tuple[str, int]:
    host = urllib.parse.urlparse(url).hostname or ""
    if url.endswith(".csv"):
        # JODI answers 406 to `Accept: text/csv` for its own CSV files.
        return "*/*", 40_000_000
    if host.endswith("jodidata.org"):
        return "text/html", 2_000_000
    return "application/json", 8_000_000


def fetch_bytes(url: str) -> bytes:
    accept, max_bytes = _limits_for(url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(request, timeout=45) as response:
        if urllib.parse.urlparse(response.geturl()).hostname != urllib.parse.urlparse(url).hostname:
            raise ValueError("source redirected outside its publisher host")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("source response exceeds size limit")
        return body


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _month_bounds(period: str) -> tuple[date, date]:
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", period):
        raise ValueError("unsupported monthly period")
    year, month = int(period[:4]), int(period[5:])
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _previous_months(today: date, count: int) -> list[str]:
    """The `count` complete months before `today`, oldest first."""
    year, month = today.year, today.month
    periods = []
    for _ in range(count):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        periods.append(f"{year}-{month:02d}")
    return periods[::-1]


# --------------------------------------------------------------- JODI-Oil

JODI_LINK = re.compile(
    r'href="(?P<href>/_resources/files/downloads/oil-data/annual-csv/primary/(?:primaryyear)?(?P<year>20\d{2})\.csv)"'
)
JODI_COLUMNS = {"REF_AREA", "TIME_PERIOD", "ENERGY_PRODUCT", "FLOW_BREAKDOWN", "UNIT_MEASURE", "OBS_VALUE", "ASSESSMENT_CODE"}


def discover_jodi_files(html: str) -> dict[int, str]:
    files = {int(match["year"]): urllib.parse.urljoin(JODI_DOWNLOADS_URL, match["href"]) for match in JODI_LINK.finditer(html)}
    if not files:
        raise ValueError("JODI primary annual CSV links missing")
    return files


def parse_jodi_csv(text: str) -> dict[tuple[str, str], dict[str, Any]]:
    """Gulf producers' crude exports (TOTEXPSB, kb/d). '-' stays not reported."""
    reader = csv.DictReader(io.StringIO(text))
    if not JODI_COLUMNS <= set(reader.fieldnames or []):
        raise ValueError("JODI CSV columns changed")
    observations: dict[tuple[str, str], dict[str, Any]] = {}
    for row in reader:
        if (row["REF_AREA"] not in PRODUCERS or row["ENERGY_PRODUCT"] != "CRUDEOIL"
                or row["FLOW_BREAKDOWN"] != "TOTEXPSB" or row["UNIT_MEASURE"] != "KBD"):
            continue
        period = row["TIME_PERIOD"].strip()
        _month_bounds(period)
        raw = (row["OBS_VALUE"] or "").strip()
        value = None if raw in ("", "-", "x", "..") else float(raw)
        if value is not None and (not math.isfinite(value) or not 0 <= value <= 20_000):
            raise ValueError("invalid JODI crude export value")
        key = (row["REF_AREA"], period)
        record = {"value": value, "assessment_code": (row["ASSESSMENT_CODE"] or "").strip() or None}
        if key in observations and observations[key]["value"] != value:
            raise ValueError("conflicting JODI rows for one country-month")
        observations[key] = record
    if not observations:
        raise ValueError("JODI CSV has no Gulf crude export rows")
    return observations


def collect_jodi(fetcher: Fetcher, today: date) -> dict[str, Any]:
    files = discover_jodi_files(fetcher(JODI_DOWNLOADS_URL).decode("utf-8", errors="replace"))
    years = sorted((year for year in files if year <= today.year), reverse=True)
    if not years:
        raise ValueError("JODI has no current or past annual file")
    observations: dict[tuple[str, str], dict[str, Any]] = {}
    used = []
    for year in years[:2]:
        parsed = parse_jodi_csv(fetcher(files[year]).decode("utf-8-sig", errors="replace"))
        observations.update({key: value for key, value in parsed.items() if key not in observations})
        used.append(files[year])
        reported_months = {period for (_, period), row in observations.items() if row["value"] is not None}
        if len(reported_months) >= JODI_MONTHS:
            break
    return {
        "observations": [
            {"iso2": iso2, "period": period, **row}
            for (iso2, period), row in sorted(observations.items())
        ],
        "files": used,
    }


def build_producer_exports(jodi: dict[str, Any]) -> dict[str, Any]:
    observations = {(row["iso2"], row["period"]): row for row in jodi.get("observations", [])}
    reported = sorted({period for (_, period), row in observations.items() if row["value"] is not None})
    months = reported[-JODI_MONTHS:]
    producers = []
    for iso2, meta in PRODUCERS.items():
        series = []
        for period in months:
            row = observations.get((iso2, period))
            status = "no_row" if row is None else "not_reported" if row["value"] is None else "reported"
            code = row.get("assessment_code") if row else None
            series.append({
                "period": period,
                "value": row["value"] if status == "reported" else None,
                "status": status,
                "assessment_code": code,
                "assessment_label_ko": JODI_ASSESSMENT_KO.get(code or "", "JODI 평가 코드 없음"),
            })
        producers.append({
            "iso2": iso2, "name_ko": meta["name_ko"], "route_class": meta["route_class"],
            "route_class_label_ko": ROUTE_CLASS_LABELS_KO[meta["route_class"]],
            "route_note_ko": meta["route_note_ko"], "series": series,
        })
    members = [iso2 for iso2, meta in PRODUCERS.items() if meta["route_class"] == "hormuz_only_seaborne"]
    group = []
    by_iso = {row["iso2"]: {point["period"]: point for point in row["series"]} for row in producers}
    for period in months:
        missing = [iso2 for iso2 in members if by_iso[iso2][period]["status"] != "reported"]
        complete = not missing
        group.append({
            "period": period,
            "status": "complete_members_reported" if complete else "incomplete_members_not_reported",
            # A missing member is never filled with zero, so an incomplete
            # group has no total at all rather than a partial one.
            "value": round(sum(by_iso[iso2][period]["value"] for iso2 in members), 1) if complete else None,
            "missing_members": missing,
            "reported_members": [iso2 for iso2 in members if iso2 not in missing],
        })
    return {
        "status": "available" if months else "unavailable",
        "statistic": "monthly_daily_mean",
        "unit": "thousand_barrels_per_day",
        "commodity": "jodi_crudeoil",
        "flow": "total_exports",
        "months": months,
        "producers": producers,
        "hormuz_only_group": {
            "members": members,
            "label_ko": "해협 외 수출로가 없는 산유국 원유 수출 합계",
            "by_month": group,
            "warning_ko": "호르무즈 원유 통과량의 일부(구성 요소)이며 전체가 아니다. 만 안쪽 목적지 납품과 월 경계 시차가 섞이고, 미보고 국가가 하나라도 있으면 합계를 내지 않는다.",
        },
        "transit_month_attribution": "export_month_not_transit_month",
        "warning_ko": "국가 전체 원유 수출 월평균이다. 우회 수출로가 있는 나라는 원산지만으로 해협 통과량을 정할 수 없다. ‘-’(미보고)를 0으로 채우지 않는다.",
    }


# --------------------------------------------------------- UN Comtrade (M)

def comtrade_url(reporter_code: int, period: str) -> str:
    return COMTRADE_PREVIEW_URL + "?" + urllib.parse.urlencode({
        "reporterCode": reporter_code,
        "period": period.replace("-", ""),
        "cmdCode": "2709",
        "flowCode": "M",
        "partnerCode": ",".join(str(meta["comtrade_code"]) for meta in PRODUCERS.values()),
    })


def parse_comtrade_preview(payload: dict[str, Any], *, reporter_code: int, period: str) -> list[dict[str, Any]]:
    if payload.get("error"):
        raise ValueError("Comtrade preview returned an error")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Comtrade preview payload changed")
    partners = {meta["comtrade_code"]: iso2 for iso2, meta in PRODUCERS.items()}
    rows: dict[str, dict[str, Any]] = {}
    for row in data:
        if (row.get("reporterCode") != reporter_code or str(row.get("period")) != period.replace("-", "")
                or str(row.get("cmdCode")) != "2709" or row.get("flowCode") != "M"
                or row.get("freqCode") != "M" or row.get("partnerCode") not in partners):
            raise ValueError("Comtrade row outside the requested reporter/period/commodity")
        # Only the all-customs-procedure, all-mode, world partner2 aggregate.
        if row.get("partner2Code") not in (0, None) or row.get("customsCode") not in ("C00", None) or row.get("motCode") not in (0, None):
            continue
        weight = row.get("netWgt")
        iso2 = partners[row["partnerCode"]]
        record = {
            "origin_iso2": iso2,
            "net_weight_tonnes": round(weight / 1000, 1) if _finite(weight) and weight > 0 else None,
            "net_weight_estimated": bool(row.get("isNetWgtEstimated")),
            "status": "reported" if _finite(weight) and weight > 0 else "weight_not_reported",
        }
        if iso2 in rows and rows[iso2] != record:
            raise ValueError("conflicting Comtrade rows for one origin")
        rows[iso2] = record
    return list(rows.values())


def collect_comtrade(fetcher: Fetcher, today: date, previous: dict[str, Any], sleep: Callable[[float], None]) -> dict[str, Any]:
    months = _previous_months(today, COMTRADE_MONTHS)
    cells = {cell["key"]: cell for cell in previous.get("cells", [])}
    fetched, failed = 0, []
    for importer, meta in IMPORTERS.items():
        for period in months:
            key = f"{importer}:{period}"
            try:
                payload = json.loads(fetcher(comtrade_url(meta["comtrade_code"], period)).decode("utf-8"))
                rows = parse_comtrade_preview(payload, reporter_code=meta["comtrade_code"], period=period)
                cells[key] = {"key": key, "importer_iso2": importer, "period": period, "rows": rows,
                              "status": "rows_returned" if rows else "no_rows"}
                fetched += 1
            except Exception as exc:  # noqa: BLE001 -- one cell must not sink the rest
                failed.append({"key": key, "error_code": type(exc).__name__})
            sleep(1.1)
    if not fetched:
        raise ValueError("no Comtrade monthly cell could be fetched")
    window = {f"{importer}:{period}" for importer in IMPORTERS for period in months}
    return {"months": months, "cells": [cells[key] for key in sorted(cells) if key in window], "cell_errors": failed}


def build_importer_receipts(comtrade: dict[str, Any]) -> dict[str, Any]:
    months = comtrade.get("months", [])
    cells = {cell["key"]: cell for cell in comtrade.get("cells", [])}
    importers = []
    for importer, meta in IMPORTERS.items():
        reported_months = [period for period in months if cells.get(f"{importer}:{period}", {}).get("status") == "rows_returned"]
        origins = []
        for iso2, producer in PRODUCERS.items():
            series = []
            for period in months:
                cell = cells.get(f"{importer}:{period}")
                row = next((item for item in (cell or {}).get("rows", []) if item["origin_iso2"] == iso2), None)
                if cell is None:
                    status = "not_fetched"
                elif cell["status"] == "no_rows":
                    status = "no_rows_for_importer_month"
                elif row is None:
                    status = "no_row_for_origin"
                else:
                    status = row["status"]
                series.append({"period": period, "value": row["net_weight_tonnes"] if row else None, "status": status})
            if any(point["value"] is not None for point in series):
                origins.append({"origin_iso2": iso2, "name_ko": producer["name_ko"], "route_class": producer["route_class"],
                                "route_class_label_ko": ROUTE_CLASS_LABELS_KO[producer["route_class"]], "series": series})
        importers.append({"iso2": importer, "name_ko": meta["name_ko"], "reported_months": reported_months,
                          "status": "monthly_rows_available" if reported_months else "no_monthly_rows_in_window",
                          "origins": origins})
    return {
        "status": "available" if any(row["reported_months"] for row in importers) else "unavailable",
        "statistic": "monthly_total",
        "unit": "tonnes_net_weight",
        "commodity": "hs_2709_crude_petroleum",
        "months": months,
        "importers": importers,
        "transit_month_attribution": "customs_month_not_transit_month",
        "warning_ko": "수입국 세관 월 기준 순중량(톤)이다. 통관 월은 해협 통과 월이 아니며, 배럴로 환산하지 않는다. 행이 없으면 ‘미보고 또는 수입 없음’이고 0이 아니다. 우회 수출로가 있는 원산지는 해협 통과분과 구분되지 않는다.",
    }


# ----------------------------------------------------------- Sentinel-1

def _point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    for index in range(len(ring) - 1):
        (x1, y1), (x2, y2) = ring[index][:2], ring[index + 1][:2]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _outer_rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    if geometry.get("type") == "Polygon":
        return [geometry["coordinates"][0]]
    if geometry.get("type") == "MultiPolygon":
        return [polygon[0] for polygon in geometry["coordinates"]]
    raise ValueError("unsupported STAC footprint geometry")


def bbox_coverage(geometries: list[dict[str, Any]], bbox: tuple[float, float, float, float] = SAR_BBOX,
                  step: float = SAR_GRID_STEP_DEG) -> float:
    """Share of grid points in bbox inside the union of footprints."""
    rings = [ring for geometry in geometries for ring in _outer_rings(geometry)]
    west, south, east, north = bbox
    columns = max(1, round((east - west) / step))
    rows = max(1, round((north - south) / step))
    covered = 0
    for row in range(rows):
        y = south + (row + 0.5) * (north - south) / rows
        for column in range(columns):
            x = west + (column + 0.5) * (east - west) / columns
            covered += any(_point_in_ring(x, y, ring) for ring in rings)
    return round(covered / (rows * columns), 3)


def stac_search_url(start: date, end: date) -> str:
    return STAC_SEARCH_URL + "?" + urllib.parse.urlencode({
        "collections": "sentinel-1-grd",
        "bbox": ",".join(str(value) for value in SAR_BBOX),
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "limit": "100",
    })


def collect_sentinel1(fetcher: Fetcher, today: date) -> dict[str, Any]:
    end = today - timedelta(days=1)
    start = end - timedelta(days=SAR_WINDOW_DAYS - 1)
    url, features, pages = stac_search_url(start, end), [], 0
    while url and pages < 5:
        payload = json.loads(fetcher(url).decode("utf-8"))
        if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
            raise ValueError("STAC search payload changed")
        features.extend(payload["features"])
        pages += 1
        url = next((link.get("href") for link in payload.get("links", [])
                    if link.get("rel") == "next" and link.get("method", "GET") == "GET"), None)
        if url and urllib.parse.urlparse(url).hostname != urllib.parse.urlparse(STAC_SEARCH_URL).hostname:
            raise ValueError("STAC pagination left the publisher host")
    by_date: dict[str, dict[str, Any]] = {}
    for feature in features:
        properties = feature.get("properties") or {}
        stamp = properties.get("datetime") or properties.get("start_datetime")
        if not stamp or not feature.get("geometry"):
            continue
        day = stamp[:10]
        date.fromisoformat(day)
        entry = by_date.setdefault(day, {"geometries": [], "platforms": set(), "orbit_states": set(), "scene_ids": set()})
        entry["geometries"].append(feature["geometry"])
        entry["platforms"].add(properties.get("platform") or "unknown")
        entry["orbit_states"].add(properties.get("sat:orbit_state") or "unknown")
        entry["scene_ids"].add(feature.get("id"))
    acquisitions = [{
        "date": day,
        "scene_count": len(entry["scene_ids"]),
        "platforms": sorted(entry["platforms"]),
        "orbit_states": sorted(entry["orbit_states"]),
        "bbox_coverage_fraction": bbox_coverage(entry["geometries"]),
    } for day, entry in sorted(by_date.items())]
    return {"window_start": start.isoformat(), "window_end": end.isoformat(), "pages": pages,
            "truncated": bool(url), "acquisitions": acquisitions}


def build_sar_coverage(sar: dict[str, Any]) -> dict[str, Any]:
    acquisitions = sar.get("acquisitions", [])
    days = [date.fromisoformat(row["date"]) for row in acquisitions]
    gaps = [(later - earlier).days for earlier, later in zip(days, days[1:])]
    return {
        "status": "metadata_only_no_detection" if acquisitions else "no_acquisitions_in_window",
        "collection": "sentinel-1-grd",
        "bbox": list(SAR_BBOX),
        "window_start": sar.get("window_start"),
        "window_end": sar.get("window_end"),
        "acquisition_dates": len(acquisitions),
        "full_coverage_dates": sum(row["bbox_coverage_fraction"] >= SAR_FULL_COVERAGE for row in acquisitions),
        "full_coverage_threshold": SAR_FULL_COVERAGE,
        "max_gap_days": max(gaps) if gaps else None,
        "latest_acquisition_date": acquisitions[-1]["date"] if acquisitions else None,
        "results_truncated": bool(sar.get("truncated")),
        "acquisitions": acquisitions,
        "vessel_detection": None,
        "warning_ko": "촬영 메타데이터만 집계한다. 영상 다운로드·선박 탐지·AIS 대조는 하지 않았고, 촬영일 수는 통항 선박 수가 아니다. 같은 날 연속 장면은 하루로 센다. 상자는 해협 핵심부이며 오만만 통제 구역 전체가 아니다.",
    }


# ----------------------------------------------------------- mass balance

def compose_mass_balance(term_values: dict[str, dict[str, Any] | None], confirmed: dict[str, Any] | None) -> dict[str, Any]:
    """Interval arithmetic over cumulative barrels for one period/boundary.

    `term_values[id]` and `confirmed` are {"value", "low", "high"} or None.
    A range is composed only when every term carries a validated low/high.
    """
    missing = [term["id"] for term in LEDGER_TERMS if not term_values.get(term["id"]) or not _finite(term_values[term["id"]].get("value"))]
    if not confirmed or not _finite(confirmed.get("value")):
        missing.append(CONFIRMED_TERM["id"])
    if missing:
        return {"status": "hold_inputs_missing", "hormuz_inflow_estimate": None, "unexplained_volume": None,
                "unexplained_range": None, "missing_terms": missing, "diagnostic": None}
    everything = {**{term["id"]: term_values[term["id"]] for term in LEDGER_TERMS}, CONFIRMED_TERM["id"]: confirmed}
    for term_id, entry in everything.items():
        low, high = entry.get("low"), entry.get("high")
        if entry["value"] < 0:
            raise ValueError(f"{term_id} must be a non-negative cumulative volume")
        if (low is None) != (high is None) or (low is not None and not low <= entry["value"] <= high):
            raise ValueError(f"{term_id} bounds must bracket its value")
    inflow = sum(term["sign"] * term_values[term["id"]]["value"] for term in LEDGER_TERMS)
    unexplained = inflow - confirmed["value"]
    bounded = all(entry.get("low") is not None for entry in everything.values())
    unexplained_range = None
    if bounded:
        positive = [term_values[term["id"]] for term in LEDGER_TERMS if term["sign"] > 0]
        negative = [term_values[term["id"]] for term in LEDGER_TERMS if term["sign"] < 0]
        inflow_low = sum(entry["low"] for entry in positive) - sum(entry["high"] for entry in negative)
        inflow_high = sum(entry["high"] for entry in positive) - sum(entry["low"] for entry in negative)
        unexplained_range = {"low": inflow_low - confirmed["high"], "high": inflow_high - confirmed["low"]}
    diagnostic = {"hormuz_inflow_estimate": inflow, "unexplained_volume": unexplained, "unexplained_range": unexplained_range}
    if inflow < 0 or unexplained < 0:
        # A negative residual is a boundary/data mismatch, not a zero. Keep
        # the arithmetic visible for review but publish no headline number.
        return {"status": "hold_negative_residual_boundary_mismatch", "hormuz_inflow_estimate": None,
                "unexplained_volume": None, "unexplained_range": None, "missing_terms": [], "diagnostic": diagnostic}
    return {"status": "computed", "missing_terms": [], **diagnostic, "diagnostic": None}


def _producer_status(producers: dict[str, Any], iso2: str, period: str | None) -> str:
    for row in producers.get("producers", []):
        if row["iso2"] == iso2:
            point = next((item for item in row["series"] if item["period"] == period), None)
            return point["status"] if point else "no_row"
    return "no_row"


def evaluate_ledger_terms(*, period: str | None, producers: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    """Every free candidate for each term, and why it does not qualify.

    A candidate qualifies only as same-period, same-boundary, crude-only
    cumulative barrels. None of today's free inputs do, so no term carries a
    value; the reasons are what the screen shows instead of a number.
    """
    oman = _producer_status(producers, "OM", period)
    uae, iran = _producer_status(producers, "AE", period), _producer_status(producers, "IR", period)
    candidates: dict[str, list[dict[str, Any]]] = {term["id"]: [] for term in LEDGER_TERMS}
    candidates[CONFIRMED_TERM["id"]] = []
    candidates["local_loading_excluding_bypass"].append({
        "source": "JODI-Oil 오만 원유 수출", "input_status": oman,
        "reasons": ["scope_country_total_includes_arabian_sea_terminals", "excludes_uae_east_coast_local_loading"]
        + ([] if oman == "reported" else ["not_reported_for_period"]),
    })
    candidates["bypass_port_loading"].append({
        "source": "JODI-Oil UAE·이란 원유 수출", "input_status": "reported" if "reported" in (uae, iran) else "not_reported",
        "reasons": ["scope_country_total_no_terminal_split"] + ([] if "reported" in (uae, iran) else ["not_reported_for_period"]),
    })
    candidates["bypass_port_loading"].append({
        "source": "ADCOP·고레–자스크 파이프라인 정격 용량", "input_status": "rejected",
        "reasons": ["nameplate_capacity_not_actual_flow"],
    })
    if context.get("portwatch_tanker_available"):
        candidates[CONFIRMED_TERM["id"]].append({
            "source": "IMF PortWatch 호르무즈 탱커 일별 추정 교역량", "input_status": "available",
            "reasons": ["unit_ship_type_tonnes_not_crude_barrels", "ais_dependent_same_blind_spot"],
        })
    if context.get("eia_crude_period"):
        candidates[CONFIRMED_TERM["id"]].append({
            "source": f"EIA 원유+콘덴세이트 {context['eia_crude_period']} 분기 일평균", "input_status": "available",
            "reasons": ["period_quarterly_not_ledger_month", "institution_estimate_not_voyage_confirmation"],
        })
    if context.get("iea_total_oil_period"):
        candidates[CONFIRMED_TERM["id"]].append({
            "source": f"IEA 석유 전체 {context['iea_total_oil_period']} 월평균", "input_status": "available",
            "reasons": ["commodity_total_oil_not_crude", "institution_estimate_not_voyage_confirmation"],
        })
    evaluated = []
    for term in (*LEDGER_TERMS, CONFIRMED_TERM):
        found = candidates[term["id"]]
        evaluated.append({
            "id": term["id"], "label_ko": term["label_ko"], "sign": term.get("sign"), "role": term.get("role", "comparison"),
            "required_ko": term["required_ko"], "unlock_ko": term["unlock_ko"],
            "status": "unqualified_input" if found else "missing_no_free_source",
            "value": None, "low": None, "high": None,
            "candidates": found,
        })
    return evaluated


REASON_LABELS_KO = {
    "scope_country_total_includes_arabian_sea_terminals": "국가 총수출이라 아라비아해 터미널 선적이 섞임",
    "excludes_uae_east_coast_local_loading": "UAE 동해안 현지 선적이 빠짐",
    "not_reported_for_period": "해당 월 미보고",
    "scope_country_total_no_terminal_split": "국가 총수출이라 터미널별 분리 불가",
    "nameplate_capacity_not_actual_flow": "정격 용량은 실제 유량이 아님",
    "unit_ship_type_tonnes_not_crude_barrels": "선종별 톤이며 원유 배럴이 아님",
    "ais_dependent_same_blind_spot": "AIS 송신 선박만 셈(같은 사각지대)",
    "period_quarterly_not_ledger_month": "분기 평균이라 월 원장 기간과 다름",
    "institution_estimate_not_voyage_confirmation": "기관 추정치이며 항차 확인이 아님",
    "commodity_total_oil_not_crude": "석유 전체이며 원유 단독이 아님",
}


# ----------------------------------------------------------------- collect

SOURCE_META = {
    "jodi": {"source_url": JODI_DOWNLOADS_URL, "terms_url": JODI_TERMS_URL, "publisher": "JODI-Oil World Database",
             "reuse_status": "free_public_statistics_site_rights_reserved_individual_facts_cited",
             "attribution": "Source: JODI-Oil World Database (jodidata.org). Individual monthly figures cited; not a bulk redistribution."},
    "comtrade": {"source_url": COMTRADE_PREVIEW_URL, "terms_url": COMTRADE_TERMS_URL, "publisher": "UN Comtrade (UNSD)",
                 "reuse_status": "free_visualization_redissemination_policy_attribution",
                 "attribution": "Source: UN Comtrade, United Nations Statistics Division; monthly HS 2709 imports, keyless public preview."},
    "sentinel1": {"source_url": STAC_SEARCH_URL, "terms_url": SENTINEL_TERMS_URL, "publisher": "Copernicus Data Space Ecosystem",
                  "reuse_status": "copernicus_sentinel_free_full_open_metadata_only",
                  "attribution": "Contains modified Copernicus Sentinel data (metadata only), Copernicus Data Space Ecosystem STAC."},
}


def _official_context(official_cargo: dict[str, Any] | None, live_status: dict[str, Any] | None) -> dict[str, Any]:
    point = ((official_cargo or {}).get("chokepoints") or {}).get("hormuz") or {}
    eia = [card for card in point.get("reference_cards", []) if card.get("cargo_category") == "crude_condensate"]
    iea = point.get("supplementary_reference_cards", [])
    tanker = (((live_status or {}).get("hormuz") or {}).get("metric_histories") or {}).get("tanker") or {}
    return {
        "eia_crude_period": eia[0].get("period") if eia else None,
        "iea_total_oil_period": iea[0].get("period") if iea else None,
        "portwatch_tanker_available": bool(tanker.get("history")),
    }


def collect_hormuz_reconstruction(
    *, fetch: bool = False, previous: dict[str, Any] | None = None, now: datetime | None = None,
    fetcher: Fetcher = fetch_bytes, sleep: Callable[[float], None] = time.sleep,
    official_cargo: dict[str, Any] | None = None, live_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    timestamp = now.isoformat()
    previous_sources = copy.deepcopy((previous or {}).get("sources", {}))
    collectors = {
        "jodi": lambda: collect_jodi(fetcher, now.date()),
        "comtrade": lambda: collect_comtrade(fetcher, now.date(), previous_sources.get("comtrade", {}).get("data", {}), sleep),
        "sentinel1": lambda: collect_sentinel1(fetcher, now.date()),
    }
    sources: dict[str, dict[str, Any]] = {}
    for source_id, collect in collectors.items():
        source = previous_sources.get(source_id, {})
        source.update({**SOURCE_META[source_id], "api_key_required": False,
                       "last_attempt_at": timestamp if fetch else source.get("last_attempt_at")})
        if fetch:
            try:
                source.update({"data": collect(), "status": "fetched", "retrieved_at": timestamp, "error_code": None})
            except Exception as exc:  # noqa: BLE001 -- keep the last good copy
                source.update({"status": "cached_fallback" if source.get("data") else "unavailable", "error_code": type(exc).__name__})
        else:
            source["status"] = "cached_offline" if source.get("retrieved_at") else "not_fetched"
        source.setdefault("data", {})
        sources[source_id] = source

    producers = build_producer_exports(sources["jodi"]["data"])
    importers = build_importer_receipts(sources["comtrade"]["data"])
    sar = build_sar_coverage(sources["sentinel1"]["data"])
    period = producers["months"][-1] if producers["months"] else None
    terms = evaluate_ledger_terms(period=period, producers=producers, context=_official_context(official_cargo, live_status))
    for term in terms:
        for candidate in term["candidates"]:
            candidate["reason_labels_ko"] = [REASON_LABELS_KO[reason] for reason in candidate["reasons"]]
    by_id = {term["id"]: term for term in terms}
    result = compose_mass_balance(
        {term["id"]: by_id[term["id"]] if by_id[term["id"]]["status"] == "qualified" else None for term in LEDGER_TERMS},
        by_id[CONFIRMED_TERM["id"]] if by_id[CONFIRMED_TERM["id"]]["status"] == "qualified" else None,
    )
    start, end = _month_bounds(period) if period else (None, None)
    computed = result["status"] == "computed"
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": timestamp,
        "status": (
            "available" if any(source["status"] == "fetched" for source in sources.values())
            else "cached" if any(source.get("retrieved_at") for source in sources.values())
            else "unavailable"
        ),
        "api_keys_required": [],
        "method_document": METHOD_DOCUMENT,
        "headline": {
            "status": "computed_monthly_unexplained_range" if computed else "not_computed_insufficient_inputs",
            "value": result["unexplained_volume"] if computed else None,
            "range": result["unexplained_range"] if computed else None,
            "unit": "barrels_cumulative_over_period",
            "period": period,
            "display_ko": "월간 미설명 물량 추정 범위" if computed else "미포착 화물량: 자료 부족으로 미산출",
            "blocking_terms": result["missing_terms"],
            "warning_ko": "미설명 물량은 입증된 AIS 미송신 화물이 아니다. 누락 수출·재고·기간/품목 오차를 함께 담는다.",
        },
        "mass_balance": {
            "boundary": {"id": "gulf_of_oman_maritime_zone", "label_ko": "오만만 해상 통제 구역 (육상 탱크 제외)",
                         "commodity": "crude_oil_including_condensate", "direction": "westbound_inflow_from_hormuz"},
            "period": {"period": period, "start": start.isoformat() if start else None,
                       "end": end.isoformat() if end else None, "days": (end - start).days + 1 if start else None},
            "unit": "barrels_cumulative_over_period",
            "equation_ko": "호르무즈 유입 = 외해 출항 + 구역 내 하역·소비 + 재고 증가 − 현지 선적(우회분 제외) − 우회항 선적 − 다른 해상 유입",
            "terms": terms,
            "result": result,
            "rules_ko": [
                "모든 항은 같은 품목·방향·기간·경계의 기간 누적 배럴이어야 한다. 월간 값을 일별로 복제하지 않는다.",
                "구역 안 STS는 내부 이전이다. 셔틀 통과와 수취 선박 출항을 함께 새 물량으로 더하지 않는다.",
                "현지 선적과 우회항 선적은 겹치지 않게 나눈다. 파이프라인 유량과 그 화물의 선적을 함께 더하지 않는다.",
                "범위는 모든 항에 검증된 상·하한이 있을 때만 합성한다. 임의 ±20%나 근거 없는 신뢰구간을 붙이지 않는다.",
                "음수 잔차는 0으로 감추지 않고 경계·자료 불일치로 보류한다.",
            ],
        },
        "producer_exports": producers,
        "importer_receipts": importers,
        "sar_coverage": sar,
        "identifiability": copy.deepcopy(IDENTIFIABILITY),
        "rejected_shortcuts": copy.deepcopy(REJECTED_SHORTCUTS),
        "sources": sources,
    }
