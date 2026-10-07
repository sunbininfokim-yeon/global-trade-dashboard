"""Conservative DART document-table adapter for P2 disclosures.

OpenDART's single-account endpoint does not consistently contain order
backlog or segment-profit disclosures.  This module retrieves a filing
document only when explicitly called, extracts *candidate* HTML/XML tables,
and emits P1 structured rows only for an exact, reviewed table mapping.

It never reads prose as a number, guesses a table type, or promotes a mapping
from a candidate.  The default production manifest deliberately contains no
verified mappings.
"""

from __future__ import annotations

import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Mapping


CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_MANIFEST = CONFIG_DIR / "p2_dart_table_manifest.json"
OPEN_DART_DOCUMENT = "https://opendart.fss.or.kr/api/document.xml"
MANIFEST_SCHEMA = "kfa-p2-dart-table-manifest/1"
ALLOWED_DISCLOSURES = frozenset({"segment_profit", "backlog_order_book"})
MAX_ARCHIVE_BYTES = 30 * 1024 * 1024
MAX_EXTRACTED_BYTES = 60 * 1024 * 1024
MAX_DOCUMENTS = 64


class P2DartTableError(ValueError):
    """A safe adapter error that never includes a request URL or credential."""


def _text(raw: Any) -> str:
    return " ".join(str(raw or "").replace("\xa0", " ").split())


