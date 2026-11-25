#!/usr/bin/env python3
"""Publish KOSPI 200 covered-call ETF supply for the UI.

    public/data/covered_call_supply_v1.json

Covered-call ETFs on the KOSPI 200 sell index calls on a schedule written
into the name of the index each one tracks ("타겟 15% 위클리", "위클리 고정
30%", "커버드콜 5% OTM", "ATM"). With each fund's size, that rule turns into
an estimate of how much call notional the funds write per week -- the
"covered-call writing flow" side of the market, the mirror image of the
daily leveraged-ETF rebalancing the overseas LETF board tracks.

Sources
  --seed-krx PATH   krx-month-paste checkout: KRX 13101 ETF EOD
                    (data/normalized/etf_eod), the history.
  --live            FinanceDataReader ETF/KR listing (today's market cap) and
                    KS200 closes. Appended under the last KS200 trading date;
                    nothing is appended when that date is unknown.

Size is market cap (종가 × 상장좌수). KRX's 순자산총액 column is blank in the
13101 export since 2026-09, and FDR carries no NAV, so market cap is used
throughout -- for an ETF it sits within a fraction of a percent of NAV.

Everything here except market cap is an estimate from published index rules,
not observed fund orders. The output says so per field.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "../../public/data/covered_call_supply_v1.json"
SCHEMA_VERSION = "covered-call-supply-v1"
# KOSPI 200 option multiplier (원 per index point), since the 2017 change.
K200_MULTIPLIER = 250_000
WEEKS_PER_MONTH = 52 / 12

# Hong Kong-listed KOSPI 200 covered call. Facts from the listing report
# (2026-07-31); no daily AUM source yet, so it is listed, not sized.
OVERSEAS = [{
    "ticker": "3537.HK",
    "name": "CSOP KOSPI 200 Covered Call Active ETF",
    "listed": "2026-07-31",
    "structure_ko": "합성 대표 표본 추출 — 코스피200 선물 보유 + 코스피200 지수 콜옵션 매도",
    "distribution_ko": "월 분배 목표",
    "fee_pct": 0.99,
    "listing_price_hkd": 7.8,
    "board_lot": 100,
    "coverage_ko": "액티브 — 커버 비율·행사가 비공개",
    "sized": False,
    "source_ko": "상장 보도 (2026-07-31)",
}]


def is_k200_covered_call(name: str) -> bool:
    """KOSPI 200 covered-call ETFs; leveraged covered-call wrappers excluded
    (their call notional is not their market cap)."""
    return "커버드콜" in name and "200" in name and "레버리지" not in name


def parse_rule(index_name: str | None, name: str) -> dict[str, Any]:
    """Call-writing rule read off the tracked index's published name."""
    text = f"{index_name or ''} {name}"
    weekly = "위클리" in text
    rule: dict[str, Any] = {
        "tenor": "weekly" if weekly else "monthly",
        "coverage_pct": None, "otm_pct": None, "target_premium_pct": None,
        "rule_source": "index_name" if index_name else "etf_name",
        "kind": None,
    }
    m_target = re.search(r"타겟\s*(\d+(?:\.\d+)?)\s*%", text)
    m_fixed = re.search(r"고정\s*(\d+(?:\.\d+)?)\s*%", text)
    m_otm = re.search(r"(\d+(?:\.\d+)?)\s*%\s*OTM", text)
    if m_target:
        rule.update(kind="target_premium", target_premium_pct=float(m_target.group(1)))
    elif m_fixed:
        rule.update(kind="fixed_coverage", coverage_pct=float(m_fixed.group(1)), otm_pct=0.0)
    elif m_otm:
        rule.update(kind="fixed_coverage", coverage_pct=100.0, otm_pct=float(m_otm.group(1)))
    elif "ATM" in text.upper():
        rule.update(kind="fixed_coverage", coverage_pct=100.0, otm_pct=0.0)
    else:
        rule["kind"] = "unknown"
    if "채권혼합" in text or "KTB" in text:
        rule["mixed_with_bonds"] = True
    return rule


