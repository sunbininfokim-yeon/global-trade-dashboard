#!/usr/bin/env python3
"""Monthly Fed purchase/runoff, broken down by security type and maturity.

build_fed_qe_qt_history.py already gives one number per month per product
(net Treasuries, net MBS) since 2003, from FRED's weekly H.4.1 series. That
answers "how much" but not "of what" -- and unlike Treasuries, MBS does not
even share the same axis: the NY Fed's SOMA API reports Treasury holdings
with a maturityDate (so "remaining maturity" is a real question), but MBS
pools instead carry a `term` (their original 15yr/30yr issuance) with no
maturityDate field at all -- these are the two axes this repo can actually
measure, not the same one applied to both.

This pulls CUSIP-level SOMA holdings from the NY Fed (public API, no key) at
each month-end over the requested window, buckets Treasuries by remaining
maturity and MBS by term, and takes the month-over-month change per bucket --
the same "positive = bought, negative = ran off" convention as the existing
monthly totals.

Bucket totals are NOT rescaled to match FRED's TREAST/WSHOMCB-based monthly
figures. CUSIP par/face-value sums run a percent or two below FRED's
(TIPS inflation compensation, accrued items) even on the level, and rescaling
a *flow* by that ratio breaks down exactly when the flow is small or its sign
differs from the whole-portfolio total for that month -- which happens.
Reported as its own honestly-sourced number instead, with the size of the gap
stated as a limitation.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from bisect import bisect_right
from datetime import date, datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "public" / "data" / "fed_qeqt_buckets_v1.json"
BASE = "https://markets.newyorkfed.org/api/soma"

TSY_BUCKETS = [("le_1y", "≤1년", 0, 1), ("1_5y", "1–5년", 1, 5),
               ("5_10y", "5–10년", 5, 10), ("gt_10y", ">10년", 10, None)]
MBS_BUCKETS = {"30yr": "30년물", "15yr": "15년물"}
MBS_OTHER_ID = "other"
MBS_OTHER_LABEL = "기타"


def _get(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "macro-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_dates() -> list[str]:
    return sorted(_get(f"{BASE}/asofdates/list.json")["soma"]["asOfDates"])


def month_ends(dates: list[str], cutoff: str) -> list[str]:
    """One asOfDate per calendar month: the last published Wednesday in it."""
    window = [d for d in dates if d >= cutoff]
    by_month: dict[str, str] = {}
    for d in window:
        by_month[d[:7]] = d  # ascending, so the last write per month wins
    return [by_month[k] for k in sorted(by_month)]


def bucket_treasuries(holdings: list[dict], asof: str) -> dict[str, float]:
    ref = date.fromisoformat(asof)
    out = {bid: 0.0 for bid, *_ in TSY_BUCKETS}
    for row in holdings:
        try:
            pv = float(row["parValue"] or 0)
            md = date.fromisoformat(row["maturityDate"])
        except (KeyError, TypeError, ValueError):
            continue
        yrs = (md - ref).days / 365.25
        for bid, _, lo, hi in TSY_BUCKETS:
            if yrs > lo and (hi is None or yrs <= hi):
                out[bid] += pv
                break
    return out


def bucket_mbs(holdings: list[dict]) -> dict[str, float]:
    out = {bid: 0.0 for bid in list(MBS_BUCKETS) + [MBS_OTHER_ID]}
    for row in holdings:
        if row.get("securityType") != "MBS":
            continue
        try:
            fv = float(row.get("currentFaceValue") or 0)
        except (TypeError, ValueError):
            continue
        term = row.get("term")
        out[term if term in MBS_BUCKETS else MBS_OTHER_ID] += fv
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--pace", type=float, default=0.12)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    cutoff = f"{datetime.now(timezone.utc).year - args.years}-01-01"
    sampled = month_ends(list_dates(), cutoff)

    tsy_levels: dict[str, dict[str, float]] = {}
    mbs_levels: dict[str, dict[str, float]] = {}
    for i, asof in enumerate(sampled):
        try:
            tsy = _get(f"{BASE}/tsy/get/all/asof/{asof}.json")["soma"]["holdings"]
            agy = _get(f"{BASE}/agency/get/all/asof/{asof}.json")["soma"]["holdings"]
        except Exception as exc:  # noqa: BLE001
            print(f"  {asof}: fetch failed ({exc}) -- skipping this month")
            continue
        tsy_levels[asof[:7]] = bucket_treasuries(tsy, asof)
        mbs_levels[asof[:7]] = bucket_mbs(agy)
        if args.pace:
            time.sleep(args.pace)
        if (i + 1) % 24 == 0:
            print(f"  fetched {i + 1}/{len(sampled)} ({asof})")

    months = sorted(set(tsy_levels) & set(mbs_levels))
    if len(months) < 2:
        print("refusing to write: fewer than 2 usable months")
        return 1

    rows = []
    for prev_m, cur_m in zip(months, months[1:]):
        t_prev, t_cur = tsy_levels[prev_m], tsy_levels[cur_m]
        m_prev, m_cur = mbs_levels[prev_m], mbs_levels[cur_m]
        rows.append({
            "month": cur_m,
            "treasuries": {bid: round((t_cur[bid] - t_prev[bid]) * 1e-9, 2) for bid, *_ in TSY_BUCKETS},
            "mbs": {bid: round((m_cur[bid] - m_prev[bid]) * 1e-9, 2) for bid in m_cur},
        })

    doc = {
        "schema_version": "fed_qeqt_buckets_v1",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0)
                        .isoformat().replace("+00:00", "Z"),
        "source": "Federal Reserve Bank of New York — SOMA holdings (public API, no key)",
        "data_status": "live",
        "frequency": "monthly",
        "unit": "bn_usd",
        "tsy_bucket_labels": {bid: lbl for bid, lbl, _, _ in TSY_BUCKETS},
        "mbs_bucket_labels": {**MBS_BUCKETS, MBS_OTHER_ID: MBS_OTHER_LABEL},
        "rows": rows,
        "limitations": [
            "국채는 잔존만기, MBS는 원 발행만기(term, 15/30년물)로 축이 다릅니다 — "
            "MBS는 NY Fed 데이터에 만기일이 없고 원 발행 조건만 있습니다.",
            "이 구간별 값은 CUSIP 실측 합계이며, fed_qe_qt_history_v1.json의 "
            "FRED 기준 월간 총계(TREAST/WSHOMCB)와 완전히 일치하지 않을 수 있습니다 "
            "(TIPS 인플레이션 보정 등 회계 차이, 통상 1~3%). 강제로 맞추지 않고 "
            "각자의 실측값 그대로 둡니다.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")

    print(f"wrote {args.out} ({len(rows)} months, {rows[0]['month']} -> {rows[-1]['month']})")
    last = rows[-1]
    print(f"  {last['month']} treasuries: {last['treasuries']}")
    print(f"  {last['month']} mbs: {last['mbs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
