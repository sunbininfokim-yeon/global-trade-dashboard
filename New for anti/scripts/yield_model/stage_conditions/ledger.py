"""Live scorecard for the stage calls.

The history check in build.py re-judges past seasons with today's rules, so
it says how the rules fit the past, not how the published calls did. This
ledger keeps the call as published: once every stage of a season is done
it is frozen (never rewritten), and when that year's official yield reaches
the model's training table it is scored against the 10-year trend, the same
yardstick as the history check.

  unfavourable -> hit when the yield came in below trend
  favourable   -> hit when it came in above trend
  neutral      -> recorded, not scored

ledger.json is committed next to this file.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger.json")
RECENT = 12


def load(path=LEDGER):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"started": None, "entries": {}}


def save(ledger, path=LEDGER):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def _complete(entry):
    stages = entry.get("stages") or []
    return bool(stages) and all(s.get("state") == "done" for s in stages)


def freeze(ledger, regions, today):
    """Record each completed season's call once. Returns the keys added."""
    added = []
    ledger["started"] = ledger.get("started") or today.isoformat()
    for region, entries in regions.items():
        for e in entries:
            if not _complete(e) or e.get("harvest_year") is None:
                continue
            key = f"{region}|{e['crop']}|{e['harvest_year']}"
            if key in ledger["entries"]:
                continue
            ov = e.get("overall") or {}
            ledger["entries"][key] = {
                "region": region, "crop": e["crop"], "label_ko": e.get("label_ko"),
                "season": e.get("season"), "harvest_year": int(e["harvest_year"]),
                "verdict": ov.get("verdict"), "verdict_ko": ov.get("verdict_ko"),
                "score": ov.get("score"), "history_check": ov.get("history_check"),
                "frozen_on": today.isoformat(),
            }
            added.append(key)
    return added


def score(ledger, residual_for):
    """Fill outcomes where the yield is now known. residual_for(region, crop)
    returns {year: log residual vs trend} or None."""
    scored = []
    cache = {}
    for key, row in ledger["entries"].items():
        if "residual_pct" in row:
            continue
        ck = (row["region"], row["crop"])
        if ck not in cache:
            cache[ck] = residual_for(*ck)
        res = cache[ck]
        if res is None or row["harvest_year"] not in res:
            continue
        r = round(float(res[row["harvest_year"]]) * 100, 1)
        row["residual_pct"] = r
        row["hit"] = (r < 0 if row["verdict"] == "unfavorable"
                      else r > 0 if row["verdict"] == "favorable" else None)
        scored.append(key)
    return scored


def summary(ledger):
    rows = list(ledger["entries"].values())
    done = [r for r in rows if "residual_pct" in r]
    out = {"started": ledger.get("started"), "frozen": len(rows), "scored": len(done),
           "pending": len(rows) - len(done)}
    for v in ("unfavorable", "favorable"):
        mine = [r for r in done if r["verdict"] == v]
        # A call flagged reference-only is kept apart: it never claimed much.
        firm = [r for r in mine if r.get("history_check") != "unmatched"]
        out[v] = {"n": len(mine), "hits": sum(1 for r in mine if r["hit"]),
                  "firm_n": len(firm), "firm_hits": sum(1 for r in firm if r["hit"])}
    neutral = [r["residual_pct"] for r in done if r["verdict"] == "neutral"]
    out["neutral"] = {"n": len(neutral),
                      "mean_residual_pct": round(sum(neutral) / len(neutral), 1) if neutral else None}
    out["recent"] = sorted(done, key=lambda r: (r["harvest_year"], r["region"]), reverse=True)[:RECENT]
    return out


def entry_record(ledger, region, crop):
    """Scored seasons for one region and crop, newest first, for its card."""
    rows = [r for r in ledger["entries"].values()
            if r["region"] == region and r["crop"] == crop and "residual_pct" in r]
    return sorted(rows, key=lambda r: -r["harvest_year"])
