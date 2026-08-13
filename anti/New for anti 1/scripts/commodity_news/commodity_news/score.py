"""Admission + ranking model for commodity / diplomacy / election news."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .lang import detect_lang, normalize_lang_tag
from .rss import RawItem


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _compile_terms(terms: Sequence[str]) -> List[re.Pattern[str]]:
    pats: List[re.Pattern[str]] = []
    for t in terms:
        t = t.strip()
        if not t:
            continue
        # Word boundary only for pure latin terms; CJK/Arabic use substring match.
        if re.fullmatch(r"[A-Za-z0-9+.\- ]+", t):
            pats.append(re.compile(rf"(?i)(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])"))
        else:
            pats.append(re.compile(re.escape(t), re.IGNORECASE))
    return pats


def _count_hits(text: str, patterns: Sequence[re.Pattern[str]], cap: float = 4.0) -> float:
    score = 0.0
    for p in patterns:
        if p.search(text):
            score += 1.0
            if score >= cap:
                break
    return score


@dataclass
class ScoredItem:
    id: str
    title_original: str
    title_ko: Optional[str]
    original_lang: str
    summary: str
    url: str
    published_at: Optional[str]
    source_id: str
    source_name: str
    region: str
    slant: Optional[str]
    commodities: List[str]
    category: str  # commodity | diplomacy | commodity_diplomacy | election | cabinet_reshuffle
    commodity_score: float
    diplomacy_score: float
    region_weight: float
    freshness: float
    final_score: float
    rank_reasons: List[str] = field(default_factory=list)
    translation_status: str = "pending"  # ok | pending | skipped | failed
    election_type: Optional[str] = None
    election_score: float = 0.0
    country_tier: Optional[str] = None
    info_grade: Optional[str] = None
    importance: float = 0.0
    country_hint: Optional[str] = None

    def to_public(self) -> Dict[str, Any]:
        out = {
            "id": self.id,
            "published_at": self.published_at,
            "source": {
                "id": self.source_id,
                "name": self.source_name,
                "region": self.region,
                "slant": self.slant,
            },
            "url": self.url,
            "category": self.category,
            "commodities": self.commodities,
            "title": {
                "original": self.title_original,
                "original_lang": self.original_lang,
                "ko": self.title_ko,
            },
            "summary": self.summary[:280],
            "scores": {
                "commodity": round(self.commodity_score, 3),
                "diplomacy": round(self.diplomacy_score, 3),
                "election": round(self.election_score, 3),
                "region_weight": round(self.region_weight, 3),
                "freshness": round(self.freshness, 3),
                "importance": round(self.importance, 3),
                "final": round(self.final_score, 3),
            },
            "rank_reasons": self.rank_reasons,
            "translation_status": self.translation_status,
            "country_tier": self.country_tier,
            "info_grade": self.info_grade,
            "country_hint": self.country_hint,
        }
        if self.election_type:
            out["election_type"] = self.election_type
        return out


class NewsScorer:
    def __init__(
        self,
        commodities_cfg: Dict[str, Any],
        diplomacy_cfg: Dict[str, Any],
        regions_cfg: Dict[str, Any],
        elections_cfg: Optional[Dict[str, Any]] = None,
        politics_extra: Optional[Dict[str, Any]] = None,
        importance_model: Any = None,
    ) -> None:
        self.min_commodity = float(commodities_cfg.get("min_commodity_score", 1.0))
        self.min_diplomacy = float(diplomacy_cfg.get("min_diplomacy_score", 1.0))
        self.bridge_min = float(diplomacy_cfg.get("diplomacy_bridge_min", 1.0))
        self.min_election = float(diplomacy_cfg.get("min_election_score", 1.0))
        self.importance_model = importance_model

        self.commodity_pats: Dict[str, List[re.Pattern[str]]] = {}
        self.commodity_labels: Dict[str, str] = {}
        self.needs_market_context: set[str] = set()
        for cid, meta in commodities_cfg.get("commodities", {}).items():
            self.commodity_pats[cid] = _compile_terms(meta.get("aliases", []))
            self.commodity_labels[cid] = meta.get("label_ko", cid)
            if meta.get("needs_market_context"):
                self.needs_market_context.add(cid)

        self.diplomacy_pats = _compile_terms(diplomacy_cfg.get("diplomacy_terms", []))
        self.bridge_pats = _compile_terms(diplomacy_cfg.get("trade_statecraft_terms", []))
        self.reject_pats = _compile_terms(diplomacy_cfg.get("hard_reject_terms", []))
        self.domestic_noise_pats = _compile_terms(
            diplomacy_cfg.get("domestic_politics_noise_terms", [])
            or diplomacy_cfg.get("domestic_politics_terms", [])
        )
        self.market_ctx_pats = _compile_terms(diplomacy_cfg.get("market_context_terms", []))

        elections_cfg = elections_cfg or {}
        self.election_pats = _compile_terms(elections_cfg.get("admission_terms", []))
        # Type classifiers (ordered specific → broad)
        self.election_type_pats: List[Tuple[str, List[re.Pattern[str]]]] = [
            (
                "by_election",
                _compile_terms(
                    [
                        "by-election",
                        "byelection",
                        "by election",
                        "special election",
                        "재보궐",
                        "보궐선거",
                        "재선거",
                        "补选",
                        "補欠選挙",
                        "ara seçim",
                        "انتخابات فرعية",
                    ]
                ),
            ),
            (
                "party_leadership",
                _compile_terms(
                    [
                        "party leadership",
                        "leadership contest",
                        "leadership race",
                        "party leader election",
                        "party chair",
                        "party chairman",
                        "selects new leader",
                        "ruling party leader",
                        "opposition leader race",
                        "당대표",
                        "당대표 선거",
                        "당대표 경선",
                        "전당대회",
                        "당수",
                        "당수 선거",
                        "여당 대표",
                        "야당 대표",
                        "总裁",
                        "党魁",
                        "党主席选举",
                        "党首選",
                        "лидер партии",
                        "genel başkan",
                    ]
                ),
            ),
            (
                "presidential",
                _compile_terms(
                    [
                        "presidential election",
                        "presidential race",
                        "대통령 선거",
                        "대선",
                        "总统选举",
                        "大統領選",
                        "総統選",
                        "cumhurbaşkanlığı seçimi",
                        "انتخابات رئاسية",
                        "президентск",
                    ]
                ),
            ),
            (
                "local",
                _compile_terms(
                    [
                        "local election",
                        "municipal election",
                        "gubernatorial election",
                        "state election",
                        "provincial election",
                        "지방선거",
                        "지선",
                        "광역단체장",
                        "基础选举",
                        "地方选举",
                        "地方選",
                        "yerel seçim",
                        "انتخابات محلية",
                        "местн",
                    ]
                ),
            ),
            (
                "general",
                _compile_terms(
                    [
                        "general election",
                        "parliamentary election",
                        "legislative election",
                        "midterm election",
                        "총선",
                        "총선거",
                        "국회의원 선거",
                        "议会选举",
                        "総選挙",
                        "衆院選",
                        "参院選",
                        "genel seçim",
                        "انتخابات برلمانية",
                        "парламентск",
                    ]
                ),
            ),
        ]

        pe = politics_extra or {}
        polls = pe.get("polls") or {}
        self.poll_reject_pats = _compile_terms(polls.get("reject_horserace_terms") or [])
        self.poll_governance_pats = _compile_terms(polls.get("admit_governance_terms") or [])
        cabinet = pe.get("cabinet_reshuffle") or {}
        self.cabinet_pats = _compile_terms(cabinet.get("terms") or [])
        self.cabinet_admit = bool(cabinet.get("admit", True))

        self.region_weights: Dict[str, float] = {
            k: float(v) for k, v in regions_cfg.get("region_weights", {}).items()
        }
        self.taiwan_balance = regions_cfg.get("taiwan_balance", {})

    def _classify_election(self, text: str) -> Tuple[float, Optional[str]]:
        # Governance / job-approval polls (not horserace) count as elections-adjacent.
        if _count_hits(text, self.poll_governance_pats, cap=1) >= 1:
            return 1.5, "governance_poll"
        if not self.election_pats:
            return 0.0, None
        score = _count_hits(text, self.election_pats, cap=4.0)
        if score < self.min_election:
            return score, None
        for etype, pats in self.election_type_pats:
            if _count_hits(text, pats, cap=1.0) >= 1:
                return score, etype
        return score, "general"

    def score(self, raw: RawItem) -> Optional[ScoredItem]:
        text = f"{raw.title}\n{raw.summary}".strip()

        if _count_hits(text, self.reject_pats, cap=1) >= 1:
            return None

        # Drop horse-race national presidential preference polls; keep governance approval.
        if _count_hits(text, self.poll_reject_pats, cap=1) >= 1:
            if _count_hits(text, self.poll_governance_pats, cap=1) < 1:
                return None

        market_ctx = _count_hits(text, self.market_ctx_pats, cap=3.0)
        bridge_score = _count_hits(text, self.bridge_pats, cap=3.0)
        diplomacy_score = _count_hits(text, self.diplomacy_pats, cap=4.0)
        election_score, election_type = self._classify_election(text)
        domestic_noise = _count_hits(text, self.domestic_noise_pats, cap=3.0)
        cabinet_hit = self.cabinet_admit and _count_hits(text, self.cabinet_pats, cap=2) >= 1

        commodity_hits: List[Tuple[str, float]] = []
        for cid, pats in self.commodity_pats.items():
            hit = _count_hits(text, pats, cap=3.0)
            if hit <= 0:
                continue
            if cid in self.needs_market_context and market_ctx < 1.0 and bridge_score < 1.0:
                continue
            commodity_hits.append((cid, hit))

        if not commodity_hits and raw.commodities_focus:
            if bridge_score >= 1.0 or market_ctx >= 1.0:
                commodity_hits = [(raw.commodities_focus[0], 0.8)]

        commodity_score = sum(h for _, h in commodity_hits)

        # Drop domestic political noise without election / diplomacy / commodity / cabinet.
        if (
            domestic_noise >= 1.0
            and election_score < self.min_election
            and diplomacy_score < self.min_diplomacy
            and commodity_score < self.min_commodity
            and not cabinet_hit
        ):
            return None

        admit_commodity = commodity_score >= self.min_commodity
        admit_diplomacy = (
            diplomacy_score >= self.min_diplomacy and bridge_score >= self.bridge_min
        )
        admit_election = election_score >= self.min_election and election_type is not None
        admit_cabinet = cabinet_hit

        if not admit_commodity and not admit_diplomacy and not admit_election and not admit_cabinet:
            return None

        if admit_cabinet and not admit_commodity and not admit_diplomacy:
            category = "cabinet_reshuffle"
            if not election_type or election_type not in {
                "presidential",
                "general",
                "governance_poll",
            }:
                election_type = "cabinet_reshuffle"
                election_score = max(election_score, 1.2)
        elif admit_election and not admit_commodity and not admit_diplomacy:
            category = "election"
        elif admit_commodity and admit_diplomacy:
            category = "commodity_diplomacy"
        elif admit_diplomacy:
            category = "diplomacy"
        elif admit_commodity:
            category = "commodity"
        else:
            category = "election"

        region_w = float(self.region_weights.get(raw.region, 1.0))
        freshness = self._freshness(raw.published_at)

        base = (
            commodity_score * 1.15
            + diplomacy_score * 0.9
            + bridge_score * 0.35
            + election_score * 1.05
            + (1.4 if admit_cabinet else 0.0)
        )
        if category == "commodity_diplomacy":
            base *= 1.15
        if category in {"election", "cabinet_reshuffle"}:
            base *= 1.05

        # Country-tier × info-grade importance is the primary geo prior.
        imp: Dict[str, Any] = {
            "country": None,
            "country_tier": None,
            "info_grade": None,
            "tier_weight": 1.0,
            "grade_weight": 1.0,
            "importance": base * region_w * freshness,
        }
        if self.importance_model is not None:
            imp = self.importance_model.apply(
                base=base,
                region=raw.region,
                text=text,
                category=category,
                election_type=election_type,
                event_type="cabinet_reshuffle" if category == "cabinet_reshuffle" else None,
                freshness=freshness,
            )
            final_score = float(imp["importance"]) * (0.55 + 0.45 * region_w)
        else:
            final_score = float(imp["importance"])

        reasons = [
            f"region:{raw.region}*{region_w:.2f}",
            f"category:{category}",
        ]
        if imp.get("country_tier"):
            reasons.append(
                f"tier:{imp['country_tier']}*{float(imp.get('tier_weight') or 1):.2f}/g{imp.get('info_grade')}"
            )
        for cid, h in commodity_hits[:4]:
            reasons.append(f"commodity:{cid}:{h:g}")
        if diplomacy_score:
            reasons.append(f"diplomacy:{diplomacy_score:g}")
        if bridge_score:
            reasons.append(f"bridge:{bridge_score:g}")
        if election_type:
            reasons.append(f"election:{election_type}:{election_score:g}")
        if admit_cabinet:
            reasons.append("cabinet_reshuffle")

        lang = normalize_lang_tag(raw.source_lang) or detect_lang(raw.title, "en")
        return ScoredItem(
            id=raw.raw_xml_hash or hashlib_fallback(raw),
            title_original=raw.title,
            title_ko=None,
            original_lang=lang,
            summary=raw.summary,
            url=raw.url,
            published_at=raw.published_at,
            source_id=raw.source_id,
            source_name=raw.source_name,
            region=raw.region,
            slant=raw.slant,
            commodities=[c for c, _ in sorted(commodity_hits, key=lambda x: -x[1])],
            category=category,
            commodity_score=commodity_score,
            diplomacy_score=diplomacy_score,
            region_weight=region_w,
            freshness=freshness,
            final_score=final_score,
            rank_reasons=reasons,
            election_type=election_type if (admit_election or admit_cabinet) else None,
            election_score=election_score,
            country_tier=imp.get("country_tier"),
            info_grade=str(imp["info_grade"]) if imp.get("info_grade") is not None else None,
            importance=float(imp.get("importance") or final_score),
            country_hint=imp.get("country"),
        )

    def _freshness(self, published_at: Optional[str]) -> float:
        dt = _parse_iso(published_at)
        if not dt:
            return 0.85
        age_h = max(0.0, (_now() - dt).total_seconds() / 3600.0)
        # Half-life ~36h
        return max(0.35, math.exp(-age_h / 36.0))


def hashlib_fallback(raw: RawItem) -> str:
    import hashlib

    return hashlib.sha1(f"{raw.source_id}|{raw.url}|{raw.title}".encode()).hexdigest()[:16]


def dedupe(items: Sequence[ScoredItem]) -> List[ScoredItem]:
    seen_url = set()
    seen_title = set()
    out: List[ScoredItem] = []
    for it in sorted(items, key=lambda x: x.final_score, reverse=True):
        u = it.url.split("?", 1)[0].rstrip("/").lower()
        t = re.sub(r"\s+", " ", it.title_original.lower())[:120]
        if u in seen_url or t in seen_title:
            continue
        seen_url.add(u)
        seen_title.add(t)
        out.append(it)
    return out


def filter_by_importance(
    items: Sequence[ScoredItem], *, min_importance: float
) -> List[ScoredItem]:
    if min_importance <= 0:
        return list(items)
    return [it for it in items if it.importance >= min_importance or it.final_score >= min_importance]


def apply_regional_and_taiwan_balance(
    items: Sequence[ScoredItem],
    *,
    limit: int,
    regions_cfg: Dict[str, Any],
) -> List[ScoredItem]:
    """Prefer high final_score but enforce soft region floors + Taiwan slant caps."""
    ranked = sorted(items, key=lambda x: x.final_score, reverse=True)
    if limit <= 0:
        return []

    quotas = regions_cfg.get("region_quota_share", {})
    min_slots: Dict[str, int] = {}
    for region, share in quotas.items():
        min_slots[region] = max(1, int(math.floor(limit * float(share)))) if float(share) > 0 else 0

    tw = regions_cfg.get("taiwan_balance", {})
    max_per_slant = int(tw.get("max_per_slant", 2))
    slant_map = tw.get("slants", {})

    selected: List[ScoredItem] = []
    selected_ids = set()
    region_counts: Dict[str, int] = {}
    slant_counts: Dict[str, int] = {}

    def try_add(it: ScoredItem) -> bool:
        if it.id in selected_ids:
            return False
        if it.region == "taiwan":
            slant = it.slant or slant_map.get(it.source_id, "center")
            if slant_counts.get(slant, 0) >= max_per_slant:
                return False
            slant_counts[slant] = slant_counts.get(slant, 0) + 1
        selected.append(it)
        selected_ids.add(it.id)
        region_counts[it.region] = region_counts.get(it.region, 0) + 1
        return True

    # Pass 1: fill soft regional floors from top of each region bucket
    by_region: Dict[str, List[ScoredItem]] = {}
    for it in ranked:
        by_region.setdefault(it.region, []).append(it)

    for region, need in min_slots.items():
        for it in by_region.get(region, []):
            if region_counts.get(region, 0) >= need:
                break
            if len(selected) >= limit:
                break
            try_add(it)

    # Pass 2: best remaining until limit
    for it in ranked:
        if len(selected) >= limit:
            break
        try_add(it)

    selected.sort(key=lambda x: x.final_score, reverse=True)
    return selected[:limit]
