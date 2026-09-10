"""Contract for Fed official-document indexes."""

from __future__ import annotations

from typing import Any, Iterable

from .contracts import validate_release_envelope


DOCUMENT_TYPES = {"fomc_statement", "fomc_minutes", "sep", "beige_book", "monetary_policy_report"}


def build_document_index(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Validate official documents and keep extracted text separate from summaries."""
    accepted = []
    rejected = []
    for raw in rows:
        row = dict(raw)
        errors = validate_release_envelope(row)
        if row.get("document_type") not in DOCUMENT_TYPES:
            errors.append(f"invalid:document_type:{row.get('document_type')}")
        if row.get("derived_summary") and not row.get("extracted_evidence"):
            errors.append("invalid:derived_summary_without_extracted_evidence")
        if errors:
            rejected.append({"release_id": row.get("release_id"), "errors": errors})
            continue
        accepted.append(row)
    accepted.sort(key=lambda row: str(row.get("published_at")), reverse=True)
    return {
        "items": accepted,
        "rejected": rejected,
        "policy": "official_extracted_evidence_separate_from_derived_summary",
    }
