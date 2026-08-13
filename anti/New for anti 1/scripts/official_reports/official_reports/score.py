"""Significance scoring + series match + light learning weights."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .fetch import RawReport, report_id


def _compile_terms(terms: Sequence[str]) -> List[re.Pattern[str]]:
    pats = []
    for t in terms:
        t = t.strip()
        if not t:
            continue
        if re.fullmatch(r"[A-Za-z0-9+.\- /]+", t):
            pats.append(re.compile(rf"(?i)(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])"))
        else:
            pats.append(re.compile(re.escape(t), re.IGNORECASE))
    return pats


def _hits(text: str, pats: Sequence[re.Pattern[str]], cap: float = 4.0) -> float:
    s = 0.0
    for p in pats:
        if p.search(text):
            s += 1.0
            if s >= cap:
                break
    return s


@dataclass
class ScoredReport:
    id: str
    title: str
    url: str
    summary: str
    published_at: Optional[str]
    country: str
    agency: str
    source_id: str
    domains: List[str]
    series_id: Optional[str]
    series_label_ko: Optional[str]
    site_slot: Optional[str]
    significance: float
    rank_reasons: List[str] = field(default_factory=list)
    learning_label: Optional[str] = None  # from history if any
    extract: Optional[Dict[str, Any]] = None
    title_ko: Optional[str] = None

    def to_ticker_item(self) -> Dict[str, Any]:
        dom = self.domains[0] if self.domains else "economy"
        tag = {
            "economy": "경제",
            "finance": "금융",
            "diplomacy": "외교",
            "security": "안보",
            "agriculture": "농업",
        }.get(dom, "공식")
        country = self.country
        ko = self.title_ko or f"[{country}·{tag}] {self.title}"
        return {
            "id": self.id,
            "published_at": self.published_at,
            "source": {
                "id": self.source_id,
                "name": self.agency,
                "region": country.lower(),
                "slant": None,
            },
            "url": self.url,
            "category": "official_report",
            "commodities": [],
            "domains": self.domains,
            "series_id": self.series_id,
            "title": {
                "original": self.title,
                "original_lang": "en",
                "ko": ko,
            },
            "summary": (self.summary or "")[:280],
            "scores": {
                "significance": round(self.significance, 3),
                "final": round(self.significance, 3),
            },
            "rank_reasons": self.rank_reasons,
            "translation_status": "ok" if self.title_ko else "skipped",
            "event_type": "official_report",
            "site_slot": self.site_slot,
        }

    def to_indicator_row(self) -> Optional[Dict[str, Any]]:
        if not self.series_id:
            return None
        row = {
            "series_id": self.series_id,
            "label_ko": self.series_label_ko,
            "country": self.country,
            "domains": self.domains,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
            "site_slot": self.site_slot,
            "significance": round(self.significance, 3),
        }
        if self.extract:
            row["values"] = self.extract
        return row


class OfficialScorer:
    def __init__(
        self,
        domains_cfg: Dict[str, Any],
        series_cfg: Dict[str, Any],
        label_history_path: Optional[Path] = None,
    ) -> None:
        self.min_domain = float(domains_cfg.get("min_domain_score", 1.0))
        self.domain_pats: Dict[str, List[re.Pattern[str]]] = {}
        for did, meta in domains_cfg.get("domains", {}).items():
            self.domain_pats[did] = _compile_terms(meta.get("terms", []))
        self.boost_pats = _compile_terms(domains_cfg.get("significance_boost_terms", []))
        self.reject_pats = _compile_terms(domains_cfg.get("hard_reject_terms", []))

        self.series = series_cfg.get("series", [])
        self.learned: Dict[str, float] = {}  # series_id -> multiplier
        if label_history_path and label_history_path.exists():
            self.learned = _load_learned_multipliers(label_history_path)

    def score(self, raw: RawReport) -> Optional[ScoredReport]:
        text = f"{raw.title}\n{raw.summary}".strip()
        if _hits(text, self.reject_pats, cap=1) >= 1:
            return None

        # skip pure scheduling noise
        low_title = raw.title.lower()
        if "scheduled dates" in low_title or "holiday hours" in low_title:
            return None

        domain_hits: List[Tuple[str, float]] = []
        for did, pats in self.domain_pats.items():
            h = _hits(text, pats, cap=3.0)
            if h <= 0 and did in raw.domains_hint:
                h = 0.4  # soft prior from source catalog
            if h > 0:
                domain_hits.append((did, h))
        if not domain_hits and raw.domains_hint:
            domain_hits = [(raw.domains_hint[0], 0.5)]
        if not domain_hits:
            return None

        domain_score = sum(h for _, h in domain_hits)
        if domain_score < self.min_domain and not raw.domains_hint:
            return None

        boost = _hits(text, self.boost_pats, cap=3.0)
        series_id = series_label = site_slot = None
        series_weight = 1.0
        extract_kind = None
        low = text.lower()
        for s in self.series:
            # Prefer country consistency when declared
            sc = (s.get("country") or "").upper()
            if sc and sc not in {"EUR", "UNK"} and sc != (raw.country or "").upper():
                # allow cross-post only if URL/agency clearly matches series country keywords
                if sc == "CHN" and "china" not in low and "nbs" not in low and "stats.gov.cn" not in low:
                    continue
            matches = s.get("match_any") or []
            if any(m.lower() in low for m in matches):
                series_id = s.get("series_id")
                series_label = s.get("label_ko")
                site_slot = s.get("site_slot")
                series_weight = float(s.get("base_weight", 1.0))
                extract_kind = s.get("extract")
                break

        learned_m = self.learned.get(series_id or "", 1.0)
        sig = (domain_score * 0.9 + boost * 0.5 + 0.5) * raw.weight * series_weight * learned_m

        reasons = [f"domains:{','.join(d for d,_ in domain_hits[:3])}"]
        if series_id:
            reasons.append(f"series:{series_id}")
        if boost:
            reasons.append(f"boost:{boost:g}")
        if learned_m != 1.0:
            reasons.append(f"learned_x{learned_m:.2f}")

        return ScoredReport(
            id=report_id(raw),
            title=raw.title,
            url=raw.url,
            summary=raw.summary,
            published_at=raw.published_at,
            country=raw.country,
            agency=raw.agency,
            source_id=raw.source_id,
            domains=[d for d, _ in sorted(domain_hits, key=lambda x: -x[1])],
            series_id=series_id,
            series_label_ko=series_label,
            site_slot=site_slot,
            significance=sig,
            rank_reasons=reasons,
        )


def _load_learned_multipliers(path: Path) -> Dict[str, float]:
    """promote -> 1.25, keep -> 1.0, drop -> 0.35 (running average)."""
    scores: Dict[str, List[float]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = row.get("series_id") or ""
        label = (row.get("label") or "").lower()
        if not sid:
            continue
        val = {"promote": 1.35, "keep": 1.0, "drop": 0.25}.get(label)
        if val is None:
            continue
        scores.setdefault(sid, []).append(val)
    out = {}
    for sid, vals in scores.items():
        out[sid] = sum(vals) / len(vals)
    return out


def append_label(
    path: Path,
    *,
    series_id: str,
    url: str,
    title: str,
    label: str,
    note: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "series_id": series_id,
        "url": url,
        "title": title,
        "label": label,
        "note": note,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
