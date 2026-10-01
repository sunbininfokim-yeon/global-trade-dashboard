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


def pdf_body_text(data: bytes, *, mark_headings: bool = False) -> str:
    """Body text only: lines set in a clearly smaller size than the document's own
    (footnotes, page furniture) are dropped so they do not land in the middle of a
    sentence. Text blocks are separated by a blank line, lines within one by a newline.

    With `mark_headings`, lines set in a bold face are emitted as "§ <heading>" (a
    heading that wraps onto a second bold line is merged; a new roman/letter marker
    starts a new heading). Headings otherwise run straight into the first sentence of
    the text below them once whitespace is collapsed.
    """
    import re
    from collections import Counter

    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar, LTTextContainer, LTTextLine

    lines: list[tuple[str, float, bool]] = []          # (text, size, bold) in reading order, "" = block break
    for page in extract_pages(io.BytesIO(data), laparams=LAParams(word_margin=0.15, char_margin=2.0, line_margin=0.4)):
        for element in page:
            if not isinstance(element, LTTextContainer):
                continue
            for line in element:
                if isinstance(line, LTTextLine):
                    chars = [c for c in line if isinstance(c, LTChar)]
                    if chars:
                        bold = sum(1 for c in chars if "bold" in c.fontname.lower()) > len(chars) / 2
                        lines.append((line.get_text().strip(), sum(c.size for c in chars) / len(chars), bold))
            lines.append(("", 0.0, False))
    dominant = Counter(round(size) for t, size, _ in lines if t).most_common(1)
    cutoff = 0.9 * dominant[0][0] if dominant else 0
    out: list[str] = []
    heading: list[str] | None = None
    for text, size, bold in lines:
        if text and size < cutoff:
            continue
        if mark_headings and text and bold:
            if heading is not None and not re.match(r"^(?:[IVX]+|[A-F])\.\s", text):
                heading.append(text)
            else:
                if heading is not None:
                    out.append("§ " + " ".join(heading))
                heading = [text]
            continue
        if heading is not None:
            out.append("§ " + " ".join(heading))
            heading = None
        out.append(text)
    if heading is not None:
        out.append("§ " + " ".join(heading))
    return "\n".join(out)


def pdf_text_by_row(data: bytes) -> str:
    """pypdf's reading order, which keeps a table's cells on their row label.
    pdfminer reads the BOJ forecast table column by column; pypdf reads it row by
    row ("Fiscal 2026 +0.6 to +0.7 [+0.6] ..."), which is the order the parser needs."""
    from pypdf import PdfReader

    return "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(data)).pages)


def collapse(text: str) -> str:
    """Single-spaced text; non-breaking spaces and stray line breaks become plain spaces."""
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
