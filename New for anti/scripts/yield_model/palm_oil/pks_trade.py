"""
PKS (palm kernel shell) imports by the two big buyers, from UN Comtrade.

Usage: python3 -m palm_oil.pks_trade     # -> training/pks_imports.csv,
                                         #    public/data/pks_imports_v1.json

Japan reports PKS under HS 1404.90 ("vegetable products n.e.s."): its 2024
imports of that code from Indonesia and Malaysia were 3.58 Mt at about
$157/t, the PKS price, so the code is read as PKS there. Korea's PKS line is
not settled: its 1404.90 imports from the two are only ~6 kt, and its
candidate codes (4401.31 wood pellets ~0.77 Mt, 2306.60 palm kernel cake
~0.96 Mt) are other products or mixed. Korean rows are collected for those
candidates but shown only for codes listed in PKS_HS, which stays empty for
Korea until the right customs code is confirmed.

Source: Comtrade public preview API (no key, one period per call, capped at
500 rows, rate limited), so calls are spaced and a 429 waits and retries.
Reachable from Actions.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "training", "pks_imports.csv")
PUBLIC = os.path.normpath(os.path.join(HERE, "..", "..", "..", "public", "data"))
OUT_JSON = os.path.join(PUBLIC, "pks_imports_v1.json")
URL = ("https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS?reporterCode={reporters}"
       "&period={period}&partnerCode={partners}&cmdCode={codes}&flowCode=M")

REPORTERS = {"392": "일본", "410": "한국"}
PARTNERS = {"360": "인도네시아", "458": "말레이시아"}
COLLECT_HS = ["140490", "440131", "230660"]
# Codes read as PKS, per importer. Korea stays empty until confirmed.
PKS_HS = {"392": ["140490"], "410": []}
FIRST_YEAR = 2015
MONTHS_BACK = 30
GAP_S = 6


def log(msg):
    print(f"[palm-oil:pks-trade] {msg}", flush=True)


def _get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            time.sleep(GAP_S * (i + 2))
    return None


def fetch(freq, period):
    body = _get(URL.format(freq=freq, period=period, reporters=",".join(REPORTERS),
                           partners=",".join(PARTNERS), codes=",".join(COLLECT_HS)))
    rows = []
    for x in (body or {}).get("data", []):
        if str(x.get("partner2Code")) not in ("0", "None") or x.get("customsCode") not in ("C00", None):
            continue
        rows.append({"freq": freq, "period": str(x["period"]), "reporter": str(x["reporterCode"]),
                     "partner": str(x["partnerCode"]), "hs": str(x["cmdCode"]),
                     "net_kg": x.get("netWgt"), "value_usd": x.get("primaryValue")})
    return rows


def _months(today, back):
    y, m = today.year, today.month
    out = []
    for _ in range(back):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y}{m:02d}")
    return out[::-1]


def collect(today=None):
    today = today or date.today()
    old = pd.read_csv(CSV, dtype=str) if os.path.exists(CSV) else pd.DataFrame()
    have = set(zip(old.get("freq", []), old.get("period", [])))
    # Years two or more back are settled; recent ones and months are re-read.
    jobs = [("A", str(y)) for y in range(FIRST_YEAR, today.year)
            if y >= today.year - 2 or ("A", str(y)) not in have]
    jobs += [("M", p) for p in _months(today, MONTHS_BACK)]
    rows, failed = [], 0
    for freq, period in jobs:
        time.sleep(GAP_S)
        try:
            got = fetch(freq, period)
        except Exception as exc:  # keep what was read before
            failed += 1
            log(f"{freq} {period}: {exc}")
            continue
        rows.extend(got)
        if got:
            have.add((freq, period))
    new = pd.DataFrame(rows, dtype=str)
    if new.empty and old.empty:
        raise SystemExit("Comtrade: nothing read")
    keep = old
    if not new.empty and not old.empty:
        fetched = set(zip(new.freq, new.period))
        keep = old[[(f, p) not in fetched for f, p in zip(old.freq, old.period)]]
    out = pd.concat([keep, new], ignore_index=True)
    out = out.sort_values(["freq", "period", "reporter", "partner", "hs"])
    os.makedirs(os.path.dirname(CSV), exist_ok=True)
    out.to_csv(CSV, index=False)
    log(f"{len(jobs)} calls, {failed} failed, {len(out)} rows -> {CSV}")
    return out


def _pks_rows(frame):
    d = frame.copy()
    d["net_kg"] = pd.to_numeric(d.net_kg, errors="coerce")
    d["value_usd"] = pd.to_numeric(d.value_usd, errors="coerce")
    mask = [h in PKS_HS.get(r, []) for r, h in zip(d.reporter.astype(str), d.hs.astype(str))]
    return d[mask]


def _pct(a, b):
    return None if not a or not b else round((a / b - 1) * 100, 1)


def summary(frame=None):
    """Imports read as PKS: annual series and the last 12 reported months."""
    if frame is None:
        frame = pd.read_csv(CSV, dtype=str)
    d = _pks_rows(frame)
    if d.empty:
        return None
    annual = (d[d.freq == "A"].groupby(["period", "reporter", "partner"]).net_kg.sum()
              .div(1e6).round(0).reset_index())
    years = []
    for y, g in annual.groupby("period"):
        years.append({"year": int(y), "total_kt": float(g.net_kg.sum()),
                      "by_origin_kt": {PARTNERS[p]: float(v) for p, v in
                                       g.groupby("partner").net_kg.sum().items()}})
    m = d[d.freq == "M"].copy()
    m["month"] = pd.to_datetime(m.period, format="%Y%m")
    importers = []
    for rep, g in m.groupby("reporter"):
        by_month = g.groupby("month").agg(net_kg=("net_kg", "sum"), value_usd=("value_usd", "sum"))
        if len(by_month) < 13:
            continue
        last = by_month.index.max()
        cur = by_month[by_month.index > last - pd.DateOffset(months=12)]
        prev = by_month[(by_month.index <= last - pd.DateOffset(months=12))
                        & (by_month.index > last - pd.DateOffset(months=24))]
        if len(cur) < 12:
            continue
        origin = (g[g.month > last - pd.DateOffset(months=12)].groupby("partner").net_kg.sum() / 1e6)
        importers.append({
            "importer": REPORTERS[rep],
            "last_month": last.strftime("%Y-%m"),
            "last12_kt": round(float(cur.net_kg.sum() / 1e6), 0),
            "last12_yoy_pct": _pct(cur.net_kg.sum(), prev.net_kg.sum()) if len(prev) == 12 else None,
            "price_usd_t": round(float(cur.value_usd.sum() / (cur.net_kg.sum() / 1000)), 1),
            "by_origin_kt": {PARTNERS[p]: round(float(v), 0) for p, v in origin.items()},
            "hs": PKS_HS[rep],
            "series": [{"month": i.strftime("%Y-%m"), "kt": round(float(r.net_kg / 1e6), 1)}
                       for i, r in by_month.tail(24).iterrows()],
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "annual": years,
        "importers": importers,
        "note_ko": ("UN Comtrade 수입국 신고 기준. 일본은 HS 1404.90을 PKS로 본다(인니·말레이시아산 "
                    "단가가 PKS 시세와 같음). 한국은 PKS 세번이 확인되지 않아 아직 넣지 않았다."),
        "source": "UN Comtrade (public preview API)",
    }


def main(argv):
    frame = collect()
    out = summary(frame)
    if out is None:
        log("no PKS rows")
        return 1
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    for i in out["importers"]:
        log(f"{i['importer']}: last 12 months to {i['last_month']} {i['last12_kt']:.0f} kt "
            f"({i['last12_yoy_pct']}%), ${i['price_usd_t']}/t, {i['by_origin_kt']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
