"""Keyless official cargo references, separate from daily AIS and scenarios.

No oil/tanker composition, dark-fleet correction or transit probability is
invented here. A quarterly daily mean is never expanded into daily records.
"""

from __future__ import annotations

import calendar
import copy
import hashlib
import math
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable

from shipping_capacity.iea_reports import collect_iea_reports


EIA_URL = "https://www.eia.gov/outlooks/steo/report/energysecurity/article.php"
IMO_URL = "https://www.imo.org/en/mediacentre/hottopics/pages/middle-east-strait-of-hormuz.aspx"
IMO_RED_SEA_URL = "https://www.imo.org/en/mediacentre/hottopics/pages/red-sea.aspx"
SCA_URL = "https://www.suezcanal.gov.eg/English/Navigation/pages/navigationstatistics.aspx"
WARNING_KO = (
    "기관의 기간별 일평균 추정값입니다. 특정 날짜의 실제 통항량이나 "
    "안전한 통항 확률이 아닙니다. AIS 누락과 사후 수정 가능성이 있습니다."
)
# Bab el-Mandeb is optional: an older or trimmed EIA page without that table
# must not cost the Hormuz/Suez references their refresh.
EIA_TABLES = (
    ("hormuz", "strait of hormuz", "strait_of_hormuz", True),
    ("suez", "suez canal and sumed pipeline", "suez_canal_and_sumed_pipeline", True),
    ("bab_el_mandeb", "bab el-mandeb strait", "strait_of_bab_el_mandeb", False),
)
POINT_IDS = tuple(point_id for point_id, *_ in EIA_TABLES)
CARGO_LABELS = {
    "total_oil": "석유 전체",
    "crude_condensate": "원유+콘덴세이트",
    "petroleum_products": "석유제품",
    "lng": "LNG",
}


def clean(value: str) -> str:
    return " ".join(value.split())


