"""Contributions to real GDP growth by expenditure component -- consumption, investment, government,
net exports -- attached to each country's `gdp` card as `contrib` and drawn by macro.js
(mmContribView: stacked quarterly bars, the GDP growth rate as a marker, the latest quarter as a table).

  USA  BEA NIPA Table 1.1.2 via FRED, percentage points at an ANNUAL rate (SAAR), as BEA reports it
  EMU  Eurostat namq_10_gdp unit CON_PPCH_PRE, percentage points of q/q growth (not annualised)
  CHE  Eurostat namq_10_gdp (Switzerland is covered there), same basis as EMU

The parts are what the statistics office publishes; they add up to the headline only up to rounding
and (for chain-linked volumes) a residual, which the table shows rather than hides.

Industry contributions (BEA GDP by Industry, TableID 13) need a BEA API key; see INDUSTRY below.
"""

from __future__ import annotations

from typing import Any, Callable

from .us_public_series import Points

WINDOW = 20                                  # quarters drawn

FRED = "https://fred.stlouisfed.org/series/{}"
ESTAT = "https://ec.europa.eu/eurostat/databrowser/view/namq_10_gdp/default/table"
_EST = "unit=CON_PPCH_PRE&s_adj=SCA&geo={geo}&na_item={item}"

# id, Korean label, colour key (shared across countries so a component keeps its colour)
COUNTRIES: dict[str, dict[str, Any]] = {
    "USA": {
        "basis_ko": "연율 %p (BEA 표 1.1.2, 계절조정)",
        "source": "BEA NIPA 1.1.2 via FRED",
        "source_urls": ["https://www.bea.gov/data/gdp/gross-domestic-product", FRED.format("A191RL1Q225SBEA")],
        "total": ("fred", "A191RL1Q225SBEA"),
        "parts": [
            ("pce", "민간소비", ("fred", "DPCERY2Q224SBEA")),
            ("investment", "민간투자(재고 포함)", ("fred", "A006RY2Q224SBEA")),
            ("government", "정부", ("fred", "A822RY2Q224SBEA")),
            ("net_exports", "순수출", ("fred", "A019RY2Q224SBEA")),
        ],
    },
    "EMU": {
        "basis_ko": "전기 대비 %p (비연율, Eurostat, 계절·영업일조정)",
        "source": "Eurostat namq_10_gdp CON_PPCH_PRE",
        "source_urls": [ESTAT],
        "total": ("eurostat", _EST.format(geo="EA", item="B1GQ")),
        "parts": [
            ("pce", "가계소비", ("eurostat", _EST.format(geo="EA", item="P31_S14_S15"))),
            ("investment", "고정투자", ("eurostat", _EST.format(geo="EA", item="P51G"))),
            ("inventories", "재고", ("eurostat", _EST.format(geo="EA", item="P52_P53"))),
            ("government", "정부", ("eurostat", _EST.format(geo="EA", item="P3_S13"))),
            ("net_exports", "순수출", ("eurostat", _EST.format(geo="EA", item="P6X7"))),
        ],
    },
    "CHE": {
        "basis_ko": "전기 대비 %p (비연율, Eurostat, 계절·영업일조정)",
        "source": "Eurostat namq_10_gdp CON_PPCH_PRE",
        "source_urls": [ESTAT],
        "note_ko": "스위스 순수출은 금·의약품 교역 때문에 분기마다 크게 흔들립니다.",
        "total": ("eurostat", _EST.format(geo="CH", item="B1GQ")),
        "parts": [
            ("pce", "가계소비", ("eurostat", _EST.format(geo="CH", item="P31_S14_S15"))),
            ("investment", "고정투자", ("eurostat", _EST.format(geo="CH", item="P51G"))),
            ("inventories", "재고", ("eurostat", _EST.format(geo="CH", item="P52_P53"))),
            ("government", "정부", ("eurostat", _EST.format(geo="CH", item="P3_S13"))),
            ("net_exports", "순수출", ("eurostat", _EST.format(geo="CH", item="P6X7"))),
        ],
    },
}


def _quarter(d: str) -> str:
    return f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}"


def build(iso3: str, read: Callable[[str, str], Points]) -> dict[str, Any]:
    """`read(kind, key)` returns (date, value) points; kind is "fred" or "eurostat"."""
    cfg = COUNTRIES[iso3]
    total = dict(read(*cfg["total"]))
    parts = [(pid, label, dict(read(*src))) for pid, label, src in cfg["parts"]]
    # quarters where the headline and every part are published
    dates = sorted(d for d in total if all(d in p for _, _, p in parts))[-WINDOW:]
    if not dates:
        raise ValueError(f"{iso3}: no quarter with every component")
    last = dates[-1]
    out_parts = [{"id": pid, "label_ko": label, "values": [round(p[d], 2) for d in dates]} for pid, label, p in parts]
    s = sum(p["values"][-1] for p in out_parts)
    return {
        "basis_ko": cfg["basis_ko"],
        "source": cfg["source"],
        "source_urls": cfg["source_urls"],
        "note_ko": cfg.get("note_ko"),
        "periods": [_quarter(d) for d in dates],
        "dates": dates,
        "total": [round(total[d], 2) for d in dates],
        "parts": out_parts,
        "latest": {"period": _quarter(last), "total": round(total[last], 2), "sum_parts": round(s, 2),
                   "residual": round(total[last] - s, 2)},
    }


def apply(country: dict[str, Any], contrib: dict[str, Any]) -> bool:
    """Attach to the `gdp` card. The card's old `components` list was a seeded fixture (round numbers
    with no source); with an observed breakdown in hand it goes."""
    gdp = next((i for i in country.get("indicators") or [] if i.get("id") == "gdp"), None)
    if gdp is None:
        return False
    changed = gdp.get("contrib") != contrib
    gdp["contrib"] = contrib
    if gdp.pop("components", None) is not None:
        changed = True
    return changed
