"""Bounded official-source collector. No AI calls, background jobs, or mail.

Manifest metadata is curator input, not inferred legal effect. Network failure
never replaces a previously saved document. Snapshots live outside the repo.
"""
import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

MAX_BYTES = 12 * 1024 * 1024
MAX_CHARS = 300_000
ORDER = ("coal", "nickel_mining", "palm_oil", "biofuel")


def normalized(text):
    return re.sub(r"\s+", " ", text).strip()


def official_url(url):
    host = urlparse(url).hostname or ""
    return urlparse(url).scheme == "https" and host.endswith(".go.id")


def html_content(data):
    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    node = soup.select_one("main") or soup.body or soup
    return normalized(node.get_text(" ", strip=True)), soup


def classify_pdf(text):
    head = normalized(text[:2500]).upper()
    if re.search(r"^(?:-\s*\d+\s*-\s*)?(?:SALINAN\s+)?RANCANGAN\b", head):
        return "draft"
    if re.search(r"\bABSTRAK\b", head):
        return "abstract"
    if re.search(r"\b(PERATURAN|KEPUTUSAN|UNDANG.UNDANG|SURAT EDARAN)\b", head):
        return "official_text"
    return "unclassified_pdf"


def pdf_content(data):
    # Some scanned PDFs stall parsers; kill only the bounded child, retain metadata.
    code = "import io,sys\nfrom pypdf import PdfReader\nr=PdfReader(io.BytesIO(sys.stdin.buffer.read()))\nif len(r.pages)>300: sys.exit('pdf_page_limit')\nprint(' '.join((p.extract_text() or '') for p in r.pages)[:600000])"
    child = subprocess.run([sys.executable, "-c", code], input=data, capture_output=True, timeout=35, check=True)
    return normalized(child.stdout.decode("utf-8"))


def fetch(url, cache_dir):
    if not official_url(url):
        raise ValueError("non_official_url")
    # No retries or bot-block workarounds. All redirects must stay official.
    with requests.get(url, timeout=(10, 25), stream=True,
                      headers={"User-Agent": "ChokeMonitor-policy-research/1.0"}) as r:
        r.raise_for_status()
        if not all(official_url(x.url) for x in [*r.history, r]):
            raise ValueError("non_official_redirect")
        chunks, size = [], 0
        started = time.monotonic()
        for chunk in r.iter_content(65536):
            if time.monotonic() - started > 60:
                raise ValueError("download_deadline")
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("response_too_large")
            chunks.append(chunk)
        data = b"".join(chunks)
        digest = hashlib.sha256(data).hexdigest()
        path = cache_dir / digest
        path.write_bytes(data)
        return data, r.url, digest


def verify_identity(text, entry):
    value = normalized(text).casefold()
    # All identity phrases are required; list pages must never become laws.
    return all(normalized(t).casefold() in value for t in entry["identity_phrases"])


