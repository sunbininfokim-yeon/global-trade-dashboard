"""Fetching and text helpers shared by the BOJ and BOK collectors."""

from __future__ import annotations

import io
import re
import time
import urllib.error
import urllib.request

USER_AGENT = "Mozilla/5.0 (compatible; macro-monitor/1.0; research)"


def fetch_bytes(url: str, *, timeout: int = 40, retries: int = 2, min_size: int = 0) -> bytes:
    """GET with a couple of retries. `min_size` guards the CDN hiccup where a
    200 comes back as a nav shell with no body (seen on bok.or.kr and, for the
    FOMC pages, federalreserve.gov)."""
    last_error: Exception | None = None
    body = b""
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
            if len(body) >= min_size:
                return body
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    if last_error is not None and not body:
        raise RuntimeError(f"fetch failed for {url}: {last_error}")
    return body


def fetch_text(url: str, **kwargs) -> str:
    return fetch_bytes(url, **kwargs).decode("utf-8", errors="replace")


def pdf_text(data: bytes) -> str:
    """Text of the whole PDF with word spacing intact.

    pypdf splits words at random ("uncollateralize d", "0. 75") on the BOJ
    statements and drops every space in the BOK minutes; pdfminer.six with a
    word margin reads both cleanly. Both banks publish PDF-only documents, so
    this is the one place that has to be right.
    """
    from pdfminer.high_level import extract_text
    from pdfminer.layout import LAParams

    return extract_text(io.BytesIO(data), laparams=LAParams(word_margin=0.15, char_margin=2.0, line_margin=0.4))


def pdf_text_by_row(data: bytes) -> str:
    """pypdf's reading order, which keeps a table's cells on their row label.
    pdfminer reads the BOJ forecast table column by column; pypdf reads it row by
    row ("Fiscal 2026 +0.6 to +0.7 [+0.6] ..."), which is the order the parser needs."""
    from pypdf import PdfReader

    return "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(data)).pages)


def collapse(text: str) -> str:
    """Single-spaced text; non-breaking spaces and stray line breaks become plain spaces."""
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
