"""Route PE/CR metrics from issuer metadata, never from account labels."""
import re

from .industry_note_mapping import reviewed_issuer_industry


_KSIC = re.compile(r"([A-Z]?)([0-9]{2,5})\Z")
_ALIASES = {"general_machinery": "machinery", "retail": "retail_wholesale", "it": "it_services",
            "software": "it_services", "platform": "retail_platform", "it_platform": "retail_platform",
            "manufacturing_other": "manufacturing", "electronics_components": "it_hardware",
            "computers": "it_hardware", "telecom_devices": "it_hardware", "display": "it_hardware"}


def dart_ksic(canonical, corp):
    if canonical.get("source") != "DART":
        return None
    for field in ("induty_code", "ksic", "industry"):
        value = str(corp.get(field) or "").strip().upper()
        if value:
            return value if _KSIC.fullmatch(value) else None
    return None


def resolve_industry(kits, *, canonical, corp=None, requested=None):
    corp = corp or {}
    code = dart_ksic(canonical, corp)
    if code:
        section, number = _KSIC.fullmatch(code).groups()
        matches = [(len(prefix), key) for key, kit in kits.items()
                   for prefix in kit.get("ksic_prefixes", [])
                   if (not section or section == prefix[0]) and number.startswith(prefix[1:])]
        if matches:
            mapped = max(matches)[1]
        elif section in {"", "C"} and 10 <= int(number[:2]) <= 34:
            mapped = "manufacturing"
        else:
            mapped = "general"
        if mapped == "financial":
            return mapped, "dart_ksic", code
    if requested is not None:
        selected = _ALIASES.get(requested, requested)
        if selected not in kits:
            raise ValueError("unsupported_pe_cr_industry:" + str(requested))
        return selected, "explicit", code
    if code:
        return mapped, "dart_ksic", code
    issuer_kit = reviewed_issuer_industry(canonical)
    if issuer_kit in kits:
        return issuer_kit, "reviewed_issuer_industry", None
    metadata_kit = corp.get("industry_kit")
    metadata_kit = _ALIASES.get(metadata_kit, metadata_kit)
    if metadata_kit in kits:
        return metadata_kit, "issuer_metadata", None
    if any(corp.get(field) for field in ("induty_code", "ksic", "industry", "industry_kit", "sic")):
        return "general", "unmapped_metadata", None
    # Maintain the existing default for old offline callers without metadata;
    # label the fallback so it is not mistaken for a classified company.
    return "manufacturing", "legacy_default", None
