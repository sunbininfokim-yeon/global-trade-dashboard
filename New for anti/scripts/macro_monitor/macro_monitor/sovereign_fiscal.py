"""Official-source snapshot builder for cross-country sovereign fiscal data.

The IMF Fiscal Policy Panel (FPP) gives the only presently usable common
definition across the monitor countries for both gross public debt and
interest paid on public debt.  It is annual and release-lagged, so this module
deliberately keeps *observed* years only; it never turns an IMF forecast into a
"latest actual" dashboard print.

For the United States the Monthly Treasury Statement is additionally used for
the requested interest-cost / Defense spending ratio.  That series is fiscal
year-to-date, therefore only completed fiscal years (September observations)
are retained for a comparable trend.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


IMF_BASE = "https://www.imf.org/external/datamapper/api/v1"
FISCALDATA_BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
UA = "Mozilla/5.0 (compatible; macro-monitor-sovereign-fiscal/1.0; research)"

# The dashboard deliberately excludes the Euro area aggregate from this common
# layer: the user wants the UK, not a synthetic Europe-wide comparison.
MONITOR_IMF_CODES: dict[str, str] = {
    "USA": "USA", "KOR": "KOR", "JPN": "JPN", "CHN": "CHN", "ZAF": "ZAF",
    "SGP": "SGP", "HKG": "HKG", "RUS": "RUS", "GBR": "GBR", "CAN": "CAN",
    "AUS": "AUS", "CHE": "CHE", "BRA": "BRA", "VNM": "VNM", "KAZ": "KAZ",
    "TWN": "TWN", "IND": "IND", "ISR": "ISR",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _get_json(url: str, timeout: int = 45) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _imf_values(indicator: str) -> dict[str, dict[str, float]]:
    """Return DataMapper values as country -> year -> finite float."""
    doc = _get_json(f"{IMF_BASE}/{indicator}")
    raw = (doc.get("values") or {}).get(indicator) or {}
    out: dict[str, dict[str, float]] = {}
    for code, years in raw.items():
        parsed: dict[str, float] = {}
        for year, value in (years or {}).items():
            number = _finite(value)
            if number is not None:
                parsed[str(year)] = number
        if parsed:
            out[str(code)] = parsed
    return out


def _completed_us_fiscal_years() -> list[dict[str, Any]]:
    """Read MTS Table 5 FYTD outlays and join the two requested line items."""
    def lines(description: str) -> dict[int, tuple[str, float]]:
        query = urllib.parse.urlencode({
            "filter": f"classification_desc:eq:{description}",
            "sort": "-record_date",
            "page[size]": "180",
        })
        doc = _get_json(f"{FISCALDATA_BASE}/v1/accounting/mts/mts_table_5?{query}")
        result: dict[int, tuple[str, float]] = {}
        for row in doc.get("data") or []:
            record_date = str(row.get("record_date") or "")
            # September is the completed US federal fiscal year.  Avoid an
            # incomplete current FY being visually compared to full years.
            if not record_date.endswith("-09-30"):
                continue
            amount = _finite(row.get("current_fytd_net_outly_amt"))
            try:
                fiscal_year = int(row.get("record_fiscal_year"))
            except (TypeError, ValueError):
                continue
            if amount is not None:
                result[fiscal_year] = (record_date, amount)
        return result

    interest = lines("Total--Interest on the Public Debt")
    defense = lines("Total--Department of Defense--Military Programs")
    observations: list[dict[str, Any]] = []
    for fiscal_year in sorted(set(interest) & set(defense)):
        date, interest_usd = interest[fiscal_year]
        _, defense_usd = defense[fiscal_year]
        if defense_usd <= 0:
            continue
        observations.append({
            "date": date,
            "fiscal_year": fiscal_year,
            "interest_tn_usd": round(interest_usd / 1e12, 6),
            "defense_tn_usd": round(defense_usd / 1e12, 6),
            "interest_to_defense_pct": round(interest_usd / defense_usd * 100.0, 4),
        })
    return observations


def build_snapshot() -> dict[str, Any]:
    """Build a versioned cache from official endpoints, with actuals only."""
    debt = _imf_values("d")       # Gross public debt, % GDP (FPP)
    interest = _imf_values("ie")  # Interest paid on public debt, % GDP (FPP)
    gdp = _imf_values("NGDPD")    # Current-price GDP, billions USD (WEO)

    countries: dict[str, Any] = {}
    for iso3, imf_code in MONITOR_IMF_CODES.items():
        common_years = sorted(
            set(debt.get(imf_code, {}))
            & set(interest.get(imf_code, {}))
            & set(gdp.get(imf_code, {})),
            key=int,
        )
        observations = []
        for year in common_years:
            # IMF FPP's observed range currently ends in 2024.  Do not accept
            # a future calendar year even if a source later changes behavior.
            if int(year) > datetime.now(timezone.utc).year:
                continue
            debt_pct = debt[imf_code][year]
            interest_pct = interest[imf_code][year]
            gdp_bn = gdp[imf_code][year]
            observations.append({
                "date": f"{year}-12-31",
                "year": int(year),
                "debt_gdp_pct": round(debt_pct, 4),
                "interest_gdp_pct": round(interest_pct, 4),
                "nominal_gdp_bn_usd": round(gdp_bn, 4),
                "debt_tn_usd": round(debt_pct * gdp_bn / 100.0 / 1000.0, 6),
                "interest_tn_usd": round(interest_pct * gdp_bn / 100.0 / 1000.0, 6),
            })
        countries[iso3] = {
            "imf_code": imf_code,
            "status": "ok" if observations else "unavailable",
            "asof": observations[-1]["date"] if observations else None,
            "observations": observations,
            "reason_ko": None if observations else "IMF 공통 실제 관측치(부채·이자·명목 GDP)가 모두 없음",
        }

    us_defense = _completed_us_fiscal_years()
    return {
        "schema_version": "sovereign-fiscal-v1",
        "retrieved_at": _now(),
        "source": {
            "imf": {
                "publisher": "IMF DataMapper / Fiscal Policy Panel",
                "debt_indicator": "d (Gross public debt, percent of GDP)",
                "interest_indicator": "ie (Interest paid on public debt, percent of GDP)",
                "gdp_indicator": "NGDPD (GDP, current prices; billions USD)",
                "url": "https://www.imf.org/external/datamapper/api/v1/d,ie,NGDPD",
            },
            "us_treasury": {
                "publisher": "U.S. Treasury FiscalData, Monthly Treasury Statement Table 5",
                "url": "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/",
                "definition_ko": "공공부채 이자 / 국방부 군사프로그램 지출 (완결 회계연도 FYTD)",
            },
        },
        "refresh": {
            "check_cadence": "monthly",
            "imf_source_frequency": "annual",
            "us_treasury_source_frequency": "monthly",
            "actuals_policy_ko": "IMF 전망치는 제외하고 실제 관측 연도만 사용",
        },
        "countries": countries,
        "us_defense_ratio": {
            "status": "ok" if us_defense else "unavailable",
            "asof": us_defense[-1]["date"] if us_defense else None,
            "observations": us_defense,
        },
    }


def write_snapshot(path: Any, snapshot: dict[str, Any]) -> None:
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
