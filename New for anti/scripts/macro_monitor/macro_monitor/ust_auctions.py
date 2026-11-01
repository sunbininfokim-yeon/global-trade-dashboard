"""US Treasury coupon auctions (who bought, at what yield, how well covered) and Treasury buybacks.

Auctions come from TreasuryDirect's securities API, which carries a result the afternoon of the auction;
Fiscal Data's auctions_query only fills a row in on the issue date, a week later. Buybacks come from
Fiscal Data (buybacks_operations), which has each operation the day after. Both are keyless.

Nominal coupons only (2/3/5/7/10/20/30-year, reopenings included): TIPS and FRNs are priced on a different
basis and would make the yield column mean two things. Bidder shares are of the competitive amount
awarded to primary dealers, direct and indirect bidders together -- the "dealer takedown" convention.

What is not here: the tail (high yield minus the when-issued yield at 1 p.m.) needs WI quotes, which are
licensed market data. Each tenor is compared with its own previous auction instead.
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from typing import Any

TD_AUCTIONED = "https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&type={type}&days={days}"
FD_BUYBACKS = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/"
               "buybacks_operations?sort=-operation_date&page[size]=400")
UA = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"

TENORS = {"2-Year": "2y", "3-Year": "3y", "5-Year": "5y", "7-Year": "7y", "10-Year": "10y",
          "20-Year": "20y", "30-Year": "30y"}
TENOR_ORDER = list(TENORS.values())
OP_TYPE_KO = {"Liquidity Support": "유동성 지원", "Cash Management": "현금 관리"}
SEC_TYPE_KO = {"Nominal Coupons": "일반 국채", "TIPS": "물가연동"}


def bucket_ko(b: Any) -> str:
    """'20Y to 30Y' -> '20~30년', '1Mo to 2Y' -> '1개월~2년'; anything else as given."""
    def side(x: str) -> str:
        x = x.strip()
        return f"{x[:-2]}개월" if x.endswith("Mo") else f"{x[:-1]}년" if x.endswith("Y") else x
    parts = str(b or "").split(" to ")
    if len(parts) != 2:
        return str(b or "")
    lo, hi = side(parts[0]), side(parts[1])
    return f"{lo[:-1]}~{hi}" if lo.endswith("년") and hi.endswith("년") else f"{lo}~{hi}"


def _get(url: str, timeout: int = 120) -> Any:
    # curl -g: the Fiscal Data query has literal brackets (page[size]).
    proc = subprocess.run(["curl", "-sS", "-g", "-L", "-m", str(timeout), "-A", UA, url], check=False, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"{url.split('?')[0]}: curl rc={proc.returncode}")
    return json.loads(proc.stdout.decode("utf-8"))


def _f(x: Any) -> float | None:
    try:
        v = float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return v


def parse_auction(r: dict[str, Any]) -> dict[str, Any] | None:
    """One TreasuryDirect record -> a row, or None when it is not a nominal coupon with results."""
    if r.get("inflationProtected") == "Yes" or r.get("floatingRate") == "Yes":
        return None
    tenor = TENORS.get(str(r.get("originalSecurityTerm") or "").strip())
    hy, btc = _f(r.get("highYield")), _f(r.get("bidToCoverRatio"))
    pd, dr, ind = (_f(r.get(k)) or 0.0 for k in ("primaryDealersCompetitiveParAwarded",
                                                  "directBiddersCompetitiveParAwarded",
                                                  "indirectBiddersCompetitiveParAwarded"))
    comp = pd + dr + ind
    date = str(r.get("competitiveAuctionCloseDate") or r.get("auctionDate") or "")[:10]
    if not tenor or hy is None or btc is None or comp <= 0 or len(date) != 10:
        return None
    return {
        "date": date,
        "tenor": tenor,
        "term": r.get("securityTerm"),
        "reopening": r.get("reopening") == "Yes",
        "cusip": r.get("cusip"),
        "offering_bn": round((_f(r.get("offeringAmount")) or 0) / 1e9, 3),
        "high_yield": hy,
        "bid_to_cover": btc,
        "pd_pct": round(pd / comp * 100, 2),
        "direct_pct": round(dr / comp * 100, 2),
        "indirect_pct": round(ind / comp * 100, 2),
        "soma_bn": round((_f(r.get("somaNoncompetitiveParAwarded")) or 0) / 1e9, 3),
    }


def fetch_auctions(days: int = 1900) -> list[dict[str, Any]]:
    rows = []
    for t in ("Note", "Bond"):
        rows += [x for x in (parse_auction(r) for r in _get(TD_AUCTIONED.format(type=t, days=days))) if x]
    uniq = {(r["date"], r["cusip"]): r for r in rows}
    return sorted(uniq.values(), key=lambda r: (r["date"], TENOR_ORDER.index(r["tenor"])))


def parse_buyback(r: dict[str, Any]) -> dict[str, Any] | None:
    offered, cap, accepted = (_f(r.get(k)) for k in ("total_par_amt_offered", "max_par_amt_redeemed", "total_par_amt_accepted"))
    if accepted is None or not r.get("operation_date"):
        return None
    return {
        "date": r["operation_date"],
        "type": r.get("operation_type"),
        "type_ko": OP_TYPE_KO.get(r.get("operation_type"), r.get("operation_type")),
        "security_type": r.get("security_type"),
        "bucket": r.get("maturity_bucket"),
        "bucket_ko": bucket_ko(r.get("maturity_bucket")),
        "security_type_ko": SEC_TYPE_KO.get(r.get("security_type"), r.get("security_type")),
        "offered_bn": round(offered / 1e9, 3) if offered is not None else None,
        "max_bn": round(cap / 1e9, 3) if cap is not None else None,
        "accepted_bn": round(accepted / 1e9, 3),
        "offered_to_max": round(offered / cap, 2) if offered and cap else None,
        "issues_accepted": int(_f(r.get("nbr_issues_accepted")) or 0),
        "issues_eligible": int(_f(r.get("nbr_issues_eligible")) or 0),
    }


def fetch_buybacks() -> list[dict[str, Any]]:
    doc = _get(FD_BUYBACKS)
    return sorted((x for x in (parse_buyback(r) for r in doc.get("data") or []) if x), key=lambda r: r["date"])


# --------------------------------------------------------------------------
# Summaries
# --------------------------------------------------------------------------

def latest_by_tenor(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each tenor's newest auction, with the change against that tenor's previous one."""
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[r["tenor"]].append(r)
    out = []
    for t in TENOR_ORDER:
        if not by[t]:
            continue
        cur = dict(by[t][-1])
        prev = by[t][-2] if len(by[t]) > 1 else None
        if prev:
            cur["prev_date"] = prev["date"]
            cur["d_yield_bp"] = round((cur["high_yield"] - prev["high_yield"]) * 100, 1)
            cur["d_bid_to_cover"] = round(cur["bid_to_cover"] - prev["bid_to_cover"], 2)
            cur["d_pd_pp"] = round(cur["pd_pct"] - prev["pd_pct"], 2)
            cur["d_indirect_pp"] = round(cur["indirect_pct"] - prev["indirect_pct"], 2)
        out.append(cur)
    return out


