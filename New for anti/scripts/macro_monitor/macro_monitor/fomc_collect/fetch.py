"""Fetch raw FOMC statement / Beige Book HTML from federalreserve.gov.

Kept separate from parsing (parse.py) the same way qra/fetch.py and
qra/parse.py are split -- a fetch failure and a parse failure are different
kinds of problem, and testing the parser should never require a live network
call.
"""

from __future__ import annotations

import time
import urllib.request

USER_AGENT = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"


def fetch_url(url: str, timeout: int = 20, retries: int = 2) -> str:
    # One 2026-04-29 fetch came back 200 with the site's nav shell and no
    # article body at all -- a fresh curl for the same URL a minute later
    # returned it fine, so this was transient (CDN/edge hiccup), not the
    # page genuinely lacking content. A page under ~3KB is essentially
    # certain to be shell-only; real statement/Beige Book pages run tens of
    # KB. One retry catches this without masking an actual structural
    # change to the page (which would fail again on retry and surface as a
    # parsed_ok: false or the dissent-count ValueError instead).
    last: str | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            last = resp.read().decode("utf-8", errors="replace")
        if len(last) > 3000:
            return last
        if attempt < retries:
            time.sleep(1.5)
    return last or ""


def statement_url(meeting_date: str) -> str:
    """meeting_date: 'YYYY-MM-DD' of the second (decision) day of the meeting."""
    ymd = meeting_date.replace("-", "")
    return f"https://www.federalreserve.gov/newsevents/pressreleases/monetary{ymd}a.htm"


def beige_book_url(year_month: str) -> str:
    """year_month: 'YYYY-MM' of the Beige Book release."""
    ym = year_month.replace("-", "")
    return f"https://www.federalreserve.gov/monetarypolicy/beigebook{ym}-summary.htm"