class OfficialHTML(HTMLParser):
    """Extract semantic HTML tables, publication dates and public links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, Any]] = []
        self.releases: list[str] = []
        self.links: list[dict[str, str]] = []
        self.table: dict[str, Any] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.caption: list[str] | None = None
        self.release: list[str] | None = None
        self.anchor: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            self.table = {"caption": "", "rows": []}
        elif tag == "caption" and self.table is not None:
            self.caption = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        if tag == "span" and "releasedate" in (attributes.get("class") or "").split():
            self.release = []
        if tag == "a" and attributes.get("href"):
            self.anchor = {"href": attributes["href"], "parts": []}

    def handle_data(self, data: str) -> None:
        for parts in (self.cell, self.caption, self.release):
            if parts is not None:
                parts.append(data)
        if self.anchor is not None:
            self.anchor["parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(clean("".join(self.cell)))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            self.table["rows"].append(self.row)
            self.row = None
        elif tag == "caption" and self.caption is not None and self.table is not None:
            self.table["caption"] = clean("".join(self.caption))
            self.caption = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None
        if tag == "span" and self.release is not None:
            self.releases.append(clean("".join(self.release)))
            self.release = None
        if tag == "a" and self.anchor is not None:
            self.links.append({"href": self.anchor["href"], "title": clean("".join(self.anchor["parts"]))})
            self.anchor = None


def quarter_dates(period: str) -> tuple[str, str]:
    match = re.fullmatch(r"([1-4])Q(\d{2}|\d{4})", period)
    if not match:
        raise ValueError("unsupported EIA observation period")
    quarter, year = int(match[1]), int(match[2])
    if year < 100:
        year += 2000
    month = 3 * quarter
    return date(year, month - 2, 1).isoformat(), date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def parse_eia(html: str, retrieved_at: str) -> dict[str, Any]:
    parsed = OfficialHTML()
    parsed.feed(html)
    if len(parsed.releases) != 1:
        raise ValueError("EIA section publication date missing or ambiguous")
    released = parsed.releases[0].removeprefix("Release Date:").strip()
    published = datetime.strptime(released, "%B %d, %Y").date().isoformat()
    records: dict[str, list[dict[str, Any]]] = {point_id: [] for point_id in POINT_IDS}
    missing_optional: list[str] = []
    for chokepoint_id, caption_term, oil_scope, required in EIA_TABLES:
        tables = [table for table in parsed.tables if caption_term in table["caption"].lower()]
        if not tables and not required:
            missing_optional.append(chokepoint_id)
            continue
        if len(tables) != 1:
            raise ValueError(f"EIA {chokepoint_id} cargo table missing or ambiguous")
        table = tables[0]
        headers = [row for row in table["rows"] if len(row) > 1 and all(re.fullmatch(r"[1-4]Q(?:\d{2}|\d{4})", item) for item in row[1:])]
        if len(headers) != 1 or not any("million barrels per day" in " ".join(row).lower() for row in table["rows"]):
            raise ValueError("EIA period headers or oil unit changed")
        periods = headers[0][1:]
        if len(set(periods)) != len(periods):
            raise ValueError("duplicate EIA periods")
        seen: set[str] = set()
        for row in table["rows"]:
            if not row:
                continue
            label = row[0].lower()
            category = (
                "total_oil" if label.startswith("total oil flows through") else
                "crude_condensate" if label == "crude oil and condensate" else
                "petroleum_products" if label == "petroleum products" else
                "lng" if label.startswith("lng flows through") else None
            )
            if category is None:
                continue
            if category in seen or len(row) != len(periods) + 1:
                raise ValueError("duplicate or misaligned EIA commodity row")
            seen.add(category)
            if category == "lng" and "billion cubic feet per day" not in label:
                raise ValueError("EIA LNG unit changed")
            unit = "billion_cubic_feet_per_day" if category == "lng" else "barrels_per_day"
            scope = "suez_canal" if chokepoint_id == "suez" and category == "lng" else oil_scope
            for period, raw_value in zip(periods, row[1:]):
                start, end = quarter_dates(period)
                if date.fromisoformat(end) > date.fromisoformat(published):
                    raise ValueError("EIA table includes future periods; forecast must be separated")
                value = None if raw_value in ("-", "—", "N/A", "") else float(raw_value.replace(",", ""))
                if value is not None and (not math.isfinite(value) or value < 0):
                    raise ValueError("invalid EIA cargo value")
                records[chokepoint_id].append({
                    "id": f"eia:{scope}:{category}:{start}",
                    "chokepoint_id": chokepoint_id,
                    "cargo_category": category,
                    "label_ko": CARGO_LABELS[category],
                    "period": period,
                    "period_start": start,
                    "period_end": end,
                    "frequency": "quarterly",
                    "statistic": "period_daily_mean",
                    "value": value if category == "lng" or value is None else round(value * 1_000_000),
                    "unit": unit,
                    "source_value": value,
                    "source_unit": "billion_cubic_feet_per_day" if category == "lng" else "million_barrels_per_day",
                    "direction": "source_aggregate_not_direction_resolved",
                    "geography_scope": scope,
                    "evidence_class": "institution_estimate",
                    "publisher": "EIA",
                    "upstream_provider": "Vortexa with EIA analysis",
                    "source_url": EIA_URL,
                    "source_published_at": published,
                    "retrieved_at": retrieved_at,
                    "revision_status": "revisable_institution_estimate",
                    "method_id": "official_table_unit_conversion_only",
                    "reuse_status": "publisher_reuse_permitted_third_party_exceptions_apply",
                    "license_url": "https://www.eia.gov/about/copyrights_reuse.php",
                    "attribution": f"Source: U.S. Energy Information Administration ({published}); EIA analysis based on Vortexa. Extracted, translated and unit-converted by Chokemonitor; original: {EIA_URL}",
                    "status": "reported" if value is not None else "not_reported",
                    "warning_ko": WARNING_KO + (" 석유 수치는 SUMED 파이프라인을 포함합니다." if scope == "suez_canal_and_sumed_pipeline" else ""),
                })
        if seen != set(CARGO_LABELS):
            raise ValueError("required EIA commodity categories missing")
        for period in periods:
            oil = {row["cargo_category"]: row["source_value"] for row in records[chokepoint_id] if row["period"] == period and row["cargo_category"] != "lng"}
            if all(value is not None for value in oil.values()):
                difference = abs(oil["total_oil"] - oil["crude_condensate"] - oil["petroleum_products"])
                if difference > 0.150001:
                    raise ValueError("EIA oil composition does not reconcile within source rounding")
    return {"records": records, "missing_optional_tables": missing_optional,
            "source_published_at": published, "content_sha256": hashlib.sha256(html.encode()).hexdigest()}


def year_ago_comparison(card: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Same publisher, frequency, scope and commodity, one year earlier."""
    start = date.fromisoformat(card["period_start"])
    target = start.replace(year=start.year - 1).isoformat()
    prior = next((row for row in rows if row["period_start"] == target
                  and all(row.get(key) == card.get(key) for key in ("publisher", "frequency", "geography_scope", "cargo_category", "unit"))), None)
    if prior is None or prior.get("value") is None or card.get("value") is None:
        return None
    return {
        "period": prior["period"],
        "value": prior["value"],
        # A zero base has no meaningful percentage; keep both values instead.
        "change_pct": round((card["value"] / prior["value"] - 1) * 100, 1) if prior["value"] > 0 else None,
    }


