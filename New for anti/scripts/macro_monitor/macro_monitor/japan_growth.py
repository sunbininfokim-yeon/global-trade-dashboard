"""Official-source builder for the Japan growth-monitor additions.

The dashboard build itself is deliberately offline and deterministic.  This
module is the explicit refresh boundary: it downloads the three primary-source
files, constructs the two ratios, and writes a small versioned snapshot that
the normal macro builder can consume without a network dependency.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from openpyxl import load_workbook


BOJ_API_URL = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
BOJ_OUTPUT_GAP_URL = "https://www.boj.or.jp/en/research/research_data/gap/gap.xlsx"

# ESRI publishes a new directory every quarterly-release vintage.  Keep the
# release page explicit so a review can reproduce the exact Cabinet Office
# vintage rather than silently switching revisions during a build.
ESRI_RELEASE_PAGE_URL = None          # None = follow the latest release (discover_esri_release_page)
ESRI_SOKUHOU_TOP = "https://www.esri.cao.go.jp/en/sna/sokuhou/sokuhou_top.html"
CAO_GETSUREI_INDEX = "https://www5.cao.go.jp/keizai3/getsurei/getsurei-index.html"

PRIVATE_NONFINANCIAL_FFA = "FOF_FFAF411L700"
GENERAL_GOVERNMENT_FFA = "FOF_FFAF420L700"


def discover_esri_release_page(fetcher: Any) -> str:
    """The English menu page of ESRI's newest quarterly release, linked from the sokuhou top page.
    (Pinning a vintage left the numbers on 2026 Q1 after the Q2 release was out.)"""
    from urllib.parse import urljoin
    top = fetcher(ESRI_SOKUHOU_TOP).decode("utf-8", errors="replace")
    m = re.search(r'href="([^"]*/qe\d+_\d+/gdemenuea\.html)"', top)
    if not m:
        raise ValueError("ESRI: no release menu linked from the sokuhou top page")
    return urljoin(ESRI_SOKUHOU_TOP, m.group(1))


def discover_cao_gap_xlsx(fetcher: Any) -> str:
    """Cabinet Office's GDP-gap workbook (renamed every release, e.g. 2622gap.xlsx), linked from the
    monthly economic report's related-data page."""
    from urllib.parse import urljoin
    page = fetcher(CAO_GETSUREI_INDEX).decode("utf-8", errors="replace")
    m = re.search(r'href="([^"]*\d+gap\.xlsx)"', page)
    if not m:
        raise ValueError("Cabinet Office: no GDP-gap workbook linked")
    return urljoin(CAO_GETSUREI_INDEX, m.group(1))


def fetch_bytes(url: str, *, timeout: int = 60) -> bytes:
    """Fetch a public source with a descriptive user agent."""
    request = Request(url, headers={"User-Agent": "global-trade-dashboard/1.0"})
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed public source URLs
        return response.read()


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "…", "..."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _quarter_end(period: int | str) -> str:
    """Turn BOJ YYYYQQ periods into ISO quarter-end dates."""
    text = str(period)
    if not re.fullmatch(r"\d{6}", text):
        raise ValueError(f"not a YYYYQQ period: {period!r}")
    year, quarter = int(text[:4]), int(text[-2:])
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"invalid quarter: {period!r}")
    return f"{year:04d}-{(3, 6, 9, 12)[quarter - 1]:02d}-{(31, 30, 30, 31)[quarter - 1]:02d}"


def _quarter_key(day: str) -> tuple[int, int]:
    parsed = date.fromisoformat(day)
    return parsed.year, (parsed.month - 1) // 3 + 1


def _previous_quarter(key: tuple[int, int]) -> tuple[int, int]:
    year, quarter = key
    return (year - 1, 4) if quarter == 1 else (year, quarter - 1)


def _is_four_quarter_window(dates: Iterable[str]) -> bool:
    keys = [_quarter_key(day) for day in dates]
    return len(keys) == 4 and all(keys[i - 1] == _previous_quarter(keys[i]) for i in range(1, 4))


