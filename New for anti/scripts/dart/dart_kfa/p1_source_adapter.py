"""Verified-source bridge for the P1 disclosure contract.

This module is deliberately stricter than the general account mapper.  It
does not use account labels, regular expressions, or an inferred D&A split.
Only an exact source concept/table identifier in a versioned *verified*
manifest can enter the P1 compute path.  Candidate mappings are retained as
research records only and are never converted into an account specification.

The bridge returns normal ``canonical-financial-facts/1`` fragments so the P1
engine can use its existing period and unit controls.  It leaves the reviewed
general account map untouched.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from .canonical_facts import adapt_dart_filings, adapt_sec_companyfacts


MANIFEST_SCHEMA_VERSION = "kfa-p1-source-validation/1"
P1_ACCOUNT_IDS = frozenset({"PPE_DEPRECIATION", "INTANGIBLE_AMORTIZATION"})
P1_REPORT_PRIORITY = {
    "DART": ("11014", "11012", "11013", "11011"),
    "SEC": ("Q3", "Q2", "Q1", "FY"),
}
_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_MANIFEST_PATH = _CONFIG_DIR / "p1_source_validation_manifest.json"


class P1SourceAdapterError(ValueError):
    """Raised when a source record or manifest crosses the P1 safety boundary."""


def load_validation_manifest(path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate the source-validation manifest without mutating it."""
    manifest_path = Path(path) if path else DEFAULT_MANIFEST_PATH
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    return validate_validation_manifest(manifest)


