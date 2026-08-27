"""Official external inflation indicators that must not be relabeled as ours.

The dashboard may display an official institution's published nowcast or
underlying-inflation measure.  It preserves provider, method, release timing,
and source URL, and keeps that material separate from our own CPI relationship
evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

from .bls import _clean_text, _rows


CLEVELAND_NOWCAST_URL = "https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting"
CLEVELAND_MEDIAN_URL = "https://www.clevelandfed.org/indicators-and-data/median-cpi"
SF_SHELTER_RESEARCH_URL = (
    "https://www.frbsf.org/research-and-insights/publications/economic-letter/"
    "where-is-shelter-inflation-headed/"
)
SF_SHELTER_LEADING_URL = (
    "https://www.frbsf.org/research-and-insights/publications/economic-letter/"
    "will-rising-rents-push-up-future-inflation/"
)
SF_CONTRIBUTIONS_URL = (
    "https://www.frbsf.org/research-and-insights/data-and-indicators/"
    "cpi-inflation-contributions-from-goods-and-services/"
)
UA = "Mozilla/5.0 (compatible; macro-monitor-official-inflation/1.0; research)"


class OfficialSourceError(RuntimeError):
    """Raised when a provider page cannot be collected or parsed safely."""


def fetch_text(url: str, *, opener: Callable[..., Any] = urlopen) -> str:
    request = Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with opener(request, timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def _number(value: str) -> float | None:
    value = _clean_text(value)
    if value in {"", "-", "--", "n/a"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _reference_period(value: str) -> str | None:
    try:
        return datetime.strptime(_clean_text(value), "%B %Y").strftime("%Y-%m")
    except ValueError:
        return None


def _matching_tables(html: str, header: list[str]) -> list[list[list[str]]]:
    """Return consecutive rows following a table header from simple HTML tables."""
    rows = _rows(html)
    normalized = [item.lower() for item in header]
    out: list[list[list[str]]] = []
    for index, row in enumerate(rows):
        if [item.lower() for item in row] != normalized:
            continue
        body: list[list[str]] = []
        for candidate in rows[index + 1 :]:
            if len(candidate) != len(header):
                break
            if candidate[0].lower() == "month" or candidate[0].lower() == "quarter":
                break
            body.append(candidate)
        if body:
            out.append(body)
    return out


def parse_cleveland_nowcast(html: str) -> dict[str, Any]:
    """Parse current monthly and annual CPI nowcasts published on the page."""
    header = ["Month", "CPI", "Core CPI", "PCE", "Core PCE", "Updated"]
    tables = _matching_tables(html, header)
    if len(tables) < 2:
        raise OfficialSourceError("Cleveland Fed nowcast monthly/annual tables were not found")

    def parse_row(row: list[str]) -> dict[str, Any]:
        reference_period = _reference_period(row[0])
        if not reference_period:
            raise OfficialSourceError(f"invalid Cleveland Fed reference period: {row[0]}")
        return {
            "reference_period": reference_period,
            "published_display_period": row[0],
            "cpi_pct": _number(row[1]),
            "core_cpi_pct": _number(row[2]),
            "pce_pct": _number(row[3]),
            "core_pce_pct": _number(row[4]),
            "provider_updated_display": row[5],
        }

    return {"monthly_pct": parse_row(tables[0][0]), "year_over_year_pct": parse_row(tables[1][0])}


def _month_columns(header: list[str]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for index, label in enumerate(header[1:], start=1):
        try:
            out.append((index, datetime.strptime(label, "%b-%Y").strftime("%Y-%m")))
        except ValueError:
            continue
    return out


def parse_cleveland_median(html: str) -> dict[str, Any]:
    """Parse the latest median and trimmed-mean CPI rows published by Cleveland Fed."""
    rows = _rows(html)
    tables: list[tuple[list[str], list[list[str]]]] = []
    for index, row in enumerate(rows):
        if not row or row[0].lower() != "date" or len(row) < 2:
            continue
        body: list[list[str]] = []
        for candidate in rows[index + 1 :]:
            if not candidate or candidate[0].lower() == "date" or len(candidate) != len(row):
                break
            body.append(candidate)
        if body:
            tables.append((row, body))
    if len(tables) < 2:
        raise OfficialSourceError("Cleveland Fed median CPI monthly/annual tables were not found")

    def latest(table: tuple[list[str], list[list[str]]]) -> dict[str, Any]:
        header, body = table
        periods = _month_columns(header)
        values = {row[0].lower(): row for row in body}
        median = values.get("median cpi")
        trimmed = values.get("16% trimmed-mean cpi")
        if not median or not trimmed:
            raise OfficialSourceError("Cleveland Fed median or trimmed row was not found")
        for index, period in reversed(periods):
            median_value, trimmed_value = _number(median[index]), _number(trimmed[index])
            if median_value is not None or trimmed_value is not None:
                return {
                    "reference_period": period,
                    "median_cpi_pct": median_value,
                    "trimmed_mean_cpi_pct": trimmed_value,
                }
        raise OfficialSourceError("Cleveland Fed median CPI table had no values")

    return {"monthly_pct": latest(tables[0]), "year_over_year_pct": latest(tables[1])}


def build_official_inflation_sources(
    nowcast: Mapping[str, Any],
    median: Mapping[str, Any],
    *,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Build a display-safe source registry and official published values."""
    retrieved_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "us-official-inflation-sources-v1",
        "retrieved_at": retrieved_at,
        "data_status": "official_external_published",
        "display_rule": "Provider values retain provider attribution and are never relabeled as dashboard forecasts or causal findings.",
        "published_indicators": [
            {
                "id": "cleveland_fed_inflation_nowcast",
                "provider": "Federal Reserve Bank of Cleveland",
                "classification": "official_external_current_period_nowcast",
                "source_url": CLEVELAND_NOWCAST_URL,
                "refresh": "each business day around 10:00 a.m. Eastern",
                "method_summary_ko": "최근 CPI·근원 CPI·식품과 일별 Brent, 주별 휘발유 등을 결합한 현재 기간 나우캐스트",
                "monthly_pct": nowcast["monthly_pct"],
                "year_over_year_pct": nowcast["year_over_year_pct"],
                "use_in_dashboard": "공식기관 나우캐스트 원문값 표시. 자체 CPI 전이 신호의 근거·대체값으로 사용하지 않음.",
            },
            {
                "id": "cleveland_fed_median_trimmed_cpi",
                "provider": "Federal Reserve Bank of Cleveland",
                "classification": "official_external_underlying_inflation_measure",
                "source_url": CLEVELAND_MEDIAN_URL,
                "refresh": "monthly after BLS CPI release",
                "method_summary_ko": "월별 CPI 항목의 극단값을 제외하거나 중앙 가중치 항목을 사용해 기저 물가 추세를 측정",
                "monthly_pct": median["monthly_pct"],
                "year_over_year_pct": median["year_over_year_pct"],
                "use_in_dashboard": "물가 확산·기저 추세 확인용. 향후 항목별 전이의 직접 예측값이 아님.",
            },
        ],
        "research_and_source_cards": [
            {
                "id": "sf_fed_shelter_leading_pipeline",
                "provider": "Federal Reserve Bank of San Francisco",
                "classification": "official_research_methodology_not_live_dashboard_forecast",
                "source_urls": [SF_SHELTER_LEADING_URL, SF_SHELTER_RESEARCH_URL],
                "relationship_ko": "신규 임대료·주택가격·공실·공급 지표는 CPI Shelter보다 앞설 수 있으나, 일대일 전이로 단정할 수 없음.",
                "published_method_ko": "지역별 지연 변수를 결합하고 롤링 표본외 오차로 모형을 선택하는 주거비 예측 접근.",
                "dashboard_policy": "Zillow·Apartment List·공실·착공 등 원자료를 point-in-time으로 결합하고 자체 표본외 검증을 통과하기 전까지는 출처 카드와 가설로만 표시.",
            },
            {
                "id": "sf_fed_cpi_contribution_breakdown",
                "provider": "Federal Reserve Bank of San Francisco",
                "classification": "official_external_contribution_breakdown",
                "source_urls": [SF_CONTRIBUTIONS_URL],
                "relationship_ko": "식품·에너지·근원 상품·주거·기타 근원 서비스의 CPI 기여도를 별도 구분해 보여주는 공식 분해 자료.",
                "dashboard_policy": "자체 Table 6/7 수집 전에는 이 출처를 참고 카드로만 사용하며, 상세 Top 3/Bottom 3는 BLS 발표 빈티지에서 계산.",
            },
        ],
        "limitations": [
            "공식기관 나우캐스트와 기저물가 지표는 제공기관의 방법론·갱신 빈티지를 따른다.",
            "SF Fed의 주거비 연구는 선행지표 사용의 근거이지, 현재 월의 정량 예측을 그대로 재사용할 권한이나 근거가 아니다.",
            "자체 항목 관계는 동일한 시점 정보로 표본외 검증을 통과하기 전까지 가설·맥락으로만 표시한다.",
        ],
    }