def _normalise(raw: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", _text(raw).lower())


def _number(raw: Any) -> float | None:
    """Parse an explicit table cell; placeholders and prose remain unavailable."""
    value = _text(raw).replace(",", "")
    if not value or value in {"-", "—", "–"}:
        return None
    negative = value.startswith("(") and value.endswith(")")
    if negative:
        value = value[1:-1].strip()
    # Footnote marks are not stripped.  A source table must be normalised by a
    # reviewed selector before it can become a numeric model input.
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", value):
        return None
    result = float(value)
    return -result if negative else result


class _TableParser(HTMLParser):
    """Small dependency-free parser for simple filing HTML/XML tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_stack: list[list[list[str]]] = []
        self._row_stack: list[list[str] | None] = []
        self._cell_stack: list[list[str] | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag == "table":
            self._table_stack.append([])
        elif tag == "tr" and self._table_stack:
            self._row_stack.append([])
        elif tag in {"td", "th"} and self._row_stack:
            self._cell_stack.append([])
        elif tag == "br" and self._cell_stack and self._cell_stack[-1] is not None:
            self._cell_stack[-1].append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell_stack and self._cell_stack[-1] is not None:
            self._cell_stack[-1].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell_stack and self._row_stack:
            cell = _text("".join(self._cell_stack.pop() or []))
            self._row_stack[-1].append(cell)
        elif tag == "tr" and self._row_stack and self._table_stack:
            row = self._row_stack.pop()
            if row and any(row):
                self._table_stack[-1].append(row)
        elif tag == "table" and self._table_stack:
            table = self._table_stack.pop()
            # Nested tables are retained independently.  The surrounding
            # cell's text is not used as a value in either table.
            if table:
                self.tables.append(table)


def _decode(raw: bytes) -> str | None:
    for encoding in ("utf-8", "utf-8-sig", "euc-kr", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _safe_document_members(archive: bytes) -> list[tuple[str, bytes]]:
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise P2DartTableError("document_archive_too_large")
    try:
        zipped = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise P2DartTableError("document_archive_not_zip") from exc
    selected = []
    total = 0
    for info in zipped.infolist():
        name = info.filename
        if info.is_dir() or name.startswith("/") or ".." in Path(name).parts:
            continue
        if Path(name).suffix.lower() not in {".xml", ".xhtml", ".html", ".htm"}:
            continue
        total += info.file_size
        if total > MAX_EXTRACTED_BYTES or len(selected) >= MAX_DOCUMENTS:
            raise P2DartTableError("document_archive_extraction_limit")
        selected.append((name, zipped.read(info)))
    if not selected:
        raise P2DartTableError("document_archive_has_no_html_or_xml")
    return selected


def extract_table_candidates(
    archive: bytes,
    *,
    report_id: str,
) -> list[dict[str, Any]]:
    """Return review candidates.  This never emits a financial disclosure."""
    if not _text(report_id):
        raise P2DartTableError("report_id_required")
    candidates: list[dict[str, Any]] = []
    for filename, raw in _safe_document_members(archive):
        source = _decode(raw)
        if source is None:
            continue
        parser = _TableParser()
        try:
            parser.feed(source)
            parser.close()
        except Exception as exc:  # HTMLParser can surface malformed declarations.
            raise P2DartTableError("document_table_parse_failed") from exc
        for index, table in enumerate(parser.tables):
            # A single cell is usually decorative markup, never an auditable
            # financial table.
            if len(table) < 2 or max(len(row) for row in table) < 2:
                continue
            header, rows = table[0], table[1:]
            candidates.append({
                "provider": "OpenDART document",
                "report_id": str(report_id),
                "source_table_id": f"{report_id}:{filename}:table:{index}",
                "source_file": filename,
                "table_index": index,
                "header": header,
                "rows": rows,
                "classification": "candidate_unverified",
            })
    return candidates


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    source = path or DEFAULT_MANIFEST
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P2DartTableError("manifest_unreadable") from exc
    validate_manifest(raw)
    return raw


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise P2DartTableError("unsupported_p2_table_manifest_schema")
    seen: set[str] = set()
    for collection, expected_status in (("verified_mappings", "verified"), ("candidate_mappings", "candidate")):
        entries = manifest.get(collection) or []
        if not isinstance(entries, list):
            raise P2DartTableError(f"manifest_{collection}_must_be_list")
        for mapping in entries:
            if not isinstance(mapping, Mapping):
                raise P2DartTableError("table_mapping_must_be_object")
            mapping_id = _text(mapping.get("id"))
            if not mapping_id or mapping_id in seen:
                raise P2DartTableError("table_mapping_id_missing_or_duplicate")
            seen.add(mapping_id)
            if mapping.get("status") != expected_status:
                raise P2DartTableError(f"table_mapping_wrong_status:{mapping_id}")
            if mapping.get("provider") != "OpenDART document":
                raise P2DartTableError(f"table_mapping_wrong_provider:{mapping_id}")
            if mapping.get("disclosure_type") not in ALLOWED_DISCLOSURES:
                raise P2DartTableError(f"table_mapping_unsupported_disclosure:{mapping_id}")
            if expected_status == "verified":
                required = ("report_id", "source_table_id", "fiscal_year", "period_end", "fs_div", "currency", "report_type", "row_selector")
                if any(mapping.get(key) in (None, "") for key in required):
                    raise P2DartTableError(f"verified_table_mapping_missing_evidence:{mapping_id}")
                selector = mapping.get("row_selector") or {}
                if not isinstance(selector, Mapping) or not isinstance(selector.get("row_index"), int) or not isinstance(selector.get("value_column"), int):
                    raise P2DartTableError(f"verified_table_mapping_invalid_selector:{mapping_id}")
                scale = _number(mapping.get("source_scale", 1))
                if scale is None or scale <= 0:
                    raise P2DartTableError(f"verified_table_mapping_invalid_scale:{mapping_id}")


def _mapping_rows(
    candidates: Iterable[Mapping[str, Any]],
    *,
    manifest: Mapping[str, Any],
    report_id: str,
) -> list[dict[str, Any]]:
    indexed = {
        _text(candidate.get("source_table_id")): candidate
        for candidate in candidates
        if isinstance(candidate, Mapping) and candidate.get("classification") == "candidate_unverified"
    }
    output: list[dict[str, Any]] = []
    for mapping in manifest.get("verified_mappings") or []:
        if _text(mapping.get("report_id")) != _text(report_id):
            continue
        table = indexed.get(_text(mapping.get("source_table_id")))
        if not table:
            continue
        selector = mapping["row_selector"]
        rows = table.get("rows") or []
        row_index, value_column = selector["row_index"], selector["value_column"]
        if row_index < 0 or row_index >= len(rows):
            continue
        row = rows[row_index]
        if value_column < 0 or value_column >= len(row):
            continue
        amount = _number(row[value_column])
        if amount is None:
            continue
        scale = _number(mapping.get("source_scale", 1)) or 1.0
        segment_column = selector.get("segment_name_column")
        segment_name = row[segment_column] if isinstance(segment_column, int) and 0 <= segment_column < len(row) else mapping.get("segment_name")
        output.append({
            "disclosure_type": mapping["disclosure_type"],
            "is_structured_reported": True,
            "segment_id": mapping.get("segment_id"),
            "segment_name": segment_name,
            "value": amount * scale,
            "unit": {"kind": "currency", "currency": mapping["currency"], "scale": 1},
            "fiscal_year": mapping["fiscal_year"],
            "period_end": mapping["period_end"],
            "fs_div": mapping["fs_div"],
            "report_id": mapping["report_id"],
            "report_type": mapping["report_type"],
            "report_code": mapping.get("report_code"),
            "provider": "OpenDART document",
            "source_concept": mapping.get("source_concept"),
            "mapping_id": mapping["id"],
            "source_table": mapping["source_table_id"],
            "source_row_id": f"{mapping['source_table_id']}:row:{row_index}",
        })
    return output


def build_verified_structured_disclosures(
    archive: bytes,
    *,
    report_id: str,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert only exact verified table rows into the P1 input contract."""
    active_manifest = dict(manifest) if manifest is not None else load_manifest()
    validate_manifest(active_manifest)
    candidates = extract_table_candidates(archive, report_id=report_id)
    rows = _mapping_rows(candidates, manifest=active_manifest, report_id=report_id)
    return {
        "schema_version": "kfa-p2-dart-table-extraction/1",
        "report_id": report_id,
        "candidate_table_count": len(candidates),
        "verified_mapping_count": len(active_manifest.get("verified_mappings") or []),
        "structured_disclosures": rows,
        "reason": None if rows else "missing:verified_dart_document_table_mapping",
    }


def fetch_dart_document(*, api_key: str, report_id: str) -> bytes:
    """Fetch a DART document archive without persisting a key or request URL."""
    if not _text(api_key):
        raise P2DartTableError("dart_api_key_required")
    if not re.fullmatch(r"\d{14}", _text(report_id)):
        raise P2DartTableError("invalid_dart_report_id")
    query = urllib.parse.urlencode({"crtfc_key": api_key, "rcept_no": report_id})
    request = urllib.request.Request(
        f"{OPEN_DART_DOCUMENT}?{query}",
        headers={"User-Agent": "kfa-p2-disclosure-adapter/1.0 (OpenDART public filings)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read(MAX_ARCHIVE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise P2DartTableError(f"opendart_document_http_status:{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise P2DartTableError("opendart_document_network_error") from exc
    if len(data) > MAX_ARCHIVE_BYTES:
        raise P2DartTableError("document_archive_too_large")
    return data


def fetch_from_environment(*, report_id: str) -> bytes:
    """Convenience entrypoint; credential is never written or returned."""
    api_key = _text(os.environ.get("DART_API_KEY"))
    if not api_key:
        raise P2DartTableError("dart_api_key_required")
    return fetch_dart_document(api_key=api_key, report_id=report_id)