def _decode_esri_csv(payload: bytes) -> list[list[str]]:
    for encoding in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            return list(csv.reader(io.StringIO(payload.decode(encoding))))
        except UnicodeDecodeError:
            continue
    raise ValueError("ESRI CSV could not be decoded as UTF-8 or CP932")


def parse_esri_nominal_calendar_year(payload: bytes) -> list[dict[str, Any]]:
    """Return annual nominal private non-residential investment / GDP ratios."""
    rows = _decode_esri_csv(payload)
    header_index = next(
        (
            index
            for index, row in enumerate(rows)
            if "GDP(Expenditure Approach)" in row and "Private Non-Resi.Investment" in row
        ),
        None,
    )
    if header_index is None:
        raise ValueError("ESRI annual nominal GDP columns were not found")
    header = rows[header_index]
    gdp_col = header.index("GDP(Expenditure Approach)")
    capex_col = header.index("Private Non-Resi.Investment")
    observations: list[dict[str, Any]] = []
    for row in rows[header_index + 1 :]:
        if not row or not re.match(r"^\d{4}/", (row[0] or "").strip()):
            continue
        if max(gdp_col, capex_col) >= len(row):
            continue
        gdp, capex = _number(row[gdp_col]), _number(row[capex_col])
        if not gdp or capex is None:
            continue
        year = int(row[0][:4])
        observations.append(
            {
                "date": f"{year:04d}-12-31",
                "value": round(capex / gdp * 100.0, 4),
                "gdp_bn_jpy": round(gdp, 1),
                "private_non_resi_investment_bn_jpy": round(capex, 1),
            }
        )
    if not observations:
        raise ValueError("ESRI annual nominal GDP contained no observations")
    return observations


def parse_esri_nominal_quarterly_gdp(payload: bytes) -> dict[str, float]:
    """Read the original (not annualised) nominal GDP quarter values in bn JPY."""
    rows = _decode_esri_csv(payload)
    header_index = next(
        (index for index, row in enumerate(rows) if "GDP(Expenditure Approach)" in row),
        None,
    )
    if header_index is None:
        raise ValueError("ESRI quarterly nominal GDP column was not found")
    gdp_col = rows[header_index].index("GDP(Expenditure Approach)")
    current_year: int | None = None
    out: dict[str, float] = {}
    for row in rows[header_index + 1 :]:
        if not row or gdp_col >= len(row):
            continue
        period = (row[0] or "").strip()
        year_match = re.match(r"^(\d{4})/\s*(\d{1,2})-\s*(\d{1,2})\.", period)
        if year_match:
            current_year = int(year_match.group(1))
            start_month, end_month = int(year_match.group(2)), int(year_match.group(3))
        else:
            range_match = re.match(r"^(\d{1,2})-\s*(\d{1,2})\.", period)
            if not range_match or current_year is None:
                continue
            start_month, end_month = int(range_match.group(1)), int(range_match.group(2))
        quarter = {3: 1, 6: 2, 9: 3, 12: 4}.get(end_month)
        gdp = _number(row[gdp_col])
        if quarter is None or gdp is None:
            continue
        out[_quarter_end(f"{current_year:04d}{quarter:02d}")] = gdp
    if not out:
        raise ValueError("ESRI quarterly nominal GDP contained no observations")
    return out


