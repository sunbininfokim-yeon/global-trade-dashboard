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

__all__ = [
    "attach_unified_views",
    "build_unified_views",
    "get_view_definitions",
    "analyze_canonical_facts",
    "build_currency_contract",
]
