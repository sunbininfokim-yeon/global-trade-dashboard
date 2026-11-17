"""Who holds KOSPI, and how much more the National Pension Service could buy.

Two blocks, both observed-only (no demo, no seed):

1. foreign_ownership -- the cap-weighted foreign holding ratio of the KOSPI
   top-N ordinary shares, built from each stock's daily `foreignerHoldRatio`
   on Naver's mobile trend API (the same endpoint the price-level tables read)
   times listed shares times that day's close. KRX publishes the market-wide
   figure only behind a login, so the top-N aggregate is the free stand-in;
   its coverage of the listing's market cap is reported next to it.
   Individuals' and institutions' *holdings* are not published daily anywhere
   free -- only their net buying is -- so they are not estimated.

2. nps -- the NPS month-end portfolio (fund.nps.or.kr, ~2.5 months behind),
   carried to today with market moves: domestic equity with the KOSPI,
   overseas equity with ACWI in won, overseas bonds with USD/KRW, the rest
   held flat. Against the 2026 domestic-equity target (20.8%) and the bands
   published before the year-end widening (TAA ±2%p, SAA ±3%p), it shows the
   current weight, the won amount to each line, and the KOSPI level at which
   each line is crossed. The widened SAA band is undisclosed (기금위
   2026-05-28), so ±5%p is the last *published* band, not the live one.
"""

from __future__ import annotations

import html as _html
import re
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd

NPS_PORTFOLIO_URL = "https://fund.nps.or.kr/oprtprcn/ivsmprcn/getOHED0016M0.do"
NPS_POLICY_URLS = [
    "https://www.korea.kr/news/policyNewsView.do?newsId=148965365",   # 목표 14.9% → 20.8% (2026-05-28)
    "https://www.fnnews.com/news/202605281827286752",                 # 허용범위 비공개 확대, 25.8%+α
]

# 2026 strategic allocation after the 5th fund committee (2026-05-28); it also
# stays 20.8% for 2027. Bands: the published pre-widening ones.
NPS_TARGET_PCT = 20.8
NPS_TAA_BAND = 2.0
NPS_SAA_BAND = 3.0

_ASSETS = {
    "국내주식": "domestic_equity",
    "국내채권": "domestic_bond",
    "해외주식": "overseas_equity",
    "해외채권": "overseas_bond",
    "대체투자": "alternatives",
    "단기자금": "short_term",
}


# --- NPS month-end portfolio ---------------------------------------------------

def _page_text(raw: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)


def parse_nps_portfolio(raw_html: str) -> dict[str, Any]:
    """Month-end portfolio from the 포트폴리오 현황 page; raises if any piece is missing."""
    t = _page_text(raw_html)
    m = re.search(r"포트폴리오 개요 \(?\s*(\d{4})년 (\d{1,2})월 말 기준", t)
    if not m:
        raise ValueError("NPS portfolio: as-of month not found")
    month = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    body = t[m.end():]
    tot = re.search(r"전체자산 ([\d,.]+) 조 원", body)
    if not tot:
        raise ValueError("NPS portfolio: total not found")
    assets: dict[str, dict[str, float]] = {}
    for ko, key in _ASSETS.items():
        a = re.search(re.escape(ko) + r" ([\d,.]+) 조 원 ([\d.]+) %", body)
        if not a:
            raise ValueError(f"NPS portfolio: {ko} not found")
        assets[key] = {"jo": float(a.group(1).replace(",", "")), "pct": float(a.group(2))}
    total = float(tot.group(1).replace(",", ""))
    if not 0 < assets["domestic_equity"]["jo"] < total:
        raise ValueError("NPS portfolio: domestic equity outside the total")
    return {"month": month, "total_jo": total, "assets": assets}