def parse_esri_nominal_quarterly(payload: bytes, columns: tuple[str, ...]) -> dict[str, dict[str, float]]:
    """Original (not annualised) nominal quarterly values, bn JPY, for each named column."""
    rows = _decode_esri_csv(payload)
    header_index = next((i for i, row in enumerate(rows) if all(c in row for c in columns)), None)
    if header_index is None:
        raise ValueError(f"ESRI quarterly nominal columns not found: {columns}")
    cols = {c: rows[header_index].index(c) for c in columns}
    out: dict[str, dict[str, float]] = {c: {} for c in columns}
    current_year: int | None = None
    for row in rows[header_index + 1:]:
        if not row:
            continue
        period = (row[0] or "").strip()
        ym = re.match(r"^(\d{4})/\s*(\d{1,2})-\s*(\d{1,2})\.", period)
        if ym:
            current_year, end_month = int(ym.group(1)), int(ym.group(3))
        else:
            rm = re.match(r"^(\d{1,2})-\s*(\d{1,2})\.", period)
            if not rm or current_year is None:
                continue
            end_month = int(rm.group(2))
        quarter = {3: 1, 6: 2, 9: 3, 12: 4}.get(end_month)
        if quarter is None:
            continue
        day = _quarter_end(f"{current_year:04d}{quarter:02d}")
        for c, idx in cols.items():
            v = _number(row[idx]) if idx < len(row) else None
            if v is not None:
                out[c][day] = v
    return out


def build_capex_ratio_4q(capex: dict[str, float], gdp: dict[str, float]) -> list[dict[str, Any]]:
    """Nominal private non-residential investment / nominal GDP over the latest four quarters (%)."""
    common = sorted(d for d in gdp if d in capex)
    out = []
    for i in range(3, len(common)):
        w = common[i - 3:i + 1]
        if not _is_four_quarter_window(w):
            continue
        c, g = sum(capex[d] for d in w), sum(gdp[d] for d in w)
        out.append({"date": w[-1], "value": round(c / g * 100.0, 4),
                    "private_non_resi_investment_bn_jpy_4q": round(c, 1), "gdp_bn_jpy_4q": round(g, 1)})
    if not out:
        raise ValueError("no four-quarter ESRI capex / GDP overlap")
    return out


def parse_cao_gdp_gap(payload: bytes) -> list[dict[str, Any]]:
    """Cabinet Office quarterly GDP gap (%), sheet 四半期: year in column A (blank = same year), quarter
    as a Roman numeral in column B, the gap in column C."""
    wb = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    roman = {"Ⅰ": 1, "Ⅱ": 2, "Ⅲ": 3, "Ⅳ": 4, "I": 1, "II": 2, "III": 3, "IV": 4}
    out, year = [], None
    for row in ws.iter_rows(values_only=True):
        if not row or len(row) < 3:
            continue
        if isinstance(row[0], (int, float)) and 1900 < row[0] < 2200:
            year = int(row[0])
        q = roman.get(str(row[1] or "").strip())
        v = _number(row[2])
        if year and q and v is not None:
            # "0.0" flagged ※ in column D means -0.0; the sign does not change the number
            out.append({"date": _quarter_end(f"{year:04d}{q:02d}"), "value": round(v, 4)})
    if not out:
        raise ValueError("Cabinet Office GDP-gap workbook contained no quarters")
    return out


def parse_boj_output_gap(payload: bytes) -> list[dict[str, Any]]:
    """Read BOJ's quarterly output gap (% of potential GDP) from gap.xlsx."""
    workbook = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    try:
        worksheet = workbook["data1"]
    except KeyError as exc:
        raise ValueError("BOJ output-gap workbook has no data1 sheet") from exc
    observations: list[dict[str, Any]] = []
    for row in worksheet.iter_rows(min_row=1, values_only=True):
        quarter = row[0] if row else None
        if not isinstance(quarter, str):
            continue
        match = re.fullmatch(r"(\d{4})\.(\d)Q", quarter.strip())
        if not match:
            continue
        value = _number(row[1] if len(row) > 1 else None)
        if value is None:
            continue
        observations.append(
            {"date": _quarter_end(f"{match.group(1)}0{match.group(2)}"), "value": round(value, 4)}
        )
    if not observations:
        raise ValueError("BOJ output-gap workbook contained no observations")
    return observations


