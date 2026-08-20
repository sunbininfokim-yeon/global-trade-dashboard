#!/usr/bin/env python3
"""Build the Fed balance sheet's liability stack and the reserves/GDP ratio.

The 연준 총자산 card shows one number (6.7T) and one line. That answers "how
big" but not "made of what", and the composition is where the liquidity signal
lives: the same 6.7T total means very different things depending on whether the
Fed's liabilities sit in reserve balances (banks' usable cash) or in currency
and the TGA (which are not).

Reserve balances are the bottom layer here, against the axis, because the
question this chart exists to answer is how much room is left above zero before
reserves become scarce -- and a layer stacked on top of others has no readable
distance to the axis.

The companion ratio is reserves as a share of nominal GDP. The 10% marker is
the level the Fed's own ample-reserves discussion treats as the rough boundary
below which reserves stop being abundant; it is a reference line, not a
forecast or a trigger, and it is drawn as one because as of 2026-08 the ratio
has already crossed it.

All series are FRED public CSV, no key:
  WALCL     total assets (mn)          WRESBAL   reserve balances (mn)
  WCURCIR   currency in circulation    WTREGEN   Treasury General Account (mn)
  RRPONTTLD ON RRP balance (bn, daily) GDP       nominal GDP (bn, quarterly)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"
DEFAULT_OUT = ROOT / "fed_balance_sheet_v1.json"

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"

# The H.4.1 liability side, ordered as they stack from the axis upward.
# Reserve balances lead deliberately -- see the module docstring.
LAYERS = [
    {"id": "reserves", "sid": "WRESBAL", "scale": 1e-6, "label_ko": "지급준비금",
     "label_en": "Reserve balances", "color": "#f97316",
     "note_ko": "은행이 연준에 예치한 잔액. 시중 유동성으로 실제 쓰일 수 있는 부분."},
    {"id": "currency", "sid": "WCURCIR", "scale": 1e-6, "label_ko": "유통현금",
     "label_en": "Currency in circulation", "color": "#3b82f6",
     "note_ko": "민간이 보유한 지폐. 연준이 임의로 회수할 수 없어 사실상 하한선으로 작동한다."},
    {"id": "tga", "sid": "WTREGEN", "scale": 1e-6, "label_ko": "재무부 일반계정(TGA)",
     "label_en": "Treasury General Account", "color": "#38bdf8",
     "note_ko": "재무부가 연준에 둔 현금. 늘면 그만큼 지급준비금에서 빠져나간다."},
    {"id": "on_rrp", "sid": "RRPONTTLD", "scale": 1e-3, "label_ko": "역레포(ON RRP)",
     "label_en": "Overnight reverse repo", "color": "#a78bfa",
     "note_ko": "MMF 등이 연준에 하루 맡긴 잔액. 2026년 들어 거의 소진됐다."},
]

# Total assets must equal total liabilities; whatever the four named layers do
# not account for is capital and the smaller liability lines. Shown as its own
# band rather than folded into a neighbour, so no named layer is inflated.
RESIDUAL = {"id": "other", "label_ko": "기타 부채·자본", "label_en": "Other liabilities & capital",
            "color": "#22c55e",
            "note_ko": "총자산에서 위 4개 항목을 뺀 나머지(자본금, 기타 예금 등). 잔차로 계산된다."}

RATIO_THRESHOLD_PCT = 10.0


def fetch(sid: str, timeout: int = 30) -> list[tuple[str, float]]:
    req = urllib.request.Request(FRED_CSV.format(sid=sid),
                                 headers={"User-Agent": "macro-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        date = (row.get("observation_date") or row.get("DATE") or "").strip()
        raw = (row.get(sid) or "").strip()
        if not date or not raw or raw == ".":
            continue
        try:
            rows.append((date, float(raw)))
        except ValueError:
            continue
    return rows


def as_of(series: list[tuple[str, float]], date: str) -> float | None:
    """Latest observation on or before `date`.

    The balance sheet is weekly (Wednesday) while ON RRP is daily and GDP is
    quarterly, so the lower-frequency and higher-frequency series both have to
    be read as "what was known as of this week" rather than interpolated --
    interpolating GDP would invent quarters that were never published.
    """
    hit = None
    for d, v in series:
        if d <= date:
            hit = v
        else:
            break
    return hit


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--years", type=int, default=10)
    args = ap.parse_args()

    total = fetch("WALCL")
    if not total:
        print("refusing to write: WALCL returned nothing")
        return 1

    raw = {spec["id"]: fetch(spec["sid"]) for spec in LAYERS}
    gdp = fetch("GDP")
    missing = [k for k, v in raw.items() if not v]
    if missing:
        print(f"refusing to write: no observations for {missing}")
        return 1

    cutoff = f"{datetime.now(timezone.utc).year - args.years}-01-01"
    weeks = [(d, v * 1e-6) for d, v in total if d >= cutoff]  # mn → tn

    dates = [d for d, _ in weeks]
    totals = [v for _, v in weeks]
    stacks: dict[str, list[float | None]] = {spec["id"]: [] for spec in LAYERS}
    residual: list[float | None] = []
    ratio: list[float | None] = []

    for (date, tot) in weeks:
        named = 0.0
        complete = True
        for spec in LAYERS:
            hit = as_of(raw[spec["id"]], date)
            val = None if hit is None else hit * spec["scale"]
            stacks[spec["id"]].append(None if val is None else round(val, 4))
            if val is None:
                complete = False
            else:
                named += val
        # Only a week with every named layer present can have a meaningful
        # residual; otherwise the gap would silently absorb the missing layer.
        residual.append(round(tot - named, 4) if complete else None)

        res = as_of(raw["reserves"], date)
        g = as_of(gdp, date)
        # WRESBAL is millions, GDP is billions -- one scale-up, then percent.
        ratio.append(round((res * 1e-3) / g * 100, 3) if (res is not None and g) else None)

    layers = [{
        "id": s["id"], "label_ko": s["label_ko"], "label_en": s["label_en"],
        "color": s["color"], "note_ko": s["note_ko"], "unit": "tn_usd",
        "fred_series_id": s["sid"], "values": stacks[s["id"]],
    } for s in LAYERS]
    layers.append({**RESIDUAL, "unit": "tn_usd", "fred_series_id": None,
                   "derived": "WALCL - (WRESBAL + WCURCIR + WTREGEN + RRPONTTLD)",
                   "values": residual})

    latest_i = len(dates) - 1
    doc = {
        "schema_version": "fed_balance_sheet_v1",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0)
                        .isoformat().replace("+00:00", "Z"),
        "source": "FRED (Federal Reserve H.4.1) — public CSV, no API key",
        "data_status": "live",
        "frequency": "weekly_wednesday",
        "unit": "tn_usd",
        "asof": dates[latest_i],
        "dates": dates,
        "total": {"label_ko": "총자산", "fred_series_id": "WALCL",
                  "values": [round(v, 4) for v in totals]},
        "stack_note_ko": ("부채 항목을 아래에서부터 쌓은 그래프입니다. 지급준비금을 "
                          "x축에 붙인 이유는, 이 그래프가 답하려는 질문이 '지급준비금이 "
                          "바닥까지 얼마나 남았는가'이기 때문입니다."),
        "layers": layers,
        "ratio": {
            "id": "reserves_to_gdp",
            "label_ko": "지급준비금 / 명목 GDP",
            "label_en": "Reserve balances as % of nominal GDP",
            "unit": "%",
            "values": ratio,
            "threshold_pct": RATIO_THRESHOLD_PCT,
            "threshold_label_ko": "10% 기준선",
            "threshold_note_ko": ("연준의 충분지준(ample reserves) 논의에서 대략의 경계로 "
                                  "언급되는 수준입니다. 정책 트리거나 예측이 아니라 참고선이며, "
                                  "이 선을 밑돈다고 자동으로 어떤 조치가 뒤따르지는 않습니다."),
            "sources": {"reserves": "WRESBAL", "gdp": "GDP"},
            "gdp_note_ko": "GDP는 분기 발표라 각 주차에는 그 시점에 공표돼 있던 직전 분기값을 사용합니다.",
        },
        "limitations": [
            "H.4.1은 수요일 기준 주간 자료이며, 최근 주차는 이후 개정될 수 있습니다.",
            "'기타 부채·자본'은 개별 계정을 받아온 값이 아니라 총자산에서 나머지를 뺀 잔차입니다.",
            "10% 기준선은 참고용 문헌값이며 연준이 공표한 목표치가 아닙니다.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")

    print(f"wrote {args.out}")
    print(f"  {len(dates)} weeks, {dates[0]} → {dates[latest_i]}")
    print(f"  total {totals[latest_i]:.2f}tn")
    for lay in layers:
        v = lay["values"][latest_i]
        print(f"    {lay['label_ko']:<18} {('—' if v is None else f'{v:.2f}tn')}")
    r = ratio[latest_i]
    if r is not None:
        side = "아래" if r < RATIO_THRESHOLD_PCT else "위"
        print(f"  지급준비금/GDP {r:.2f}% ({RATIO_THRESHOLD_PCT:.0f}% 기준선 {side})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