def fetch_nps_portfolio() -> dict[str, Any]:
    import requests

    r = requests.get(NPS_PORTFOLIO_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    return parse_nps_portfolio(r.text)


NPS_ASSET_PAGES = {
    "domestic_equity": "https://fund.nps.or.kr/oprtprcn/ivsmprcn/getOHED0003M0.do",
    "domestic_bond": "https://fund.nps.or.kr/oprtprcn/ivsmprcn/getOHED0004M0.do",
    "overseas_equity": "https://fund.nps.or.kr/oprtprcn/ivsmprcn/getOHED0005M0.do",
    "overseas_bond": "https://fund.nps.or.kr/oprtprcn/ivsmprcn/getOHED0006M0.do",
}


def parse_nps_yearly(raw_html: str) -> dict[str, tuple[float, float]]:
    """year -> (조원, % of the fund) from an asset-class page's 투자개요 table.
    The current year's row is the latest month, not a year end -- callers drop it."""
    rows = re.findall(r"<td>(\d{4})</td><td>([\d.]+)</td><td>([\d.]+)</td>", raw_html)
    return {y: (float(v) / 1000, float(p)) for y, v, p in rows}


def nps_year_ends(pages: dict[str, dict[str, tuple[float, float]]], *, current_year: str) -> list[dict[str, Any]]:
    """Year-end snapshots where all four tracked classes are published. The fund
    total is not on these pages; amount/share is averaged over the four classes
    (each share is rounded to 0.1%p, so one class alone is off by up to ~0.5%)."""
    years = set.intersection(*(set(v) for v in pages.values())) - {current_year}
    out = []
    for y in sorted(years):
        amts = {k: pages[k][y][0] for k in pages}
        tots = [pages[k][y][0] / pages[k][y][1] * 100 for k in pages if pages[k][y][1] >= 3]
        if not tots:
            continue
        total = sum(tots) / len(tots)
        out.append({"month": f"{y}-12", "total_jo": round(total, 1), "kind": "year_end",
                    "assets": {k: {"jo": round(a, 1), "pct": pages[k][y][1]} for k, a in amts.items()}})
    return out


def fetch_nps_year_ends(*, current_year: str) -> list[dict[str, Any]]:
    import requests

    pages = {}
    for k, url in NPS_ASSET_PAGES.items():
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        pages[k] = parse_nps_yearly(r.text)
        if not pages[k]:
            raise ValueError(f"NPS yearly table empty: {k}")
    return nps_year_ends(pages, current_year=current_year)


def nps_path(snapshots: list[dict[str, Any]], *, kospi: pd.Series, acwi: pd.Series,
             usdkrw: pd.Series) -> list[dict[str, Any]]:
    """Daily estimated weight: each day carries the latest published month end
    before it. At a new month end the line jumps to the published figure -- the
    gap is what the fund actually did (trades, inflows) that markets cannot explain."""
    idx = kospi.dropna().index
    a = acwi.reindex(idx.union(acwi.index)).ffill().reindex(idx)
    f = usdkrw.reindex(idx.union(usdkrw.index)).ffill().reindex(idx)
    k = kospi.dropna()
    snaps = sorted(snapshots, key=lambda s: s["month"])
    out = []
    for snap in snaps:
        try:
            refs = {n: month_end_value(sr, snap["month"]) for n, sr in (("k", k), ("a", a), ("f", f))}
        except Exception:  # noqa: BLE001
            continue
        if any(v is None for v in refs.values()):
            continue
        nxt = [s["month"] for s in snaps if s["month"] > snap["month"]]
        ref_day = pd.Timestamp(refs["k"][0])
        end_day = None
        if nxt:
            later = k[k.index.strftime("%Y-%m") == nxt[0]]
            end_day = later.index[-1] if len(later) else None
        A = snap["assets"]
        rest = snap["total_jo"] - A["domestic_equity"]["jo"] - A["overseas_equity"]["jo"] - A["overseas_bond"]["jo"]
        for d in k.index[(k.index >= ref_day) & ((k.index < end_day) if end_day is not None else True)]:
            if not (pd.notna(a.get(d)) and pd.notna(f.get(d))):
                continue
            fx = f[d] / refs["f"][1]
            dom = A["domestic_equity"]["jo"] * k[d] / refs["k"][1]
            tot = dom + A["overseas_equity"]["jo"] * a[d] / refs["a"][1] * fx + A["overseas_bond"]["jo"] * fx + rest
            out.append({"date": d.strftime("%Y-%m-%d"), "weight_pct": round(dom / tot * 100, 2),
                        "domestic_equity_jo": round(dom, 1), "kospi": round(float(k[d]), 2),
                        "basis": snap["month"]})
    return out


def month_end_value(series: pd.Series, month: str) -> tuple[str, float] | None:
    """Last observation inside `month` (YYYY-MM)."""
    s = series.dropna()
    s = s[s.index.strftime("%Y-%m") == month]
    if s.empty:
        return None
    return s.index[-1].strftime("%Y-%m-%d"), float(s.iloc[-1])


def nps_now(snapshot: dict[str, Any], *, kospi: pd.Series, acwi: pd.Series,
            usdkrw: pd.Series) -> dict[str, Any]:
    """Carry the month-end portfolio to the last common date of the three markers."""
    month = snapshot["month"]
    refs, nows = {}, {}
    for name, s in (("kospi", kospi), ("acwi", acwi), ("usdkrw", usdkrw)):
        ref = month_end_value(s, month)
        if ref is None:
            raise ValueError(f"no {name} close in {month}")
        refs[name] = ref
        last = s.dropna()
        nows[name] = (last.index[-1].strftime("%Y-%m-%d"), float(last.iloc[-1]))
    k = nows["kospi"][1] / refs["kospi"][1]
    fx = nows["usdkrw"][1] / refs["usdkrw"][1]
    eq = nows["acwi"][1] / refs["acwi"][1] * fx
    a = snapshot["assets"]
    dom = a["domestic_equity"]["jo"] * k
    ovs_eq = a["overseas_equity"]["jo"] * eq
    ovs_bd = a["overseas_bond"]["jo"] * fx
    rest = snapshot["total_jo"] - a["domestic_equity"]["jo"] - a["overseas_equity"]["jo"] - a["overseas_bond"]["jo"]
    total = dom + ovs_eq + ovs_bd + rest
    return {
        "as_of": nows["kospi"][0],
        "kospi_ref": {"date": refs["kospi"][0], "close": refs["kospi"][1]},
        "kospi_now": {"date": nows["kospi"][0], "close": nows["kospi"][1]},
        "factors": {"kospi": round(k, 4), "overseas_equity_krw": round(eq, 4), "usdkrw": round(fx, 4)},
        "domestic_equity_jo": round(dom, 1),
        "others_jo": round(total - dom, 1),
        "total_jo": round(total, 1),
        "weight_pct": round(dom / total * 100, 2),
    }


def nps_lines(target: float = NPS_TARGET_PCT) -> list[dict[str, Any]]:
    band = NPS_TAA_BAND + NPS_SAA_BAND
    return [
        {"id": "upper_published", "pct": target + band, "label_ko": f"공개 상단 {target + band:.1f}% (목표+SAA 3+TAA 2)"},
        {"id": "taa_upper", "pct": target + NPS_TAA_BAND, "label_ko": f"전술 상단 {target + NPS_TAA_BAND:.1f}%"},
        {"id": "target", "pct": target, "label_ko": f"목표 {target:.1f}%"},
        {"id": "taa_lower", "pct": target - NPS_TAA_BAND, "label_ko": f"전술 하단 {target - NPS_TAA_BAND:.1f}%"},
        {"id": "lower_published", "pct": target - band, "label_ko": f"공개 하단 {target - band:.1f}% (목표−SAA 3−TAA 2)"},
    ]


def nps_scenarios(now: dict[str, Any], *, shocks: tuple[float, ...] = (0, -5, -10, -15, -20, -25, -30),
                  target: float = NPS_TARGET_PCT) -> dict[str, Any]:
    """Weight and won amount to each line as the KOSPI moves; other assets held at today's value.

    Buying shifts money from other assets into domestic equity, so the total is
    unchanged by the purchase: amount to line c = c·T − E.
    """
    E, O, L0 = now["domestic_equity_jo"], now["others_jo"], now["kospi_now"]["close"]
    lines = nps_lines(target)
    rows = []
    for s in shocks:
        e = E * (1 + s / 100)
        t = e + O
        rows.append({
            "shock_pct": s,
            "kospi": round(L0 * (1 + s / 100), 1),
            "domestic_equity_jo": round(e, 1),
            "weight_pct": round(e / t * 100, 2),
            "to_line_jo": {ln["id"]: round(ln["pct"] / 100 * t - e, 1) for ln in lines},
        })
    # KOSPI level at which the weight reaches each line: E·x/(E·x+O) = c → x = cO/(E(1−c))
    crossings = []
    for ln in lines:
        c = ln["pct"] / 100
        x = c * O / (E * (1 - c))
        crossings.append({**ln, "kospi": round(L0 * x, 1), "move_pct": round((x - 1) * 100, 1)})
    return {"rows": rows, "crossings": crossings, "lines": lines, "target_pct": target}


# --- Foreign ownership of the KOSPI top-N --------------------------------------

def parse_pct(s: Any) -> float | None:
    if s is None:
        return None
    t = str(s).replace("%", "").replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def foreign_rows(trend: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    """date -> (foreign hold %, close) from Naver trend rows."""
    from .investor_price_levels import parse_close_krw

    out: dict[str, tuple[float, float]] = {}
    for row in trend:
        biz = str(row.get("bizdate") or "")
        r, c = parse_pct(row.get("foreignerHoldRatio")), parse_close_krw(row.get("closePrice"))
        if len(biz) == 8 and r is not None and c and 0 <= r <= 100:
            out[f"{biz[:4]}-{biz[4:6]}-{biz[6:]}"] = (r, c)
    return out


def aggregate_foreign(per_ticker: dict[str, dict[str, tuple[float, float]]], shares: dict[str, float],
                      *, min_cap_share: float = 0.97) -> list[dict[str, Any]]:
    """Cap-weighted foreign % per date; a date counts only when tickers covering
    ≥ min_cap_share of the group's latest cap reported that day (a late-publishing
    name must not swing the ratio)."""
    dates = sorted({d for rows in per_ticker.values() for d in rows})
    if not dates:
        return []
    last_cap = {t: shares[t] * rows[max(rows)][1] for t, rows in per_ticker.items() if rows and t in shares}
    full = sum(last_cap.values())
    out = []
    for d in dates:
        cap = held = 0.0
        n = 0
        for t, rows in per_ticker.items():
            if d in rows and t in shares:
                r, c = rows[d]
                v = shares[t] * c
                cap += v
                held += v * r / 100
                n += 1
        have = sum(last_cap[t] for t, rows in per_ticker.items() if d in rows and t in last_cap)
        if cap > 0 and full > 0 and have / full >= min_cap_share:
            out.append({"date": d, "foreign_pct": round(held / cap * 100, 3),
                        "foreign_jo": round(held / 1e12, 1), "cap_jo": round(cap / 1e12, 1), "n": n})
    return out


def build_foreign_ownership(listing: pd.DataFrame, *, top_n: int = 100,
                            fetch: Callable[[str], list[dict[str, Any]]],
                            previous: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    df = listing.sort_values("Marcap", ascending=False)
    total_cap = float(df["Marcap"].sum())
    top = df.head(top_n)
    if "Stocks" not in top.columns:
        raise ValueError("listing has no Stocks column")
    shares = {str(r.Code).zfill(6): float(r.Stocks) for r in top.itertuples() if r.Stocks and r.Stocks > 0}
    per, errors = {}, []
    for code in shares:
        try:
            per[code] = foreign_rows(fetch(code))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{code}: {type(e).__name__}: {e}")
    if len(per) < 0.9 * len(shares):
        raise RuntimeError(f"foreign ownership: only {len(per)}/{len(shares)} tickers fetched")
    series = aggregate_foreign(per, shares)
    # Keep earlier days the 60-row window no longer reaches; today's fetch wins on overlap.
    merged = {r["date"]: r for r in (previous or [])}
    merged.update({r["date"]: r for r in series})
    hist = [merged[d] for d in sorted(merged)]
    top_cap = float(top["Marcap"].sum())
    latest = hist[-1] if hist else None

    def chg(days: int) -> float | None:
        if not latest or len(hist) <= days:
            return None
        return round(latest["foreign_pct"] - hist[-1 - days]["foreign_pct"], 2)

    by_ticker = []
    names = dict(zip(top["Code"].astype(str).str.zfill(6), top["Name"].astype(str)))
    for code, rows in per.items():
        if not rows:
            continue
        ds = sorted(rows)
        r0, r1 = rows[ds[0]][0], rows[ds[-1]][0]
        by_ticker.append({"ticker": code, "label_ko": names.get(code, code), "foreign_pct": r1,
                          "chg_pp": round(r1 - r0, 2), "since": ds[0],
                          "cap_jo": round(shares[code] * rows[ds[-1]][1] / 1e12, 1)})
    by_ticker.sort(key=lambda x: -x["cap_jo"])
    return {
        "quality": "observed" if latest else "missing",
        "scope_ko": f"코스피 보통주 시가총액 상위 {len(shares)}종목 (상장주식수×종가 가중)",
        "coverage_pct": round(top_cap / total_cap * 100, 1) if total_cap else None,
        "latest": latest,
        "chg_pp": {"1m": chg(21), "3m": chg(63)},
        "history": hist,
        "by_ticker": by_ticker,
        "errors": errors,
        "method_ko": ("종목별 외국인 보유율(네이버, 한도 소진율 아닌 보유 비율) × 상장주식수(FDR 상장목록) × 그날 종가를 "
                      "합산. KRX 시장 전체 외국인 보유 비중은 로그인 뒤에만 있어 상위 종목 합계로 대신합니다."),
        "source": ["https://m.stock.naver.com/api/stock/{ticker}/trend (foreignerHoldRatio)",
                   "FinanceDataReader KOSPI 상장목록 (Stocks, Marcap)"],
    }


def build_report(*, listing: pd.DataFrame, fetch_trend: Callable[[str], list[dict[str, Any]]],
                 previous: dict[str, Any] | None, nps_snapshot: dict[str, Any] | None,
                 year_ends: list[dict[str, Any]] | None = None,
                 kospi: pd.Series, acwi: pd.Series, usdkrw: pd.Series) -> dict[str, Any]:
    prev = previous or {}
    errors: list[str] = []
    try:
        fo = build_foreign_ownership(listing, fetch=fetch_trend,
                                     previous=(prev.get("foreign_ownership") or {}).get("history"))
        errors += fo.pop("errors")
    except Exception as e:  # noqa: BLE001
        fo = prev.get("foreign_ownership") or {"quality": "missing"}
        fo = {**fo, "stale_reason": f"{type(e).__name__}: {e}"}
        errors.append(f"foreign_ownership: {type(e).__name__}: {e}")

    history = {h["month"]: h for h in ((prev.get("nps") or {}).get("history") or [])}
    for ye in year_ends or []:
        history.setdefault(ye["month"], ye)        # a published month end beats a derived year end
    if nps_snapshot:
        history[nps_snapshot["month"]] = {**nps_snapshot, "kind": "month_end"}
    hist = [history[m] for m in sorted(history)]
    nps: dict[str, Any] = {"quality": "missing", "history": hist}
    if hist:
        snap = hist[-1]
        path_from = f"{int(snap['month'][:4]) - 1}-12"
        try:
            now = nps_now(snap, kospi=kospi, acwi=acwi, usdkrw=usdkrw)
            kospi_cap_jo = float(listing["Marcap"].sum()) / 1e12
            nps = {
                "quality": "estimated",
                "snapshot": snap,
                "now": now,
                "scenarios": nps_scenarios(now),
                "share_of_kospi_cap_pct": round(now["domestic_equity_jo"] / kospi_cap_jo * 100, 1),
                # observed: published year/month ends; path: daily estimate since the earliest
                # snapshot the market series reach (the year before last onward)
                "observed": [{"month": h["month"], "kind": h.get("kind", "month_end"),
                              "weight_pct": h["assets"]["domestic_equity"]["pct"],
                              "domestic_equity_jo": h["assets"]["domestic_equity"]["jo"],
                              "total_jo": h["total_jo"]} for h in hist],
                "path": nps_path([h for h in hist if h["month"] >= path_from], kospi=kospi, acwi=acwi, usdkrw=usdkrw),
                "history": hist,
                "policy_ko": [
                    "2026년 국내주식 목표 20.8% (2026-05-28 기금위, 14.9%에서 상향, 2027년도 20.8% 유지).",
                    "허용범위: 그전까지 공개된 것은 전략(SAA) ±3%p + 전술(TAA) ±2%p = ±5%p.",
                    "SAA 허용범위는 연말까지 한시 확대했고 그 폭은 비공개. 상·하단 ±5%p는 공개된 마지막 기준일 뿐입니다.",
                    "리밸런싱은 허용범위를 벗어날 때 의무가 됩니다. 범위 안에서 목표 쪽으로 사는 것은 재량입니다.",
                ],
                "method_ko": ("국민연금 공시 월말 포트폴리오(약 2.5개월 지연)를 오늘로 이월: 국내주식은 코스피, 해외주식은 "
                              "ACWI×원/달러, 해외채권은 원/달러로 움직이고 나머지는 그대로 둡니다. 국내주식에는 코스닥도 "
                              "들어 있어 코스피 하나로 움직이는 것은 근사입니다. 월말 이후 국민연금의 실제 매매는 반영되지 "
                              "않습니다(공개되지 않음)."),
                "source": [NPS_PORTFOLIO_URL, *NPS_POLICY_URLS,
                           "FinanceDataReader KS11 · ACWI · USD/KRW"],
            }
        except Exception as e:  # noqa: BLE001
            errors.append(f"nps: {type(e).__name__}: {e}")
            nps["error"] = f"{type(e).__name__}: {e}"
    return {
        "schema_version": "kospi-holders-v1",
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "foreign_ownership": fo,
        "nps": nps,
        "cannot_do_ko": [
            "개인·기관의 '보유' 비율은 매일 공개되지 않습니다 (순매수만 공개). 예탁결제원 연간 소유자 현황은 주식 수 기준이라 붙이지 않았습니다.",
            "국민연금의 일별·월중 매매 내역은 공개되지 않습니다. '연기금' 순매수는 국민연금 외 기금도 섞인 값입니다.",
        ],
        "errors": errors,
        "disclaimer_ko": "투자 권유 아님. 공개 실측과 그것을 이월한 추정치.",
    }