def parse_boj_api_series(payload: bytes) -> dict[str, dict[str, float | None]]:
    """Map BOJ API result rows to ``series code -> ISO date -> numeric value``."""
    doc = json.loads(payload.decode("utf-8"))
    if doc.get("STATUS") != 200:
        raise ValueError(f"BOJ API failed: {doc.get('MESSAGE') or doc.get('STATUS')}")
    out: dict[str, dict[str, float | None]] = {}
    for row in doc.get("RESULTSET") or []:
        values = row.get("VALUES") or {}
        periods = values.get("SURVEY_DATES") or []
        raw_values = values.get("VALUES") or []
        if len(periods) != len(raw_values):
            raise ValueError(f"BOJ API length mismatch for {row.get('SERIES_CODE')}")
        out[str(row["SERIES_CODE"])] = {
            _quarter_end(period): _number(value) for period, value in zip(periods, raw_values)
        }
    return out


def build_net_funding_demand(
    private_nonfinancial: dict[str, float | None],
    general_government: dict[str, float | None],
    quarterly_gdp_bn_jpy: dict[str, float],
) -> list[dict[str, Any]]:
    """Construct 4-quarter net funding demand as a percentage of nominal GDP.

    BOJ's financial surplus/deficit is a quarterly flow in 100 million JPY.  A
    four-quarter sum of each sector is therefore divided by the matching
    four-quarter sum of ESRI nominal GDP (bn JPY); 100 million JPY is 0.1 bn.
    Positive values mean the combined corporate-plus-government sector is a
    net financial surplus; negative values mean it is a net funding demander.
    """
    common = sorted(
        day
        for day in quarterly_gdp_bn_jpy
        if private_nonfinancial.get(day) is not None and general_government.get(day) is not None
    )
    observations: list[dict[str, Any]] = []
    for index in range(3, len(common)):
        window = common[index - 3 : index + 1]
        if not _is_four_quarter_window(window):
            continue
        corporate = sum(float(private_nonfinancial[day]) for day in window)
        fiscal = sum(float(general_government[day]) for day in window)
        gdp = sum(float(quarterly_gdp_bn_jpy[day]) for day in window)
        if not gdp:
            continue
        corporate_pct = corporate * 0.1 / gdp * 100.0
        fiscal_pct = fiscal * 0.1 / gdp * 100.0
        observations.append(
            {
                "date": window[-1],
                "value": round(corporate_pct + fiscal_pct, 4),
                "private_nonfinancial_pct_gdp": round(corporate_pct, 4),
                "general_government_pct_gdp": round(fiscal_pct, 4),
                "nominal_gdp_bn_jpy_4q": round(gdp, 1),
            }
        )
    if not observations:
        raise ValueError("no four-quarter BOJ FFA / ESRI GDP overlap")
    return observations


def _esri_table_urls(release_page_url: str, release_page: bytes) -> tuple[str, str]:
    """Find the calendar-year and quarterly nominal GDP CSVs on an ESRI page."""
    from urllib.parse import urljoin

    html = release_page.decode("utf-8", errors="replace")
    annual = re.search(r'href="([^"]*/gaku-mcy\d+\.csv)"', html)
    quarterly = re.search(r'href="([^"]*/gaku-mg\d+\.csv)"', html)
    if not annual or not quarterly:
        raise ValueError("ESRI release page did not contain nominal GDP CSV links")
    return urljoin(release_page_url, annual.group(1)), urljoin(release_page_url, quarterly.group(1))


def _boj_api_url(codes: list[str], *, start_date: str, end_date: str | None = None) -> str:
    params: list[tuple[str, str]] = [
        ("format", "JSON"),
        ("lang", "EN"),
        ("db", "FF"),
        ("startDate", start_date),
        ("code", ",".join(codes)),
    ]
    if end_date:
        params.insert(5, ("endDate", end_date))
    # BOJ's API accepts a comma-separated code list but rejects an encoded
    # comma (%2C) with HTTP 400.
    return f"{BOJ_API_URL}?{urlencode(params, safe=',')}"


