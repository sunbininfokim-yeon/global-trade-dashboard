"""Refresh the House floor Atom/XML and the Senate Congressional Record RSS."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parents[1] / "public/data/usa_congress_agenda_v1.json"
MILESTONES = ROOT / "config/usa_congress_milestones.json"
HOUSE_FEED = "https://docs.house.gov/BillsThisWeek-RSS.xml"
HOUSE_FLOOR = "https://docs.house.gov/floor/"
SENATE_RECORDS = "https://www.govinfo.gov/rss/crec.xml"
SENATE_FLOOR = "https://www.senate.gov/legislative/floor_activity_pail.htm"
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def fetch_xml(url: str) -> ET.Element:
    with urlopen(Request(url, headers={"User-Agent": "ChokePointMonitor/1.0 (public Congress agenda)"}), timeout=20) as response:
        raw = response.read(64_000_001)
    if len(raw) > 64_000_000:
        raise ValueError("Feed exceeds size limit")
    return ET.fromstring(raw)


def house_week(feed: ET.Element, read=fetch_xml) -> dict:
    weeks = set()
    for link in feed.findall("{*}entry/{*}link"):
        parsed = urlsplit(link.get("href", ""))
        if parsed.hostname != "docs.house.gov" or parsed.path.lower() != "/floor/default.aspx":
            continue
        week, *_ = parse_qs(parsed.query).get("date", [""])
        if DATE.fullmatch(week):
            weeks.add(date.fromisoformat(week))
    if not weeks:
        raise ValueError("No House legislative weeks in Atom feed")
    week = max(weeks).isoformat()
    compact = week.replace("-", "")
    download = f"{HOUSE_FLOOR}Download.aspx?" + urlencode({"file": f"/billsthisweek/{compact}/{compact}.xml"})
    xml = read(download)
    if xml.tag != "floorschedule" or xml.get("week-date") != week:
        raise ValueError("House XML does not match the advertised week")
    page = f"{HOUSE_FLOOR}Default.aspx?date={week}"
    entries = []
    for category in xml.findall("category"):
        for row in category.findall("floor-items/floor-item"):
            if row.get("remove-date"):
                continue
            context = row.find("floor-text")
            title = " ".join("".join(context.itertext()).split()) if context is not None else ""
            if not title:
                continue
            reference = row.findtext("legis-num", "").strip()
            entries.append({
                "title": f"{reference} · {title}" if reference else title,
                "date_note_ko": "심의 가능 안건",
                "url": page,
            })
    if not entries:
        raise ValueError("House XML contained no published agenda items")
    return {"date": week, "published_at": xml.get("update-date"), "page_url": page, "entries": entries}


def senate_records(feed: ET.Element) -> dict:
    by_date = {}
    for item in feed.findall("channel/item"):
        match = re.fullmatch(r"CREC-(\d{4}-\d{2}-\d{2})", item.findtext("guid", ""))
        if not match:
            continue
        issue = date.fromisoformat(match[1]).isoformat()
        url = f"https://www.govinfo.gov/content/pkg/CREC-{issue}/pdf/CREC-{issue}-dailydigest.pdf"
        by_date[issue] = {"title_ko": "의회의사록 일일 요약", "date": issue, "date_note_ko": "공개 기록", "url": url}
    if not by_date:
        raise ValueError("No Congressional Record issues found")
    dates = sorted(by_date, reverse=True)[:5]
    return {"date": dates[0], "page_url": SENATE_FLOOR, "entries": [by_date[issue] for issue in dates]}


def refresh(previous: dict, milestones: list[dict], checked_at: str, read=fetch_xml) -> dict:
    prior = {source["id"]: source for source in previous.get("sources", [])}
    sources = []
    for key, chamber, label, url, page in (
        ("house_floor", "house", "하원 주간 본회의 안건 · Atom/XML", HOUSE_FEED, HOUSE_FLOOR),
        ("senate_record", "senate", "최근 의회의사록 · GovInfo RSS", SENATE_RECORDS, SENATE_FLOOR),
    ):
        source = {"id": key, "chamber": chamber, "label_ko": label, "url": url, "page_url": page}
        old = prior.get(key, {})
        try:
            records = house_week(read(url), read) if key == "house_floor" else senate_records(read(url))
            if old.get("date") and records["date"] < old["date"]:
                raise ValueError("Feed is older than the last published source date")
            sources.append({**source, **records, "status": "ok", "checked_at": checked_at})
        except (OSError, URLError, ET.ParseError, ValueError) as error:
            print(f"{key}: {error}")
            sources.append({**source, **old, "status": "stale" if old.get("entries") else "unavailable"})
    return {"schema": "usa_congress_agenda_v1", "sources": sources, "milestones": milestones}


def source_content(data: dict) -> list[dict]:
    return [{key: value for key, value in row.items() if key != "checked_at"}
            for row in data.get("sources", [])]


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, default=OUTPUT)
    args = cli.parse_args()
    previous = json.loads(args.output.read_text()) if args.output.exists() else {}
    milestones = json.loads(MILESTONES.read_text())
    output = refresh(previous, milestones, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    # A periodic job need only publish content changes or source health changes.
    if previous.get("milestones") == milestones and source_content(previous) == source_content(output):
        return
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
