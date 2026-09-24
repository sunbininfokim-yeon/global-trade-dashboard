"""Indicators that have no public series. Drop them instead of showing a fixture.

Kept on purpose, because the publisher posts the number without a terminal
subscription: NBS PMI, KOF barometer, procure.ch PMI, SIPMM PMI, Ivey PMI.
Those stay in the pack until a public file is parsed. They are not in this set.
"""

from __future__ import annotations

from typing import Any

# Markit/ICE CDS, CME FedWatch, ISM, S&P Global PMIs (Caixin, HCOB, Absa,
# Jibun and the other country PMIs stored under these ids), Wind LGFV,
# Markit Asia property high yield, Argus Urals, Centaline CCL.
PAID_ONLY_IDS = frozenset({
    "sovereign_cds_5y",
    "fedwatch",
    "ism_mfg",
    "ism_services",
    "absa_pmi",
    "caixin_pmi",
    "hcob_pmi_mfg",
    "hcob_pmi_svc",
    "pmi_mfg_br",
    "pmi_svc_br",
    "pmi_mfg_tw",
    "pmi_mfg_vn",
    "pmi_services_in",
    "pmi_services_jp",
    "lgfv_spread",
    "cn_hy_prop_spread",
    "urals_brent_spread",
    "ccl_index",
})


def strip_paid_only(universe: dict[str, Any]) -> list[str]:
    """Remove paid-only cards, chips, and headlines. Returns removed keys."""
    removed: list[str] = []
    for country in universe.get("countries") or []:
        iso = str(country.get("iso3") or "")
        country["indicators"] = _drop(country.get("indicators"), iso, removed)
        if isinstance(country.get("headlines"), list):
            country["headlines"] = _drop(country["headlines"], iso, removed)
        categories = country.get("categories") or {}
        if isinstance(categories, dict):
            for name, chips in list(categories.items()):
                categories[name] = _drop(chips, iso, removed)
    return removed


def _drop(items: Any, iso: str, removed: list[str]) -> list[Any]:
    if not isinstance(items, list):
        return [] if items is None else items
    kept: list[Any] = []
    for item in items:
        if isinstance(item, dict) and item.get("id") in PAID_ONLY_IDS:
            removed.append(f"{iso}:{item['id']}")
            continue
        kept.append(item)
    return kept
