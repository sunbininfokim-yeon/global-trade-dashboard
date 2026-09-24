"""HS / product code equivalence and hierarchy matching.

When sources use different code systems (HS4 vs HS6, JODI product codes,
USDA PSD commodity names), decide:
  same | parent | child | sibling_under | incompatible

Normalization rules:
  - strip non-digits for HS-like codes
  - leading-prefix: HS 2709 is parent of 270900 / 2709.00.00
  - explicit alias map for non-HS vocabularies (JODI CRUDEOIL ↔ HS 2709)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Non-HS product aliases → canonical commodity_id used in commodity_trade_board
PRODUCT_ALIASES: dict[str, str] = {
    # JODI oil
    "CRUDEOIL": "crude_oil",
    "TOTCRUDE": "crude_oil",
    "OTHERCRUDE": "crude_oil",
    "NGL": "petroleum_products",  # partial; not pure petroleum products
    "GASDIES": "petroleum_products",
    "MOTORGAS": "petroleum_products",
    "JETKERO": "petroleum_products",
    "RESFUEL": "petroleum_products",
    "LPG": "petroleum_products",
    "NATGAS": "lng",  # volume not always LNG; flag as proxy in adapter
    # board ids identity
    "crude_oil": "crude_oil",
    "petroleum_products": "petroleum_products",
    "lng": "lng",
    "coal": "coal",
    "uranium": "uranium",
    "wheat": "wheat",
    "corn": "corn",
    "soybeans": "soybeans",
    "rice": "rice",
}


# Canonical commodity → preferred HS stems (parent codes)
COMMODITY_HS_STEMS: dict[str, list[str]] = {
    "crude_oil": ["2709"],
    "petroleum_products": ["2710"],
    "lng": ["271111", "2711"],
    "coal": ["2701"],
    "uranium": ["284410", "2844"],
    "iron_ore": ["2601"],
    "copper": ["2603", "7403"],
    "nickel": ["2604", "7502"],
    "aluminum": ["7601"],
    "bauxite": ["2606"],
    "lithium": ["283691", "282520"],
    "cobalt": ["2605", "8105"],
    "graphite": ["2504"],
    "rare_earths": ["2805", "2846"],
    "tungsten": ["2611", "8101"],
    "antimony": ["8110", "2617"],
    "wheat": ["1001"],
    "corn": ["1005"],
    "soybeans": ["1201"],
    "rice": ["1006"],
    "sunflowerseed_oil": ["1512"],
    "palm_oil": ["1511"],
    "sugar": ["1701"],
    "cotton": ["5201"],
    "soybean_meal": ["2304"],
    "barley": ["1003"],
}


@dataclass
class MatchResult:
    relation: str  # same | parent | child | sibling_under | alias | incompatible
    a_norm: str
    b_norm: str
    depth_delta: int  # >0 if a is parent of b (a shorter)
    note: str = ""


def normalize_hs(code: str | None) -> str:
    if not code:
        return ""
    s = "".join(ch for ch in str(code).strip() if ch.isdigit())
    return s


def hs_relation(a: str, b: str) -> MatchResult:
    """Compare two HS-like codes."""
    na, nb = normalize_hs(a), normalize_hs(b)
    if not na or not nb:
        return MatchResult("incompatible", na, nb, 0, "empty code")
    if na == nb:
        return MatchResult("same", na, nb, 0)
    # same root but different length → hierarchy
    if nb.startswith(na):
        return MatchResult("parent", na, nb, len(nb) - len(na), f"{na} parent of {nb}")
    if na.startswith(nb):
        return MatchResult("child", na, nb, len(na) - len(nb), f"{na} child of {nb}")
    # common prefix of at least 2 digits → weak sibling under shared chapter
    common = 0
    for ca, cb in zip(na, nb):
        if ca == cb:
            common += 1
        else:
            break
    if common >= 4:
        return MatchResult("sibling_under", na, nb, 0, f"shared prefix {na[:common]}")
    if common >= 2:
        return MatchResult("sibling_under", na, nb, 0, f"shared chapter {na[:2]}")
    return MatchResult("incompatible", na, nb, 0)


def resolve_commodity_id(raw: str) -> Optional[str]:
    key = (raw or "").strip()
    if key in PRODUCT_ALIASES:
        return PRODUCT_ALIASES[key]
    upper = key.upper()
    if upper in PRODUCT_ALIASES:
        return PRODUCT_ALIASES[upper]
    # HS → commodity by stem
    hs = normalize_hs(key)
    if hs:
        for cid, stems in COMMODITY_HS_STEMS.items():
            for stem in stems:
                rel = hs_relation(stem, hs)
                if rel.relation in ("same", "parent", "child"):
                    return cid
    return None


def codes_compatible_for_merge(code_a: str, code_b: str) -> bool:
    """True if series can be summed/aligned without double-counting caution.

    same / parent-child: OK to align on parent bucket (child rolls into parent).
    sibling under same 4-digit: do NOT auto-sum (overlap risk).
    """
    r = hs_relation(code_a, code_b)
    return r.relation in ("same", "parent", "child", "alias")


def prefer_code(codes: list[str], prefer_len: int = 4) -> str:
    """Pick a reporting code closest to prefer_len digits (default HS4)."""
    norms = [normalize_hs(c) for c in codes if normalize_hs(c)]
    if not norms:
        return ""
    norms.sort(key=lambda x: (abs(len(x) - prefer_len), len(x)))
    return norms[0]
