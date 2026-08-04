"""Optional field extractors for known series (no full PDF/LLM)."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .httputil import fetch_text, html_to_text

_BORROW = re.compile(
    r"During the (?P<period>[A-Za-z]+–[A-Za-z]+ \d{4}|[A-Za-z]+-[A-Za-z]+ \d{4}) quarter,?\s+"
    r"Treasury expects to borrow \$(?P<borrow>[\d,\.]+)\s*billion in privately-held net marketable debt,?\s+"
    r"assuming an end-of-(?P<month>[A-Za-z]+) cash balance of \$(?P<cash>[\d,\.]+)\s*billion\."
    r"(?:\s+The borrowing estimate is \$(?P<vs>[\d,\.]+)\s*billion (?P<dir>higher|lower)[^\.]+\.)?",
    re.I,
)


def extract_for_series(
    series_id: Optional[str],
    *,
    url: str,
    title: str,
    summary: str,
    user_agent: str,
    timeout: float = 18.0,
    fetch_detail: bool = True,
) -> Optional[Dict[str, Any]]:
    if not series_id:
        return None
    if series_id == "US_QRA_MARKETABLE_BORROWING":
        text = f"{title}\n{summary}"
        if fetch_detail and "treasury.gov" in url:
            try:
                html = fetch_text(url, user_agent=user_agent, timeout=timeout)
                text = html_to_text(html)
            except Exception:
                pass
        quarters = []
        for m in _BORROW.finditer(text):
            gd = m.groupdict()
            vs = None
            if gd.get("vs"):
                vs = float(gd["vs"].replace(",", ""))
                if (gd.get("dir") or "").lower() == "lower":
                    vs = -vs
            quarters.append(
                {
                    "period": gd["period"],
                    "net_borrowing_bn": float(gd["borrow"].replace(",", "")),
                    "end_cash_bn": float(gd["cash"].replace(",", "")),
                    "vs_prior_bn": vs,
                }
            )
        if not quarters:
            return {"parsed": False}
        return {
            "parsed": True,
            "quarters": quarters,
            "qra_next_net_borrowing_bn": quarters[0]["net_borrowing_bn"],
            "qra_end_cash_bn": quarters[0]["end_cash_bn"],
            "qra_vs_prior_bn": quarters[0].get("vs_prior_bn"),
        }
    if series_id == "US_FED_BEIGE_BOOK":
        low = f"{title} {summary}".lower()
        soft = sum(1 for t in ("modest", "slowed", "weak", "softening") if t in low)
        firm = sum(1 for t in ("strong", "robust", "solid", "tight") if t in low)
        tone = "soft" if soft > firm else "firm" if firm > soft else "mixed" if soft or firm else "unknown"
        return {"beige_tone": tone}
    return None