def parse_imo_links(html: str, base_url: str = IMO_URL, include_statements: bool = False) -> list[dict[str, str]]:
    parsed = OfficialHTML()
    parsed.feed(html)
    links: dict[str, dict[str, str]] = {}
    for link in parsed.links:
        title = link["title"]
        url = urllib.parse.urljoin(base_url, link["href"])
        parts = urllib.parse.urlparse(url)
        # The Red Sea page also lists IMO's own statements on attacks; they
        # are official text, so they are kept as links (not parsed for counts).
        statement = (include_statements and parts.hostname == "www.imo.org" and "/pressbriefings/" in parts.path.lower()
                     and re.search(r"statement|attack", title, re.IGNORECASE) is not None)  # not the menu link
        if not statement and not any(term in title.lower() for term in ("list of incidents", "latest incidents", "advisories", "navarea ix warnings")):
            continue
        if parts.scheme != "https" or parts.hostname not in {"www.imo.org", "wwwcdn.imo.org", "www.ukmto.org", "hydrography.paknavy.gov.pk"}:
            continue
        links[url] = {"title": title, "source_url": url, "publisher": "IMO" if statement else "IMO linked official source",
                      "evidence_class": "official_statement" if statement else "official_advisory_reference"}
    if not links:
        raise ValueError("IMO official advisory references missing")
    return list(links.values())


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Chokemonitor/1.0 public-reference-collector", "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=12) as response:
        if urllib.parse.urlparse(response.geturl()).hostname != urllib.parse.urlparse(url).hostname:
            raise ValueError("official source redirected outside its publisher host")
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("official HTML response exceeds size limit")
        return body.decode(response.headers.get_content_charset() or "utf-8")


