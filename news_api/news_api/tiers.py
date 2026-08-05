"""news_api scoring helpers: geo 1-4, info 1-4, hub boost, pair rank, legacy A/B/C map."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def load_json(name: str) -> Dict[str, Any]:
    path = CONFIG_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# Old commodity_news importance.json used A/B/C. New system uses 1-4.
LEGACY_GEO_LETTER_TO_INT = {
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
}


def legacy_geo_letter_to_int(letter: Union[str, int, None]) -> int:
    """A→1, B→2, C→3, D/unknown→4. Accepts already-numeric grades too."""
    if letter is None:
        return 4
    if isinstance(letter, int):
        return min(4, max(1, letter))
    return LEGACY_GEO_LETTER_TO_INT.get(str(letter).strip().upper(), 4)


def legacy_info_to_int(grade: Union[str, int, None]) -> int:
    """Old info was 1–3; clamp to 1–4 (missing → 4)."""
    if grade is None:
        return 4
    try:
        g = int(grade)
    except (TypeError, ValueError):
        return 4
    return min(4, max(1, g))


def legacy_abc_region_bucket(region: str) -> int:
    """Fallback when no ISO: old region bucket → approximate geo 1–4."""
    r = (region or "").lower()
    if r in {"china", "japan", "russia"}:
        return 1
    if r in {"korea", "india", "turkey", "mena", "taiwan", "west"}:
        # west is mixed (USA=1 vs EU wires); bias to 2 without ISO
        return 2 if r != "west" else 2
    if r in {"latam", "sea", "asean", "eu_core", "eu_other", "oceania", "cis"}:
        return 3
    if r in {"africa", "ssa", "global_wire", "global_specialist"}:
        return 4
    return 4


@dataclass
class TierResult:
    geo_base: int
    geo_effective: int
    info: int
    pair_rank: int
    iso3: Optional[str]
    hub_boost_ids: List[str]
    elevated: bool
    notes: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "geo_base": self.geo_base,
            "geo_effective": self.geo_effective,
            "info": self.info,
            "pair_rank": self.pair_rank,
            "iso3": self.iso3,
            "hub_boost_ids": self.hub_boost_ids,
            "elevated": self.elevated,
            "notes": self.notes,
        }


class NewsTier:
    """Loads news_api/config and resolves geo / info / pair_rank."""

    def __init__(
        self,
        country_cfg: Optional[Dict[str, Any]] = None,
        info_cfg: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.country = country_cfg or load_json("country_tiers_v1.json")
        self.info_cfg = info_cfg or load_json("info_value_v1.json")
        self._iso_to_geo = self._build_iso_map()
        self._pair_rank = {
            k: int(v)
            for k, v in (self.info_cfg.get("pair_priority") or {}).get("rank", {}).items()
        }
        self._hub_rules = (self.country.get("hub_boost") or {}).get("rules") or []
        self._escape = (self.country.get("critical_escape") or {}).get("triggers") or []
        # Best geo number hub may grant (1=best; cap 2 ⇒ hub cannot make a country "tier 1")
        self._hub_best = int((self.country.get("hub_boost") or {}).get("effective_geo_cap", 2))
        self._max_boost = int((self.country.get("hub_boost") or {}).get("max_boost", 1))

        self._country_name_pats: List[Tuple[re.Pattern[str], str]] = [
            (re.compile(r"(?i)\b(united states|u\.s\.a\.?|u\.s\.|america|washington)\b"), "USA"),
            (re.compile(r"(?i)\b(china|beijing|prc)\b|中国|中國"), "CHN"),
            (re.compile(r"(?i)\b(japan|tokyo)\b|日本"), "JPN"),
            (re.compile(r"(?i)\b(russia|moscow)\b|러시아|росс"), "RUS"),
            (re.compile(r"(?i)\b(south korea|seoul)\b|한국"), "KOR"),
            (re.compile(r"(?i)\b(india|new delhi)\b|인도"), "IND"),
            (re.compile(r"(?i)\b(brazil|brasília|brasilia)\b|브라질"), "BRA"),
            (re.compile(r"(?i)\b(ukraine|kyiv|kiev)\b|우크라이나"), "UKR"),
            (re.compile(r"(?i)\b(netherlands|amsterdam|rotterdam|dutch)\b|네덜란드|암스테르담|로테르담"), "NLD"),
            (re.compile(r"(?i)\b(switzerland|swiss|zurich|geneva)\b|스위스"), "CHE"),
            (re.compile(r"(?i)\b(singapore)\b|싱가포르"), "SGP"),
            (re.compile(r"(?i)\b(argentina|buenos aires)\b|아르헨"), "ARG"),
            (re.compile(r"(?i)\b(nigeria|lagos|abuja)\b"), "NGA"),
            (re.compile(r"(?i)\b(south africa|johannesburg|pretoria)\b|남아공"), "ZAF"),
            (re.compile(r"(?i)\b(saudi|riyadh)\b|사우디"), "SAU"),
            (re.compile(r"(?i)\b(iran|tehran)\b|이란"), "IRN"),
            (re.compile(r"(?i)\b(israel|tel aviv|jerusalem)\b|이스라엘"), "ISR"),
            (re.compile(r"(?i)\b(turkey|türkiye|ankara)\b|튀르키예"), "TUR"),
            (re.compile(r"(?i)\b(germany|berlin)\b|독일"), "DEU"),
            (re.compile(r"(?i)\b(france|paris)\b|프랑스"), "FRA"),
            (re.compile(r"(?i)\b(united kingdom|britain|london)\b|영국"), "GBR"),
            (re.compile(r"(?i)\b(mexico|mexico city)\b|멕시코"), "MEX"),
        ]

    def _build_iso_map(self) -> Dict[str, int]:
        m: Dict[str, int] = {}
        for tier, key in [(1, "tier_1"), (2, "tier_2"), (3, "tier_3")]:
            for iso in (self.country.get(key) or {}).get("iso3") or []:
                m[str(iso).upper()] = tier
        return m

    def geo_for_iso(self, iso3: Optional[str]) -> int:
        if not iso3:
            return 4
        return self._iso_to_geo.get(iso3.upper(), 4)

    def infer_iso(self, text: str) -> Optional[str]:
        for pat, iso in self._country_name_pats:
            if pat.search(text or ""):
                return iso
        return None

    def apply_hub_boost(
        self, geo: int, iso3: Optional[str], text: str
    ) -> Tuple[int, List[str]]:
        """Smaller geo number = stronger. boost 1 on geo 3 → effective 2. Hub cannot grant better than hub_best (2)."""
        if not iso3 or geo <= 1:
            return geo, []
        hits: List[str] = []
        t = text or ""
        iso_u = iso3.upper()
        boost = 0
        for rule in self._hub_rules:
            allowed = [x.upper() for x in (rule.get("iso3") or [])]
            if iso_u not in allowed:
                continue
            delta = int(rule.get("boost_geo") or 0)
            if delta <= 0:
                continue
            kws = rule.get("keywords") or []
            if any(k and re.search(re.escape(k), t, re.I) for k in kws):
                hits.append(str(rule.get("id") or "hub"))
                boost = max(boost, min(delta, self._max_boost))
        if not boost:
            return geo, hits
        # Improve (lower) geo number, but not stronger than hub_best (e.g. 2).
        effective = max(self._hub_best, geo - boost)
        return effective, hits

    def critical_escape(
        self, text: str, iso3: Optional[str]
    ) -> Tuple[bool, int, int, str]:
        t = text or ""
        for tr in self._escape:
            terms = tr.get("terms") or []
            if not any(term and re.search(re.escape(term), t, re.I) for term in terms):
                continue
            return (
                True,
                int(tr.get("min_info_grade") or 1),
                int(tr.get("effective_geo_floor") or 2),
                str(tr.get("id") or "escape"),
            )
        return False, 0, 0, ""

    def pair_rank(self, geo: int, info: int) -> int:
        key = f"{int(geo)}_{int(info)}"
        if key in self._pair_rank:
            return self._pair_rank[key]
        gw = {1: 1.0, 2: 0.78, 3: 0.52, 4: 0.28}.get(int(geo), 0.28)
        iw = {1: 1.0, 2: 0.72, 3: 0.45, 4: 0.22}.get(int(info), 0.22)
        return int(round(100 * gw * iw))

    def resolve(
        self,
        *,
        text: str = "",
        iso3: Optional[str] = None,
        info_grade: Union[int, str] = 3,
        legacy_geo_letter: Optional[str] = None,
        region: Optional[str] = None,
    ) -> TierResult:
        notes: List[str] = []
        iso = (iso3 or self.infer_iso(text) or "").upper() or None

        if iso:
            geo_base = self.geo_for_iso(iso)
        elif legacy_geo_letter:
            geo_base = legacy_geo_letter_to_int(legacy_geo_letter)
            notes.append(f"legacy_letter:{legacy_geo_letter}")
        elif region:
            geo_base = legacy_abc_region_bucket(region)
            notes.append(f"legacy_region:{region}")
        else:
            geo_base = 4
            notes.append("default_geo4")

        geo_eff, hubs = self.apply_hub_boost(geo_base, iso, text)
        if hubs:
            notes.append(f"hub:{','.join(hubs)}")

        info = legacy_info_to_int(info_grade)
        elev = False
        hit, min_info, geo_floor, tid = self.critical_escape(text, iso)
        if hit:
            elev = True
            # Smaller info number = stronger; force at least as strong as min_info
            info = min(info, min_info)
            # Smaller geo = stronger; floor 2 means treat at least as geo 2
            geo_eff = min(geo_eff, geo_floor)
            notes.append(f"escape:{tid}")

        return TierResult(
            geo_base=geo_base,
            geo_effective=geo_eff,
            info=info,
            pair_rank=self.pair_rank(geo_eff, info),
            iso3=iso,
            hub_boost_ids=hubs,
            elevated=elev,
            notes=notes,
        )


def map_legacy_scored_fields(
    *,
    country_tier_letter: Optional[str] = None,
    info_grade_old: Optional[Union[int, str]] = None,
    region: Optional[str] = None,
    text: str = "",
    iso3: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Bridge: commodity_news style A/B/C + info 1–3
         → news_api geo 1–4, info 1–4, pair_rank.

    Example:
        map_legacy_scored_fields(country_tier_letter=\"B\", info_grade_old=2, text=title)
    """
    tiers = NewsTier()
    res = tiers.resolve(
        text=text,
        iso3=iso3,
        info_grade=info_grade_old if info_grade_old is not None else 3,
        legacy_geo_letter=country_tier_letter,
        region=region,
    )
    return {
        "legacy": {
            "country_tier_letter": country_tier_letter,
            "info_grade_old": info_grade_old,
            "region": region,
        },
        "letter_only_geo": legacy_geo_letter_to_int(country_tier_letter),
        "info_int": res.info,
        "geo_int": res.geo_effective,
        **res.as_dict(),
    }
