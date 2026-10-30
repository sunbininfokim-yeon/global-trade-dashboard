"""News-outlet items: real links, trusted outlets, one row per story.

The official reports are the point of this dashboard; news headlines ride
along beside them. What a news item carries is a headline and a link -- no
summary -- and it is only worth showing if (1) the link opens the article
itself, (2) the outlet is one we would put our name next to, and (3) it is not
the fourth outlet repeating the same story.

(1) Google News hands out its own redirect URLs. They are encrypted, so the
real address has to be asked of Google (the same call its own page makes), and
the answer is accepted only if it is on the outlet's own domain.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set
from urllib.parse import quote, urlsplit

GN_ARTICLE_RE = re.compile(r"^https?://news\.google\.com/(?:rss/)?articles/([A-Za-z0-9_-]+)")
GN_PAGE = "https://news.google.com/rss/articles/{id}?hl=en-US&gl=US&ceid=US:en"
GN_BATCH = "https://news.google.com/_/DotsSplashUi/data/batchexecute"


def is_google_news_url(url: str) -> bool:
    return bool(GN_ARTICLE_RE.match(url or ""))


def google_news_ref(url: str) -> Optional[str]:
    m = GN_ARTICLE_RE.match(url or "")
    return m.group(1) if m else None


# ---- 1. resolving Google News links ---------------------------------------

def _decode_embedded(article_id: str) -> Optional[str]:
    """Older ids are plain base64 around the address; newer ones are not."""
    try:
        raw = base64.urlsafe_b64decode(article_id + "=" * (-len(article_id) % 4))
    except Exception:  # noqa: BLE001
        return None
    if raw.startswith(b"\x08\x13\x22") and b"AU_yqL" not in raw:
        m = re.search(rb"https?://[\x21-\x7e]+", raw)
        if m:
            return m.group(0).decode("ascii", "ignore")
    return None


def resolve_google_news_url(
    url: str, *, get: Callable[[str], str], post: Callable[[str, str], str],
) -> Optional[str]:
    """The article address behind a Google News link, or None.

    `get(url) -> html` and `post(url, body) -> text` are injected so tests run
    offline and the build can add its own pacing and headers.
    """
    article_id = google_news_ref(url)
    if not article_id:
        return None
    embedded = _decode_embedded(article_id)
    if embedded:
        return embedded
    try:
        html = get(GN_PAGE.format(id=article_id))
        sig = re.search(r'data-n-a-sg="([^"]+)"', html)
        ts = re.search(r'data-n-a-ts="([^"]+)"', html)
        if not sig or not ts:
            return None
        inner = json.dumps([
            "garturlreq",
            [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
             "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
            article_id, int(ts.group(1)), sig.group(1),
        ], separators=(",", ":"))
        body = "f.req=" + quote(json.dumps([[["Fbv4je", inner, None, "generic"]]], separators=(",", ":")))
        reply = post(GN_BATCH, body)
        parts = reply.split("\n\n")
        data = json.loads(parts[1])
        target = json.loads(data[0][2])[1]
    except Exception:  # noqa: BLE001 -- an unresolved link is dropped, never guessed
        return None
    return target if isinstance(target, str) and target.startswith(("http://", "https://")) else None


# ---- 2. outlets --------------------------------------------------------------

_TWO_PART_SUFFIXES = {"co.uk", "co.za", "co.id", "co.jp", "co.kr", "co.zw", "co.tz", "co.ke", "com.au", "com.my",
                      "com.ng", "com.sg", "com.cn", "com.br", "com.na", "com.gh", "or.id", "go.id", "co.in", "org.uk"}


def registrable_domain(url_or_host: str) -> str:
    """example.co.uk for www.example.co.uk, example.com for news.example.com."""
    host = urlsplit(url_or_host if "//" in url_or_host else f"//{url_or_host}").hostname or ""
    host = host.lower().strip(".")
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if ".".join(parts[-2:]) in _TWO_PART_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_outlet(article_url: str, publisher_url: Optional[str]) -> bool:
    """The article is on the outlet's own domain (a redirect that lands
    somewhere else is not the outlet's article)."""
    if not article_url or not publisher_url:
        return False
    a, p = registrable_domain(article_url), registrable_domain(publisher_url)
    return bool(a) and a == p


def trusted_outlet(publisher_url: Optional[str], trusted_domains: Iterable[str]) -> bool:
    return bool(publisher_url) and registrable_domain(publisher_url) in {registrable_domain(d) for d in trusted_domains}


# ---- 3. one row per story -------------------------------------------------------

_STOP = set("""a an the and or of in on at to for from by with as is are was were be been it its this that these those
after over under into out up down new says say said will would could may might more most less than about amid
vs via per s us also not no""".split())
_WORD = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")


def story_tokens(title: str) -> Set[str]:
    text = (title or "").lower().replace("&", " and ")
    words = _WORD.findall(text)
    return {w for w in words if len(w) >= 3 and w not in _STOP}


def same_story(a: Set[str], b: Set[str], *, min_shared: int = 4, ratio: float = 0.75) -> bool:
    """Two headlines tell the same story when most of the shorter one's words
    are in the other. Four shared words is the floor: 'copper price record' is
    three, and 'copper rises' and 'copper falls' must stay two rows."""
    if not a or not b:
        return False
    shared = len(a & b)
    return shared >= min_shared and shared / min(len(a), len(b)) >= ratio
