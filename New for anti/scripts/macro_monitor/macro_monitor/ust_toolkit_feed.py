"""Treasury's debt-management 'toolkit' as a feed: official releases that move Treasury supply or speak to it.

Treasury has no press-release RSS on home.treasury.gov. Three keyless sources together:
  * GovDelivery's official 'All Treasury Press Releases' RSS (USTREAS_49, newest 25) -- the e-mail feed;
    it skips some debt-management releases (the 2026-11-04 refunding statement was not in it);
  * the press-release list page on home.treasury.gov (newest 10, server-rendered);
  * the quarterly refunding documents page (policy statement), read in ust_auctions.find_refunding_docs.
Run daily, the items accumulate in config/ust_toolkit_feed_v1.json, so neither window has to be long.

Each item is classified by its title; a speech, testimony, statement or readout is kept only when its text
talks about debt management (two or more of the terms in BODY_TERMS) -- that is where 'jawboning' lives.
"""

from __future__ import annotations

import html as _html
import re
import subprocess
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import urljoin

GOVDELIVERY = "https://public.govdelivery.com/topics/USTREAS_49/feed.rss"
PRESS_LIST = "https://home.treasury.gov/news/press-releases"

KINDS = [  # (kind, label, title pattern) -- first match wins
    ("buyback", "바이백", re.compile(r"buyback", re.I)),
    ("refunding", "분기 발행계획", re.compile(r"refunding|borrowing estimates|borrowing advisory|\bTBAC\b|financing estimates", re.I)),
    ("issuance", "발행·입찰", re.compile(r"auction|treasury bills?\b|cash management bill|\bCMB\b|issuance|marketable", re.I)),
    ("speech", "발언·성명", re.compile(r"remarks|testimony|testifies|statement|interview|readout|op-ed|speech", re.I)),
]
KIND_KO = {k: ko for k, ko, _ in KINDS} | {"policy": "정책"}
BODY_TERMS = re.compile(r"buyback|refunding|treasury bills|t-bills|\bbills\b|coupon|term premium|10-year|long end|"
                        r"duration|issuance|debt management|auction sizes|stablecoin|supplementary leverage|\bSLR\b|"
                        r"treasury general account|\bTGA\b|treasury market liquidity|yields?", re.I)


def _curl(url: str, timeout: int = 40) -> str:
    proc = subprocess.run(["curl", "-sS", "-L", "-m", str(timeout), "-A", "Mozilla/5.0", url], check=False, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"{url}: curl rc={proc.returncode}")
    return proc.stdout.decode("utf-8", errors="replace")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", " ", s or ""))).strip()


def parse_govdelivery(xml: str) -> list[dict[str, Any]]:
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        g = lambda k: (re.search(rf"<{k}[^>]*>(.*?)</{k}>", it, re.S) or [None, ""])[1]  # noqa: E731
        try:
            date = parsedate_to_datetime(g("pubDate").strip()).date().isoformat()
        except (TypeError, ValueError):
            continue
        own = re.search(r"https://home\.treasury\.gov/news/press-releases/[a-z]{2}\d+", it)
        out.append({"date": date, "title": _clean(g("title")), "url": own.group(0) if own else g("link").strip(),
                    "text": _clean(g("description"))[:6000], "source": "govdelivery"})
    return out


def parse_press_list(page: str) -> list[dict[str, Any]]:
    out = []
    for d, href, title in re.findall(r'<time[^>]*datetime="?([0-9T:\-Z]+)[^>]*>.*?<a[^>]+href="?(/news/press-releases/[a-z]{2}\d+)"?[^>]*>([^<]+)</a>',
                                     page, re.S):
        out.append({"date": d[:10], "title": _clean(title), "url": urljoin(PRESS_LIST, href), "source": "treasury"})
    return out


def classify(title: str, text: str | None) -> tuple[str | None, list[str]]:
    """(kind or None, matched body terms). Releases about something else are dropped."""
    terms = sorted({m.group(0).lower() for m in BODY_TERMS.finditer(text or "")})
    for kind, _, rx in KINDS:
        if rx.search(title):
            if kind == "speech":
                return ("speech", terms) if len(terms) >= 2 else (None, terms)
            return kind, terms
    return ("policy", terms) if len(terms) >= 3 else (None, terms)


def _key(title: str) -> str:
    return re.sub(r"[\W_]+", "", title).lower()[:60]


def update(store: list[dict[str, Any]], fresh: list[dict[str, Any]], page_text: Callable[[str], str],
           today: str) -> list[dict[str, Any]]:
    """Add the new items of `fresh` to `store` (newest first). The text of a release is read only when its
    title alone does not settle it (speeches and unclassified releases), and only once."""
    seen = {_key(x["title"]) for x in store} | {x["url"] for x in store}
    added = []
    by_title: dict[str, dict] = {}
    for f in fresh:                              # one entry per release; the Treasury URL beats the GovDelivery one
        k = _key(f["title"])
        cur = by_title.get(k)
        if cur is None:
            by_title[k] = dict(f)
        elif "home.treasury.gov" in f["url"] and "home.treasury.gov" not in cur["url"]:
            cur.update(url=f["url"], source=f["source"])
    for k, f in by_title.items():
        if k in seen or f["url"] in seen:
            continue
        kind, terms = classify(f["title"], None)
        if kind in (None, "speech"):
            text = f.get("text") or ""
            if "home.treasury.gov" in f["url"]:
                try:
                    text = _clean(page_text(f["url"]))
                except Exception:  # noqa: BLE001 -- keep what the feed carried
                    pass
            kind, terms = classify(f["title"], text)
        if kind is None:
            continue
        added.append({"date": f["date"], "title": f["title"], "url": f["url"], "kind": kind, "kind_ko": KIND_KO[kind],
                      "terms": terms[:8], "source": f.get("source"), "seen_on": today})
    return sorted(added + store, key=lambda x: (x["date"], x["title"]), reverse=True)


def fetch_fresh() -> tuple[list[dict[str, Any]], list[str]]:
    items, errors = [], []
    for name, url, parse in (("govdelivery", GOVDELIVERY, parse_govdelivery), ("press list", PRESS_LIST, parse_press_list)):
        try:
            items += parse(_curl(url))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
    return items, errors


def page_text(url: str) -> str:
    raw = _curl(url)
    m = re.search(r"<main.*?</main>", raw, re.S)
    return (m.group(0) if m else raw)[:200000]
