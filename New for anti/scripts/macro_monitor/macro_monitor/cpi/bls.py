"""Parse BLS CPI tables into a non-overlapping CPI contribution map.

Table 6 and Table 7 publish the effect on All Items and are the sole basis
for contribution rankings.  Table 2 only adds a detailed SA MoM observation;
it must never be promoted to a contribution ranking by itself.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


BLS_RELEASE_BASE = "https://www.bls.gov/news.release"
TABLE_URLS = {
    "detail": f"{BLS_RELEASE_BASE}/cpi.t02.htm",
    "one_month": f"{BLS_RELEASE_BASE}/cpi.t06.htm",
    "twelve_month": f"{BLS_RELEASE_BASE}/cpi.t07.htm",
}
UA = "Mozilla/5.0 (compatible; macro-monitor-cpi/1.0; research)"
MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ),
        start=1,
    )
}


class CpiFetchError(RuntimeError):
    """Raised when BLS blocks or cannot serve the current release tables."""


class _TableRows(HTMLParser):
    """Dependency-free reader for BLS's simple release HTML tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: Optional[list[str]] = None
        self._cell: Optional[list[str]] = None

    def handle_starttag(self, tag: str, attrs: Sequence[tuple[str, Optional[str]]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(_clean_text("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


@dataclass(frozen=True)
class CpiRow:
    label: str
    relative_importance: Optional[float]
    pct_change: Optional[float]
    effect: Optional[float]
    source_table: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "relative_importance": self.relative_importance,
            "pct_change": self.pct_change,
            "effect": self.effect,
            "source_table": self.source_table,
        }


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value).replace("\xa0", " ")).strip()


def normalize_label(value: str) -> str:
    """Remove BLS footnote markers while retaining published category text."""
    value = _clean_text(value)
    value = re.sub(r"\(\s*\d+\s*\)", "", value)
    return _clean_text(value).lower()


def _number(value: str) -> Optional[float]:
    value = _clean_text(value).replace(",", "")
    if value in {"", "-", "--", "n.a."}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _rows(html: str) -> list[list[str]]:
    parser = _TableRows()
    parser.feed(html)
    parser.close()
    return parser.rows


def parse_analysis_table(html: str, *, source_table: str) -> list[CpiRow]:
    """Parse BLS Table 6 or 7: label, weight, percent change, effect."""
    out: list[CpiRow] = []
    started = False
    for cells in _rows(html):
        if not cells:
            continue
        label = _clean_text(cells[0])
        if normalize_label(label) == "all items":
            started = True
        if not started or len(cells) < 4:
            continue
        if label.lower().startswith("footnotes"):
            break
        weight, pct, effect = _number(cells[1]), _number(cells[2]), _number(cells[3])
        if weight is None and pct is None and effect is None:
            continue
        out.append(CpiRow(normalize_label(label), weight, pct, effect, source_table))
    if not out:
        raise ValueError(f"could not locate data rows in BLS {source_table}")
    return out


def parse_detail_table(html: str) -> list[CpiRow]:
    """Parse detailed SA MoM from BLS Table 2 without inventing an effect."""
    out: list[CpiRow] = []
    started = False
    for cells in _rows(html):
        if not cells:
            continue
        label = _clean_text(cells[0])
        if normalize_label(label) == "all items":
            started = True
        if not started or len(cells) < 6:
            continue
        if label.lower().startswith("footnotes"):
            break
        weight, mom = _number(cells[1]), _number(cells[-1])
        yoy = _number(cells[2])
        if weight is None and mom is None and yoy is None:
            continue
        out.append(CpiRow(normalize_label(label), weight, mom, None, "Table 2"))
    if not out:
        raise ValueError("could not locate data rows in BLS Table 2")
    return out


def release_month(html: str) -> Optional[str]:
    match = re.search(
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",
        html,
        re.I,
    )
    if not match:
        return None
    month_name = match.group(0).rsplit(" ", 1)[0].title()
    return f"{match.group(1)}-{MONTHS[month_name]:02d}"


def fetch_release_tables(*, timeout: int = 45) -> dict[str, str]:
    """Fetch current BLS HTML tables; cached files are the supported fallback."""
    tables: dict[str, str] = {}
    for key, url in TABLE_URLS.items():
        request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                tables[key] = response.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            raise CpiFetchError(
                f"BLS {key} table unavailable: {url}: {exc}. "
                "Save BLS Tables 2, 6, and 7 as HTML and pass them with --table*-html."
            ) from exc
    return tables


def load_mapping(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _by_label(rows: Iterable[CpiRow]) -> dict[str, CpiRow]:
    return {row.label: row for row in rows}


def _mapped_item(item: Mapping[str, Any], rows: Mapping[str, CpiRow]) -> Optional[dict[str, Any]]:
    row = rows.get(normalize_label(item["bls_label"]))
    if row is None:
        return None
    return {
        "id": item["id"],
        "label": item["bls_label"],
        "label_ko": item["label_ko"],
        "parent_id": item.get("parent_id"),
        **row.to_dict(),
    }


def _rank(items: Iterable[Mapping[str, Any]], *, top_n: int) -> dict[str, list[dict[str, Any]]]:
    rows = [dict(item) for item in items if item.get("effect") is not None]
    positive = sorted((x for x in rows if x["effect"] > 0), key=lambda x: x["effect"], reverse=True)[:top_n]
    negative = sorted((x for x in rows if x["effect"] < 0), key=lambda x: x["effect"])[:top_n]
    return {"top_positive": positive, "top_negative": negative}


def _effect_total(rows: Iterable[Mapping[str, Any]]) -> Optional[float]:
    effects = [row["effect"] for row in rows if row.get("effect") is not None]
    return round(sum(effects), 3) if effects else None


def _render_relationship(relation: Mapping[str, Any], mapped: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    source_ids = list(relation["source_ids"])
    target_ids = list(relation["target_ids"])
    source_rows = [mapped[item_id] for item_id in source_ids if item_id in mapped]
    target_rows = [mapped[item_id] for item_id in target_ids if item_id in mapped]
    missing = [item_id for item_id in [*source_ids, *target_ids] if item_id not in mapped]
    mapping_status = "mapped" if not missing else "partial" if source_rows or target_rows else "unmapped"
    relation_type = relation["type"]
    return {
        "id": relation["id"],
        "group": relation.get("group"),
        "type": relation_type,
        "source_ids": source_ids,
        "target_ids": target_ids,
        "directionality": relation.get("directionality"),
        "mechanism_ko": relation["mechanism_ko"],
        "lag_months": relation["lag_months"],
        "evidence_status": relation["evidence_status"],
        "evidence_source": relation.get("evidence_source"),
        "validation_required": relation["validation_required"],
        "sources": source_rows,
        "targets": target_rows,
        "missing_item_ids": missing,
        "mapping_status": mapping_status,
        "current_effect_pp": {"sources": _effect_total(source_rows), "targets": _effect_total(target_rows)},
        "lag_validation_eligible": relation_type == "market_hypothesis",
        "signal_eligible": False,
        "interpretation": "candidate_structure_not_causal_finding_or_forecast",
    }


def _active_pathways(
    relationships: Iterable[Mapping[str, Any]],
    mapped: Mapping[str, Mapping[str, Any]],
    positive_frontier_ids: set[str],
    parents: Mapping[str, Optional[str]],
) -> list[dict[str, Any]]:
    def is_descendant(item_id: str, ancestor_id: str) -> bool:
        current: Optional[str] = item_id
        while current is not None:
            if current == ancestor_id:
                return True
            current = parents.get(current)
        return False

    out: list[dict[str, Any]] = []
    for relation in relationships:
        # Only a previously validated market hypothesis can appear here. This
        # identifies a release-relevant path, not a signal, causal finding, or forecast.
        if relation["type"] != "market_hypothesis" or relation.get("historical_status") not in {
            "historically_supported", "conditional"
        }:
            continue
        source_rows = [mapped[x] for x in relation["source_ids"] if x in mapped]
        target_rows = [mapped[x] for x in relation["target_ids"] if x in mapped]
        if not source_rows or not target_rows:
            continue
        source_is_active = any(
            row.get("effect", 0) is not None
            and row["effect"] > 0
            and any(is_descendant(row["id"], frontier) for frontier in positive_frontier_ids)
            for row in source_rows
        )
        if source_is_active:
            out.append({
                **_render_relationship(relation, mapped),
                "interpretation": "validated_candidate_pathway_currently_relevant_not_causal_finding_or_forecast",
            })
    return out


def build_cpi_structure(
    *,
    one_month_html: str,
    twelve_month_html: str,
    mapping: Mapping[str, Any],
    detail_html: Optional[str] = None,
    top_n: int = 3,
) -> dict[str, Any]:
    """Build one CPI release snapshot from a single BLS release vintage."""
    monthly = _by_label(parse_analysis_table(one_month_html, source_table="Table 6"))
    annual = _by_label(parse_analysis_table(twelve_month_html, source_table="Table 7"))
    detail = _by_label(parse_detail_table(detail_html)) if detail_html else {}
    frontier = [_mapped_item(item, monthly) for item in mapping["driver_frontier"]]
    frontier = [item for item in frontier if item is not None]
    components = [_mapped_item(item, monthly) for item in mapping["items"]]
    components = [item for item in components if item is not None]
    annual_frontier = [_mapped_item(item, annual) for item in mapping["driver_frontier"]]
    annual_frontier = [item for item in annual_frontier if item is not None]
    for item in [*components, *frontier]:
        table2 = detail.get(normalize_label(item["label"]))
        item["detail_mom_sa"] = table2.pct_change if table2 else None
    frontier_ids = {item["id"] for item in frontier}
    parents = {item["id"]: item.get("parent_id") for item in [*mapping["driver_frontier"], *mapping["items"]]}
    monthly_by_id = {item["id"]: item for item in [*frontier, *components]}
    rank_monthly = _rank(frontier, top_n=top_n)
    rank_annual = _rank(annual_frontier, top_n=top_n)
    positive_ids = {item["id"] for item in rank_monthly["top_positive"] if item["id"] in frontier_ids}
    relationship_catalog = [_render_relationship(relation, monthly_by_id) for relation in mapping["relationships"]]
    one_month_headline = monthly.get("all items")
    twelve_month_headline = annual.get("all items")
    return {
        "schema_version": mapping["schema_version"],
        "model": "us_cpi_structure",
        "release_month": release_month(one_month_html) or release_month(twelve_month_html),
        "source": {**mapping["source"], "urls": TABLE_URLS, "vintage_policy": "as_released_single_vintage", "ranking_policy": "Table 6/7 effect on All Items; never rank Table 2 MoM as contribution"},
        "headline": {"one_month_sa_pct": one_month_headline.pct_change if one_month_headline else None, "twelve_month_pct": twelve_month_headline.pct_change if twelve_month_headline else None},
        "drivers": {"one_month": {"frontier": frontier, **rank_monthly}, "twelve_month": {"frontier": annual_frontier, **rank_annual}},
        "mapped_components": components,
        "relationship_catalog": relationship_catalog,
        "active_pathways": _active_pathways(mapping["relationships"], monthly_by_id, positive_ids, parents),
        "relationship_policy": {**mapping.get("mapping_policy", {}), "active_pathways_rule": "Only previously validated market_hypothesis edges can be release-relevant; this is not a causal finding or forecast."},
        "coverage": {"mapped_components": len(components), "configured_components": len(mapping["items"]), "configured_relationships": len(mapping["relationships"]), "fully_mapped_relationships": sum(row["mapping_status"] == "mapped" for row in relationship_catalog), "table2_loaded": detail_html is not None},
    }
