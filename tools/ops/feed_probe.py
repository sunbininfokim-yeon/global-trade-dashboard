#!/usr/bin/env python3
"""Check candidate report feeds from a GitHub Actions runner.

The Claude Code sessions that edit scripts/commodity_reports/config/sources.json
cannot reach most publishers (their egress proxy refuses the CONNECT), so a
feed URL written there is a guess until a runner fetches it. This script is
that fetch, for a whole list at once, before anything is enabled.

For each target in feed_probe_targets.json it reports the HTTP status, whether
the body is RSS/Atom/RDF, how many items it carries and how recent the newest
one is. An HTML page is searched for the feeds it advertises
(<link rel="alternate" type="application/rss+xml">, plus hrefs that look like
feed paths), and those are fetched too, so a publisher's real feed URL is
found rather than guessed. `link_re` counts matching hrefs on an HTML page,
for publishers that only have a list page (html_list sources).

`variants` refetches a blocked URL with other client fingerprints -- the
pipeline's own urllib request, browser-like headers, and curl_cffi
impersonating Chrome's TLS handshake when it is installed -- to tell a
User-Agent rule from a TLS fingerprint rule (what Akamai Bot Manager uses).

Read-only: GETs only, nothing written anywhere but stdout and, on Actions,
the job summary.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

HERE = Path(__file__).resolve().parent
TARGETS = HERE / "feed_probe_targets.json"
PIPELINE_UA = "GlobalTradeDashboard-CommodityReports/1.0 (+research; official sources only)"
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
PIPELINE_HEADERS = {
    "User-Agent": PIPELINE_UA,
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html, */*",
    "Accept-Language": "en,pt;q=0.8,es;q=0.8,fr;q=0.6",
}
TIMEOUT = 20.0
MAX_DISCOVERED = 4

_ALT_RE = re.compile(r"<link\b[^>]*>", re.I)
_HREF_RE = re.compile(r"href=[\"']([^\"'#]+)[\"']", re.I)
_TYPE_RE = re.compile(r"type=[\"'](application/(?:rss|atom|rdf)\+xml|text/xml|application/xml)[\"']", re.I)
_FEEDISH_RE = re.compile(r"(?:/rss(?:[./?_-]|$)|/feed/?$|/feeds?/|\.rss$|\.atom$|rss\.xml|atom\.xml|format=feed)", re.I)


def _get(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context()) as resp:
            body = resp.read(3_000_000)
            return {"status": resp.status, "ctype": resp.headers.get("Content-Type", ""),
                    "final": resp.geturl(), "body": body, "server": resp.headers.get("Server", "")}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "ctype": exc.headers.get("Content-Type", "") if exc.headers else "",
                "final": url, "body": exc.read(20_000) if hasattr(exc, "read") else b"",
                "server": exc.headers.get("Server", "") if exc.headers else ""}
    except Exception as exc:  # noqa: BLE001 -- a probe reports, never raises
        return {"status": None, "error": f"{type(exc).__name__}: {exc}"[:160], "body": b"", "ctype": "", "final": url}


def _get_impersonated(url: str) -> Dict[str, Any]:
    try:
        from curl_cffi import requests as creq  # type: ignore
    except ImportError:
        return {"status": None, "error": "curl_cffi not installed", "body": b"", "ctype": "", "final": url}
    try:
        r = creq.get(url, impersonate="chrome", timeout=TIMEOUT, allow_redirects=True)
        return {"status": r.status_code, "ctype": r.headers.get("Content-Type", ""), "final": str(r.url),
                "body": r.content[:3_000_000], "server": r.headers.get("Server", "")}
    except Exception as exc:  # noqa: BLE001
        return {"status": None, "error": f"{type(exc).__name__}: {exc}"[:160], "body": b"", "ctype": "", "final": url}


def _text(body: bytes) -> str:
    if body.startswith(b"\xef\xbb\xbf"):
        body = body[3:]
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _date(raw: str) -> Optional[datetime]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError):
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def feed_summary(text: str) -> Optional[Dict[str, Any]]:
    head = text[:4000].lower()
    if "<rss" not in head and "<feed" not in head and "<rdf" not in head:
        return None
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        return {"items": 0, "parse_error": str(exc)[:80]}
    entries = [el for el in root.iter() if _local(el.tag) in {"item", "entry"}]
    titles: List[str] = []
    newest: Optional[datetime] = None
    for el in entries:
        for ch in el:
            name = _local(ch.tag)
            if name == "title" and len(titles) < 3:
                titles.append(re.sub(r"\s+", " ", "".join(ch.itertext())).strip()[:90])
            elif name in {"pubDate", "published", "updated", "date"}:
                d = _date("".join(ch.itertext()))
                if d and (newest is None or d > newest):
                    newest = d
    return {"items": len(entries), "newest": newest.date().isoformat() if newest else None, "titles": titles}


def discover(url: str, html: str) -> List[str]:
    found: List[str] = []
    for tag in _ALT_RE.findall(html):
        if "alternate" in tag.lower() and _TYPE_RE.search(tag):
            m = _HREF_RE.search(tag)
            if m:
                found.append(urljoin(url, unescape(m.group(1))))
    host = urlparse(url).netloc
    for href in _HREF_RE.findall(html):
        full = urljoin(url, unescape(href))
        if urlparse(full).netloc == host and _FEEDISH_RE.search(full) and not full.lower().endswith((".pdf", ".xlsx")):
            found.append(full)
    out: List[str] = []
    for f in found:
        if f not in out and f.rstrip("/") != url.rstrip("/"):
            out.append(f)
    return out[:MAX_DISCOVERED]


def describe(res: Dict[str, Any], link_re: Optional[str] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": res.get("status")}
    if res.get("error"):
        out["error"] = res["error"]
    if res.get("final") and res.get("final") != res.get("url"):
        out["final"] = res["final"]
    body = res.get("body") or b""
    text = _text(body)
    fs = feed_summary(text) if body else None
    if fs is not None:
        out["feed"] = fs
    elif body:
        out["html_bytes"] = len(body)
        m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        if m:
            out["page_title"] = re.sub(r"\s+", " ", unescape(m.group(1))).strip()[:70]
        if res.get("status") and res["status"] >= 400:
            out["server"] = res.get("server", "")
            low = text.lower()
            out["block_hint"] = next((k for k in ("akamai", "cloudflare", "access denied", "captcha", "incapsula", "forbidden") if k in low), "")
        if link_re:
            links = []
            for href in _HREF_RE.findall(text):
                full = urljoin(res.get("final") or "", unescape(href))
                if re.search(link_re, full) and full not in links:
                    links.append(full)
            out["links"] = len(links)
            out["link_samples"] = links[:4]
    return out


def probe(target: Dict[str, Any]) -> Dict[str, Any]:
    url = target["url"]
    raw: Dict[str, Dict[str, Any]] = {"pipeline": _get(url, PIPELINE_HEADERS)}
    blocked = not raw["pipeline"].get("status") or raw["pipeline"]["status"] >= 400
    if target.get("variants") or blocked:
        raw["browser"] = _get(url, BROWSER_HEADERS)
        raw["impersonate"] = _get_impersonated(url)
    report: Dict[str, Any] = {"id": target["id"], "group": target.get("group", ""), "url": url}
    for key, res in raw.items():
        res["url"] = url
        report[key] = describe(res, target.get("link_re"))
    # Feed discovery from the first variant that got a readable page.
    for key, res in raw.items():
        d = report[key]
        if d.get("html_bytes") and (d.get("status") or 0) < 400:
            report["discovered"] = []
            for f in discover(res.get("final") or url, _text(res["body"])):
                fr = _get(f, PIPELINE_HEADERS)
                fr["url"] = f
                fd = describe(fr)
                fd["url"] = f
                report["discovered"].append(fd)
            break
    return report


def line(r: Dict[str, Any]) -> str:
    def fmt(d: Dict[str, Any]) -> str:
        if not d:
            return "-"
        s = str(d.get("status"))
        if d.get("error"):
            s += f" {d['error']}"
        if "feed" in d:
            f = d["feed"]
            s += f" FEED items={f.get('items')} newest={f.get('newest')} {f.get('titles', [])[:2]}"
            if f.get("parse_error"):
                s += f" parse_error={f['parse_error']}"
        elif "html_bytes" in d:
            s += f" html={d['html_bytes']} title={d.get('page_title', '')!r}"
            if "links" in d:
                s += f" links={d['links']} {d.get('link_samples', [])[:3]}"
            if d.get("block_hint") is not None and (d.get("status") or 0) >= 400:
                s += f" server={d.get('server', '')!r} hint={d.get('block_hint')!r}"
        if d.get("final"):
            s += f" -> {d['final']}"
        return s

    out = [f"### [{r['group']}] {r['id']}  {r['url']}", f"  pipeline: {fmt(r['pipeline'])}"]
    if "browser" in r:
        out.append(f"  browser: {fmt(r['browser'])}")
        out.append(f"  impersonate: {fmt(r['impersonate'])}")
    for d in r.get("discovered", []):
        out.append(f"  found {d['url']}: {fmt(d)}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default=str(TARGETS))
    ap.add_argument("--only", help="comma-separated groups")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    targets = json.loads(Path(args.targets).read_text(encoding="utf-8"))["targets"]
    if args.only:
        groups = set(args.only.split(","))
        targets = [t for t in targets if t.get("group") in groups]
    with ThreadPoolExecutor(max_workers=8) as pool:
        reports = list(pool.map(probe, targets))
    text = "\n".join(line(r) for r in reports)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("```\n" + text + "\n```\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
