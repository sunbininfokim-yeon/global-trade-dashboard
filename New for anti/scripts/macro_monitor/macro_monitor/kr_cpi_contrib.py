"""Korea CPI contributions by item: how many percentage points each of the 458 items added to headline
CPI and to core CPI ('농산물 및 석유류 제외'), month on month and year on year.

Everything comes from the Bank of Korea's ECOS, which republishes Statistics Korea's CPI:
  * 901Y009 (지출목적별 소비자물가지수): every item and group, monthly and annual, with the item weights
    (per 1,000) on every row and the parent of every item in the item list;
  * 901Y010 (품목성질별): the published core index (QB) to check the core basket against.

How the index is put together, checked against the published total to two decimals:
  I_all(t) = I_all(R) * sum_i w_i * I_i(t) / I_i(R) / sum_i w_i
where w are the current weights and R is the year they describe (the weight year's annual average is
the price reference). In 2026 that is R = 2022 (2022 expenditure weights on the 2020=100 indexes).
R is not hard-coded: `reference_year` picks the year that reproduces the published total, so the
2025=100 rebasing (2026-12) is followed without a code change.

So a part's contribution to the change from p to t is exact (up to the published rounding):
  contribution_i = w_i * (I_i(t) - I_i(p)) / I_i(R)  /  sum_j w_j * I_j(p) / I_j(R)  * 100.
Parents are the sums of their children.

Core = Statistics Korea's '농산물 및 석유류 제외': every item except agricultural products other than
grains, petroleum products and city gas (401 of 458 items, weight 909.8 in 2026). The excluded items are
named in CORE_EXCLUDE; `core_check` verifies the result against the published index and weight, and a
basket that no longer matches (new items after a rebasing) is withheld instead of being shown wrong.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from . import ecos

STAT, STAT_CORE, CORE_CODE = "901Y009", "901Y010", "QB"

# 곡물 외 농산물 (채소·과실·기타농산물), 석유류, 도시가스 -- the 57 items Statistics Korea leaves out of
# '농산물 및 석유류 제외지수' (2020 basket). Checked by core_check against the published index.
CORE_EXCLUDE = frozenset("""
가지 감 감자 고구마 고사리 고춧가루 귤 깻잎 당근 도라지 딸기 마늘 망고 무 미나리 바나나 밤 배 배추 버섯
복숭아 부추 브로콜리 블루베리 사과 상추 생강 수박 시금치 아몬드 아보카도 양배추 양파 열무 오렌지 오이 인삼
참깨 참외 체리 콩나물 키위 토마토 파 파인애플 파프리카 포도 풋고추 호박 화초
휘발유 경유 자동차용LPG 등유 취사용LPG 부탄가스 도시가스
""".split())

Index = dict[str, dict[str, float]]            # code -> {YYYY-MM or YYYY: index}


# --------------------------------------------------------------------------
# Fetching (ECOS_API_KEY)
# --------------------------------------------------------------------------

def _rows(stat: str, cycle: str, start: str, end: str, item: str = "", get: Callable = ecos._get) -> list[dict]:
    out, first = [], 1
    while True:
        path = f"StatisticSearch/@KEY/json/kr/{first}/{first + 9999}/{stat}/{cycle}/{start}/{end}"
        doc = get(path + (f"/{item}" if item else ""))
        block = (doc or {}).get("StatisticSearch") or {}
        got = block.get("row") or []
        out += got
        if not got or len(out) >= int(block.get("list_total_count") or 0):
            return out
        first += 10000


def fetch_items(get: Callable = ecos._get) -> list[dict]:
    doc = get(f"StatisticItemList/@KEY/json/kr/1/5000/{STAT}")
    return [r for r in ((doc or {}).get("StatisticItemList") or {}).get("row") or [] if r.get("CYCLE") == "M"]


def parse(rows: list[dict], monthly: bool) -> tuple[Index, dict[str, float]]:
    idx: Index = defaultdict(dict)
    weights: dict[str, float] = {}
    for r in rows:
        code, t, v = r.get("ITEM_CODE1"), str(r.get("TIME") or ""), r.get("DATA_VALUE")
        try:
            idx[code][f"{t[:4]}-{t[4:6]}" if monthly else t[:4]] = float(v)
        except (TypeError, ValueError):
            pass
        try:
            weights[code] = float(r["WGT"])
        except (KeyError, TypeError, ValueError):
            pass
    return dict(idx), weights


def latest_month(get: Callable = ecos._get, today_ym: str = "") -> str | None:
    rows = _rows(STAT, "M", "201501", today_ym or "209912", "0", get=get)
    months = sorted(f"{r['TIME'][:4]}-{r['TIME'][4:6]}" for r in rows if r.get("DATA_VALUE") not in (None, ""))
    return months[-1] if months else None


# --------------------------------------------------------------------------
# Hierarchy and arithmetic
# --------------------------------------------------------------------------

def build_nodes(items: list[dict], weights: dict[str, float]) -> list[dict[str, Any]]:
    """Depth-first from the total ('0'), keeping ECOS's order among siblings."""
    kids: dict[str | None, list[str]] = defaultdict(list)
    name = {}
    for r in items:
        name[r["ITEM_CODE"]] = r["ITEM_NAME"]
        kids[r.get("P_ITEM_CODE")].append(r["ITEM_CODE"])
    nodes: list[dict[str, Any]] = []

    def walk(code: str, parent: int | None, level: int) -> None:
        k = len(nodes)
        nodes.append({"code": code, "name": name[code], "level": level, "parent": parent,
                      "weight": weights.get(code), "children": []})
        if parent is not None:
            nodes[parent]["children"].append(k)
        for c in kids.get(code, []):
            walk(c, k, level + 1)

    walk("0", None, 0)
    return nodes