def _read_seed(source: Path) -> dict[str, dict[str, dict[str, Any]]]:
    base = source / "data" / "normalized" / "etf_eod"
    by_date: dict[str, dict[str, dict[str, Any]]] = {}
    for part in sorted(base.glob("year=*/month=*/part.jsonl.gz")):
        with gzip.open(part, "rt", encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                name = str(r.get("etf_name") or "")
                if not r.get("date") or not is_k200_covered_call(name):
                    continue
                mcap = r.get("market_cap_krw")
                if not isinstance(mcap, (int, float)) or mcap <= 0:
                    continue
                prev = by_date.setdefault(r["date"], {}).get(r["etf_ticker"])
                if prev is None or str(r.get("collected_at") or "") >= str(prev.get("collected_at") or ""):
                    by_date[r["date"]][r["etf_ticker"]] = {
                        "name": name, "index_name": r.get("index_name"), "mcap_krw": float(mcap),
                        "collected_at": r.get("collected_at")}
    return by_date


def _k200_closes(start: str) -> dict[str, float]:
    import FinanceDataReader as fdr

    df = fdr.DataReader("KS200", start)
    out = {}
    for idx, row in df.iterrows():
        c = row.get("Close")
        if c is not None and c == c and c > 0:
            out[idx.strftime("%Y-%m-%d")] = float(c)
    return out


def _read_live() -> tuple[str | None, dict[str, dict[str, Any]]]:
    import FinanceDataReader as fdr

    etfs = fdr.StockListing("ETF/KR")
    if "MarCap" not in etfs.columns:
        raise RuntimeError("FDR ETF/KR listing has no MarCap column")
    rows: dict[str, dict[str, Any]] = {}
    for _, r in etfs.iterrows():
        name = str(r.get("Name") or "")
        if not is_k200_covered_call(name):
            continue
        mc = r.get("MarCap")
        if mc is None or mc != mc or float(mc) <= 0:
            continue
        # FDR publishes ETF MarCap in 백만원.
        rows[str(r.get("Symbol"))] = {"name": name, "index_name": None, "mcap_krw": float(mc) * 1e6}
    return None, rows


def build(seed: dict, live: tuple[str | None, dict] | None, k200: dict[str, float],
          previous: dict | None) -> dict[str, Any]:
    history: dict[str, dict[str, Any]] = {}
    products: dict[str, dict[str, Any]] = {}

    def add_day(day: str, rows: dict[str, dict[str, Any]], source: str) -> None:
        by = {t: round(v["mcap_krw"]) for t, v in rows.items()}
        history[day] = {"date": day, "source": source, "by_ticker": by}
        for t, v in rows.items():
            p = products.setdefault(t, {"ticker": t, "name": v["name"], "index_name": v.get("index_name")})
            p["name"] = v["name"]
            if v.get("index_name"):
                p["index_name"] = v["index_name"]

    for h in (previous or {}).get("history") or []:
        history[h["date"]] = h
    for p in (previous or {}).get("products") or []:
        products[p["ticker"]] = {k: p.get(k) for k in ("ticker", "name", "index_name")}
    for day, rows in sorted(seed.items()):
        add_day(day, rows, "KRX 13101 ETF EOD (krx-month-paste)")
    if live and live[0] and live[1]:
        add_day(live[0], live[1], "FinanceDataReader ETF/KR")

    for p in products.values():
        p["rule"] = parse_rule(p.get("index_name"), p["name"])

    rows_out = []
    for day in sorted(history):
        h = history[day]
        total = sum(h["by_ticker"].values())
        k = k200.get(day) or h.get("k200")
        rows_out.append({**h, "total_mcap_krw": total, "k200": k, **_estimate(h["by_ticker"], products, k)})
    latest = rows_out[-1] if rows_out else None
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": latest["date"] if latest else None,
        "unit": "krw",
        "multiplier": K200_MULTIPLIER,
        "products": sorted(products.values(), key=lambda p: -(latest or {}).get("by_ticker", {}).get(p["ticker"], 0)),
        "history": rows_out,
        "overseas": OVERSEAS,
        "notes_ko": [
            "규모는 시가총액(종가×상장좌수)입니다. KRX 순자산총액 열이 2026-09부터 비어 있어 대신 씁니다.",
            "콜 매도 규칙은 각 ETF가 추종하는 지수 이름에서 읽은 것입니다(타겟 %, 고정 %, OTM %, ATM). 실제 운용 주문이 아닙니다.",
            "고정 커버 상품: 주당 콜 매도 명목 = 시총 × 커버 비율 (월물은 ÷ 52/12). 계약 수 = 명목 ÷ (코스피200 × 25만원).",
            "타겟 프리미엄 상품: 커버 비율이 시장 IV에 따라 바뀌어 명목을 알 수 없으므로, 목표를 맞추려면 매주 받아야 하는 프리미엄(시총 × 목표% ÷ 52)만 계산합니다.",
            "레버리지 커버드콜 ETF는 시총이 콜 명목이 아니어서 제외합니다.",
        ],
    }