def build_snapshot(
    *,
    release_page_url: str | None = ESRI_RELEASE_PAGE_URL,
    retrieved_at: str | None = None,
    fetcher: Any = fetch_bytes,
) -> dict[str, Any]:
    """Fetch official inputs and return the committed Japan-growth snapshot."""
    release_page_url = release_page_url or discover_esri_release_page(fetcher)
    release_page = fetcher(release_page_url)
    annual_url, quarterly_url = _esri_table_urls(release_page_url, release_page)
    calendar_year = parse_esri_nominal_calendar_year(fetcher(annual_url))
    q = parse_esri_nominal_quarterly(fetcher(quarterly_url), ("GDP(Expenditure Approach)", "Private Non-Resi.Investment"))
    quarterly_gdp = q["GDP(Expenditure Approach)"]
    capex_4q = build_capex_ratio_4q(q["Private Non-Resi.Investment"], quarterly_gdp)
    ffa_url = _boj_api_url(
        [PRIVATE_NONFINANCIAL_FFA, GENERAL_GOVERNMENT_FFA],
        start_date="199801",
    )
    ffa = parse_boj_api_series(fetcher(ffa_url))
    net_funding = build_net_funding_demand(
        ffa[PRIVATE_NONFINANCIAL_FFA],
        ffa[GENERAL_GOVERNMENT_FFA],
        quarterly_gdp,
    )
    output_gap = parse_boj_output_gap(fetcher(BOJ_OUTPUT_GAP_URL))
    try:
        cao_gap_url = discover_cao_gap_xlsx(fetcher)
        cao_gap = parse_cao_gdp_gap(fetcher(cao_gap_url))
    except Exception:  # noqa: BLE001 -- the BOJ gap still stands on its own
        cao_gap_url, cao_gap = None, []
    stamp = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    vintage = re.search(r"/(qe\d+_\d+)/", release_page_url)

    latest_net = net_funding[-1]
    return {
        "schema_version": "jp-growth-monitor-v2",
        "retrieved_at": stamp,
        "esri_vintage": vintage.group(1) if vintage else None,
        "source": {
            "cabinet_office_release_page": release_page_url,
            "cabinet_office_nominal_calendar_year_csv": annual_url,
            "cabinet_office_nominal_quarterly_csv": quarterly_url,
            "cabinet_office_gdp_gap_xlsx": cao_gap_url,
            "boj_output_gap_xlsx": BOJ_OUTPUT_GAP_URL,
            "boj_ffa_api": ffa_url,
        },
        "series": {
            "capex_gdp_ratio": {
                "frequency": "quarterly_rolling_4q",
                "asof": capex_4q[-1]["date"],
                "unit": "pct_gdp",
                "formula_ko": "최근 4분기 명목 민간기업 설비투자 합계 ÷ 같은 4분기 명목 GDP 합계 × 100 (내각부 원계열)",
                "observations": capex_4q,
                "annual_observations": calendar_year,
            },
            "net_funding_demand": {
                "frequency": "quarterly_rolling_4q",
                "asof": latest_net["date"],
                "unit": "pct_gdp",
                "formula_ko": (
                    "(BOJ 민간비금융법인 금융잉여/부족 + 일반정부 금융잉여/부족)의 "
                    "4분기 합계 ÷ 같은 4분기 명목 GDP 합계 × 100"
                ),
                "sign_convention_ko": "음수=기업·정부 합산 순자금수요(투자초과), 양수=순자금잉여.",
                "components_latest": {
                    "private_nonfinancial_pct_gdp": latest_net["private_nonfinancial_pct_gdp"],
                    "general_government_pct_gdp": latest_net["general_government_pct_gdp"],
                    "nominal_gdp_bn_jpy_4q": latest_net["nominal_gdp_bn_jpy_4q"],
                },
                "observations": net_funding,
            },
            "gdp_gap": {
                "frequency": "quarterly",
                "asof": output_gap[-1]["date"],
                "unit": "pct_potential_gdp",
                "formula_ko": "(실제 GDP − 잠재 GDP) ÷ 잠재 GDP × 100. 일본은행 추정(수급갭)과 내각부 추정(GDP갭)을 함께 표시",
                "observations": output_gap,
                "cabinet_office_observations": cao_gap,
            },
        },
    }


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
