"""Descriptive fixed-snapshot diagnostics, not a backtest or forecast."""
import argparse
import hashlib
import math
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from option_direction_model import PUBLIC, calendar, read, unique, write
from research_direction_diagnostics import ReviewedCalendar


def components(row):
    if row.get("quality") != "observed":
        return None
    f, m = row.get("foreign", {}), row.get("market_total", {})
    b, s, n, mb, ms = (f.get("buy_krw"), f.get("sell_krw"), f.get("net_krw"),
                       m.get("buy_krw"), m.get("sell_krw"))
    if any(v is None or not math.isfinite(v) for v in (b, s, n, mb, ms)):
        return None
    if min(b, s) < 0 or min(mb, ms) <= 0 or abs(b-s-n) > 1 or abs(mb-ms) > 1:
        return None
    if b > mb+1 or s > ms+1 or b+s <= 0:
        return None
    return {"net_share": n/mb, "imbalance": n/(b+s), "participation": (b+s)/(mb+ms)}


def targets(day, prices, cal):
    def ret(start, sf, end, ef):
        a, b = prices.get(start, {}).get(sf), prices.get(end, {}).get(ef)
        if any(x is None or not math.isfinite(x) or x <= 0 for x in (a,b)):
            return None
        return b/a-1
    pos = cal.sessions.get_loc(day)
    days = cal.sessions[pos:pos+4].strftime("%Y-%m-%d").tolist()
    out = {"same_intraday": ret(day,"open",day,"close")}
    for h in (1,2,3):
        if len(days) <= h:
            continue
        out[f"day{h}_intraday"] = ret(days[h],"open",days[h],"close")
        if h == 1:
            out["next_gap"] = ret(day,"close",days[1],"open")
        else:
            out[f"hold{h}"] = ret(days[1],"open",days[h],"close")
    return out


def association(rows, feature, target):
    pairs = [(r["features"][feature], r["targets"].get(target)) for r in rows
             if r["targets"].get(target) is not None]
    if len(pairs) < 20:
        return {"n": len(pairs), "spearman": None}
    x,y = np.array(pairs).T
    rho = None if np.std(x)==0 or np.std(y)==0 else float(spearmanr(x,y).statistic)
    return {"n":len(pairs), "spearman":rho}


def run(board, etfs):
    cal = ReviewedCalendar(calendar())
    products = board["kr"]["investor_nets"]["detailed_15007"]["products"]
    data, audit = {}, {}
    for side in ("call", "put"):
        source = unique(products[f"options_{side}"]["series"])
        good = {d:components(r) for d,r in source.items() if cal.is_session(d)}
        data[side] = {d:v for d,v in good.items() if v is not None}
        audit[side] = {"source_n":len(source), "usable_n":len(data[side]),
                       "first":min(source),"last":max(source),
                       "excluded":sorted(set(source)-set(data[side]))}
    candidate = next(c for c in etfs["candidates"] if c["ticker"]=="069500")
    prices = unique(candidate["rows"])
    rows = []
    for d in sorted(set(data["call"]) & set(data["put"]) & set(prices)):
        features = {f"{side}_{k}":v for side in data for k,v in data[side][d].items()}
        rows.append({"date":d,"features":features,"targets":targets(d,prices,cal)})
    target_names = ["same_intraday","next_gap","day1_intraday","day2_intraday",
                    "day3_intraday","hold2","hold3"]
    groups = {"all":rows}
    groups.update({str(y):[r for r in rows if r["date"].startswith(str(y))]
                   for y in sorted({int(r["date"][:4]) for r in rows})})
    stats = {group:{f:{t:association(rs,f,t) for t in target_names} for f in rows[0]["features"]}
             for group,rs in groups.items()} if rows else {}
    return {"status":"descriptive_research_only", "audit":audit,
            "price_adjustment":candidate.get("price_adjustment"),
            "common_n":len(rows),"latest_components":rows[-1] if rows else None,
            "associations":stats,
            "limitations":["Frozen local snapshot, not latest-main coverage",
                "No predictive validation, no causal inference, no significance claims",
                "Same-day association uses end-of-day information",
                "Historical availability and adjusted OHLC common factor unverified",
                "Annual splits describe stability; they are not independent holdouts"]}


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--board",type=Path,default=PUBLIC/"derivatives_board_v1.json")
    p.add_argument("--prices",type=Path,default=PUBLIC/"kospi200_etf_candidates_daily_v1.json")
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    report=run(read(args.board),read(args.prices))
    report["input_sha256"]={path.name:hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in (args.board,args.prices)}
    report["code_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    write(args.output,report)
    print({"common_n":report["common_n"],"output":str(args.output)})
