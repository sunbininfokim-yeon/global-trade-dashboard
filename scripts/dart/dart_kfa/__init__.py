"""KFA engine package — filings-only numbers, view presets, model contracts.

Source adapters are intentionally optional imports while the engine is being
distributed.  A UI snapshot / fixture must remain analysable even when the
private SEC/OpenDART adapter modules are not checked into this worktree.
"""

from .view_presets import get_view_presets, DEFAULT_VIEW, CARDS, MODELS
from .accounting_pack import empty_accounting_pack, coverage_status
from .model_contracts import (
    OE_HURDLE_DEFAULTS,
    FCFF_DCF_DEFAULTS,
    investor_models_stub,
    pe_models_stub,
    deal_models_stub,
)
from .derived_cards import (
    accounting_pack_from_snapshot,
    build_expert_cards,
    enrich_snapshot,
    run_kfa_analysis,
)

try:  # optional source adapters, not prerequisites for pure calculations
    from .sec_facts import fetch_accounting_pack, build_accounting_pack_from_facts
except ImportError:  # pragma: no cover - depends on deployment package
    fetch_accounting_pack = None
    build_accounting_pack_from_facts = None

try:  # optional source adapter, uses DART_API_KEY at runtime only
    from .dart_facts import fetch_accounting_pack_kr
except ImportError:  # pragma: no cover - depends on deployment package
    fetch_accounting_pack_kr = None

__all__ = [
    "get_view_presets",
    "DEFAULT_VIEW",
    "CARDS",
    "MODELS",
    "empty_accounting_pack",
    "coverage_status",
    "OE_HURDLE_DEFAULTS",
    "FCFF_DCF_DEFAULTS",
    "investor_models_stub",
    "pe_models_stub",
    "deal_models_stub",
    "accounting_pack_from_snapshot",
    "build_expert_cards",
    "enrich_snapshot",
    "run_kfa_analysis",
    "fetch_accounting_pack",
    "build_accounting_pack_from_facts",
    "fetch_accounting_pack_kr",
]