def collect(entry, cache_dir):
    data, url, raw_hash = fetch(entry["url"], cache_dir)
    is_pdf = data.startswith(b"%PDF")
    if is_pdf:
        text = pdf_content(data)
        soup = None
    else:
        text, soup = html_content(data)
        if any(x in text[:1500].lower() for x in ["request rejected", "access denied", "maintenance", "verify you are human"]):
            raise ValueError("blocked_or_maintenance")
    if len(text) < 150 or not verify_identity(text, entry):
        raise ValueError("document_identity_not_verified")
    kind = classify_pdf(text) if is_pdf else "official_metadata"
    # Drafts can be observed but never silently stored as an enacted text.
    if kind in ("draft", "unclassified_pdf"):
        raise ValueError("draft_or_unclassified_document")
    links = []
    if soup:
        for a in soup.select("a[href], iframe[src], embed[src], object[data]"):
            href = a.get("href") or a.get("src") or a.get("data")
            target = urljoin(url, href)
            label = normalized(a.get_text(" ", strip=True))
            if official_url(target) and (re.search(r"\.pdf(?:[?#]|$)|/download|/unduh", target, re.I)):
                if not any(x["url"] == target for x in links):
                    links.append({"url": target, "label": label[:250]})
    text_source_url = url
    raw_text_sha256 = raw_hash
    body_status = "extracted" if is_pdf and kind == "official_text" else "metadata_only"
    # Prefer the publisher's explicit final-document link. Draft links are
    # separate on Kemendag pages and must never substitute for signed text.
    preferred = [x for x in links if re.search(r"Fulltext|Peraturan \[ID\]|Download Dokumen", x["label"], re.I)]
    if not is_pdf and preferred:
        candidate = preferred[0]
        try:
            time.sleep(2)
            pdf, pdf_url, pdf_hash = fetch(candidate["url"], cache_dir)
            if not pdf.startswith(b"%PDF"):
                raise ValueError("not_pdf")
            pdf_text = pdf_content(pdf)
            pdf_kind = classify_pdf(pdf_text)
            if pdf_kind != "official_text" or not verify_identity(pdf_text, entry):
                raise ValueError("pdf_identity_or_final_status_unverified")
            text, kind = pdf_text, pdf_kind
            text_source_url, raw_text_sha256 = pdf_url, pdf_hash
            body_status = "extracted"
        except Exception as exc:
            body_status = "unavailable:" + str(exc)[:150]
    # Save evidence, never scrape a guessed download address or draft link.
    observed = datetime.now(timezone.utc).isoformat()
    excerpt = text[:MAX_CHARS]
    return {
        "document_id": entry["document_id"], "country_code": "IDN",
        "title": entry["title"], "title_ko": entry["title_ko"],
        "issuer_name": entry["issuer_name"], "issuer_level": entry["issuer_level"],
        "jurisdiction": entry["jurisdiction"], "document_type": entry["document_type"],
        "document_number": entry["document_number"], "document_year": entry["document_year"],
        "topics": entry["topics"], "primary_stage": entry["primary_stage"],
        "scope_note": entry["scope_note"], "source_url": url,
        "observed_at": observed, "content_kind": kind,
        "text_content": excerpt, "text_truncated": len(text) > MAX_CHARS,
        "content_hash": hashlib.sha256(excerpt.encode()).hexdigest(),
        "raw_sha256": raw_hash, "download_candidates": links,
        "text_source_url": text_source_url, "raw_text_sha256": raw_text_sha256,
        "body_status": body_status,
        "legal_status": "unverified", "status_note": "Official source found; current legal effect and amendments require review.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=[*ORDER, "all"], default="coal")
    p.add_argument("--document-id", action="append", help="Retry only selected manifest IDs in a new run directory")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--limit", type=int, default=30)
    args = p.parse_args()
    out = Path(args.output_dir).resolve()
    root = Path(__file__).resolve().parents[2]
    if out == root or root in out.parents:
        p.error("output must be outside repository")
    if (out / "collection.json").exists():
        p.error("collection exists; use a new run directory to preserve prior evidence")
    if not 1 <= args.limit <= 100:
        p.error("limit must be 1..100")
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw").mkdir(exist_ok=True)
    manifest = json.loads(Path(__file__).with_name("sources.json").read_text())
    entries = [e for e in manifest if args.stage == "all" or e["primary_stage"] == args.stage]
    if args.document_id:
        requested = set(args.document_id)
        entries = [e for e in entries if e['document_id'] in requested]
        if {e['document_id'] for e in entries} != requested:
            p.error("document ID missing from the selected stage")
    entries.sort(key=lambda e: ORDER.index(e["primary_stage"]))
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "documents": [], "failures": []}
    blocked_hosts = set()
    for entry in entries[:args.limit]:
        try:
            if urlparse(entry["url"]).hostname in blocked_hosts:
                raise ValueError("host_blocked_earlier_in_run")
            doc = collect(entry, out / "raw")
            result["documents"].append(doc)
            print(json.dumps({"id": entry["document_id"], "status": "collected", "kind": doc["content_kind"], "chars": len(doc["text_content"])}), flush=True)
        except Exception as exc:
            if isinstance(exc, requests.HTTPError) and exc.response.status_code in (403, 429):
                blocked_hosts.add(urlparse(entry["url"]).hostname)
            detail = str(exc)[:300]
            result["failures"].append({"document_id": entry["document_id"], "url": entry["url"], "error": detail})
            print(json.dumps({"id": entry["document_id"], "status": "failed", "error": detail}), flush=True)
        # Checkpoint only after each attempt; prior successful artifacts remain.
        tmp = out / "collection.json.tmp"
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        tmp.replace(out / "collection.json")
        time.sleep(2)
    print(json.dumps({"collected": len(result["documents"]), "failed": len(result["failures"])}))


if __name__ == "__main__":
    main()