def _estimate(by_ticker: dict[str, float], products: dict, k200: float | None) -> dict[str, Any]:
    fixed_week = 0.0
    target_prem_week = 0.0
    unknown = 0.0
    for t, mcap in by_ticker.items():
        rule = (products.get(t) or {}).get("rule") or {}
        if rule.get("kind") == "fixed_coverage" and rule.get("coverage_pct") is not None:
            notional = mcap * rule["coverage_pct"] / 100
            fixed_week += notional if rule["tenor"] == "weekly" else notional / WEEKS_PER_MONTH
        elif rule.get("kind") == "target_premium" and rule.get("target_premium_pct") is not None:
            target_prem_week += mcap * rule["target_premium_pct"] / 100 / 52
        else:
            unknown += mcap
    return {
        "est_fixed_call_notional_per_week_krw": round(fixed_week),
        "est_fixed_call_contracts_per_week": round(fixed_week / (k200 * K200_MULTIPLIER)) if k200 else None,
        "est_target_premium_per_week_krw": round(target_prem_week),
        "unclassified_mcap_krw": round(unknown),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed-krx", type=Path, default=None)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--print-stats", action="store_true")
    args = ap.parse_args()

    previous = None
    if args.out.is_file():
        try:
            previous = json.loads(args.out.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = None
    seed = _read_seed(args.seed_krx) if args.seed_krx and args.seed_krx.is_dir() else {}
    live = None
    k200: dict[str, float] = {}
    if args.live:
        dates = sorted(seed) + [h["date"] for h in (previous or {}).get("history") or []]
        try:
            k200 = _k200_closes(min(dates) if dates else "2023-01-01")
        except Exception as exc:  # noqa: BLE001
            print(f"KS200 closes unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        try:
            _, rows = _read_live()
            last_day = max(k200) if k200 else None
            live = (last_day, rows)
            if not last_day:
                print("no KS200 trading date; today's listing not appended", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"FDR ETF/KR unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
    payload = build(seed, live, k200, previous)
    if not payload["history"]:
        print("no covered-call observations; nothing written", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    if args.print_stats:
        lt = payload["history"][-1]
        print(json.dumps({"as_of": payload["as_of"], "days": len(payload["history"]), "products": len(payload["products"]),
                          "total_mcap_jo": round(lt["total_mcap_krw"] / 1e12, 2),
                          "est_fixed_week_eok": round(lt["est_fixed_call_notional_per_week_krw"] / 1e8),
                          "est_target_prem_week_eok": round(lt["est_target_premium_per_week_krw"] / 1e8),
                          "k200": lt["k200"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