def leaves(nodes: list[dict[str, Any]]) -> list[int]:
    return [k for k, n in enumerate(nodes) if not n["children"]]


def prev_month(m: str, n: int = 1) -> str:
    t = int(m[:4]) * 12 + int(m[5:7]) - 1 - n
    return f"{t // 12}-{t % 12 + 1:02d}"


def reference_year(nodes: list[dict[str, Any]], monthly: Index, annual: Index, months: list[str]) -> tuple[str, float]:
    """The year whose annual average indexes, with the current weights, reproduce the published total
    over `months` best -- and the worst miss, in index points."""
    best: tuple[str, float] = ("", float("inf"))
    lv = leaves(nodes)
    years = sorted(set.intersection(*(set(annual.get(nodes[k]["code"], {})) for k in lv)) & set(annual.get("0", {})))
    for y in years:
        tw = sum(nodes[k]["weight"] or 0 for k in lv)
        err = 0.0
        for m in months:
            try:
                est = annual["0"][y] * sum((nodes[k]["weight"] or 0) * monthly[nodes[k]["code"]][m]
                                           / annual[nodes[k]["code"]][y] for k in lv) / tw
                err = max(err, abs(est - monthly["0"][m]))
            except (KeyError, ZeroDivisionError):
                err = float("inf")
                break
        if err < best[1]:
            best = (y, err)
    return best


def core_members(nodes: list[dict[str, Any]], exclude: frozenset[str] = CORE_EXCLUDE) -> set[int]:
    return {k for k in leaves(nodes) if nodes[k]["name"] not in exclude}


def contributions(nodes: list[dict[str, Any]], monthly: Index, annual: Index, ref: str, month: str, lag: int,
                  members: set[int] | None = None) -> dict[str, Any] | None:
    """{"by_node": {idx: [change %, contribution %p, weight %]}, "sum_pp"} for the change from
    `lag` months before to `month`, over the leaves in `members` (all leaves when None)."""
    base = prev_month(month, lag)
    lv = [k for k in leaves(nodes) if members is None or k in members]
    q: dict[int, float] = {}
    for k in lv:
        code = nodes[k]["code"]
        s = monthly.get(code, {})
        if month not in s or base not in s or ref not in annual.get(code, {}):
            return None
        q[k] = (nodes[k]["weight"] or 0) / annual[code][ref]
    denom = sum(q[k] * monthly[nodes[k]["code"]][base] for k in lv)
    if not denom:
        return None
    contrib = {k: q[k] * (monthly[nodes[k]["code"]][month] - monthly[nodes[k]["code"]][base]) / denom * 100 for k in lv}
    share = {k: q[k] * monthly[nodes[k]["code"]][base] / denom * 100 for k in lv}
    out: dict[int, list[float | None]] = {}

    def change(k: int) -> float | None:
        s = monthly.get(nodes[k]["code"], {})
        return round((s[month] / s[base] - 1) * 100, 2) if month in s and base in s and s[base] else None

    def fold(k: int) -> tuple[float, float, bool]:
        if not nodes[k]["children"]:
            if k not in contrib:
                return 0.0, 0.0, False
            out[k] = [change(k), round(contrib[k], 3), round(share[k], 2)]
            return contrib[k], share[k], True
        c = w = 0.0
        seen = False
        for ch in nodes[k]["children"]:
            a, b, s = fold(ch)
            c, w, seen = c + a, w + b, seen or s
        if seen:
            out[k] = [change(k), round(c, 3), round(w, 2)]
        return c, w, seen

    fold(0)
    return {"by_node": out, "sum_pp": round(sum(contrib.values()), 3)}


def published(series: dict[str, float], month: str, lag: int) -> float | None:
    base = prev_month(month, lag)
    if month not in series or base not in series or not series[base]:
        return None
    return round((series[month] / series[base] - 1) * 100, 3)


def core_check(nodes: list[dict[str, Any]], members: set[int], monthly: Index, annual: Index, ref: str,
               core_monthly: dict[str, float], core_weight: float | None, months: list[str]) -> tuple[bool, str]:
    """Does the core basket built from CORE_EXCLUDE reproduce the published core index and weight?"""
    w = sum(nodes[k]["weight"] or 0 for k in members)
    if core_weight is not None and abs(w - core_weight) > 0.15:
        return False, f"core weight {w:.1f} != published {core_weight}"
    worst = 0.0
    for m in months:
        for lag in (1, 12):
            pub = published(core_monthly, m, lag)
            got = contributions(nodes, monthly, annual, ref, m, lag, members)
            if pub is None or got is None:
                continue
            worst = max(worst, abs(pub - got["sum_pp"]))
    if worst > 0.05:
        return False, f"core basket misses the published core index by up to {worst:.3f}pp"
    return True, f"core basket matches (weight {w:.1f}, worst {worst:.3f}pp)"