def collect_official_cargo(
    *, fetch: bool = False, previous: dict[str, Any] | None = None,
    now: datetime | None = None, fetcher: Callable[[str], str] = fetch_html,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    timestamp = now.isoformat()
    previous = previous or {}
    eia: dict[str, Any] = copy.deepcopy(previous.get("sources", {}).get("eia", {}))
    eia.setdefault("records", {})
    for point_id in POINT_IDS:
        eia["records"].setdefault(point_id, [])
    imo = copy.deepcopy(previous.get("sources", {}).get("imo", {}))
    imo.setdefault("links", [])
    imo_red_sea = copy.deepcopy(previous.get("sources", {}).get("imo_red_sea", {}))
    imo_red_sea.setdefault("links", [])
    for source_id, source, url, parser in (
        ("eia", eia, EIA_URL, lambda html: parse_eia(html, timestamp)),
        ("imo", imo, IMO_URL, lambda html: {"links": parse_imo_links(html)}),
        ("imo_red_sea", imo_red_sea, IMO_RED_SEA_URL,
         lambda html: {"links": parse_imo_links(html, IMO_RED_SEA_URL, include_statements=True)}),
    ):
        source.update({"source_url": url, "last_attempt_at": timestamp if fetch else source.get("last_attempt_at"), "api_key_required": False})
        if fetch:
            try:
                update = parser(fetcher(url))
                # Never replace a newer good revision with an older response.
                if source_id == "eia" and update["source_published_at"] < source.get("source_published_at", ""):
                    raise ValueError("official source revision regressed")
                source.update(update)
                source.update({"status": "fetched", "retrieved_at": timestamp, "error_code": None})
            except Exception as exc:
                has_cache = bool(source.get("links")) if source_id != "eia" else any(source.get("records", {}).values())
                source.update({"status": "cached_fallback" if has_cache else "unavailable", "error_code": type(exc).__name__})
        else:
            source["status"] = "cached_offline" if source.get("retrieved_at") else "not_fetched"
    iea = collect_iea_reports(
        fetch=fetch, previous=previous.get("sources", {}).get("iea"), timestamp=timestamp, fetcher=fetcher,
    )
    sources = {"eia": eia, "imo": imo, "imo_red_sea": imo_red_sea, "iea": iea}
    advisories = {
        "hormuz": (imo["links"], imo["status"]),
        "suez": ([{"title": "Suez Canal Authority navigation statistics", "source_url": SCA_URL, "evidence_class": "official_reference"}], "reference_link_only"),
        "bab_el_mandeb": (imo_red_sea["links"], imo_red_sea["status"]),
    }
    points = {}
    for point_id in POINT_IDS:
        eia_rows = eia.get("records", {}).get(point_id, [])
        iea_rows = iea.get("records", {}).get(point_id, [])
        rows = eia_rows + iea_rows
        cards = []
        for category in CARGO_LABELS:
            matching = [row for row in eia_rows if row["cargo_category"] == category]
            if matching:
                card = copy.deepcopy(max(matching, key=lambda row: row["period_end"]))
                card["source_status"] = eia["status"]
                card["period_end_age_days"] = max(0, (now.date() - date.fromisoformat(card["period_end"])).days)
                card["display_label_ko"] = f"{card['label_ko']} · {card['period']} 일평균"
                card["year_ago"] = year_ago_comparison(card, eia_rows)
                cards.append(card)
        supplementary = []
        if iea_rows:
            card = copy.deepcopy(max(iea_rows, key=lambda row: row["period_end"]))
            card["source_status"] = iea["status"]
            card["period_end_age_days"] = max(0, (now.date() - date.fromisoformat(card["period_end"])).days)
            card["display_label_ko"] = f"IEA 석유 전체 · {card['period']} 월평균"
            card["year_ago"] = year_ago_comparison(card, iea_rows)
            supplementary.append(card)
        points[point_id] = {
            "status": "references_available" if cards or supplementary else "official_reference_unavailable",
            "reference_cards": cards,
            "supplementary_reference_cards": supplementary,
            "reported_series": rows,
            "reference_comparison_policy": "group_by_publisher_period_scope_and_commodity_never_mix_composition",
            "daily_chart": {
                "source_path": f"chokepoints_live.{point_id}.metric_histories",
                "unit": "estimated_trade_tonnes_per_day",
                "classification": "ship_type_not_commodity",
                "ship_type_keys": ["all", "container", "dry_bulk", "tanker", "general_cargo"],
                "warning_ko": "선종별 일별 AIS 기반 추정 교역량입니다. 원유·제품별 실제 화물 명세가 아닙니다.",
            },
            "daily_crude_barrels": {"status": "unavailable_no_validated_daily_commodity_source", "value": None, "unit": "barrels_per_day"},
            "transit_assessment": {
                "status": "evidence_references_only_not_probability",
                "success_probability": None,
                "insurance_availability": "unknown",
                "advisory_references": advisories[point_id][0],
                "advisory_source_status": advisories[point_id][1],
                "warning_ko": "통항 물량은 안전·보험·허가를 갖춘 일반 상업운항의 성공확률이 아닙니다. 경보 원문과 발표일을 확인하세요.",
            },
            "commodity_breakdown_status": "latest_sca_commodity_tonnes_not_connected" if point_id == "suez" else "official_quarterly_energy_reference_only",
        }
    return {
        "contract_version": "official-chokepoint-cargo-v1",
        "generated_at": timestamp,
        "status": "available" if any(source["status"] == "fetched" and any(source["records"].values()) for source in (eia, iea)) else "cached" if any(rows for source in (eia, iea) for rows in source["records"].values()) else "unavailable",
        "api_keys_required": [],
        "collection_policy": "keyless_reports_with_last_good_fallback_no_seed_no_daily_imputation",
        "sources": sources,
        "chokepoints": points,
    }