def monthly_dealer_share(rows: list[dict[str, Any]]) -> list[tuple[str, float]]:
    """Offering-weighted primary-dealer share of each month's coupon auctions."""
    w: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        m = r["date"][:7]
        w[m][0] += r["pd_pct"] * r["offering_bn"]
        w[m][1] += r["offering_bn"]
    return [(f"{m}-01", round(a / b, 2)) for m, (a, b) in sorted(w.items()) if b]


def monthly_buybacks(rows: list[dict[str, Any]]) -> list[tuple[str, float]]:
    s: dict[str, float] = defaultdict(float)
    for r in rows:
        s[r["date"][:7]] += r["accepted_bn"]
    return [(f"{m}-01", round(v, 3)) for m, v in sorted(s.items())]


def _history(points: list[tuple[str, float]]) -> dict[str, Any]:
    def window(n: int) -> dict[str, list]:
        pts = points[-n:]
        return {"dates": [d for d, _ in pts], "values": [v for _, v in pts]}
    return {"5y": window(60), "10y": window(120)}


def auction_card(rows: list[dict[str, Any]], retrieved_at: str) -> dict[str, Any]:
    monthly = monthly_dealer_share(rows)
    month, share = monthly[-1]
    n = sum(1 for r in rows if r["date"].startswith(month[:7]))
    last = rows[-1]
    note = (f"{month[:7]} 쿠폰 국채 입찰 {n}건에서 프라이머리 딜러가 경쟁 낙찰분의 {share:.1f}%를 가져갔습니다"
            f"(발행액 가중). 낮을수록 딜러가 떠안은 물량이 적어 실수요가 강했다는 뜻입니다. "
            f"'입찰 결과' 탭에 만기별 최근 입찰의 낙찰금리·응찰률·응찰자 구성이 직전 입찰과 함께 있습니다. "
            f"테일(낙찰금리 − 발행 전 시장금리)은 유료 시장자료가 필요해 싣지 않았습니다.")
    return {
        "id": "ust_auction_demand",
        "category": "liquidity",
        "label_ko": "국채 입찰 수요",
        "unit": "%",
        "format": "pct1",
        "value": share,
        "display": f"딜러 {share:.1f}%",
        "display_chip": f"딜러 {share:.1f}%",
        "change_1m_pct": None,
        "change_1y_pct": None,
        "asof": last["date"],
        "observed_at": last["date"],
        "reference_period": month[:7],
        "history": _history(monthly),
        "source": "treasurydirect:auctioned",
        "source_urls": ["https://www.treasurydirect.gov/auctions/auction-query/"],
        "quality": "live",
        "data_status": "live",
        "refresh_tier": "daily",
        "chart_type": "line",
        "retrieved_at": retrieved_at,
        "note_ko": note,
        "news_query": "Treasury auction bid-to-cover primary dealers indirect bidders",
        "auctions": {
            "latest_by_tenor": latest_by_tenor(rows),
            "recent": list(reversed(rows[-15:])),
            "basis_ko": "응찰자 비율은 경쟁입찰 낙찰액(딜러+직접+간접) 대비입니다. 간접은 해외 중앙은행 등 대리 응찰, 직접은 기관의 직접 응찰입니다.",
        },
    }


