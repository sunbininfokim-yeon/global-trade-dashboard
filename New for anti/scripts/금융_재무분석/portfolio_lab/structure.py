"""Portfolio structure helpers: clusters, FX mix, stress windows, profile checks."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .risk import portfolio_returns


EQUITY_LIKE = {"equity", "etf"}


def currency_exposure(positions: list[dict[str, Any]]) -> dict[str, Any]:
    krw = 0.0
    foreign = 0.0
    for p in positions:
        w = abs(float(p.get("weight") or 0.0))
        ccy = p["instrument"].get("currency") or "KRW"
        if ccy == "KRW" and not p["instrument"].get("fx_as_asset"):
            krw += w
        else:
            foreign += w
    return {
        "krw_weight": krw,
        "foreign_weight": foreign,
    }


def corr_clusters(
    corr: pd.DataFrame,
    weights: pd.Series,
    names: dict[str, str],
    *,
    threshold: float = 0.55,
) -> list[dict[str, Any]]:
    """Greedy clusters of assets with pairwise |corr| or corr above threshold."""
    ids = [i for i in corr.columns if abs(float(weights.get(i, 0.0))) > 1e-6]
    # skip flat cash
    parent = {i: i for i in ids}

    def find(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            c = float(corr.loc[a, b])
            if c >= threshold:
                union(a, b)

    groups: dict[str, list[str]] = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)

    out = []
    for _, members in groups.items():
        if len(members) < 2:
            continue
        wsum = float(sum(max(float(weights.get(m, 0.0)), 0.0) for m in members))
        label_members = [names.get(m, m) for m in members]
        # heuristic label
        blob = " ".join(label_members)
        if any(k in blob for k in ("엔비디아", "나스닥", "QQQ", "하이닉스", "러셀", "NVDA", "TSLA")):
            label_ko, label_en = "기술·성장 묶음", "Tech / growth cluster"
        elif any(k in blob for k in ("금", "은", "채권", "국채", "GLD", "SLV", "AGG")):
            label_ko, label_en = "방어·실물 묶음", "Defensive / real-assets cluster"
        else:
            label_ko, label_en = "함께 움직이는 묶음", "Assets that tend to move together"
        out.append(
            {
                "label_ko": label_ko,
                "label_en": label_en,
                "members": members,
                "members_ko": label_members,
                "weight_sum": wsum,
                "threshold": threshold,
            }
        )
    out.sort(key=lambda x: x["weight_sum"], reverse=True)
    return out


def stress_windows(
    rets: pd.DataFrame,
    weights: pd.Series,
) -> dict[str, Any]:
    """Buy-and-hold stress using current weights on historical windows."""
    pr = portfolio_returns(rets, weights)
    windows = [
        (
            "covid_crash",
            "코로나 급락 (2020-02-19~2020-03-23)",
            "COVID crash (19 Feb–23 Mar 2020)",
            "2020-02-19",
            "2020-03-23",
        ),
        (
            "inflation_2022",
            "긴축·인플레 구간 (2022)",
            "Tightening / inflation stretch (2022)",
            "2022-01-03",
            "2022-12-30",
        ),
        ("recent_90d", "최근 90거래일", "Last 90 trading days", None, None),
    ]
    rows = []
    for wid, label_ko, label_en, start, end in windows:
        if wid == "recent_90d":
            seg = pr.iloc[-90:] if len(pr) >= 20 else pr
        else:
            seg = pr.loc[start:end]
        if seg.empty:
            continue
        rows.append(
            {
                "id": wid,
                "label_ko": label_ko,
                "label_en": label_en,
                "start": str(seg.index.min().date()),
                "end": str(seg.index.max().date()),
                "portfolio_return": float(np.expm1(seg.sum())),
            }
        )
    return {
        "windows": rows,
        "note_ko": "당시 비중·매매가 아니라, ‘지금 비중’을 그 구간에 대입한 참고 수치입니다.",
        "note_en": (
            "Not what you actually held or traded then — a what-if using today’s weights "
            "on that historical window."
        ),
    }


def load_profile(path, profile_id: str) -> dict[str, Any]:
    import json
    from pathlib import Path

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    profiles = raw.get("profiles") or {}
    if profile_id not in profiles:
        profile_id = "balanced"
    return profile_id, profiles[profile_id]


def check_profile(
    positions: list[dict[str, Any]],
    weights: pd.Series,
    risk: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    breaches_ko: list[str] = []
    breaches_en: list[str] = []
    abs_w = weights.abs()

    cash_w = 0.0
    equity_like = 0.0
    lev_w = 0.0
    for p in positions:
        iid = p["instrument"]["id"]
        w = abs(float(weights.get(iid, p.get("weight") or 0.0)))
        ac = p["instrument"].get("asset_class")
        if ac == "cash":
            cash_w += w
        if ac in EQUITY_LIKE or p["instrument"].get("leveraged"):
            # leveraged ETF counts as equity-like
            if ac in EQUITY_LIKE:
                equity_like += w
        if p["instrument"].get("leveraged"):
            lev_w += w

    # single name max among positive longs
    long_names = {p["instrument"]["id"]: p["instrument"]["name_ko"] for p in positions}
    peak_id, peak_w = None, 0.0
    for iid, w in weights.items():
        if w > peak_w:
            peak_id, peak_w = iid, float(w)

    if cash_w < float(profile["cash_min"]) - 1e-6:
        breaches_ko.append(
            f"현금 비중 {_pct(cash_w)}가 성향 하한 {_pct(profile['cash_min'])}보다 낮습니다."
        )
        breaches_en.append(
            f"Cash weight {_pct(cash_w)} is below your profile floor of {_pct(profile['cash_min'])}."
        )
    if cash_w > float(profile["cash_max"]) + 1e-6:
        breaches_ko.append(
            f"현금 비중 {_pct(cash_w)}가 성향 상한 {_pct(profile['cash_max'])}보다 높습니다 "
            "(방어는 두텁지만 기회비용이 클 수 있음)."
        )
        breaches_en.append(
            f"Cash weight {_pct(cash_w)} is above your profile ceiling of {_pct(profile['cash_max'])} "
            "(extra defense, but opportunity cost can be high)."
        )
    if equity_like > float(profile["equity_like_max"]) + 1e-6:
        breaches_ko.append(
            f"주식·ETF 성격 합 {_pct(equity_like)}가 성향 상한 {_pct(profile['equity_like_max'])}을 넘습니다."
        )
        breaches_en.append(
            f"Stocks/ETFs at {_pct(equity_like)} exceed your profile cap of "
            f"{_pct(profile['equity_like_max'])}."
        )
    if peak_w > float(profile["single_name_max"]) + 1e-6:
        peak_name = long_names.get(peak_id, peak_id)
        breaches_ko.append(
            f"단일 자산 '{peak_name}' {_pct(peak_w)}가 "
            f"성향 한도 {_pct(profile['single_name_max'])}을 넘습니다."
        )
        breaches_en.append(
            f"Single holding '{peak_name}' at {_pct(peak_w)} exceeds your profile "
            f"limit of {_pct(profile['single_name_max'])}."
        )
    if lev_w > float(profile["leveraged_max"]) + 1e-6:
        breaches_ko.append(
            f"레버리지 상품 합 {_pct(lev_w)}가 성향 한도 {_pct(profile['leveraged_max'])}을 넘습니다."
        )
        breaches_en.append(
            f"Leveraged products at {_pct(lev_w)} exceed your profile limit of "
            f"{_pct(profile['leveraged_max'])}."
        )

    var10 = float(risk["short"].get("var_10d_95") or 0.0)
    budget = float(profile["var_10d_budget"])
    if var10 > budget + 1e-6:
        breaches_ko.append(
            f"10일 VaR {_pct(var10)}가 성향 한도 {_pct(budget)}을 넘습니다 "
            "(성향 대비 손실·변동 규모가 큽니다)."
        )
        breaches_en.append(
            f"10-day VaR {_pct(var10)} is above your profile budget of {_pct(budget)} "
            "(swings look large vs. your risk style)."
        )

    return {
        "cash_weight": cash_w,
        "equity_like_weight": equity_like,
        "leveraged_weight": lev_w,
        "peak_name_ko": long_names.get(peak_id, peak_id) if peak_id else None,
        "peak_weight": peak_w,
        "var_10d_95": var10,
        "var_10d_budget": budget,
        "ok": len(breaches_ko) == 0,
        "breaches_ko": breaches_ko,
        "breaches_en": breaches_en,
    }


def _pct(x: float) -> str:
    return f"{100.0 * float(x):.1f}%"


def suggest_aliases(registry, query: str, limit: int = 8) -> list[dict[str, str]]:
    """Typeahead: '삼성전' → 삼성전자 등."""
    from .resolve import _norm

    q = _norm(query)
    if not q:
        return []
    hits = []
    seen = set()
    for inst in registry.instruments:
        keys = list(inst.aliases) + [inst.name_ko, inst.id]
        if inst.yahoo:
            keys.append(inst.yahoo)
        for a in keys:
            an = _norm(a)
            if q in an or an in q:
                if inst.id in seen:
                    continue
                seen.add(inst.id)
                hits.append(
                    {
                        "id": inst.id,
                        "name_ko": inst.name_ko,
                        "yahoo": inst.yahoo or "",
                        "match": a,
                    }
                )
                break
        if len(hits) >= limit:
            break
    return hits
