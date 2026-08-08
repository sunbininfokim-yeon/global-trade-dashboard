"""Discover and download Treasury QRA press releases from archive indexes."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

UA = "Mozilla/5.0 (compatible; macro-monitor-qra/1.0; research)"
BASE = "https://home.treasury.gov"

ARCHIVE_URLS = {
    "financing_estimates": (
        f"{BASE}/policy-issues/financing-the-government/quarterly-refunding/"
        "quarterly-refunding-archives/quarterly-refunding-financing-estimates-by-calendar-year"
    ),
    "official_remarks": (
        f"{BASE}/policy-issues/financing-the-government/quarterly-refunding/"
        "quarterly-refunding-archives/official-remarks-on-quarterly-refunding-by-calendar-year"
    ),
    "most_recent": (
        f"{BASE}/policy-issues/financing-the-government/quarterly-refunding/"
        "most-recent-quarterly-refunding-documents"
    ),
}

_QTR_MAP = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4}


@dataclass(frozen=True)
class ArchiveDoc:
    kind: str  # financing_estimates | official_remarks | other
    year: int
    quarter: Optional[int]
    url: str
    label: str


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def absolutize(href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE + href
    return f"{BASE}/{href}"


def parse_year_quarter_table(html: str, kind: str) -> List[ArchiveDoc]:
    """Parse Treasury archive tables: year header row + quarter link row."""
    docs: List[ArchiveDoc] = []
    # Each year block: id="YYYY" ... then links with headers="YYYY"
    for ym in re.finditer(
        r'id="(20\d{2})"[\s\S]*?</tr>\s*<tr>([\s\S]*?)</tr>',
        html,
    ):
        year = int(ym.group(1))
        row = ym.group(2)
        # Prefer headers=YEAR + optional <a href=... attrs...>Quarter
        for m in re.finditer(
            r'headers="%d"[^>]*>\s*(?:<a href="([^"]+)"[^>]*>)?\s*'
            r"((?:1st|2nd|3rd|4th)\s*Quarter[^<]*)"
            % year,
            row,
            re.I,
        ):
            href, label = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
            # strip zero-width / odd unicode in Treasury labels
            label = label.replace("\u200b", "").strip()
            qmatch = re.match(r"(1st|2nd|3rd|4th)", label, re.I)
            quarter = _QTR_MAP.get(qmatch.group(1).lower()) if qmatch else None
            if not href:
                # e.g. 2026 4th Quarter not yet published — plain text cell
                continue
            docs.append(
                ArchiveDoc(
                    kind=kind,
                    year=year,
                    quarter=quarter,
                    url=absolutize(href),
                    label=f"{year} Q{quarter} {kind}" if quarter else f"{year} {label}",
                )
            )
    return docs


def discover_archives(*, from_year: int = 2020, to_year: int = 2099) -> List[ArchiveDoc]:
    out: List[ArchiveDoc] = []
    for kind, url in (
        ("financing_estimates", ARCHIVE_URLS["financing_estimates"]),
        ("official_remarks", ARCHIVE_URLS["official_remarks"]),
    ):
        html = _get(url).decode("utf-8", errors="replace")
        for doc in parse_year_quarter_table(html, kind):
            if from_year <= doc.year <= to_year:
                out.append(doc)
    # stable unique by (kind,url)
    seen = set()
    uniq: List[ArchiveDoc] = []
    for d in sorted(out, key=lambda x: (x.year, x.quarter or 0, x.kind), reverse=True):
        key = (d.kind, d.url)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d)
    return uniq


def discover_most_recent_assets() -> List[Tuple[str, str]]:
    """Return (label, url) for PDFs / press links on the most-recent documents page."""
    html = _get(ARCHIVE_URLS["most_recent"]).decode("utf-8", errors="replace")
    items: List[Tuple[str, str]] = []
    for m in re.finditer(
        r'href="([^"]+)"[^>]*>\s*([^<]{3,160})',
        html,
    ):
        href, text = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
        low = (href + " " + text).lower()
        if not any(
            k in low
            for k in (
                "financing estimate",
                "policy statement",
                "tbac",
                "auction schedule",
                "buyback",
                "presentation",
                "recommended financing",
                "press-releases",
                ".pdf",
            )
        ):
            continue
        if href.startswith("#") or "javascript:" in href:
            continue
        items.append((text, absolutize(href)))
    seen = set()
    out = []
    for t, u in items:
        if u in seen:
            continue
        seen.add(u)
        out.append((t, u))
    return out


def slug_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1].split("?")[0] or "doc"


def download_docs(
    docs: Iterable[ArchiveDoc],
    cache_dir: Path,
    *,
    sleep_s: float = 0.35,
    force: bool = False,
) -> Dict[str, Path]:
    """Download HTML (and follow PDF links later). Returns url -> path map."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    index_path = cache_dir / "manifest.json"
    manifest: Dict[str, dict] = {}
    if index_path.exists():
        try:
            manifest = json.loads(index_path.read_text())
        except json.JSONDecodeError:
            manifest = {}

    paths: Dict[str, Path] = {}
    for doc in docs:
        slug = slug_from_url(doc.url)
        sub = cache_dir / "html" / doc.kind / str(doc.year)
        sub.mkdir(parents=True, exist_ok=True)
        path = sub / f"Q{doc.quarter or 0}_{slug}.html"
        meta = {
            **asdict(doc),
            "path": str(path.relative_to(cache_dir)),
        }
        if path.exists() and not force and path.stat().st_size > 1000:
            paths[doc.url] = path
            manifest[doc.url] = meta
            continue
        try:
            data = _get(doc.url)
            path.write_bytes(data)
            paths[doc.url] = path
            manifest[doc.url] = meta
            print(f"  saved {doc.kind} {doc.year} Q{doc.quarter} -> {path.name}", flush=True)
        except urllib.error.HTTPError as exc:
            print(f"  FAIL {doc.url}: HTTP {exc.code}", flush=True)
            meta["error"] = f"HTTP {exc.code}"
            manifest[doc.url] = meta
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {doc.url}: {exc}", flush=True)
            meta["error"] = str(exc)
            manifest[doc.url] = meta
        time.sleep(sleep_s)

    index_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return paths


def download_url(url: str, dest: Path, *, force: bool = False) -> Optional[Path]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force and dest.stat().st_size > 500:
        return dest
    try:
        dest.write_bytes(_get(url))
        return dest
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL asset {url}: {exc}", flush=True)
        return None
