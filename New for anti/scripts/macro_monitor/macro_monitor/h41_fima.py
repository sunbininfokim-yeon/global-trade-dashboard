"""FIMA repo facility usage from the Fed's H.4.1 releases.

FRED carries the total of repurchase agreements (WORAL) but not the foreign-official
line the FIMA facility shows up in, and the Fed's Data Download Program does not list it
either. Table 1 of every weekly H.4.1 release does: "Repurchase agreements -> Foreign
official", with the Wednesday level in the last column ($ millions). Each release lives at
/releases/h41/YYYYMMDD/, so the history is built one release at a time and kept in a
small cache file (config/fima_repo_v1.json) that a weekly run only extends.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup

BASE = "https://www.federalreserve.gov/releases/h41"
USER_AGENT = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"
_HEADER = re.compile(r"Wednesday\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})")


def release_url(day: str) -> str:
    return f"{BASE}/{day.replace('-', '')}/"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def parse_release(html: str) -> dict[str, Any]:
    """{'wednesday': 'YYYY-MM-DD', 'foreign_official_mn': float} from one H.4.1 release page."""
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        text = _clean(table.get_text(" "))
        m = _HEADER.search(text)
        if not m or "Repurchase agreements" not in text or "Foreign official" not in text:
            continue
        wednesday = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").date()
        seen_repo = False
        for row in table.find_all("tr"):
            cells = [_clean(c.get_text(" ")) for c in row.find_all(["th", "td"])]
            if not cells:
                continue
            if cells[0].startswith("Repurchase agreements"):
                seen_repo = True
            elif seen_repo and cells[0] == "Foreign official":
                raw = cells[-1].replace(",", "").replace(" ", "")
                try:
                    return {"wednesday": wednesday.isoformat(), "foreign_official_mn": float(raw)}
                except ValueError as exc:
                    raise ValueError(f"unreadable Wednesday level {cells[-1]!r} in the FIMA row") from exc
        raise ValueError("no 'Foreign official' row under 'Repurchase agreements'")
    raise ValueError("no H.4.1 Table 1 with a Wednesday column found")


def fetch_release(day: str, *, timeout: int = 40, tries: int = 3) -> str | None:
    """The release published on `day` (a Thursday, usually), or None on 404 -- the Fed moves the
    release around holidays, so callers try the neighbouring days. A read that times out is
    retried; after the last try the error is raised (it is not a 404 and must not read as one)."""
    req = urllib.request.Request(release_url(day), headers={"User-Agent": USER_AGENT})
    last: Exception | None = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            last = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"H.4.1 {day}: {last}")


def collect_one(day: str) -> tuple[dict[str, Any] | None, str | None]:
    """(row, problem) for one expected release day, trying the neighbouring days if it was moved."""
    d = date.fromisoformat(day)
    for shift in (0, 1, -1, 2, -2):
        candidate = (d + timedelta(days=shift)).isoformat()
        try:
            html = fetch_release(candidate)
        except RuntimeError as exc:
            return None, str(exc)
        if html:
            try:
                return {**parse_release(html), "release": candidate}, None
            except ValueError as exc:
                return None, f"{candidate}: {exc}"
    return None, f"{day}: no release found"


def collect(days: list[str], *, workers: int = 3, chunk: int = 30, on_chunk=None) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch and parse each release day, a few at a time. `on_chunk(rows_so_far)` runs after every
    `chunk` days so a long backfill that dies part-way keeps what it had."""
    from concurrent.futures import ThreadPoolExecutor

    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    for i in range(0, len(days), chunk):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for row, problem in pool.map(collect_one, days[i:i + chunk]):
                if row:
                    rows.append(row)
                if problem:
                    problems.append(problem)
        if on_chunk:
            on_chunk(rows)
    return rows, problems


def thursdays(start: date, end: date) -> list[str]:
    d = start + timedelta(days=(3 - start.weekday()) % 7)
    out = []
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=7)
    return out
