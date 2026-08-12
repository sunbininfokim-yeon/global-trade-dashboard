"""Country-tier × info-grade importance model for ticker curation."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _compile(terms: Sequence[str]) -> List[re.Pattern[str]]:
    pats: List[re.Pattern[str]] = []
    for t in terms:
        t = (t or "").strip()
        if not t:
            continue
        if re.fullmatch(r"[A-Za-z0-9+.\- /]+", t):
            pats.append(re.compile(rf"(?i)(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])"))
        else:
            pats.append(re.compile(re.escape(t), re.IGNORECASE))
    return pats


def _hits(text: str, pats: Sequence[re.Pattern[str]], cap: float = 3.0) -> float:
    s = 0.0
    for p in pats:
        if p.search(text):
            s += 1.0
            if s >= cap:
                break
    return s


class ImportanceModel:
    def __init__(self, cfg: Dict[str, Any], label_history: Optional[Path] = None) -> None:
        self.cfg = cfg
        self.tiers = cfg.get("country_tiers", {})
        self.grades = cfg.get("info_grades", {})
        self.min_importance = float(cfg.get("min_importance", 0.35))
        self.ticker_cap = int(cfg.get("ticker_cap", 24))
        self.region_hint = cfg.get("region_to_country_hint", {})
        self.grade_keyword_pats = {
            g: _compile(meta.get("keywords") or []) for g, meta in self.grades.items()
        }
        self.country_name_map = [
            (re.compile(r"(?i)\b(united states|u\.s\.|america|washington)\b"), "USA"),
            (re.compile(r"(?i)\b(china|beijing|prc)\b|中国|中國"), "CHN"),
            (re.compile(r"(?i)\b(japan|tokyo)\b|日本"), "JPN"),
            (re.compile(r"(?i)\b(south korea|seoul)\b|한국|韓國"), "KOR"),
            (re.compile(r"(?i)\b(india|new delhi)\b|인도"), "IND"),
            (re.compile(r"(?i)\b(russia|moscow)\b|러시아"), "RUS"),
            (re.compile(r"(?i)\b(taiwan|taipei)\b|대만|台灣"), "TWN"),
            (re.compile(r"(?i)\b(turkey|türkiye|ankara)\b|튀르키예"), "TUR"),
            (re.compile(r"(?i)\b(germany|berlin)\b|독일"), "DEU"),
            (re.compile(r"(?i)\b(united kingdom|britain|london)\b|영국"), "GBR"),
            (re.compile(r"(?i)\b(france|paris)\b|프랑스"), "FRA"),
            (re.compile(r"(?i)\b(brazil|brasília|brasilia)\b|브라질"), "BRA"),
        ]
        self.learned: Dict[str, float] = {}
        if label_history and label_history.exists():
            self.learned = self._load_labels(label_history)

    @staticmethod
    def _load_labels(path: Path) -> Dict[str, float]:
        acc: Dict[str, List[float]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = row.get("key") or ""
            lab = (row.get("label") or "").lower()
            m = {"promote": 1.25, "keep": 1.0, "demote": 0.7, "drop": 0.35}.get(lab)
            if key and m is not None:
                acc.setdefault(key, []).append(m)
        return {k: sum(v) / len(v) for k, v in acc.items()}

    def resolve_country(self, *, region: str, text: str) -> Tuple[str, str]:
        """Return (iso_or_region, tier A|B|C)."""
        for pat, iso in self.country_name_map:
            if pat.search(text):
                return iso, self._tier_for_country(iso)
        hint = self.region_hint.get(region)
        if hint:
            return hint, self._tier_for_country(hint)
        for tier, meta in self.tiers.items():
            if region in (meta.get("regions") or []):
                return (region.upper()[:3] if len(region) >= 3 else region), tier
        return "UNK", "C"

    def _tier_for_country(self, country: str) -> str:
        c = (country or "").upper()
        for tier, meta in self.tiers.items():
            if c in [x.upper() for x in (meta.get("countries") or [])]:
                return tier
        return "C"

    def resolve_grade(
        self,
        *,
        text: str,
        category: str,
        election_type: Optional[str],
        event_type: Optional[str] = None,
    ) -> str:
        if _hits(text, self.grade_keyword_pats.get("1", []), cap=1) >= 1:
            return "1"
        g1 = self.grades.get("1", {})
        if event_type and event_type in (g1.get("match_event_types") or []):
            return "1"
        if election_type and election_type in (g1.get("match_election_types") or []):
            return "1"
        if category in (g1.get("match_categories") or []):
            return "1"

        g2 = self.grades.get("2", {})
        if event_type and event_type in (g2.get("match_event_types") or []):
            return "2"
        if election_type and election_type in (g2.get("match_election_types") or []):
            return "2"
        if category in (g2.get("match_categories") or []):
            return "2"

        g3 = self.grades.get("3", {})
        if election_type and election_type in (g3.get("match_election_types") or []):
            return "3"
        if category in (g3.get("match_categories") or []):
            return "3"
        return "3"

    def apply(
        self,
        *,
        base: float,
        region: str,
        text: str,
        category: str,
        election_type: Optional[str] = None,
        event_type: Optional[str] = None,
        freshness: float = 1.0,
    ) -> Dict[str, Any]:
        country, tier = self.resolve_country(region=region, text=text)
        grade = self.resolve_grade(
            text=text,
            category=category,
            election_type=election_type,
            event_type=event_type,
        )
        tw = float(self.tiers.get(tier, {}).get("weight", 0.42))
        gw = float(self.grades.get(grade, {}).get("weight", 0.48))
        learned = self.learned.get(f"{country}:{category}", 1.0) * self.learned.get(
            f"grade:{grade}", 1.0
        ) * self.learned.get(f"tier:{tier}", 1.0)
        importance = base * tw * gw * freshness * learned
        return {
            "country": country,
            "country_tier": tier,
            "info_grade": grade,
            "tier_weight": tw,
            "grade_weight": gw,
            "learned_mult": learned,
            "importance": importance,
        }


def append_importance_label(
    path: Path,
    *,
    key: str,
    label: str,
    note: str = "",
) -> None:
    """Append a promote|keep|demote|drop label for online tuning."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "key": key,
        "label": label,
        "note": note,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
