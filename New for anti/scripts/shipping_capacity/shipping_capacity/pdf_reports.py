"""Fetch, verify and extract small auditable snapshots from official PDFs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def _require_pdf_reader() -> Any:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # Keep the rest of the model runnable without optional PDF packages.
        raise RuntimeError("pypdf is required; install requirements-ml.txt") from exc
    return PdfReader


def _context(text: str, match: re.Match[str], radius: int = 180) -> str:
    return " ".join(text[max(0, match.start() - radius) : match.end() + radius].split())


def fetch_pdf_report(source: dict[str, Any], *, download_dir: Path) -> dict[str, Any]:
    """Download one configured official PDF and retain metadata plus textual evidence.

    Original PDFs are deliberately stored outside source control.  The JSON
    snapshot holds checksum, source URL and short matched contexts so a later
    analyst can reproduce the extraction from the original publication.
    """

    url = str(source["pdf_url"])
    if not url.startswith("https://"):
        raise ValueError("only HTTPS PDF sources are accepted")
    maximum_bytes = int(source.get("maximum_bytes", 40_000_000))
    request = Request(url, headers={"User-Agent": "global-trade-dashboard-shipping/1.0"})
    with urlopen(request, timeout=int(source.get("timeout_seconds", 60))) as response:
        data = response.read(maximum_bytes + 1)
        content_type = response.headers.get("Content-Type", "")
    if len(data) > maximum_bytes:
        raise RuntimeError(f"PDF exceeds configured {maximum_bytes} byte limit")
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"source did not return a PDF (content-type={content_type!r})")

    download_dir.mkdir(parents=True, exist_ok=True)
    path = download_dir / f"{source['id']}.pdf"
    path.write_bytes(data)
    reader = _require_pdf_reader()(str(path))
    max_pages = int(source.get("max_pages", len(reader.pages)))
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:max_pages])
    evidence: list[dict[str, str]] = []
    missing_patterns: list[str] = []
    for pattern in source.get("required_patterns", []):
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match is None:
            missing_patterns.append(pattern)
        else:
            evidence.append({"pattern": pattern, "context": _context(text, match)})
    return {
        "id": source["id"],
        "publisher": source.get("publisher"),
        "title": source.get("title"),
        "source_url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "byte_size": len(data),
        "page_count": len(reader.pages),
        "extracted_page_count": min(max_pages, len(reader.pages)),
        "status": "verified_text_extract" if not missing_patterns else "text_patterns_missing",
        "required_patterns_missing": missing_patterns,
        "evidence": evidence,
        "storage_note": "Original PDF is ephemeral download-cache input and is not committed with this snapshot.",
    }


def fetch_pdf_reports(config: dict[str, Any], *, download_dir: Path | None = None) -> dict[str, Any]:
    cache = download_dir or Path(tempfile.mkdtemp(prefix="shipping-pdf-"))
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for source in config.get("sources", []):
        try:
            reports.append(fetch_pdf_report(source, download_dir=cache))
        except Exception as exc:
            errors.append({"id": str(source.get("id")), "error": str(exc)})
    return {
        "status": "fetched" if not errors else "partial_quality_gated",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": reports,
        "errors": errors,
        "methodology": config.get("methodology"),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=root / "config" / "pdf_sources.json")
    parser.add_argument("--output", type=Path, default=root / "config" / "pdf_report_snapshots.json")
    parser.add_argument("--download-dir", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = fetch_pdf_reports(config, download_dir=args.download_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(result['sources'])} verified source(s))")


if __name__ == "__main__":
    main()
