#!/usr/bin/env python3
"""Freeze Korea's CPI on the 2020=100 base before the 2025=100 rebasing (published 2026-12-18).

After the rebasing ECOS 901Y009 serves the new base: new item list, new weights, re-referenced
indexes. The contribution engine needs the *old* item indexes and weights for every month up to the
link (Dec 2025) so the series can be chained instead of restarted, and nothing guarantees the old base
stays downloadable. This writes, once, everything the engine reads from ECOS on the old base:

  * the item tree (458 items + groups, parent links) and the 2022 weights (per 1,000);
  * monthly indexes 2020-01 .. latest for every code, and annual averages 2020 .. last full year;
  * the published core index (901Y010 QB, '농산물 및 석유류 제외') and its weight;
  * a check that the archived items, re-aggregated, reproduce the published total.

  set -a; . ~/.config/ecos.env; set +a
  python archive_kr_cpi_base2020.py   # appends new old-base months; freezes itself once the base changes
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import kr_cpi_contrib as kc  # noqa: E402

OUT = ROOT / "config" / "kr_cpi_base2020_archive_v1.json"


def _ym(m: str) -> str:
    return m.replace("-", "")


def months_between(a: str, b: str) -> list[str]:
    out, (y, m) = [], (int(a[:4]), int(a[5:7]))
    while f"{y:04d}-{m:02d}" <= b:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def build(get=None) -> dict:
    kw = {"get": get} if get else {}
    latest = kc.latest_month(**kw)
    if not latest:
        raise SystemExit("ECOS returned no CPI months")
    items = kc.fetch_items(**kw)
    monthly, weights = kc.parse(kc._rows(kc.STAT, "M", "202001", _ym(latest), **kw), True)
    last_year = int(latest[:4]) - (0 if latest.endswith("-12") else 1)
    annual, _ = kc.parse(kc._rows(kc.STAT, "A", "2020", str(last_year), **kw), False)
    core_m, core_w = kc.parse(kc._rows(kc.STAT_CORE, "M", "202001", _ym(latest), kc.CORE_CODE, **kw), True)
    nodes = kc.build_nodes(items, weights)
    months = months_between("2020-01", latest)

    # The archive is only worth keeping if it reproduces the published total: same check the
    # engine runs to pick the weight reference year.
    recent = months[-24:]
    ref, err = kc.reference_year(nodes, monthly, annual, recent)
    if err is None or err > 0.06:
        raise SystemExit(f"archive does not reproduce the published total (ref {ref}, worst {err})")
    leaves = kc.leaves(nodes)
    missing = [nodes[k]["code"] for k in leaves if not monthly.get(nodes[k]["code"])]

    return {
        "schema": "kr_cpi_base2020_archive_v1",
        "base": "2020=100",
        "weight_year": "2022",
        "price_reference_year": ref,
        "check_ko": f"품목 {len(leaves)}개를 가중치로 다시 합쳐 공표 총지수와 비교, 최근 24개월 최대 오차 {err:.3f}p",
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "latest_month": latest,
        "source": "한국은행 ECOS 901Y009 지출목적별 소비자물가지수(2020=100), 901Y010 QB 농산물 및 석유류 제외",
        "items": [{"code": n["code"], "name": n["name"], "level": n["level"],
                   "parent": None if n["parent"] is None else nodes[n["parent"]]["code"],
                   "weight": n["weight"]} for n in nodes],
        "months": months,
        "monthly": {code: [series.get(m) for m in months] for code, series in monthly.items()},
        "annual": annual,
        "core": {"code": kc.CORE_CODE, "weight": core_w.get(kc.CORE_CODE),
                 "monthly": [core_m.get(kc.CORE_CODE, {}).get(m) for m in months]},
        "leaves_without_series": missing,
    }


def same_base(old: dict, new: dict, tol: float = 0.0051) -> tuple[bool, str]:
    """Is `new` still the 2020=100 base the archive holds? Same item codes and weights, and every
    month both have agrees (published to two decimals). The rebasing changes all three."""
    oc = {i["code"]: i["weight"] for i in old["items"]}
    nc = {i["code"]: i["weight"] for i in new["items"]}
    if oc != nc:
        return False, f"item list or weights changed ({len(oc)} -> {len(nc)} codes)"
    om, nm = old["months"], new["months"]
    if nm[:len(om)] != om:
        return False, "month axis changed"
    worst = 0.0
    for code, vals in old["monthly"].items():
        for a, b in zip(vals, new["monthly"].get(code, [])):
            if a is not None and b is not None:
                worst = max(worst, abs(a - b))
    if worst > tol:
        return False, f"archived months revised by up to {worst:.3f}p (re-referenced)"
    return True, "same base"


def main() -> int:
    """Run daily until the rebasing: appends new old-base months (November CPI, out in early
    December, is still 2020=100), and freezes for good once ECOS serves anything else."""
    argparse.ArgumentParser(description=__doc__).parse_args()
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
    if old and old.get("frozen"):
        print(f"{OUT.name}: frozen at {old['latest_month']} ({old['frozen']}); nothing to do")
        return 0
    try:
        doc = build()
    except SystemExit as e:
        if old is None:
            raise
        # A total the old weights can no longer reproduce is what the rebasing looks like.
        old["frozen"] = f"{datetime.now(timezone.utc).date()}: {e}"
        OUT.write_text(json.dumps(old, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"{OUT.name}: frozen at {old['latest_month']} -- {e}")
        return 0
    if old:
        ok, why = same_base(old, doc)
        if not ok:
            old["frozen"] = f"{datetime.now(timezone.utc).date()}: {why}"
            OUT.write_text(json.dumps(old, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
            print(f"{OUT.name}: frozen at {old['latest_month']} -- {why}")
            return 0
        if doc["latest_month"] == old["latest_month"]:
            print(f"{OUT.name}: up to date ({old['latest_month']})")
            return 0
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB): {len(doc['items'])} codes, "
          f"{doc['months'][0]}..{doc['latest_month']}, reference {doc['price_reference_year']}; {doc['check_ko']}")
    if doc["leaves_without_series"]:
        print(f"WARN: {len(doc['leaves_without_series'])} leaves without a series", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
