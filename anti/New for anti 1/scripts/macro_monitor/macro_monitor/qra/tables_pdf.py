"""Parse Treasury Sources & Uses and TBAC recommended financing PDFs into tables."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_NUM = re.compile(r"\(?-?[\d,]+(?:\.\d+)?\)?")
_MONTH_ROW = re.compile(
    r"\b(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(?P<yy>\d{2})\s+(?P<rest>.+)$",
    re.I | re.M,
)

_TENORS = [
    "c2y",
    "c3y",
    "c5y",
    "c7y",
    "c10y",
    "c20y",
    "c30y",
    "tips5y",
    "tips10y",
    "tips30y",
    "frn2y",
]


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _parse_num(tok: str) -> Optional[float]:
    tok = tok.strip()
    if not tok or tok in {".", "-", "—", "–"}:
        return None
    neg = tok.startswith("(") and tok.endswith(")")
    tok = tok.strip("()")
    tok = tok.replace(",", "")
    try:
        v = float(tok)
    except ValueError:
        return None
    return -v if neg else v


def _nums_in(s: str) -> List[float]:
    out: List[float] = []
    for m in _NUM.finditer(s):
        v = _parse_num(m.group(0))
        if v is not None:
            out.append(v)
    return out


@dataclass
class SourcesUsesRow:
    period: str  # e.g. Jul-Sep 2026
    row_kind: str  # actual | estimate | revisions
    announcement_date: Optional[str] = None
    financing_need_bn: Optional[float] = None
    marketable_borrowing_bn: Optional[float] = None
    all_other_sources_bn: Optional[float] = None
    total_sources_bn: Optional[float] = None
    change_in_cash_bn: Optional[float] = None
    end_cash_balance_bn: Optional[float] = None
    soma_redemptions_bn: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SourcesUsesTable:
    source_pdf: str
    title: str = "Sources and Uses Reconciliation Table"
    unit: str = "billions_usd"
    rows: List[SourcesUsesRow] = field(default_factory=list)
    parse_ok: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_pdf": self.source_pdf,
            "title": self.title,
            "unit": self.unit,
            "parse_ok": self.parse_ok,
            "rows": [r.to_dict() for r in self.rows],
            "latest_estimates": [
                r.to_dict()
                for r in self.rows
                if r.row_kind == "estimate"
            ][-3:],
            "latest_revisions": [
                r.to_dict() for r in self.rows if r.row_kind == "revisions"
            ][-2:],
        }


def _normalize_su_text(text: str) -> str:
    """Join quarter label lines split across newlines by pdf extractors."""
    text = text.replace("\r", "\n")
    text = re.sub(
        r"(Oct|Jan|Apr|Jul)\s*-\s*(Dec|Mar|Jun|Sep)\s*\n\s*(\d{4})",
        r"\1 - \2 \3",
        text,
    )
    text = re.sub(r"QuarterDate", "Quarter Date", text)
    # Glue "Apr - JunMay 4" → "Apr - Jun May 4"
    text = re.sub(
        r"(Oct|Jan|Apr|Jul)\s*-\s*(Dec|Mar|Jun|Sep)(?=(January|February|March|April|May|June|July|August|September|October|November|December))",
        r"\1 - \2 ",
        text,
    )
    return text


_Q_LABEL = re.compile(r"^(Oct|Jan|Apr|Jul)\s*-\s*(Dec|Mar|Jun|Sep)\b", re.I)
_DATE_RE = re.compile(
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})",
    re.I,
)


def _row_from_nums(
    period: str,
    kind: str,
    nums: List[float],
    *,
    announcement_date: Optional[str] = None,
) -> Optional[SourcesUsesRow]:
    if len(nums) < 7:
        return None
    return SourcesUsesRow(
        period=period,
        row_kind=kind,
        announcement_date=announcement_date,
        financing_need_bn=nums[0],
        marketable_borrowing_bn=nums[1],
        all_other_sources_bn=nums[2],
        total_sources_bn=nums[3],
        change_in_cash_bn=nums[4],
        end_cash_balance_bn=nums[5],
        soma_redemptions_bn=nums[6],
    )


def parse_sources_uses_text(text: str, *, source_pdf: str = "") -> SourcesUsesTable:
    """
    Sequential parse. Treasury PDF extract often looks like:

      Jul - Sep May 4, 2026 557 671 ...
      2026 August 3, 2026 633 739 ...
      Revisions 76 68 ...
    """
    text = _normalize_su_text(text)
    table = SourcesUsesTable(source_pdf=source_pdf)

    cur_q: Optional[str] = None  # "Jul - Sep"
    cur_year: Optional[int] = None
    last_period = ""

    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or line.startswith("Memo") or "Financing Marketable" in line:
            continue
        if line.startswith("Sources and Uses") or line.startswith("Quarter"):
            continue
        if re.match(r"^\(?\d\)", line) or "Announcement" in line and "Need" in line:
            continue

        # Revisions
        if re.match(r"^Revisions\b", line, re.I):
            nums = _nums_in(line.split(" ", 1)[-1] if " " in line else "")
            # line is "Revisions 76 68 ..."
            nums = _nums_in(re.sub(r"^Revisions\s*", "", line, flags=re.I))
            row = _row_from_nums(last_period, "revisions", nums)
            if row:
                table.rows.append(row)
            continue

        # Detect quarter at start
        qm = _Q_LABEL.match(line)
        if qm:
            cur_q = f"{qm.group(1).title()} - {qm.group(2).title()}"
            # Fix title case for Oct/Dec etc already fine
            cur_q = re.sub(r"\s+", " ", qm.group(0)).replace(qm.group(1), qm.group(1).title()).replace(qm.group(2), qm.group(2).title())
            # simpler:
            a, b = qm.group(1), qm.group(2)
            cur_q = f"{a[:1].upper()+a[1:].lower()} - {b[:1].upper()+b[1:].lower()}"
            rest = line[qm.end() :].strip()
        else:
            rest = line

        # Year at start of rest
        ym = re.match(r"^(\d{4})\s+(.*)$", rest)
        if ym:
            cur_year = int(ym.group(1))
            rest = ym.group(2).strip()

        if not cur_q or cur_year is None:
            # try year-only Actual/Date lines without quarter — need prior cur_q
            if cur_q is None:
                continue

        # Actual
        if re.match(r"^Actual\b", rest, re.I):
            nums = _nums_in(re.sub(r"^Actual\s*", "", rest, flags=re.I))
            period = f"{cur_q} {cur_year}"
            row = _row_from_nums(period, "actual", nums)
            if row:
                table.rows.append(row)
                last_period = period
            continue

        # Estimate with date
        dm = _DATE_RE.search(rest)
        if dm:
            date_s = re.sub(r"\s+", " ", dm.group(1))
            # If year was not set on this line but date has year, and rest started with date
            date_year = int(date_s[-4:])
            if cur_year is None:
                cur_year = date_year
            # Forward-looking: Oct announce for Jan-Mar → calendar year date_year+1
            year_for_period = cur_year
            if cur_q.lower().startswith("jan") and date_year == cur_year and "October" in date_s:
                year_for_period = date_year + 1
            # When line is "2026 August 3, 2026" cur_year already 2026 — good
            # When line is "Jul - Sep May 4, 2026" without year before date: ym didn't fire; cur_year may be stale from previous
            if qm and not ym:
                # quarter line with date but no explicit year token — use date year,
                # except Jan-Mar after Oct announce
                year_for_period = date_year
                if cur_q.lower().startswith("jan") and "October" in date_s:
                    year_for_period = date_year + 1
                elif cur_q.lower().startswith("apr") and date_year and "January" in date_s:
                    # Jan announce for Apr-Jun same year
                    year_for_period = date_year
                cur_year = year_for_period

            nums = _nums_in(rest[dm.end() :])
            period = f"{cur_q} {year_for_period}"
            row = _row_from_nums(period, "estimate", nums, announcement_date=date_s)
            if row:
                table.rows.append(row)
                last_period = period
            continue

    # Deduplicate
    seen = set()
    uniq: List[SourcesUsesRow] = []
    for r in table.rows:
        key = (
            r.period,
            r.row_kind,
            r.announcement_date,
            r.marketable_borrowing_bn,
            r.financing_need_bn,
        )
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    table.rows = uniq
    table.parse_ok = len([r for r in table.rows if r.row_kind in ("actual", "estimate")]) >= 3
    return table


def parse_sources_uses_pdf(path: Path) -> SourcesUsesTable:
    return parse_sources_uses_text(_pdf_text(path), source_pdf=str(path.name))


# --- TBAC recommended financing schedule ---


@dataclass
class TbacMonthRow:
    month: str  # Aug-26
    section: str  # historical | recommendations | provisional
    values_bn: Dict[str, Optional[float]]

    def to_dict(self) -> Dict[str, Any]:
        return {"month": self.month, "section": self.section, **self.values_bn}


@dataclass
class TbacFinancingTable:
    source_pdf: str
    title: str = ""
    quarter_label: str = ""
    unit: str = "billions_usd"
    rows: List[TbacMonthRow] = field(default_factory=list)
    parse_ok: bool = False

    def to_dict(self) -> Dict[str, Any]:
        rec = [r for r in self.rows if r.section == "recommendations"]
        components = _tbac_quarter_components(rec)
        return {
            "source_pdf": self.source_pdf,
            "title": self.title,
            "quarter_label": self.quarter_label,
            "unit": self.unit,
            "parse_ok": self.parse_ok,
            "rows": [r.to_dict() for r in self.rows],
            "recommendation_months": [r.to_dict() for r in rec],
            "qra_issuance_components": components,
        }


def _tbac_quarter_components(rows: List[TbacMonthRow]) -> List[Dict[str, Any]]:
    """Sum recommendation-month coupon sizes into qra_issuance-like bars."""
    labels = {
        "c2y": ("c2y", "2Y"),
        "c3y": ("c3y", "3Y"),
        "c5y": ("c5y", "5Y"),
        "c7y": ("c7y", "7Y"),
        "c10y": ("c10y", "10Y"),
        "c20y": ("c20y", "20Y"),
        "c30y": ("c30y", "30Y"),
    }
    sums = {k: 0.0 for k in labels}
    for r in rows:
        for k in labels:
            v = r.values_bn.get(k)
            if v is not None:
                sums[k] += v
    out = []
    for k, (cid, lab) in labels.items():
        out.append(
            {
                "id": cid,
                "label_ko": lab,
                "tenor": cid.replace("c", ""),
                "value": round(sums[k], 1),
            }
        )
    # bills placeholder not in TBAC coupon table
    return out


def parse_tbac_financing_text(text: str, *, source_pdf: str = "") -> TbacFinancingTable:
    table = TbacFinancingTable(source_pdf=source_pdf)
    m = re.search(
        r"TBAC RECOMMENDED US TREASURY FINANCING SCHEDULE FOR\s+(.+?QUARTER)",
        text,
        re.I | re.S,
    )
    if m:
        label = re.sub(r"\s+", " ", m.group(1)).strip()
        table.title = f"TBAC Recommended Financing — {label}"
        table.quarter_label = label

    section = "historical"
    # Section headers may be split across lines: "Recommendations\nfor this Refunding"
    flat_flags = re.sub(r"\s+", " ", text)
    # Pre-mark line indices by scanning with carry
    pending_rec = False
    pending_prov = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        low = line.lower()
        if "recommendations" in low:
            pending_rec = True
        if pending_rec and "refunding" in low:
            section = "recommendations"
            pending_rec = False
            continue
        if "provisional" in low:
            pending_prov = True
        if pending_prov and ("next" in low or "refunding" in low or "indication" in low):
            section = "provisional"
            pending_prov = False
            if not _MONTH_ROW.match(line):
                continue
        # single-line headers
        if "recommendations" in low and "refunding" in low:
            section = "recommendations"
            continue
        if low.startswith("provisional"):
            section = "provisional"
            if not _MONTH_ROW.match(line):
                continue
        mm = _MONTH_ROW.match(line)
        if not mm:
            continue
        toks = mm.group("rest").split()
        vals_raw = [_parse_num(t) for t in toks if _parse_num(t) is not None]
        vals: List[Optional[float]] = [None] * 11
        if not vals_raw:
            continue
        # Coupons always present as first 7; FRN is last when present; TIPS sparse in middle.
        for i in range(min(7, len(vals_raw))):
            vals[i] = vals_raw[i]
        if len(vals_raw) > 7:
            vals[10] = vals_raw[-1]  # 2Y FRN
            mid = vals_raw[7:-1]
            for i, v in enumerate(mid[:3]):
                vals[7 + i] = v
        mapping = {k: vals[i] for i, k in enumerate(_TENORS)}
        table.rows.append(
            TbacMonthRow(
                month=f"{mm.group('mon').title()}-{mm.group('yy')}",
                section=section,
                values_bn=mapping,
            )
        )

    table.parse_ok = len(table.rows) >= 3
    return table


def parse_tbac_financing_pdf(path: Path) -> TbacFinancingTable:
    return parse_tbac_financing_text(_pdf_text(path), source_pdf=str(path.name))


def extract_pdf_links_from_html(html: str, *, base: str = "https://home.treasury.gov") -> List[Tuple[str, str]]:
    """Return (kind, url) for Sources-Uses / TBAC / Presentation PDFs."""
    out: List[Tuple[str, str]] = []
    for href in re.findall(r'href="([^"]+\.pdf[^"]*)"', html, re.I):
        full = href if href.startswith("http") else base + href
        low = full.lower()
        if "sources" in low and "use" in low:
            out.append(("sources_uses", full))
        elif "tbacrecommendedfinancing" in low or "recommendedfinancingtable" in low:
            out.append(("tbac_financing", full))
        elif "presentationtotbac" in low:
            out.append(("tbac_presentation", full))
    # dedupe
    seen = set()
    uniq = []
    for k, u in out:
        if u in seen:
            continue
        seen.add(u)
        uniq.append((k, u))
    return uniq