def validate_validation_manifest(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the small, explicit allow-list format.

    A mapping must say ``status: verified`` *and* contain an acceptance record
    before it can become an adapter specification.  Candidate records have a
    looser format because they are intentionally non-executable research.
    """
    if not isinstance(raw, Mapping):
        raise P1SourceAdapterError("manifest_must_be_object")
    manifest = deepcopy(dict(raw))
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise P1SourceAdapterError("unsupported_p1_source_manifest_schema")
    priority = manifest.get("report_priority") or {}
    for provider, expected in P1_REPORT_PRIORITY.items():
        if tuple(priority.get(provider) or ()) != expected:
            raise P1SourceAdapterError(f"invalid_report_priority:{provider}")
    seen: set[str] = set()
    for mapping in manifest.get("verified_mappings") or []:
        if not isinstance(mapping, Mapping):
            raise P1SourceAdapterError("verified_mapping_must_be_object")
        _validate_verified_mapping(mapping, seen)
    for mapping in manifest.get("candidate_mappings") or []:
        if not isinstance(mapping, Mapping):
            raise P1SourceAdapterError("candidate_mapping_must_be_object")
        mapping_id = str(mapping.get("mapping_id") or "")
        if not mapping_id or mapping_id in seen:
            raise P1SourceAdapterError("candidate_mapping_id_missing_or_duplicate")
        seen.add(mapping_id)
        if mapping.get("status") != "candidate":
            raise P1SourceAdapterError(f"candidate_mapping_not_marked_candidate:{mapping_id}")
    return manifest


def _validate_verified_mapping(mapping: Mapping[str, Any], seen: set[str]) -> None:
    mapping_id = str(mapping.get("mapping_id") or "")
    if not mapping_id or mapping_id in seen:
        raise P1SourceAdapterError("verified_mapping_id_missing_or_duplicate")
    seen.add(mapping_id)
    provider = str(mapping.get("provider") or "").upper()
    if provider not in P1_REPORT_PRIORITY:
        raise P1SourceAdapterError(f"verified_mapping_invalid_provider:{mapping_id}")
    if mapping.get("status") != "verified":
        raise P1SourceAdapterError(f"verified_mapping_not_verified:{mapping_id}")
    acceptance = mapping.get("acceptance_record")
    required_acceptance = ("reviewed_at", "reviewer", "evidence_ids", "acceptance_basis")
    if not isinstance(acceptance, Mapping) or any(not acceptance.get(key) for key in required_acceptance):
        raise P1SourceAdapterError(f"verified_mapping_missing_acceptance_record:{mapping_id}")
    kind = mapping.get("kind")
    if kind == "account":
        if mapping.get("canonical_account_id") not in P1_ACCOUNT_IDS:
            raise P1SourceAdapterError(f"invalid_p1_account_mapping:{mapping_id}")
        if mapping.get("separate_component") is not True:
            raise P1SourceAdapterError(f"account_mapping_requires_separate_component:{mapping_id}")
        if not str(mapping.get("source_concept") or ""):
            raise P1SourceAdapterError(f"account_mapping_requires_exact_source_concept:{mapping_id}")
        if str(mapping.get("statement") or "").upper() not in {"IS", "CIS", "CF"}:
            raise P1SourceAdapterError(f"account_mapping_invalid_statement:{mapping_id}")
    elif kind == "structured_row":
        if mapping.get("disclosure_type") not in {"segment_profit", "backlog_order_book"}:
            raise P1SourceAdapterError(f"structured_mapping_invalid_disclosure_type:{mapping_id}")
        if not str(mapping.get("source_table_id") or "") or not str(mapping.get("source_row_type") or ""):
            raise P1SourceAdapterError(f"structured_mapping_requires_exact_table_and_row_type:{mapping_id}")
    else:
        raise P1SourceAdapterError(f"verified_mapping_invalid_kind:{mapping_id}")


def verified_mappings(manifest: Mapping[str, Any], *, provider: str, kind: str | None = None) -> list[dict[str, Any]]:
    """Return executable mappings only; candidates intentionally never appear."""
    checked = validate_validation_manifest(manifest)
    target = str(provider).upper()
    return [
        dict(item)
        for item in checked.get("verified_mappings") or []
        if item.get("provider") == target and (kind is None or item.get("kind") == kind)
    ]


def build_verified_p1_account_specs(manifest: Mapping[str, Any], *, provider: str) -> dict[str, dict[str, Any]]:
    """Build exact canonical-adapter specs from verified account mappings only."""
    target = str(provider).upper()
    specs: dict[str, dict[str, Any]] = {}
    for mapping in verified_mappings(manifest, provider=target, kind="account"):
        account_id = str(mapping["canonical_account_id"])
        spec = specs.setdefault(
            account_id,
            {
                "nature": "flow",
                "statement": str(mapping["statement"]).upper(),
                "unit_kind": "currency",
                "source_ids": [],
                "sec_concepts": [],
            },
        )
        if spec["statement"] != str(mapping["statement"]).upper():
            raise P1SourceAdapterError(f"conflicting_verified_statement:{account_id}")
        concept = str(mapping["source_concept"])
        if target == "DART":
            spec["source_ids"].append(concept)
        elif target == "SEC":
            # Companyfacts keys are bare taxonomy identifiers.  The manifest
            # accepts either representation but does not attempt fuzzy prefix
            # matching.
            spec["sec_concepts"].append(concept.removeprefix("us-gaap:"))
        else:  # validate_validation_manifest normally makes this unreachable.
            raise P1SourceAdapterError(f"unsupported_provider:{target}")
    for spec in specs.values():
        if target == "DART":
            spec.pop("sec_concepts", None)
        else:
            spec.pop("source_ids", None)
    return specs


def adapt_verified_dart_p1_accounts(
    filings: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    fiscal_year_end: str,
    entity_id: str | None = None,
    fs_div: str = "CFS",
    currency: str = "KRW",
    scale: int | float = 1,
    source_unit_label: str | None = "원",
    report_periods: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Adapt raw ``fnlttSinglAcntAll`` rows through the verified allow-list."""
    specs = build_verified_p1_account_specs(manifest, provider="DART")
    if not specs:
        return _empty_fragment("DART", fiscal_year_end, entity_id, fs_div, currency)
    return adapt_dart_filings(
        filings,
        account_specs=specs,
        fiscal_year_end=fiscal_year_end,
        entity_id=entity_id,
        fs_div=fs_div,
        currency=currency,
        scale=scale,
        source_unit_label=source_unit_label,
        report_periods=report_periods,
    )


def adapt_verified_sec_p1_accounts(
    companyfacts: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    fiscal_year_end: str,
    entity_id: str | None = None,
    currency: str = "USD",
    report_periods: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Adapt SEC companyfacts through the same verified allow-list."""
    specs = build_verified_p1_account_specs(manifest, provider="SEC")
    if not specs:
        return _empty_fragment("SEC", fiscal_year_end, entity_id, "CFS", currency)
    return adapt_sec_companyfacts(
        companyfacts,
        account_specs=specs,
        fiscal_year_end=fiscal_year_end,
        entity_id=entity_id,
        currency=currency,
        report_periods=report_periods,
    )


def merge_verified_p1_accounts(canonical: Mapping[str, Any], fragment: Mapping[str, Any]) -> dict[str, Any]:
    """Attach a verified fragment without overwriting a reported P1 fact.

    Source, entity, fiscal year, scope and currency must match.  This is an
    explicit bridge rather than an implicit change to the general account map.
    """
    if canonical.get("schema_version") != "canonical-financial-facts/1" or fragment.get("schema_version") != "canonical-financial-facts/1":
        raise P1SourceAdapterError("canonical_fragment_schema_required")
    for key in ("source", "entity_id", "fiscal_year", "fs_div", "currency", "fiscal_year_end"):
        left, right = canonical.get(key), fragment.get(key)
        if left is not None and right is not None and left != right:
            raise P1SourceAdapterError(f"incompatible_fragment_{key}")
    output = deepcopy(dict(canonical))
    output.setdefault("series", {})
    for account_id, series in (fragment.get("series") or {}).items():
        if account_id not in P1_ACCOUNT_IDS:
            continue
        existing = (output["series"].get(account_id) or {})
        if _series_has_available_value(existing):
            raise P1SourceAdapterError(f"refuse_to_overwrite_existing_p1_account:{account_id}")
        output["series"][account_id] = deepcopy(series)
    return output


def _series_has_available_value(series: Mapping[str, Any]) -> bool:
    cells = [series.get("annual")] + list((series.get("quarters") or {}).values())
    return any(isinstance(cell, Mapping) and cell.get("availability") == "available" for cell in cells)


def _empty_fragment(
    provider: str,
    fiscal_year_end: str,
    entity_id: str | None,
    fs_div: str,
    currency: str,
) -> dict[str, Any]:
    """Represent a valid no-observation result when no mapping is verified."""
    year = int(str(fiscal_year_end)[:4])
    return {
        "schema_version": "canonical-financial-facts/1",
        "source": provider,
        "entity_id": entity_id,
        "fiscal_year": year,
        "fiscal_year_start": None,
        "fiscal_year_end": str(fiscal_year_end),
        "fs_div": str(fs_div).upper(),
        "currency": str(currency).upper(),
        "series": {},
        "p1_source_adapter": {"status": "no_verified_account_mapping"},
    }


def adapt_verified_structured_disclosures(
    records: Sequence[Mapping[str, Any]],
    *,
    manifest: Mapping[str, Any],
    provider: str,
) -> list[dict[str, Any]]:
    """Convert verified table rows into the P1 structured-row contract.

    Text/narrative fields are not examined.  A record must identify the exact
    manifest-approved table and row type and explicitly say it came from a
    structured table.  This keeps prose and LLM extraction out of the path.
    """
    target = str(provider).upper()
    allow = {
        (str(item["source_table_id"]), str(item["source_row_type"])): item
        for item in verified_mappings(manifest, provider=target, kind="structured_row")
    }
    accepted: list[dict[str, Any]] = []
    for raw in records:
        if not isinstance(raw, Mapping) or str(raw.get("provider") or "").upper() != target:
            continue
        if raw.get("structure") not in {"table", "xbrl_table"}:
            continue
        mapping = allow.get((str(raw.get("source_table_id") or ""), str(raw.get("source_row_type") or "")))
        if not mapping:
            continue
        unit = raw.get("unit") if isinstance(raw.get("unit"), Mapping) else {
            "kind": "currency",
            "currency": raw.get("currency"),
            "scale": raw.get("scale", 1),
        }
        required = ("value", "fiscal_year", "period_end", "fs_div", "report_id", "report_type", "source_row_id")
        if any(raw.get(field) is None for field in required) or not unit.get("currency"):
            continue
        accepted.append({
            "disclosure_type": mapping["disclosure_type"],
            "is_structured_reported": True,
            "segment_id": raw.get("segment_id"),
            "segment_name": raw.get("segment_name"),
            "value": raw.get("value"),
            "unit": dict(unit),
            "fiscal_year": raw.get("fiscal_year"),
            "period_start": raw.get("period_start"),
            "period_end": raw.get("period_end"),
            "fs_div": str(raw.get("fs_div")).upper(),
            "report_id": raw.get("report_id"),
            "report_code": raw.get("report_code"),
            "report_type": raw.get("report_type"),
            "source_table": raw.get("source_table_id"),
            "source_row_id": raw.get("source_row_id"),
            "provider": target,
            "source_concept": raw.get("source_concept"),
            "mapping_id": mapping["mapping_id"],
            "acceptance_record": deepcopy(mapping["acceptance_record"]),
        })
    return accepted
