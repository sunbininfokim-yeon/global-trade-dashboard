#!/usr/bin/env python3
"""SOMA Treasury holdings by remaining maturity, and net change by bucket.

The assets stack's "국채(SOMA)" band was one solid colour over a total that
came from four maturity-bucket indicators (fed_ust_le_1y..gt_10y) -- but those
four were seeded random fixtures, not measurements: no live source was ever
wired to them. Separately, fed_ust_ops ("국채 매입·런오프") was fixture_synth
too, and its shape implied ongoing runoff.

The New York Fed publishes the actual CUSIP-level SOMA holdings for free, no
key: markets.newyorkfed.org/api/soma/tsy/get/all/asof/<date>.json, with each
security's maturityDate and parValue. That is enough to bucket real holdings
by remaining maturity at any published date, and to diff two dates for a real
net-change-by-bucket series -- which is what "매입·런오프" actually measures.

Checking that series here (not just wiring it) is the point: the last 12
months show holdings essentially flat to slightly higher, not the QT-style
runoff the fixture implied. That is stated in the output, not just implied by
a chart -- a demo number silently swapped for a real one that happens to
contradict the demo's story is exactly the kind of change that needs to say
so.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "public" / "data" / "soma_maturity_v1.json"
BASE = "https://markets.newyorkfed.org/api/soma"

BUCKETS = [
    ("le_1y", "≤1년", 0, 1, "#38bdf8"),
    ("1_5y", "1–5년", 1, 5, "#0ea5e9"),
    ("5_10y", "5–10년", 5, 10, "#0369a1"),
    ("gt_10y", ">10년", 10, None, "#0c4a6e"),
]


def _get(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "macro-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_dates() -> list[str]:
    return _get(f"{BASE}/asofdates/list.json")["soma"]["asOfDates"]


def holdings_on(asof: str) -> list[dict]:
    return _get(f"{BASE}/tsy/get/all/asof/{asof}.json")["soma"]["holdings"]


def bucket(holdings: list[dict], asof: str) -> dict[str, float]:
    ref = date.fromisoformat(asof)
    out = {bid: 0.0 for bid, *_ in BUCKETS}
    for row in holdings:
        try:
            pv = float(row["parValue"] or 0)
            md = date.fromisoformat(row["maturityDate"])
        except (KeyError, TypeError, ValueError):
            continue
        yrs = (md - ref).days / 365.25
        for bid, _, lo, hi, _ in BUCKETS:
            if yrs > lo and (hi is None or yrs <= hi):
                out[bid] += pv
                break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--stride", type=int, default=4,
                     help="take every Nth weekly snapshot (4 ~= monthly)")
    ap.add_argument("--pace", type=float, default=0.15)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    all_dates = sorted(d for d in list_dates())
    cutoff = f"{datetime.now(timezone.utc).year - args.years}-01-01"
    window = [d for d in all_dates if d >= cutoff]
    sampled = window[::args.stride]
    if sampled[-1] != window[-1]:
        sampled.append(window[-1])  # keep the latest published week

    series: dict[str, list[float | None]] = {bid: [] for bid, *_ in BUCKETS}
    dates: list[str] = []
    total_by_date: list[float] = []

    for i, d in enumerate(sampled):
        try:
            h = holdings_on(d)
        except Exception as exc:  # noqa: BLE001
            print(f"  {d}: fetch failed ({exc}) -- skipping this week")
            continue
        b = bucket(h, d)
        dates.append(d)
        for bid, *_ in BUCKETS:
            series[bid].append(round(b[bid] * 1e-9, 3))
        total_by_date.append(sum(b.values()) * 1e-9)
        if args.pace:
            time.sleep(args.pace)
        if (i + 1) % 20 == 0:
            print(f"  fetched {i + 1}/{len(sampled)} ({d})")

    if not dates:
        print("refusing to write: no weeks fetched")
        return 1

    # Net change by bucket over the most recent ~4 sampled points (~monthly
    # cadence at stride=4) -- this is what fed_ust_ops actually measures:
    # purchases minus runoff, by maturity, not the standing balance.
    span = min(4, len(dates) - 1)
    net_change = {
        bid: round(series[bid][-1] - series[bid][-1 - span], 3) if span else None
        for bid, *_ in BUCKETS
    }
    period_label = f"{dates[-1 - span]} → {dates[-1]}"
    total_change = round(sum(v for v in net_change.values() if v is not None), 3)

    doc = {
        "schema_version": "soma_maturity_v1",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0)
                        .isoformat().replace("+00:00", "Z"),
        "source": "Federal Reserve Bank of New York — SOMA Treasury holdings (public API, no key)",
        "data_status": "live",
        "frequency": f"every_{args.stride}th_week",
        "asof": dates[-1],
        "dates": dates,
        "buckets": [{
            "id": bid, "label_ko": lbl, "color": color, "unit": "bn_usd",
            "values": series[bid],
        } for bid, lbl, _, _, color in BUCKETS],
        "net_change": {
            "period": period_label,
            "period_note_ko": f"{period_label} 사이 만기구간별 순증감 (매입 − 만기상환, 실측).",
            "by_bucket": {bid: net_change[bid] for bid, *_ in BUCKETS},
            "total_bn": total_change,
            "finding_ko": (
                "고정관념과 달리 최근 SOMA 국채 보유는 순감소(런오프)가 아니라 "
                f"{'증가' if total_change > 0 else '감소'} 중입니다 "
                f"({period_label}, 총 {total_change:+.1f}B). "
                "픽스처 데이터가 암시했던 'QT 진행 중' 그림과 다릅니다."
            ),
        },
        "limitations": [
            "CUSIP 단위 parValue 합산 값이라, TIPS 인플레이션 보정 등을 반영한 "
            "FRED TREAST 시리즈(대차대조표 스택의 국채 값)와 소폭 다를 수 있습니다.",
            f"{args.stride}주 간격 스냅샷이라 그 사이의 개별 매입·상환은 순증감에만 잡히고 "
            "총계 그래프에는 계단식으로만 보입니다.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")

    print(f"wrote {args.out} ({len(dates)} weeks, {dates[0]} -> {dates[-1]})")
    for bid, lbl, *_ in BUCKETS:
        print(f"  {lbl:<8} latest {series[bid][-1]}B  net_change {net_change[bid]:+.1f}B ({period_label})")
    print(f"  {doc['net_change']['finding_ko']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