def buyback_card(rows: list[dict[str, Any]], retrieved_at: str) -> dict[str, Any]:
    monthly = monthly_buybacks(rows)
    last = rows[-1]
    cover = f", 신청이 한도의 {last['offered_to_max']:.1f}배" if last.get("offered_to_max") else ""
    note = (f"{last['date']} {last['type_ko']} 바이백({last['security_type_ko']} {last['bucket_ko']})에서 {last['accepted_bn']:.1f}B를 사들였습니다"
            f"(한도 {last['max_bn']:.1f}B{cover}). 차트는 월별 매입 합계입니다. 유동성 지원은 오래된 비지표물을 사들여 "
            f"시장 유동성을 돕고, 현금 관리는 세수가 몰리는 시기 단기 현금을 조절합니다.")
    return {
        "id": "ust_buybacks",
        "category": "liquidity",
        "label_ko": "국채 바이백",
        "unit": "bn_usd",
        "format": "bn1",
        "value": last["accepted_bn"],
        "display": f"${last['accepted_bn']:.1f}B",
        "display_chip": f"${last['accepted_bn']:.1f}B",
        "change_1m_pct": None,
        "change_1y_pct": None,
        "asof": last["date"],
        "observed_at": last["date"],
        "reference_period": last["date"],
        "history": _history(monthly),
        "source": "fiscaldata:buybacks_operations",
        "source_urls": ["https://fiscaldata.treasury.gov/datasets/treasury-securities-buybacks/"],
        "quality": "live",
        "data_status": "live",
        "refresh_tier": "daily",
        "chart_type": "bar",
        "retrieved_at": retrieved_at,
        "note_ko": note,
        "news_query": "Treasury buyback operation",
        "buybacks": {"rows": list(reversed(rows[-20:]))},
    }


CHIP_KEYS = ("id", "label_ko", "display", "value", "unit", "change_1m_pct", "change_1y_pct", "asof", "note_ko",
             "observed_at", "retrieved_at", "source", "data_status", "chart_type")


def upsert(country: dict[str, Any], card: dict[str, Any]) -> bool:
    """Replace or add the card and keep its chip in step. True when the pack changed."""
    inds = country["indicators"]
    i = next((k for k, x in enumerate(inds) if x["id"] == card["id"]), None)
    changed = i is None or inds[i] != card
    if i is None:
        inds.append(card)
    else:
        inds[i] = card
    chips = country.setdefault("categories", {}).setdefault(card["category"], [])
    chip = {k: card.get(k) for k in CHIP_KEYS}
    j = next((k for k, x in enumerate(chips) if x["id"] == card["id"]), None)
    if j is None:
        chips.append(chip)
        changed = True
    elif {k: v for k, v in chips[j].items() if k != "hidden"} != chip:
        chips[j] = {**chip, **({"hidden": True} if chips[j].get("hidden") else {})}
        changed = True
    return changed
