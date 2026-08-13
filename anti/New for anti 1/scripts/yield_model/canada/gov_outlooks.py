"""Catalog + scrape Canadian federal/provincial crop outlooks.

Federal:
  - AAFC Outlook for Principal Field Crops (≈ monthly)
  - StatsCan field-crop survey releases (seasonal calendar)
  - CCYF / Canadian Crop Metrics (Jul–Oct monthly yield model)

Provincial weekly crop-condition reports (growing season ~May–Oct):
  - Saskatchewan Crop Report (weekly)
  - Alberta Crop Report (≈ weekly; full + abbreviated alternate weeks)
  - Manitoba Crop Report (weekly PDF)

Writes cache/gov_outlooks_latest.json and returns a payload suitable for
embedding in canada_yield_forecast.json.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from html import unescape

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(CACHE, "gov_outlooks_latest.json")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

AAFC_INDEX = (
    "https://agriculture.canada.ca/en/sector/crops/reports-statistics"
)
AAFC_BASE = "https://agriculture.canada.ca"
STATCAN_JUNE_2026 = (
    "https://www150.statcan.gc.ca/n1/daily-quotidien/260630/dq260630b-eng.htm"
)
SK_CROP = (
    "https://www.saskatchewan.ca/business/agriculture-natural-resources-and-industry/"
    "agribusiness-farmers-and-ranchers/market-and-trade-statistics/crops-statistics/"
    "crop-report"
)
AB_CROP = "https://open.alberta.ca/publications/2830245"
MB_CROP = (
    "https://www.gov.mb.ca/agriculture/crops/seasonal-reports/crop-report/index.html"
)
MB_BASE = "https://www.gov.mb.ca"
CROP_METRICS = (
    "https://agriculture.canada.ca/en/agricultural-production/weather/"
    "canadian-crop-metrics"
)

# Static cadence contract (what they publish, not what we scraped today).
CADENCE = [
    {
        "id": "aafc_outlook",
        "level": "federal",
        "agency": "AAFC",
        "agency_ko": "캐나다농식품부",
        "title_ko": "주요 밭작물 수급 전망 (Outlook)",
        "cadence": "monthly",
        "cadence_ko": "월 1회",
        "season_window": "year-round",
        "content": "production / supply / exports / prices; mid-season uses CCYF yields",
        "url_index": AAFC_INDEX,
    },
    {
        "id": "ccyf",
        "level": "federal",
        "agency": "AAFC + Statistics Canada",
        "agency_ko": "AAFC·StatsCan",
        "title_ko": "Canadian Crop Yield Forecaster (CCYF)",
        "cadence": "monthly_in_season",
        "cadence_ko": "시즌 중 월 1회 (7–9월, 옥수수·대두 10월 추가)",
        "season_window": "Jul–Oct",
        "content": "CAR/province/national yield model via Crop Metrics",
        "url_index": CROP_METRICS,
    },
    {
        "id": "statcan_field_crops",
        "level": "federal",
        "agency": "Statistics Canada",
        "agency_ko": "통계청",
        "title_ko": "주요 밭작물 면적·생산 조사",
        "cadence": "seasonal_survey",
        "cadence_ko": "시즌 캘린더 (3월 의향·6월 면적·7/8월 생산·11월 확정)",
        "season_window": "survey calendar",
        "content": "official area & production labels (tables 32-10-0359 / SAD)",
        "url_index": "https://www150.statcan.gc.ca/n1/en/type/data",
    },
    {
        "id": "sk_crop_report",
        "level": "provincial",
        "agency": "Saskatchewan Ministry of Agriculture",
        "agency_ko": "서스캐처원 주",
        "title_ko": "주간 Crop Report",
        "cadence": "weekly",
        "cadence_ko": "주 1회 (생육기)",
        "season_window": "≈ May–Oct",
        "content": "topsoil moisture, crop stage, harvest %, damage — not formal yield Mt",
        "url_index": SK_CROP,
    },
    {
        "id": "ab_crop_report",
        "level": "provincial",
        "agency": "Alberta Agriculture and Irrigation",
        "agency_ko": "앨버타 주",
        "title_ko": "주간 Alberta Crop Report",
        "cadence": "weekly",
        "cadence_ko": "주 1회 (격주 요약본 + 격주 전문)",
        "season_window": "≈ May–Oct",
        "content": "crop condition, moisture, progress; used to validate StatCan",
        "url_index": AB_CROP,
    },
    {
        "id": "mb_crop_report",
        "level": "provincial",
        "agency": "Manitoba Agriculture",
        "agency_ko": "매니토바 주",
        "title_ko": "주간 Crop Report PDF",
        "cadence": "weekly",
        "cadence_ko": "주 1회 (생육기 PDF)",
        "season_window": "≈ May–Oct",
        "content": "precip, GDD, pests, regional progress",
        "url_index": MB_CROP,
    },
]


def _fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-CA,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as handle:
        return handle.read().decode("utf-8", errors="replace")


def _strip(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _latest_aafc_outlook() -> dict:
    html = _fetch(AAFC_INDEX)
    paths = re.findall(
        r'href="(/en/sector/crops/reports-statistics/'
        r'canada-outlook-principal-field-crops-20\d{2}-\d{2}-\d{2})"',
        html,
    )
    if not paths:
        raise RuntimeError("no AAFC outlook links on index")
    # Paths are newest-first on the index page.
    path = paths[0]
    url = AAFC_BASE + path
    m = re.search(r"(\d{4}-\d{2}-\d{2})$", path)
    published = m.group(1) if m else None
    body = _fetch(url)
    text = _strip(body)
    ccyf = "CCYF" in text or "Crop Yield Forecast" in text
    # Keep a short English snippet for provenance.
    snippet = ""
    for needle in [
        "The first Canadian Crop Yield Forecast",
        "Canadian Crop Yield Forecast",
        "For 2026-27",
        "For 2026‑27",
    ]:
        i = text.find(needle)
        if i >= 0:
            snippet = text[i:i + 280]
            break
    if not snippet:
        snippet = text[200:480]
    return {
        "id": "aafc_outlook_latest",
        "agency": "AAFC",
        "agency_ko": "캐나다농식품부",
        "title": f"Canada: Outlook for Principal Field Crops, {published}",
        "title_ko": f"주요 밭작물 수급 전망 ({published})",
        "published": published,
        "url": url,
        "incorporates_ccyf": ccyf,
        "summary": snippet,
        "summary_ko": (
            "연방 월간 수급 전망. 시즌 중이면 CCYF 단수 전망을 반영. "
            "주간 작황 리포트가 아니라 생산·수출·재고 표가 핵심."
        ),
    }


def _statcan_area() -> dict:
    # June 2026 seeded-area Daily is the latest area release as of Aug 2026.
    try:
        html = _fetch(STATCAN_JUNE_2026)
        text = _strip(html)
        canola = re.search(
            r"record\s+([\d\.]+)\s+million\s+acres\s+of\s+canola", text, re.I)
        wheat = re.search(
            r"total wheat area falling\s+([\d\.]+)%\s+to\s+([\d\.]+)\s+million",
            text, re.I)
        summary_bits = []
        if canola:
            summary_bits.append(f"canola seeded area record {canola.group(1)} M acres")
        if wheat:
            summary_bits.append(
                f"wheat area {wheat.group(2)} M acres ({wheat.group(1)}% y/y)")
        summary = "; ".join(summary_bits) or text[180:420]
        return {
            "id": "statcan_june_area_2026",
            "agency": "Statistics Canada",
            "agency_ko": "통계청",
            "title": "Principal field crop areas, June 2026",
            "title_ko": "주요 밭작물 파종면적 (2026년 6월)",
            "published": "2026-06-30",
            "url": STATCAN_JUNE_2026,
            "summary": summary,
            "summary_ko": (
                "공식 면적 조사. 단수 전망이 아니라 파종면적 정본. "
                "AAFC July Outlook이 이 수치와 CCYF를 결합해 생산을 상향."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "id": "statcan_june_area_2026",
            "agency": "Statistics Canada",
            "agency_ko": "통계청",
            "title": "Principal field crop areas, June 2026",
            "title_ko": "주요 밭작물 파종면적 (2026년 6월)",
            "published": "2026-06-30",
            "url": STATCAN_JUNE_2026,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _sk_weekly() -> dict:
    html = _fetch(SK_CROP)
    text = _strip(html)
    period = re.search(
        r"For the Period ([A-Za-z]+ \d{1,2} to [A-Za-z]+ \d{1,2},? 20\d{2})",
        text,
    )
    moisture = re.search(
        r"Cropland topsoil moisture is:\s*"
        r"(\d+) per cent surplus;\s*"
        r"(\d+) per cent adequate;\s*"
        r"(\d+) per cent short;\s*and\s*"
        r"(\d+) per cent very short",
        text, re.I,
    )
    harvest = re.search(
        r"harvest is\s+([\d\.]+)\s+per cent complete", text, re.I)
    summary_parts = []
    if moisture:
        summary_parts.append(
            f"cropland moisture surplus/adequate/short/v.short="
            f"{moisture.group(1)}/{moisture.group(2)}/"
            f"{moisture.group(3)}/{moisture.group(4)}%"
        )
    if harvest:
        summary_parts.append(f"harvest {harvest.group(1)}% complete")
    return {
        "id": "sk_crop_report_latest",
        "agency": "Saskatchewan Ministry of Agriculture",
        "agency_ko": "서스캐처원 주",
        "title": f"SK Crop Report — {period.group(1) if period else 'latest'}",
        "title_ko": f"SK 주간 작황 — {period.group(1) if period else '최신'}",
        "period": period.group(1) if period else None,
        "published_hint": period.group(1) if period else None,
        "url": SK_CROP,
        "cadence": "weekly",
        "summary": "; ".join(summary_parts) or text[200:450],
        "summary_ko": (
            "주간 작황·수분·수확 진도. 주 단위 Mt 단수 전망은 없고 "
            "상태 지표(수분·생육·피해) 중심."
        ),
    }


def _ab_weekly() -> dict:
    # Open Alberta often 403s automated clients; keep a curated fallback
    # refreshed when the live scrape succeeds.
    fallback = {
        "id": "ab_crop_report_latest",
        "agency": "Alberta Agriculture and Irrigation",
        "agency_ko": "앨버타 주",
        "title": "AB Crop Report — as of July 28, 2026",
        "title_ko": "AB 주간 작황 — July 28, 2026",
        "as_of": "July 28, 2026",
        "page_updated": "July 31, 2026",
        "recent_releases": [
            "July 28, 2026", "July 21, 2026", "July 14, 2026",
            "July 7, 2026", "June 30, 2026", "June 23, 2026",
        ],
        "url": AB_CROP,
        "cadence": "weekly",
        "fetch_status": "fallback_curated",
        "summary": (
            "Latest condition report as of July 28, 2026; "
            "Open Alberta page updated July 31, 2026. "
            "Program alternates full and abbreviated weekly reports."
        ),
        "summary_ko": (
            "주간(격주 요약) 작황. StatsCan 주 추정치 교차검증용. "
            "연방 Mt 전망과는 별층. (자동 수집 403 시 수동 확인본)"
        ),
    }
    try:
        html = _fetch(AB_CROP)
    except Exception as exc:  # noqa: BLE001
        fallback["error"] = f"{type(exc).__name__}: {exc}"
        return fallback
    text = _strip(html)
    dates = re.findall(
        r"Crop conditions as of ([A-Za-z]+ \d{1,2}, 20\d{2})", text)
    updated = re.search(r"Updated\s+([A-Za-z]+ \d{1,2}, 20\d{2})", text)
    latest = dates[0] if dates else None
    if not latest:
        fallback["fetch_status"] = "parsed_empty_using_fallback"
        return fallback
    return {
        "id": "ab_crop_report_latest",
        "agency": "Alberta Agriculture and Irrigation",
        "agency_ko": "앨버타 주",
        "title": f"AB Crop Report — as of {latest}",
        "title_ko": f"AB 주간 작황 — {latest}",
        "as_of": latest,
        "page_updated": updated.group(1) if updated else None,
        "recent_releases": dates[:6],
        "url": AB_CROP,
        "cadence": "weekly",
        "fetch_status": "live",
        "summary": (
            f"Latest condition report as of {latest}; "
            f"page updated {updated.group(1) if updated else '?'}. "
            f"Recent: {', '.join(dates[:4])}"
        ),
        "summary_ko": (
            "주간(격주 요약) 작황. StatsCan 주 추정치 교차검증용. "
            "연방 Mt 전망과는 별층."
        ),
    }


def _mb_weekly() -> dict:
    html = _fetch(MB_CROP)
    # Absolute or relative PDF links with dates in filename.
    pdfs = re.findall(
        r'href="([^"]*crop-report-20\d{2}-\d{2}-\d{2}\.pdf)"', html)
    labels = re.findall(
        r'crop-report-(20\d{2}-\d{2}-\d{2})\.pdf"[^>]*>([^<]+)<', html)
    if not labels:
        labels = [(m.group(1), m.group(1)) for m in
                  (re.search(r"crop-report-(20\d{2}-\d{2}-\d{2})", p)
                   for p in pdfs) if m]
    latest_date, latest_label = (labels[0] if labels else (None, None))
    href = pdfs[0] if pdfs else MB_CROP
    if href.startswith("/"):
        href = MB_BASE + href
    return {
        "id": "mb_crop_report_latest",
        "agency": "Manitoba Agriculture",
        "agency_ko": "매니토바 주",
        "title": f"MB Crop Report — {latest_label or latest_date or 'latest'}",
        "title_ko": f"MB 주간 작황 — {latest_label or latest_date or '최신'}",
        "published": latest_date,
        "url": href,
        "index_url": MB_CROP,
        "cadence": "weekly",
        "recent_releases": [d for d, _ in labels[:8]],
        "summary": (
            f"Latest PDF {latest_date}; "
            f"recent weekly releases: {', '.join(d for d, _ in labels[:5])}"
        ),
        "summary_ko": (
            "주간 PDF. 강수·GDD·병해충·지역 진도. "
            "단수 kg/ha 공식 전망은 StatsCan/AAFC 쪽."
        ),
    }


def build_snapshot() -> dict:
    errors = {}
    outlooks = []
    weekly = []

    try:
        outlooks.append(_latest_aafc_outlook())
    except Exception as exc:  # noqa: BLE001
        errors["aafc"] = f"{type(exc).__name__}: {exc}"

    outlooks.append(_statcan_area())

    for name, fn in (
        ("sk", _sk_weekly),
        ("ab", _ab_weekly),
        ("mb", _mb_weekly),
    ):
        try:
            weekly.append(fn())
        except Exception as exc:  # noqa: BLE001
            errors[name] = f"{type(exc).__name__}: {exc}"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "country": "Canada",
        "cadence": CADENCE,
        "government_outlooks": outlooks,
        "provincial_weekly_crop_reports": weekly,
        "notes_ko": (
            "연방 AAFC는 월간 수급·단수(시즌 중 CCYF) 전망을 내고, "
            "프레리 3개 주는 생육기 주간 작황(수분·진도·피해)을 올린다. "
            "주간 리포트는 Mt/kg·ha 공식 전망이 아니라 상태 지표다."
        ),
        "errors": errors,
    }
    os.makedirs(CACHE, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return payload


def main() -> int:
    payload = build_snapshot()
    print(f"[gov] outlooks={len(payload['government_outlooks'])} "
          f"weekly={len(payload['provincial_weekly_crop_reports'])} "
          f"errors={payload['errors'] or '{}'}", flush=True)
    for row in payload["government_outlooks"]:
        print(f"[gov] FED {row.get('published') or row.get('title')} → "
              f"{row.get('url')}", flush=True)
    for row in payload["provincial_weekly_crop_reports"]:
        print(f"[gov] PROV {row.get('id')}: "
              f"{row.get('period') or row.get('as_of') or row.get('published')} "
              f"→ {row.get('url')}", flush=True)
    print(f"[gov] wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
