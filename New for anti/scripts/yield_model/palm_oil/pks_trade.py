"""
PKS (palm kernel shell) exports from Indonesia and Malaysia, every buyer, from
UN Comtrade.

Usage: python3 -m palm_oil.pks_trade     # -> training/pks_exports.csv,
                                         #    public/data/pks_trade_v1.json

Read from the exporters' side: one call per period returns both countries'
exports of HS 1404.90 to every destination, so no importer has to be wired
in one by one. Indonesia and Malaysia ship PKS under 1404.90 (vegetable
products n.e.s.): in 2024 that code was 4.83 Mt from Indonesia and 1.29 Mt
from Malaysia at $105-115/t, the PKS price, about 90% of it to Japan.
Other goods under the code are small next to that, but it is not a pure PKS
line, and the screen says so.

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
CSV = os.path.join(HERE, "training", "pks_exports.csv")
PUBLIC = os.path.normpath(os.path.join(HERE, "..", "..", "..", "public", "data"))
OUT_JSON = os.path.join(PUBLIC, "pks_trade_v1.json")
URL = ("https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS?reporterCode={exporters}"
       "&period={period}&cmdCode={hs}&flowCode=X")

HS = "140490"
EXPORTERS = {"360": "인도네시아", "458": "말레이시아"}
WORLD = "0"
NAMES_KO = {
    "392": "일본", "410": "한국", "764": "태국", "702": "싱가포르", "156": "중국",
    "458": "말레이시아", "360": "인도네시아", "528": "네덜란드", "616": "폴란드",
    "620": "포르투갈", "608": "필리핀", "704": "베트남", "826": "영국", "276": "독일",
    "158": "대만", "490": "대만", "344": "홍콩", "586": "파키스탄", "724": "스페인",
    "380": "이탈리아", "784": "UAE", "842": "미국", "699": "인도",
}
FIRST_YEAR = 2015
MONTHS_BACK = 30
GAP_S = 6
TOP = 5


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
    body = _get(URL.format(freq=freq, period=period, exporters=",".join(EXPORTERS), hs=HS))
    rows = []
    for x in (body or {}).get("data", []):
        if str(x.get("partner2Code")) not in ("0", "None") or x.get("customsCode") not in ("C00", None):
            continue
        if str(x.get("motCode")) not in ("0", "None"):
            continue
        rows.append({"freq": freq, "period": str(x["period"]), "exporter": str(x["reporterCode"]),
                     "partner": str(x["partnerCode"]), "net_kg": x.get("netWgt"),
                     "value_usd": x.get("primaryValue")})
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
            rows.extend(fetch(freq, period))
        except Exception as exc:  # keep what was read before
            failed += 1
            log(f"{freq} {period}: {exc}")
    new = pd.DataFrame(rows, dtype=str)
    if new.empty and old.empty:
        raise SystemExit("Comtrade: nothing read")
    keep = old
    if not new.empty and not old.empty:
        fetched = set(zip(new.freq, new.period, new.exporter))
        keep = old[[(f, p, e) not in fetched for f, p, e in zip(old.freq, old.period, old.exporter)]]
    out = pd.concat([keep, new], ignore_index=True)
    out = out.sort_values(["freq", "period", "exporter", "partner"])
    os.makedirs(os.path.dirname(CSV), exist_ok=True)
    out.to_csv(CSV, index=False)
    log(f"{len(jobs)} calls, {failed} failed, {len(out)} rows -> {CSV}")
    return out


def _pct(a, b):
    return None if not a or not b else round((a / b - 1) * 100, 1)


def _name(code):
    return NAMES_KO.get(str(code), f"기타({code})")


def _window(frame, last, k):
    """Rows in the k-th 12-month window ending at ``last`` (k=1 latest)."""
    hi = last - pd.DateOffset(months=12 * (k - 1))
    lo = last - pd.DateOffset(months=12 * k)
    return frame[(frame.month > lo) & (frame.month <= hi)]


def _full(frame):
    n = frame.groupby("exporter").month.nunique()
    return len(n) == len(EXPORTERS) and bool((n == 12).all())


def summary(frame=None):
    """Annual totals and the last 12 months both exporters have reported."""
    if frame is None:
        frame = pd.read_csv(CSV, dtype=str)
    d = frame.copy()
    for c in ("net_kg", "value_usd"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["exporter"], d["partner"] = d.exporter.astype(str), d.partner.astype(str)
    world = d[d.partner == WORLD]
    if world.empty:
        return None

    years = []
    for y, g in world[world.freq == "A"].groupby("period"):
        if set(g.exporter) != set(EXPORTERS):
            continue
        years.append({"year": int(y), "total_kt": round(float(g.net_kg.sum() / 1e6), 0),
                      "by_exporter_kt": {EXPORTERS[e]: round(float(v / 1e6), 0)
                                         for e, v in g.groupby("exporter").net_kg.sum().items()}})

    m = d[d.freq == "M"].copy()
    m["month"] = pd.to_datetime(m.period, format="%Y%m")
    wm = m[m.partner == WORLD]
    lasts = [g.month.max() for _, g in wm.groupby("exporter")]
    recent = None
    if len(lasts) == len(EXPORTERS):
        last = min(lasts)
        cur, prev = _window(wm, last, 1), _window(wm, last, 2)
        if _full(cur):
            total = cur.net_kg.sum()
            dest = (_window(m[m.partner != WORLD], last, 1).groupby("partner").net_kg.sum()
                    .sort_values(ascending=False))
            recent = {
                "last_month": last.strftime("%Y-%m"),
                "total_kt": round(float(total / 1e6), 0),
                "yoy_pct": _pct(total, prev.net_kg.sum()) if _full(prev) else None,
                "price_usd_t": round(float(cur.value_usd.sum() / (total / 1000)), 1),
                "by_exporter_kt": {EXPORTERS[e]: round(float(v / 1e6), 0)
                                   for e, v in cur.groupby("exporter").net_kg.sum().items()},
                "top_destinations": [{"country": _name(p), "kt": round(float(v / 1e6), 0),
                                      "share_pct": round(float(v / total * 100), 1)}
                                     for p, v in dest.head(TOP).items()],
                "korea_kt": round(float(dest.get("410", 0.0) / 1e6), 1),
                "series": [{"month": i.strftime("%Y-%m"), "kt": round(float(v / 1e6), 1)}
                           for i, v in wm[wm.month <= last].groupby("month").net_kg.sum().tail(24).items()],
            }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hs": HS,
        "annual": years,
        "recent": recent,
        "note_ko": ("UN Comtrade 수출국(인도네시아·말레이시아) 신고 기준 HS 1404.90 수출. 두 나라는 PKS를 "
                    "이 세번으로 내보내며 단가가 PKS 시세와 같다. 다른 품목이 일부 섞일 수 있다."),
        "source": "UN Comtrade (public preview API)",
    }


def main(argv):
    frame = collect()
    out = summary(frame)
    if out is None:
        log("no rows")
        return 1
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    r = out["recent"]
    if r:
        log(f"last 12 months to {r['last_month']}: {r['total_kt']:.0f} kt ({r['yoy_pct']}%), "
            f"${r['price_usd_t']}/t, top {r['top_destinations']}, Korea {r['korea_kt']} kt")
    log(f"annual {[(a['year'], a['total_kt']) for a in out['annual']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
