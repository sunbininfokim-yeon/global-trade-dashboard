"""Bounded discovery of explicitly licensed, completed-period IEA references.

This is not a daily oil model. Unsupported prose becomes a review candidate,
not an inferred number. Private datasets and chart pixel extraction are absent.
"""

from __future__ import annotations

import calendar
import copy
import hashlib
import math
import re
import urllib.parse
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any, Callable


IEA_DISCOVERY_URL = "https://www.iea.org/topics/the-middle-east-and-global-energy-markets"
MONTHS = {calendar.month_name[number]: number for number in range(1, 13)}
FLOW_PATTERN = re.compile(
    r"\bFlows through the Strait of Hormuz averaged(?: only)? "
    r"(?P<value>\d+(?:\.\d+)?) (?:mb/d|million barrels per day) in "
    r"(?P<month>" + "|".join(MONTHS) + r")(?: (?P<year>20\d{2}))?(?=[\s,.])"
)


class ReportHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.canonical: list[str] = []
        self.dates: list[str] = []
        self.paragraphs: list[str] = []
        self.paragraph: list[str] | None = None
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if self.hidden:
            return
        if tag == "p":
            self.paragraph = []
        elif tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])
        elif tag == "link" and attributes.get("rel") == "canonical":
            self.canonical.append(attributes.get("href") or "")
        elif tag == "time" and attributes.get("datetime"):
            self.dates.append(attributes["datetime"][:10])

    def handle_data(self, data: str) -> None:
        if not self.hidden and self.paragraph is not None:
            self.paragraph.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        elif tag == "p" and self.paragraph is not None:
            self.paragraphs.append(" ".join("".join(self.paragraph).split()))
            self.paragraph = None


def public_report_url(url: str) -> bool:
    parts = urllib.parse.urlparse(url)
    return (
        parts.scheme == "https" and parts.netloc == "www.iea.org"
        and parts.path.startswith("/commentaries/")
        and not parts.query and not parts.fragment
    )


def discover_iea_reports(html: str) -> list[str]:
    parsed = ReportHTML()
    parsed.feed(html)
    candidates: list[str] = []
    for link in parsed.links:
        url = urllib.parse.urljoin(IEA_DISCOVERY_URL, link)
        if public_report_url(url) and any(term in url for term in ("hormuz", "middle-east", "gulf")):
            if url not in candidates:
                candidates.append(url)
    if not candidates:
        raise ValueError("IEA official discovery has no supported public report links")
    return candidates[:4]


