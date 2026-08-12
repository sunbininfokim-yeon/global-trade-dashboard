"""Official-only Fed collector for FOMC votes, membership, and Beige Book.

This module deliberately indexes public facts rather than assigning policy
preferences or a sentiment score.  A failed parser returns an explicit error
to the caller; it never fills a missing official item from a fixture.
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


FED_ROOT = "https://www.federalreserve.gov"
FOMC_CALENDAR_URL = f"{FED_ROOT}/monetarypolicy/fomccalendars.htm"
FOMC_MEMBERS_URL = f"{FED_ROOT}/monetarypolicy/fomc.htm"
BEIGE_BOOK_URL = f"{FED_ROOT}/monetarypolicy/publications/beige-book-default.htm"
UA = "Mozilla/5.0 (compatible; macro-monitor-fed-quality/1.0; research)"
ET = ZoneInfo("America/New_York")


class FedOfficialSourceError(RuntimeError):
    """Raised when an official Fed page changes beyond a safe parser path."""


def fetch_text(url: str, *, opener: Callable[..., Any] = urlopen) -> str:
    request = Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with opener(request, timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def _clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _absolute(path: str) -> str:
    return urljoin(FED_ROOT, html.unescape(path))


def _person_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _names(value: str) -> list[str]:
    value = _clean(value).rstrip(".")
    value = re.sub(r"^(?:;\s*)?(?:and|&|as well as)\s+", "", value, flags=re.IGNORECASE)
    # Many FOMC statements use semicolons because a name is followed by a
    # title (", Chair").  Split that form first so titles do not become names.
    if ";" in value:
        parts = re.split(r";\s*", value)
    else:
        value = re.sub(r",?\s*(?:and|&|as well as)\s+", ", ", value, flags=re.IGNORECASE)
        parts = re.split(r",\s*|\s+(?:and|&|as well as)\s+", value, flags=re.IGNORECASE)
    out = []
    for part in parts:
        part = re.sub(r"^(?:and|&|as well as)\s+", "", part.strip(), flags=re.IGNORECASE)
        part = re.sub(r",\s*(?:Chair|Vice Chair)$", "", part, flags=re.IGNORECASE)
        if part:
            out.append(part)
    return out


def _published_at(meeting_date: str) -> str:
    parsed = datetime.strptime(meeting_date, "%Y-%m-%d").replace(hour=14, tzinfo=ET)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _retrieved_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_fomc_calendar(html_text: str, *, years: Iterable[int]) -> list[dict[str, Any]]:
    """Extract statement/minutes/SEP links from official calendar panels."""
    wanted = {int(year) for year in years}
    out: list[dict[str, Any]] = []
    panels = list(
        re.finditer(
            r"<h4>\s*<a[^>]*>\s*(?P<year>20\d{2})\s+FOMC Meetings\s*</a>\s*</h4>(?P<body>.*?)(?=<div class=\"panel panel-default\"|<h4>\s*<a[^>]*>\s*20\d{2}\s+FOMC Meetings|\Z)",
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )
    for panel in panels:
        year = int(panel.group("year"))
        if year not in wanted:
            continue
        body = panel.group("body")
        starts = [
            match.start()
            for match in re.finditer(
                r'<div\s+class="[^\"]*\brow\s+fomc-meeting\b[^\"]*"[^>]*>', body, flags=re.IGNORECASE
            )
        ]
        for index, start in enumerate(starts):
            chunk = body[start : starts[index + 1] if index + 1 < len(starts) else len(body)]
            if not re.search(r"<strong>\s*Statement:\s*</strong>", chunk, flags=re.IGNORECASE):
                continue
            statement = re.search(r'href="([^"]*/monetary(20\d{6})a\.htm)"', chunk, flags=re.IGNORECASE)
            if not statement:
                continue
            yyyymmdd = statement.group(2)
            if int(yyyymmdd[:4]) != year:
                continue
            minutes = re.search(r'href="([^"]*/fomcminutes20\d{6}\.htm)"', chunk, flags=re.IGNORECASE)
            sep = re.search(r'href="([^"]*/fomcprojtabl20\d{6}\.htm)"', chunk, flags=re.IGNORECASE)
            month = re.search(r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>', chunk, flags=re.IGNORECASE)
            out.append(
                {
                    "meeting_date": f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}",
                    "meeting_month_display": _clean(month.group(1)) if month else None,
                    "statement_url": _absolute(statement.group(1)),
                    "minutes_url": _absolute(minutes.group(1)) if minutes else None,
                    "sep_url": _absolute(sep.group(1)) if sep else None,
                }
            )
    unique = {row["meeting_date"]: row for row in out}
    return [unique[key] for key in sorted(unique)]


def parse_fomc_members(html_text: str) -> dict[str, Any]:
    """Extract the current public voting roster, not inferred participant views."""
    heading = re.search(r"<h4>\s*(20\d{2})\s+Committee Members\s*</h4>\s*<ul>(?P<body>.*?)</ul>", html_text, re.IGNORECASE | re.DOTALL)
    if not heading:
        raise FedOfficialSourceError("current FOMC Committee Members list was not found")
    members = []
    for item in re.findall(r"<li>(.*?)</li>", heading.group("body"), flags=re.IGNORECASE | re.DOTALL):
        text = _clean(item)
        if not text or "," not in text:
            continue
        name, role = [part.strip() for part in text.split(",", 1)]
        members.append({"person_id": _person_id(name), "name": name, "role": role})
    if len(members) < 8:
        raise FedOfficialSourceError("current FOMC roster was unexpectedly sparse")
    return {
        "roster_year": int(heading.group(1)),
        "source_url": FOMC_MEMBERS_URL,
        "members": members,
        "policy": "official_current_voting_members_only",
    }


def _dissent_direction(preference: str) -> str:
    low = preference.lower()
    if re.search(r"\b(raise|increase|higher|tighten)\b", low):
        return "tighter"
    if re.search(r"\b(lower|decrease|reduce|cut|easier)\b", low):
        return "easier"
    return "other_public_dissent"


def parse_fomc_statement(html_text: str, *, meeting_date: str, source_url: str) -> dict[str, Any]:
    """Parse public FOMC vote names and dissent wording from a statement."""
    text = _clean(html_text)
    for_match = re.search(
        r"Voting for (?:(?:the )?(?:monetary )?policy action|this action) (?:were|was) (?P<names>.+?)(?=\s+Voting against|\s+For media|\s+Implementation Note|$)",
        text,
        flags=re.IGNORECASE,
    )
    against_start = re.search(
        r"Voting against (?:(?:the )?(?:monetary )?policy action|this action) (?:were|was) (?P<body>.+?)(?=\s+For media|\s+Implementation Note|$)",
        text,
        flags=re.IGNORECASE,
    )
    decision = re.search(r"The Committee decided to (?P<decision>.+?)\.", text, flags=re.IGNORECASE)
    votes = [
        {"person_id": _person_id(name), "name": name, "vote": "for", "evidence": "official_statement"}
        for name in _names(for_match.group("names"))
    ] if for_match else []
    if against_start:
        dissent_body = against_start.group("body").rstrip(".")
        groups = list(
            re.finditer(
                r"(?P<names>.+?),\s*(?:who preferred|preferring|who supported)\s+(?P<preference>.+?)(?=(?:;\s*(?:and\s+)?)|$)",
                dissent_body,
                flags=re.IGNORECASE,
            )
        )
        if not groups:
            groups = [None]
        for group in groups:
            names = _names(group.group("names")) if group else _names(dissent_body)
            preference = group.group("preference") if group else ""
            direction = _dissent_direction(preference) if preference else "other_public_dissent"
            for name in names:
                votes.append(
                    {
                        "person_id": _person_id(name),
                        "name": name,
                        "vote": "against",
                        "dissent_direction": direction,
                        "evidence": "official_statement",
                    }
                )
    tally = re.search(r"approved the following statement for release by a\s*(?P<for>\d+)\s*[–-]\s*(?P<against>\d+)\s*vote", text, re.IGNORECASE)
    if not votes and not tally:
        raise FedOfficialSourceError(f"FOMC voting sentence not found for {meeting_date}")
    return {
        "meeting_date": meeting_date,
        "source_url": source_url,
        "eligible_voters": [vote["person_id"] for vote in votes],
        "votes": votes,
        "public_vote_tally": {
            "for": int(tally.group("for")) if tally else None,
            "against": int(tally.group("against")) if tally else sum(vote["vote"] == "against" for vote in votes),
        },
        "decision_text": decision.group("decision") if decision else None,
        "evidence_status": "official_statement_parsed",
    }


def parse_beige_book_index(html_text: str) -> list[dict[str, Any]]:
    """Extract issued (not merely scheduled) Beige Book HTML links."""
    month_map = {name: index for index, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}
    out = []
    pattern = re.compile(
        r"<td>\s*(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}):.*?href=\"(?P<url>[^\"]*beigebook(?P<period>20\d{4})-summary\.htm)\"",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html_text):
        month = month_map.get(match.group("month").title())
        period = match.group("period")
        if not month:
            continue
        day = int(match.group("day"))
        out.append(
            {
                "release_date": f"{period[:4]}-{month:02d}-{day:02d}",
                "source_url": _absolute(match.group("url")),
            }
        )
    unique = {row["release_date"]: row for row in out}
    return [unique[key] for key in sorted(unique)]


def parse_beige_book_summary(html_text: str, *, source_url: str) -> dict[str, Any]:
    """Keep labelled national sections and all 12 official district links."""
    sections = []
    for match in re.finditer(r"<h4[^>]*>(?P<label>[^<]+)</h4>\s*<p>(?P<text>.*?)</p>", html_text, re.IGNORECASE | re.DOTALL):
        label = _clean(match.group("label"))
        if label not in {"Overall Economic Activity", "Labor Markets", "Prices"}:
            continue
        sections.append({"section": label, "text": _clean(match.group("text"))})
    districts = []
    for path, name in re.findall(r'href="([^\"]*beigebook20\d{4}-[^\"]+\.htm)"[^>]*>(Federal Reserve Bank of [^<]+)</a>', html_text, re.IGNORECASE):
        districts.append({"name": _clean(name), "source_url": _absolute(path)})
    if len(sections) < 3 or len(districts) < 12:
        raise FedOfficialSourceError("Beige Book national sections or district links were incomplete")
    return {"source_url": source_url, "national_sections": sections, "districts": districts}


def _release_row(
    *,
    source_id: str,
    release_id: str,
    published_at: str,
    reference_period: str,
    source_url: str,
    retrieved_at: str,
    document_type: str,
    artifact_sha256: str | None = None,
    extracted_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "source_id": source_id,
        "release_id": release_id,
        "published_at": published_at,
        "reference_period": reference_period,
        "vintage": "first",
        "source_url": source_url,
        "quality": "parsed",
        "retrieved_at": retrieved_at,
        "document_type": document_type,
    }
    if artifact_sha256:
        row["artifact_sha256"] = artifact_sha256
    if extracted_evidence:
        row["extracted_evidence"] = extracted_evidence
    return row


def build_fed_official_input(
    *,
    years: Iterable[int],
    fetcher: Callable[[str], str] = fetch_text,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Collect Fed facts for the existing point-in-time quality snapshot."""
    retrieved_at = retrieved_at or _retrieved_now()
    calendar_html = fetcher(FOMC_CALENDAR_URL)
    members_html = fetcher(FOMC_MEMBERS_URL)
    beige_index_html = fetcher(BEIGE_BOOK_URL)
    meetings_index = parse_fomc_calendar(calendar_html, years=years)
    roster = parse_fomc_members(members_html)
    meetings = []
    documents = []
    errors = []
    for event in meetings_index:
        meeting_date = event["meeting_date"]
        published_at = _published_at(meeting_date)
        try:
            statement_html = fetcher(event["statement_url"])
            meeting = parse_fomc_statement(statement_html, meeting_date=meeting_date, source_url=event["statement_url"])
            # Some current statements identify dissenters and only publish an
            # aggregate vote tally. Complete the "for" roster only if the
            # official current-year roster reconciles exactly to that tally.
            tally = meeting.get("public_vote_tally") or {}
            roster_members = roster.get("members") or []
            named_against = [vote for vote in meeting["votes"] if vote["vote"] == "against"]
            if (
                not any(vote["vote"] == "for" for vote in meeting["votes"])
                and int(meeting_date[:4]) == roster.get("roster_year")
                and tally.get("for") is not None
                and tally.get("against") == len(named_against)
                and tally["for"] + tally["against"] == len(roster_members)
            ):
                dissent_ids = {vote["person_id"] for vote in named_against}
                meeting["votes"] = [
                    {
                        "person_id": member["person_id"],
                        "name": member["name"],
                        "vote": "for",
                        "evidence": "official_statement_tally_plus_current_official_roster",
                    }
                    for member in roster_members
                    if member["person_id"] not in dissent_ids
                ] + named_against
                meeting["eligible_voters"] = [vote["person_id"] for vote in meeting["votes"]]
            meetings.append(meeting)
            documents.append(
                _release_row(
                    source_id="fed_fomc_statement",
                    release_id=f"fomc-statement-{meeting_date}",
                    published_at=published_at,
                    reference_period=meeting_date,
                    source_url=event["statement_url"],
                    retrieved_at=retrieved_at,
                    document_type="fomc_statement",
                    artifact_sha256=_hash_text(statement_html),
                    extracted_evidence={
                        "decision_text": meeting.get("decision_text"),
                        "vote_count": len(meeting["votes"]),
                        "dissent_count": sum(vote["vote"] == "against" for vote in meeting["votes"]),
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"fomc:{meeting_date}:{exc}")
            continue
        if event.get("minutes_url"):
            documents.append(
                _release_row(
                    source_id="fed_fomc_minutes",
                    release_id=f"fomc-minutes-{meeting_date}",
                    published_at=published_at,
                    reference_period=meeting_date,
                    source_url=event["minutes_url"],
                    retrieved_at=retrieved_at,
                    document_type="fomc_minutes",
                )
            )
        if event.get("sep_url"):
            documents.append(
                _release_row(
                    source_id="fed_sep",
                    release_id=f"fomc-sep-{meeting_date}",
                    published_at=published_at,
                    reference_period=meeting_date,
                    source_url=event["sep_url"],
                    retrieved_at=retrieved_at,
                    document_type="sep",
                )
            )
    beige_releases = parse_beige_book_index(beige_index_html)
    if beige_releases:
        latest = beige_releases[-1]
        try:
            latest_html = fetcher(latest["source_url"])
            latest_evidence = parse_beige_book_summary(latest_html, source_url=latest["source_url"])
        except Exception as exc:  # noqa: BLE001
            latest_evidence = None
            errors.append(f"beige:{latest['release_date']}:{exc}")
        for release in beige_releases:
            evidence = latest_evidence if release == latest else None
            documents.append(
                _release_row(
                    source_id="fed_beige_book",
                    release_id=f"beige-book-{release['release_date']}",
                    published_at=_published_at(release["release_date"]),
                    reference_period=release["release_date"],
                    source_url=release["source_url"],
                    retrieved_at=retrieved_at,
                    document_type="beige_book",
                    artifact_sha256=_hash_text(latest_html) if evidence else None,
                    extracted_evidence=evidence,
                )
            )
    return {
        "releases": documents,
        "official_documents": documents,
        "fomc_meetings": sorted(meetings, key=lambda row: row["meeting_date"]),
        "fomc_current_roster": roster,
        "collector": {
            "source_urls": [FOMC_CALENDAR_URL, FOMC_MEMBERS_URL, BEIGE_BOOK_URL],
            "years": sorted({int(year) for year in years}),
            "errors": errors,
            "policy": "official_facts_only_no_preference_or_sentiment_score",
        },
    }
