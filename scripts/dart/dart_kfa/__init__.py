"""KFA engine package — filings-only numbers, view presets, model contracts."""

from .view_presets import get_view_presets, DEFAULT_VIEW, CARDS, MODELS
from .accounting_pack import empty_accounting_pack, coverage_status
from .model_contracts import (
    OE_HURDLE_DEFAULTS,
    FCFF_DCF_DEFAULTS,
    investor_models_stub,
    pe_models_stub,
    deal_models_stub,
)
from .sec_facts import fetch_accounting_pack, build_accounting_pack_from_facts
from .dart_facts import fetch_accounting_pack_kr
from .investor_models import run_investor_models, owner_earnings

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
    "fetch_accounting_pack",
    "build_accounting_pack_from_facts",
    "fetch_accounting_pack_kr",
    "run_investor_models",
    "owner_earnings",
]
