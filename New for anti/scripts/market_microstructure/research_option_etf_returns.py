"""Exploratory fixed-rule associations, never a live trading recommendation."""
import hashlib
import json
from pathlib import Path
from statistics import mean
from build_kospi200_price_panel import PUBLIC, ROOT


def summarize(values):
    return {"n": len(values), "mean_pct": mean(values) * 100 if values else None,
            "positive_pct": mean(v > 0 for v in values) * 100 if values else None}


def main():
    names = ["derivatives_board_v1.json", "kospi200_etf_candidates_daily_v1.json"]
    raw = {name: (PUBLIC / name).read_bytes() for name in names}
    board, etfs = (json.loads(raw[name]) for name in names)
    products = board["kr"]["investor_nets"]["detailed_15007"]["products"]
    flows = {}
    for name in ("options_call", "options_put"):
        flows[name] = {r["date"]: r["foreign"]["net_krw"] / r["market_total"]["buy_krw"]
                       for r in products[name]["series"] if r.get("quality") == "observed"
                       and r["market_total"].get("buy_krw", 0) > 0
                       and r["foreign"].get("net_krw") is not None}
    result = {"input_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()},
        "method": {"rules": "fixed signs; no optimization or fitted model",
          "split": "2019-2023 discovery / 2024-2026 chronological evaluation by outcome date",
          "limitations": ["Exploratory, not an untouched holdout", "Historical publication times unknown",
            "Adjusted close-to-close is an association, not executable P&L",
            "Next open-to-close assumes common daily OHLC adjustment factor; unverified",
            "Costs 5/10/20bps are illustrative round trip, not actual quotes",
            "Exclude TIGER 2026-10-29 unexplained adjustment-reset outcome",
            "No LETF, cash-flow, or activity-gap inputs; no short strategy inferred"]}, "tickers": {}}
    for code in ("069500", "102110"):
        rows = sorted(next(c["rows"] for c in etfs["candidates"] if c["ticker"] == code), key=lambda r:r["date"])
        records = []
        for current, following in zip(rows, rows[1:]):
            day, outcome = current["date"], following["date"]
            if code == "102110" and outcome == "2026-10-29":
                continue
            if not all(day in flows[n] for n in flows):
                continue
            call, put = (flows[n][day] for n in ("options_call", "options_put"))
            if min(current["close"], following["close"], following["open"]) <= 0:
                raise ValueError("invalid price")
            records.append({"date": outcome, "call_positive": call > 0, "put_positive": put > 0,
                "spread_positive": call - put > 0,
                "adjusted_close_to_close": following["close"] / current["close"] - 1,
                "next_open_to_close_assumed": following["close"] / following["open"] - 1})
        sections = {}
        for label, low, high in (("discovery", "2019", "2024"), ("evaluation", "2024", "2027")):
            sample = [r for r in records if low <= r["date"] < high]
            section = {}
            for target in ("adjusted_close_to_close", "next_open_to_close_assumed"):
                stats = {"baseline": summarize([r[target] for r in sample])}
                for rule in ("call_positive", "put_positive", "spread_positive"):
                    values = [r[target] for r in sample if r[rule]]
                    stats[rule] = summarize(values)
                    if target == "next_open_to_close_assumed":
                        stats[rule]["net_mean_pct_by_cost_bps"] = {
                            str(cost): mean(values)*100-cost/100 if values else None for cost in (5,10,20)}
                section[target] = stats
            sections[label] = section
        result["tickers"][code] = sections
    path = ROOT.parent / "data/manifests/option_etf_exploration_20261101.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(path)


if __name__ == "__main__":
    main()
