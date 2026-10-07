"""KFA-Engine — Korean Filing Analytics (deterministic financial ratios).

L0 fetch → L1 account normalize → L2 metric formulas → optional L3/L4 later.
Numbers are never invented by a model; missing inputs become null + reason.
"""

from __future__ import annotations

__version__ = "1.0.0"
ENGINE_VERSION = "kfa-1.0.0"

# The unified view layer is adapter-independent: both SEC and OpenDART callers
# attach it after their facts have entered the common dart-company schema.
from .view_engine import attach_unified_views, build_unified_views, get_view_definitions
from .canonical_analysis import analyze_canonical_facts
from .currency import build_currency_contract
from .snapshot_adapter import build_kfa_snapshot, build_kfa_snapshot_from_dart_filings
from .p1_disclosures import build_p1_disclosures, compute_receivables_to_sales, compute_strict_ebitda, resolve_latest_endpoint
from .p1_source_adapter import (
    adapt_verified_dart_p1_accounts,
    adapt_verified_sec_p1_accounts,
    adapt_verified_structured_disclosures,
    load_validation_manifest,
    merge_verified_p1_accounts,
)

__all__ = [
    "attach_unified_views",
    "build_unified_views",
    "get_view_definitions",
    "analyze_canonical_facts",
    "build_currency_contract",
    "build_kfa_snapshot",
    "build_kfa_snapshot_from_dart_filings",
    "build_p1_disclosures",
    "compute_receivables_to_sales",
    "compute_strict_ebitda",
    "resolve_latest_endpoint",
    "adapt_verified_dart_p1_accounts",
    "adapt_verified_sec_p1_accounts",
    "adapt_verified_structured_disclosures",
    "load_validation_manifest",
    "merge_verified_p1_accounts",
]
