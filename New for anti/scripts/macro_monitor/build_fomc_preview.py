#!/usr/bin/env python3
"""What is scheduled around the next FOMC meeting -> config/fomc_preview_v1.json, merged by
build_us_macro_quality_from_collect.py into policy_committee.schedule.preview.

  next meeting   dates and whether it carries a Summary of Economic Projections -- read off the Fed's
                 calendar page, where SEP meetings are marked with an asterisk ("September 15-16*")
  blackout       the Fed's communications blackout: from the second Saturday before the meeting through
                 the day after it (Fed policy, not an estimate)
  releases       BEA's release schedule (www.bea.gov/news/schedule) from today through a week after the
                 decision, each flagged before/after the decision

Not here, and why: BLS (CPI, jobs) and FRED's release calendar refuse automated requests from here, so
those dates are left out rather than guessed; the panel says so.

    python3 build_fomc_preview.py

Idempotent; on a fetch failure the previous file is kept and the run exits 1.
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "config" / "fomc_preview_v1.json"
FED_CALENDAR = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BEA_SCHEDULE = "https://www.bea.gov/news/schedule"
MONTHS = {m: i + 1 for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July",
                                           "August", "September", "October", "November", "December"))}


def _text(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def parse_fed_calendar(raw: str, year: int) -> list[dict]:
    """Meetings of `year`: [{start, end, sep}]. 'October 27-28', 'April 30-May 1', '*' marks an SEP."""
    t = _text(raw)
    i = t.find(f"{year} FOMC Meetings")
    if i < 0:
        raise ValueError(f"Fed calendar: no {year} section")
    j = t.find(f"{year - 1} FOMC Meetings", i + 1)
    block = t[i:j if j > 0 else None]
    out = []
    pat = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})-(?:(" + "|".join(MONTHS) + r")\s+)?(\d{1,2})(\*?)")
    for m in pat.finditer(block):
        m1, d1, m2, d2, star = m.group(1), int(m.group(2)), m.group(3) or m.group(1), int(m.group(4)), m.group(5)
        out.append({"start": date(year, MONTHS[m1], d1).isoformat(), "end": date(year, MONTHS[m2], d2).isoformat(),
                    "sep": star == "*"})
    if not out:
        raise ValueError(f"Fed calendar: no {year} meetings parsed")
    return out


def blackout(start: date, end: date) -> tuple[str, str]:
    """Second Saturday before the meeting's first day, through the day after its last day."""
    days_back = (start.weekday() - 5) % 7 or 7          # to the Saturday before
    first_saturday = start - timedelta(days=days_back)
    return (first_saturday - timedelta(days=7)).isoformat(), (end + timedelta(days=1)).isoformat()


def parse_bea_schedule(raw: str) -> list[dict]:
    """[{date, time, title}] from BEA's release schedule table (the year is in its header row)."""
    m = re.search(r"Year\s+(\d{4})", raw)
    if not m:
        raise ValueError("BEA schedule: no year header")
    year = int(m.group(1))
    out, last_month = [], 0
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", raw, re.S):
        d = re.search(r'class="release-date">\s*([A-Za-z]+)\s+(\d{1,2})', row)
        title = re.search(r'class="release-title[^"]*"[^>]*>(.*?)</td>', row, re.S)
        if not (d and title) or d.group(1) not in MONTHS:
            continue
        month = MONTHS[d.group(1)]
        if month < last_month:                          # the table runs into the next year
            year += 1
        last_month = month
        tm = re.search(r'<small[^>]*>\s*([^<]+?)\s*</small>', row)
        out.append({"date": date(year, month, int(d.group(2))).isoformat(), "time": tm.group(1).strip() if tm else None,
                    "title": _text(title.group(1)).strip(), "source": "BEA"})
    return out


def build(fed_raw: str, bea_raw: str, today: date) -> dict:
    meetings = parse_fed_calendar(fed_raw, today.year)
    upcoming = [m for m in meetings if m["end"] >= today.isoformat()]
    if not upcoming and today.month == 12:
        upcoming = parse_fed_calendar(fed_raw, today.year + 1)
    if not upcoming:
        raise ValueError("no upcoming FOMC meeting on the Fed calendar")
    nxt = upcoming[0]
    b0, b1 = blackout(date.fromisoformat(nxt["start"]), date.fromisoformat(nxt["end"]))
    horizon = (date.fromisoformat(nxt["end"]) + timedelta(days=7)).isoformat()
    releases = [dict(r, relative="before" if r["date"] < nxt["end"] else ("same_day" if r["date"] == nxt["end"] else "after"))
                for r in parse_bea_schedule(bea_raw) if today.isoformat() <= r["date"] <= horizon]
    return {
        "schema_version": "fomc-preview-v1",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "next_meeting": {**nxt, "statement_time_et": "2:00 p.m.", "source_url": FED_CALENDAR},
        "blackout": {"start": b0, "end": b1,
                     "note_ko": "연준 커뮤니케이션 규칙: 회의 전 둘째 토요일부터 회의 다음 날까지 위원들은 통화정책 공개 발언을 하지 않습니다."},
        "releases": releases,
        "releases_note_ko": "BEA 공식 일정입니다. BLS(CPI·고용)와 FRED 일정 페이지는 자동 수집이 막혀 있어 넣지 않았습니다.",
        "source_urls": [FED_CALENDAR, BEA_SCHEDULE],
    }


def main() -> int:
    from macro_monitor.fomc_collect.fetch import fetch_url
    try:
        doc = build(fetch_url(FED_CALENDAR), fetch_url(BEA_SCHEDULE), date.today())
    except Exception as exc:  # noqa: BLE001 -- keep the previous preview rather than write a broken one
        print(f"FOMC preview: {exc}", file=sys.stderr)
        return 1
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n = doc["next_meeting"]
    print(f"next FOMC {n['start']}~{n['end']} (SEP {'yes' if n['sep'] else 'no'}), blackout {doc['blackout']['start']}~"
          f"{doc['blackout']['end']}, {len(doc['releases'])} BEA releases through a week after")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
