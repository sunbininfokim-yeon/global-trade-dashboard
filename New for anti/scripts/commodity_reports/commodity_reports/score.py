"""Rank the reports competing for one commodity × country card.

Dozens of releases a day reach the tagger, and a country card shows maybe
six. What decides the six is: is it a report at all (a recipe post and a
photo gallery are not), is it one of the named series the catalog tracks,
how recent is it, and what has the operator promoted or dropped before.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .feeds import RawReport, report_id
from .tag import Tagged, compile_terms

# Headlines an agency publishes that are not commodity intelligence. Kept
# short: the commodity tagger already rejects nearly everything off-topic,
# and this only has to catch releases that do mention a commodity.
REJECT_TERMS = [
    "photo gallery", "holiday hours", "office closure", "recipe", "cookbook",
    "job opening", "vacancy", "internship", "webinar registration",
    "scheduled dates", "correction notice", "obituary", "award winners",
    "national school lunch week", "podcast episode",
    # Malay/Indonesian board and agency housekeeping (MPOB, BPDP, Kemendag):
    # procurement, tenders, vacancies, scholarships, audited accounts, hoax
    # warnings. The palm oil prior would otherwise file them all as palm oil.
    "pengadaan", "pemenang tender", "sebut harga", "jawatan kosong", "beasiswa",
    "call for proposal", "laporan keuangan", "hoaks", "penggajian",
]

# Events, not reports: a forum, a keynote, a seminar is news about the
# publisher, not about the market. Only the headline is checked (a market
# report may mention a conference in passing), and a headline that also
# names a series or carries a figure is kept -- "OPEC Seminar: output cut
# of 2 mb/d" is still a market story.
EVENT_TERMS = [
    "forum", "conference", "seminar", "workshop", "webinar", "symposium", "summit",
    "convene", "convenes", "concludes", "keynote", "speaker", "invited to speak",
    "high level dialogue", "courtesy visit", "networking", "gala", "exhibition", "expo",
    "anniversary", "award", "awards", "ceremony", "signing ceremony",
    "hội nghị", "họp mặt", "hội thảo", "tọa đàm", "hoi nghi", "hop mat", "hoi thao",
    "persidangan", "majlis", "kunjungan",
    "seminário", "congreso", "foro", "penghargaan", "larian", "opini publik",
]

# Housekeeping, not reports: a release that is late, a series that is
# suspended, a survey being re-run, a tender, a new secretary general.
# Headline only, and unlike EVENT_TERMS a series name does not save it --
# "Crop Progress report delayed until 5pm" names the series and is still a
# notice about a timetable. A figure in the headline does.
ADMIN_TERMS = [
    "report delayed", "release delayed", "delayed until", "delays weekly", "suspends", "suspended",
    "discontinue", "discontinues", "discontinued", "to review", "re-survey", "resurvey",
    "to collect", "released on-time", "appoints", "appointed", "secretary general", "reinstates",
    "aviso de pauta", "pregão", "pregao", "nota oficial", "suscriben acuerdo", "acuerdo de colaboración",
    "(t/p)", "tender", "lelang", "sebut harga", "call for proposal",
]

# A release that carries a number is a release that moved a balance sheet.
NUMBER_RE = re.compile(
    # "%" is not a word character, so a trailing \b after it never matched:
    # "fell 12%" scored as a figure-less headline. The boundary is only for
    # the word units.
    r"\b\d{1,3}(?:[.,]\d+)?\s*(?:%|(?:percent|million|billion|mmt|mt|tonnes?|tons?|"
    r"bushels?|barrels?|bpd|bu/ac|kg/ha|t/ha)\b)",
    re.I,
)
REVISION_TERMS = [
    "raised", "lowered", "cut", "increased", "reduced", "revised", "record",
    "higher", "lower", "up from", "down from", "shortfall", "surplus", "deficit",
    "상향", "하향", "감소", "증가", "사상 최대",
    "elevou", "reduziu", "revisou", "aumento", "queda",
]


@dataclass
class ScoredReport:
    id: str
    title: str
    summary: str
    url: str
    published_at: Optional[str]
    agency: str
    agency_ko: str
    source_id: str
    lang: str
    commodities: List[str]
    countries: List[str]
    scope: str
    country_source: str
    series_id: Optional[str]
    series_label_ko: Optional[str]
    importance: float
    reasons: List[str] = field(default_factory=list)
    title_ko: Optional[str] = None
    date_precision: str = "day"
    board: Optional[str] = None

    def to_item(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": {"original": self.title, "original_lang": self.lang, "ko": self.title_ko},
            "summary": self.summary or None,
            "url": self.url,
            "published_at": self.published_at,
            **({"published_precision": self.date_precision} if self.date_precision != "day" else {}),
            "agency": self.agency,
            "agency_ko": self.agency_ko,
            "source_id": self.source_id,
            "commodities": self.commodities,
            "countries": self.countries,
            "scope": self.scope,
            "country_source": self.country_source,
            "series_id": self.series_id,
            "series_label_ko": self.series_label_ko,
            "importance": round(self.importance, 3),
            "reasons": self.reasons,
            **({"board": self.board} if self.board else {}),
        }


def _age_days(published_at: Optional[str], now: datetime) -> Optional[float]:
    if not published_at:
        return None
    try:
        dt = datetime.fromisoformat(published_at)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 86400.0)


class ReportScorer:
    def __init__(
        self,
        series_cfg: Dict[str, Any],
        *,
        label_history_path: Optional[Path] = None,
        half_life_days: float = 21.0,
    ) -> None:
        self.series = series_cfg.get("series", [])
        self.reject_pats = compile_terms(REJECT_TERMS)
        self.event_pats = compile_terms(EVENT_TERMS)
        self.admin_pats = compile_terms(ADMIN_TERMS)
        from .tag import CONTEXT_TERMS

        self.context_pats = compile_terms(CONTEXT_TERMS)
        self.revision_pats = compile_terms(REVISION_TERMS)
        self.half_life_days = half_life_days
        self.learned: Dict[str, float] = {}
        if label_history_path and Path(label_history_path).exists():
            self.learned = load_learned_multipliers(Path(label_history_path))

    def match_series(self, text_low: str) -> Optional[Dict[str, Any]]:
        best = None
        for s in self.series:
            for m in s.get("match_any") or []:
                if m.lower() in text_low:
                    # Longest matching phrase wins: "crop production report"
                    # should not lose to a two-word series that also matched.
                    if best is None or len(m) > best[1]:
                        best = (s, len(m))
                    break
        return best[0] if best else None

    def score(self, raw: RawReport, tagged: Tagged, *, now: Optional[datetime] = None) -> Optional[ScoredReport]:
        now = now or datetime.now(timezone.utc)
        text = f"{raw.title}\n{raw.summary}"
        if any(p.search(text) for p in self.reject_pats):
            return None
        # No commodity, no window to put it on. This is the whole filter: the
        # dashboard has nowhere to show a report that is about nothing it trades
        # -- unless its source feeds a board, which is shown on its own.
        if not tagged.commodities and not raw.board:
            return None

        low = text.lower()
        series = self.match_series(low)
        title_has_figure = bool(NUMBER_RE.search(raw.title))
        if not series and not title_has_figure and any(p.search(raw.title) for p in self.event_pats):
            return None
        if not title_has_figure and any(p.search(raw.title) for p in self.admin_pats):
            return None
        # A PR-heavy board (market_only in sources.json): keep only what reads
        # as market news -- a production, price, trade or policy term -- or a
        # named series.
        if raw.market_only and not series and not any(p.search(text) for p in self.context_pats):
            return None
        series_weight = float(series.get("base_weight", 1.0)) if series else 1.0
        series_id = series.get("series_id") if series else None

        base = 1.0
        reasons = []
        if series_id:
            reasons.append(f"series:{series_id}")
        if NUMBER_RE.search(text):
            base += 0.6
            reasons.append("has_figure")
        if any(p.search(text) for p in self.revision_pats):
            base += 0.4
            reasons.append("revision_language")
        if raw.summary:
            base += 0.2
        if tagged.country_source == "text":
            # A named country is what makes this a country-window report rather
            # than a world report the country view merely inherits.
            base += 0.3
            reasons.append("country_in_text")

        age = _age_days(raw.published_at, now)
        if age is None:
            # List-page sources carry no date. Treat as a week old rather than
            # brand new, so a dateless link cannot outrank today's WASDE.
            recency = 0.5 ** (7.0 / self.half_life_days)
            reasons.append("no_date")
        else:
            recency = 0.5 ** (age / self.half_life_days)

        learned = self.learned.get(series_id or "", 1.0)
        if learned != 1.0:
            reasons.append(f"learned_x{learned:.2f}")

        importance = base * series_weight * raw.weight * learned * (0.35 + 0.65 * recency)

        return ScoredReport(
            id=report_id(raw),
            title=raw.title,
            summary=raw.summary,
            url=raw.url,
            published_at=raw.published_at,
            agency=raw.agency,
            agency_ko=raw.agency_ko,
            source_id=raw.source_id,
            lang=raw.lang,
            commodities=tagged.commodities,
            countries=tagged.countries,
            scope=tagged.scope,
            country_source=tagged.country_source,
            series_id=series_id,
            series_label_ko=series.get("label_ko") if series else None,
            importance=importance,
            reasons=reasons,
            date_precision=getattr(raw, "date_precision", "day"),
            board=raw.board,
        )


def load_learned_multipliers(path: Path) -> Dict[str, float]:
    """promote -> 1.35, keep -> 1.0, drop -> 0.25, averaged per series."""
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
        val = {"promote": 1.35, "keep": 1.0, "drop": 0.25}.get((row.get("label") or "").lower())
        if not sid or val is None:
            continue
        scores.setdefault(sid, []).append(val)
    return {sid: sum(v) / len(v) for sid, v in scores.items()}


def append_label(
    path: Path, *, series_id: str, url: str, title: str, label: str, note: str = ""
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
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
