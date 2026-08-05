"""HTTP helpers (stdlib)."""

from __future__ import annotations

import html as html_lib
import re
import ssl
import urllib.request
from typing import Optional
from urllib.parse import urljoin

_TAG_RE = re.compile(r"<[^>]+>", re.S)
_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.I | re.S)
_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.I | re.S)
_WS_RE = re.compile(r"\s+")


def fetch_bytes(url: str, *, user_agent: str, timeout: float = 22.0) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html, */*",
        },
        method="GET",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read()


def fetch_text(url: str, *, user_agent: str, timeout: float = 22.0) -> str:
    raw = fetch_bytes(url, user_agent=user_agent, timeout=timeout)
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    for enc in ("utf-8", "euc-kr", "cp949", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def html_to_text(doc: str) -> str:
    doc = _SCRIPT_RE.sub(" ", doc)
    doc = _STYLE_RE.sub(" ", doc)
    doc = _TAG_RE.sub(" ", doc)
    doc = html_lib.unescape(doc)
    return _WS_RE.sub(" ", doc).strip()


def absolutize(base: str, href: str) -> str:
    return urljoin(base, href)
