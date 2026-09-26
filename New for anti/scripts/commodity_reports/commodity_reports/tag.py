"""Decide which (commodity, country) window a report belongs on.

The rule the dashboard needs is not "who published it" but "what is it
about": a USDA release on Brazilian wheat belongs on Brazil·밀, not on
USA·밀. So the text decides the country, and the publisher's own country is
only a fallback for releases that name no country at all (CONAB's
"Acompanhamento da safra" never says "Brazil" -- it does not have to).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Words that make a bare metal or crop noun a market statement rather than a
# figure of speech ("lead the talks", "golden opportunity", "corn maze").
CONTEXT_TERMS = [
    "production", "producer", "output", "harvest", "crop", "yield", "acreage",
    "planting", "planted", "sown", "supply", "demand", "stocks", "inventory",
    "inventories", "export", "exports", "import", "imports", "shipment",
    "shipments", "price", "prices", "market", "tonne", "tonnes", "ton", "tons",
    "bushel", "bushels", "barrel", "barrels", "metric", "mine", "mining",
    "smelter", "refinery", "refined", "concentrate", "reserves", "forecast",
    "estimate", "estimates", "outlook", "balance sheet", "consumption",
    "생산", "수확", "수출", "수입", "재고", "가격", "전망", "출하",
    "produção", "producao", "safra", "colheita", "exportação", "exportacao",
    "estimada", "estimativa", "produccion", "producción",
    "cosecha", "exportaciones", "exportación", "precio", "precios", "preço", "mercado",
    "добыч", "урожа", "экспорт",
    # Producer-country languages of the rubber and palm-oil windows, whose
    # boards publish in them (ANRPC members, MPOB, GAPKI, RAOT, VRA).
    "ekspor", "impor", "eksport", "produksi", "pengeluaran", "harga", "stok",
    "ส่งออก", "ราคา", "ผลผลิต", "xuất khẩu", "sản lượng", "giá cả",
    "出口", "进口", "产量", "价格", "库存",
]


def compile_terms(terms: Sequence[str]) -> List[re.Pattern[str]]:
    r"""Word-boundary match for ASCII terms, substring for everything else.

    CJK and Korean have no spaces to anchor on, so `\b` never fires there;
    Latin terms need it or "tin" matches "tinned" and "corn" matches
    "Cornwall".
    """
    out: List[re.Pattern[str]] = []
    for term in terms:
        term = term.strip()
        if not term:
            continue
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .'\-/]*", term):
            out.append(re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.I))
        else:
            # IGNORECASE matters beyond Latin script: "Việt Nam", "Thái Lan"
            # and "Нефть" are capitalized in headlines, the aliases are not.
            # CJK and Hangul have no case, so it changes nothing there.
            out.append(re.compile(re.escape(term), re.I))
    return out


def _compile_cased(terms: Sequence[str]) -> List[re.Pattern[str]]:
    """Case-sensitive aliases -- `US` is a country, `us` is a pronoun."""
    return [
        re.compile(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])")
        for t in terms
        if t.strip()
    ]


@dataclass
class CommodityTagger:
    """Dashboard commodity keys (`soybeans`, `iron_ore`…) found in free text."""

    patterns: Dict[str, List[re.Pattern[str]]]
    requires_context: Dict[str, bool]
    labels_ko: Dict[str, str]
    context_pats: List[re.Pattern[str]]
    # Aliases that count only next to a market term, on a commodity whose
    # other aliases are unambiguous ("cao su" is always rubber, "rubber" is
    # also a stamp).
    context_patterns: Dict[str, List[re.Pattern[str]]] = field(default_factory=dict)
    # Phrases that contain an alias but name another market: "crude steel"
    # and "crude palm oil" are not crude oil.
    not_when: Dict[str, List[re.Pattern[str]]] = field(default_factory=dict)

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "CommodityTagger":
        pats, need, labels, ctx, excl = {}, {}, {}, {}, {}
        for key, meta in (cfg.get("commodities") or {}).items():
            pats[key] = compile_terms(meta.get("aliases") or [])
            need[key] = bool(meta.get("require_context"))
            labels[key] = meta.get("label_ko") or key
            ctx[key] = compile_terms(meta.get("context_aliases") or [])
            excl[key] = compile_terms(meta.get("not_when") or [])
        return cls(pats, need, labels, compile_terms(CONTEXT_TERMS), ctx, excl)

    def tag(self, text: str) -> List[str]:
        has_context = any(p.search(text) for p in self.context_pats)
        hits = []
        for key, pats in self.patterns.items():
            own = text
            for p in self.not_when.get(key, []):
                own = p.sub(" ", own)
            plain = any(p.search(own) for p in pats)
            if plain and self.requires_context[key] and not has_context:
                plain = False
            contextual = has_context and any(p.search(own) for p in self.context_patterns.get(key, []))
            if plain or contextual:
                hits.append(key)
        return hits


@dataclass
class CountryTagger:
    """ISO3 codes for the countries a report actually talks about."""

    # (iso3, compiled pattern, alias length) -- length breaks ties so that
    # "Papua New Guinea" wins over "Guinea" and "North Korea" over "Korea".
    entries: List[Tuple[str, re.Pattern[str], int]]
    names: Dict[str, str]
    names_ko: Dict[str, str]

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "CountryTagger":
        entries: List[Tuple[str, re.Pattern[str], int]] = []
        names, names_ko = {}, {}
        for iso, meta in (cfg.get("countries") or {}).items():
            names[iso] = meta.get("name") or iso
            names_ko[iso] = meta.get("name_ko") or meta.get("name") or iso
            aliases = list(meta.get("aliases") or []) + list(meta.get("regions") or [])
            for pat, alias in zip(compile_terms(aliases), aliases):
                entries.append((iso, pat, len(alias)))
            cased = list(meta.get("cased_aliases") or [])
            for pat, alias in zip(_compile_cased(cased), cased):
                entries.append((iso, pat, len(alias)))
        # Longest alias first, so the winner claims the span before a shorter
        # alias of a different country can.
        entries.sort(key=lambda e: -e[2])
        return cls(entries, names, names_ko)

    def tag(self, text: str) -> List[str]:
        claimed: List[Tuple[int, int]] = []
        found: List[str] = []

        def overlaps(a: int, b: int) -> bool:
            return any(a < end and start < b for start, end in claimed)

        for iso, pat, _ in self.entries:
            for m in pat.finditer(text):
                if overlaps(m.start(), m.end()):
                    continue
                claimed.append((m.start(), m.end()))
                if iso not in found:
                    found.append(iso)
        return found


@dataclass
class Tagged:
    commodities: List[str]
    countries: List[str]
    scope: str  # "country" when a country is named, else "global"
    country_source: str  # "text" | "source_default" | "none"


# Unit names and set phrases that embed a country adjective but never mean
# the country. Found via a real miscount: an EIA gas report quoting a price
# in "million British thermal units (MMBtu)" landed on the UK's window over
# a purely domestic US release. Extend this list as more turn up rather than
# trying to enumerate every possible collocation up front.
_FALSE_COUNTRY_COLLOCATIONS = [
    re.compile(r"british\s+thermal\s+units?", re.I),
]


def _strip_false_country_collocations(text: str) -> str:
    for pat in _FALSE_COUNTRY_COLLOCATIONS:
        text = pat.sub("", text)
    return text


def tag_report(
    *,
    title: str,
    summary: str,
    commodity_tagger: CommodityTagger,
    country_tagger: CountryTagger,
    commodity_hint: Iterable[str] = (),
    default_country: Optional[str] = None,
    max_countries: int = 3,
    max_commodities: int = 3,
) -> Tagged:
    """Tag one report.

    The title carries the claim; the summary only corroborates it. Both are
    read for commodities (a WASDE headline names none of the crops it
    revises), but a country found only in the body is kept behind the ones in
    the headline -- "Argentina's drought lifts US soybean exports" is a US
    report that mentions Argentina, and the ordering is what says so.
    """
    title = title or ""
    summary = summary or ""
    both = f"{title}\n{summary}"

    commodities = commodity_tagger.tag(both)
    if not commodities:
        commodities = [c for c in commodity_hint if c in commodity_tagger.patterns]

    in_title = country_tagger.tag(_strip_false_country_collocations(title))
    in_body = [c for c in country_tagger.tag(_strip_false_country_collocations(summary)) if c not in in_title]
    countries = (in_title + in_body)[:max_countries]

    if countries:
        scope, origin = "country", "text"
    elif default_country:
        countries, scope, origin = [default_country], "country", "source_default"
    else:
        scope, origin = "global", "none"

    return Tagged(
        commodities=commodities[:max_commodities],
        countries=countries,
        scope=scope,
        country_source=origin,
    )
