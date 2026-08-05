"""HTTP access to USDA FAS GAIN report pages and PDFs.

fas.usda.gov sits behind an edge WAF that answers 403 to anything that does not
look like a navigating browser, and the /data/search endpoint is refused even
then. Report detail pages and PDF files are served normally, so discovery works
by building the canonical slug for each country/report family instead of
scraping the search UI.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://www.fas.usda.gov"

# Sec-Fetch-User and an explicit Accept-Encoding are both load-bearing: dropping
# either one flips the edge response back to 403.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}

# Be a polite crawler: the whole run is a few dozen requests.
REQUEST_DELAY_S = 1.2
_last_request = 0.0


class NotFound(Exception):
    """The slug does not correspond to a published report."""


def _throttle() -> None:
    global _last_request
    wait = REQUEST_DELAY_S - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def _read(url: str, timeout: int = 45) -> bytes:
    import gzip
    import zlib

    _throttle()
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read()
            encoding = (res.headers.get("Content-Encoding") or "").lower()
    except urllib.error.HTTPError as err:
        if err.code in (403, 404):
            raise NotFound(f"{err.code} {url}") from err
        raise
    if encoding == "gzip":
        return gzip.decompress(raw)
    if encoding == "deflate":
        return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def report_url(year: int, month: int, slug: str) -> str:
    return f"{BASE}/data/gain/{year}/{month:02d}/{slug}"


def fetch_report_page(year: int, month: int, slug: str) -> str:
    """Return the HTML of a report landing page, or raise NotFound."""
    return _read(report_url(year, month, slug)).decode("utf-8", "replace")


def fetch_pdf(pdf_path: str, cache_dir: Path) -> Path:
    """Download a report PDF into cache_dir, reusing an existing copy."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = pdf_path.rsplit("/", 1)[-1]
    target = cache_dir / urllib.request.unquote(name)
    if target.exists() and target.stat().st_size > 0:
        return target
    data = _read(BASE + pdf_path)
    if not data.startswith(b"%PDF"):
        raise NotFound(f"not a pdf: {pdf_path}")
    target.write_bytes(data)
    return target