def parse_iea_report(html: str, source_url: str, retrieved_at: str) -> list[dict[str, Any]]:
    if not public_report_url(source_url):
        raise ValueError("unsupported IEA report URL")
    parsed = ReportHTML()
    parsed.feed(html)
    if parsed.canonical != [source_url]:
        raise ValueError("IEA report canonical identity missing or changed")
    if not any("Licence: CC BY 4.0" in paragraph for paragraph in parsed.paragraphs):
        raise ValueError("IEA report reuse license not explicitly verified")
    if len(set(parsed.dates)) != 1:
        raise ValueError("IEA report publication date missing or ambiguous")
    published = date.fromisoformat(parsed.dates[0])
    if published > datetime.fromisoformat(retrieved_at).date():
        raise ValueError("IEA report publication date is in the future")
    records: dict[str, dict[str, Any]] = {}
    for paragraph in parsed.paragraphs:
        for match in FLOW_PATTERN.finditer(paragraph):
            month = MONTHS[match["month"]]
            year = int(match["year"]) if match["year"] else published.year - int(month > published.month)
            start = date(year, month, 1)
            end = date(year, month, calendar.monthrange(year, month)[1])
            if end > published:
                raise ValueError("IEA incomplete or future monthly reference must not be history")
            value = float(match["value"])
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError("invalid IEA oil flow reference")
            record_id = f"iea:strait_of_hormuz:total_oil:{start.isoformat()}"
            record = {
                "id": record_id, "chokepoint_id": "hormuz", "cargo_category": "total_oil",
                "label_ko": "석유 전체", "period": f"{year}-{month:02d}",
                "period_start": start.isoformat(), "period_end": end.isoformat(),
                "frequency": "monthly", "statistic": "period_daily_mean",
                "value": round(value * 1_000_000), "unit": "barrels_per_day",
                "source_value": value, "source_unit": "million_barrels_per_day",
                "direction": "source_aggregate_not_direction_resolved",
                "geography_scope": "strait_of_hormuz", "evidence_class": "institution_estimate",
                "publisher": "IEA", "upstream_provider": "IEA published analysis; report also cites Kpler; not an independent raw AIS feed",
                "source_url": source_url, "source_published_at": published.isoformat(),
                "retrieved_at": retrieved_at, "status": "reported",
                "revision_status": "revisable_institution_estimate",
                "method_id": "explicit_licensed_report_unit_conversion_only",
                "reuse_status": "publisher_cc_by_4_0", "license": "CC BY 4.0",
                "attribution": f"IEA ({published.year}), {source_url}, Licence: CC BY 4.0; extracted and unit-converted by Chokemonitor.",
                "warning_ko": "기관이 발표한 해당 월의 석유 전체 일평균 추정값입니다. 원유 단독·오늘의 실측량·미포착 물량 보정치가 아닙니다. 다른 기간·품목 카드와 구성비를 계산하지 마세요.",
            }
            if record_id in records and records[record_id]["value"] != record["value"]:
                raise ValueError("conflicting IEA values in one report")
            records[record_id] = record
    if not records:
        raise ValueError("IEA prose has no supported explicit completed-month Hormuz flow")
    return list(records.values())


def collect_iea_reports(
    *, fetch: bool, previous: dict[str, Any] | None, timestamp: str,
    fetcher: Callable[[str], str],
) -> dict[str, Any]:
    source = copy.deepcopy(previous or {})
    source.setdefault("records", {"hormuz": [], "suez": []})
    source.update({
        "source_url": IEA_DISCOVERY_URL, "api_key_required": False,
        "last_attempt_at": timestamp if fetch else source.get("last_attempt_at"),
        "collection_policy": "official_topic_discovery_max_4_reports_explicit_cc_by_facts_only",
    })
    if not fetch:
        source["status"] = "cached_offline" if source.get("retrieved_at") else "not_fetched"
        return source
    try:
        candidates = discover_iea_reports(fetcher(IEA_DISCOVERY_URL))
        records = {row["id"]: row for row in source["records"].get("hormuz", [])}
        parsed_count = 0
        errors = []
        for url in candidates:
            try:
                html = fetcher(url)
                incoming = parse_iea_report(html, url, timestamp)
                for row in incoming:
                    old = records.get(row["id"])
                    if old and old["source_published_at"] > row["source_published_at"]:
                        raise ValueError("IEA revision regressed")
                # Validate the whole candidate before replacing any cached row.
                for row in incoming:
                    row["content_sha256"] = hashlib.sha256(html.encode()).hexdigest()
                    records[row["id"]] = row
                parsed_count += 1
            except Exception as exc:
                errors.append({"source_url": url, "error_code": type(exc).__name__, "status": "review_required_not_published"})
        source["candidate_errors"] = errors
        source["discovered_report_urls"] = candidates
        if not parsed_count:
            raise ValueError("no newly verified IEA monthly report")
        source["records"] = {"hormuz": sorted(records.values(), key=lambda row: row["period_end"]), "suez": []}
        source.update({"status": "fetched", "retrieved_at": timestamp, "error_code": None})
    except Exception as exc:
        source.update({
            "status": "cached_fallback" if any(source["records"].values()) else "unavailable",
            "error_code": type(exc).__name__,
        })
    return source
