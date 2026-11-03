"""
Wood pellet trade (HS 4401.31) from UN Comtrade: Korea and Japan imports by
supplier, and the big exporters' totals.

Usage: python3 -m biomass.pellet_trade   # -> training/pellet_trade.csv,
                                         #    public/data/pellet_trade_v1.json

Korean and Japanese power plants burn imported wood pellets next to coal and
PKS. In 2024 Korea imported 4.0 Mt (Vietnam 2.1 Mt, Russia 0.6, Indonesia
0.5, Canada 0.35, Malaysia 0.26) at about $126/t, and Japan 6.4 Mt.
HS 4401.31 is pellets only, so unlike PKS (1404.90) the line is clean.

Two reads:
  importers  Korea and Japan, flow M, every partner: annual from 2015 and the
             last 30 months. One call per period covers both.
  exporters  the main shippers, flow X, partner World, annual only.

Source: Comtrade public preview API (no key, one period per call, capped at
500 rows, rate limited), so calls are spaced and a 429 waits and retries.
Reachable from Actions, not from every sandbox. Rows without a reported net
weight are kept but never counted as zero tonnes.
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
CSV = os.path.join(HERE, "training", "pellet_trade.csv")
PUBLIC = os.path.normpath(os.path.join(HERE, "..", "..", "..", "public", "data"))
OUT_JSON = os.path.join(PUBLIC, "pellet_trade_v1.json")
URL = ("https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS?reporterCode={reporters}"
       "&period={period}&cmdCode={hs}&flowCode={flow}{extra}")

HS = "440131"
IMPORTERS = {"410": "한국", "392": "일본"}
EXPORTERS = {"842": "미국", "124": "캐나다", "704": "베트남", "360": "인도네시아",
             "458": "말레이시아", "643": "러시아", "428": "라트비아", "233": "에스토니아"}
WORLD = "0"
NAMES_KO = {
    "704": "베트남", "643": "러시아", "360": "인도네시아", "124": "캐나다", "458": "말레이시아",
    "764": "태국", "842": "미국", "392": "일본", "410": "한국", "156": "중국", "116": "캄보디아",
    "36": "호주", "554": "뉴질랜드", "608": "필리핀", "158": "대만", "490": "대만", "428": "라트비아",
    "233": "에스토니아", "440": "리투아니아", "276": "독일", "826": "영국", "528": "네덜란드",
    "208": "덴마크", "112": "벨라루스", "804": "우크라이나", "418": "라오스", "104": "미얀마",
}
FIRST_YEAR = 2015
MONTHS_BACK = 36
GAP_S = 6
TOP = 6


def log(msg):
    print(f"[biomass:pellet-trade] {msg}", flush=True)


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


def fetch(side, freq, period):
    if side == "M":
        url = URL.format(freq=freq, period=period, reporters=",".join(IMPORTERS), hs=HS, flow="M", extra="")
    else:
        url = URL.format(freq=freq, period=period, reporters=",".join(EXPORTERS), hs=HS, flow="X",
                         extra="&partnerCode=0")
    rows = []
    for x in (_get(url) or {}).get("data", []):
        if str(x.get("partner2Code")) not in ("0", "None") or x.get("customsCode") not in ("C00", None):
            continue
        if str(x.get("motCode")) not in ("0", "None"):
            continue
        rows.append({"side": side, "freq": freq, "period": str(x["period"]),
                     "reporter": str(x["reporterCode"]), "partner": str(x["partnerCode"]),
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
    have = set(zip(old.get("side", []), old.get("freq", []), old.get("period", [])))
    jobs = []
    for side in ("M", "X"):
        # Years two or more back are settled; recent ones are re-read.
        jobs += [(side, "A", str(y)) for y in range(FIRST_YEAR, today.year)
                 if y >= today.year - 2 or (side, "A", str(y)) not in have]
    jobs += [("M", "M", p) for p in _months(today, MONTHS_BACK)]
    rows, failed = [], 0
    for side, freq, period in jobs:
        time.sleep(GAP_S)
        try:
            rows.extend(fetch(side, freq, period))
        except Exception as exc:  # keep what was read before
            failed += 1
            log(f"{side} {freq} {period}: {exc}")
    new = pd.DataFrame(rows, dtype=str)
    if new.empty and old.empty:
        raise SystemExit("Comtrade: nothing read")
    keep = old
    if not new.empty and not old.empty:
        fetched = set(zip(new.side, new.freq, new.period, new.reporter))
        keep = old[[k not in fetched for k in zip(old.side, old.freq, old.period, old.reporter)]]
    out = pd.concat([keep, new], ignore_index=True)
    out = out.sort_values(["side", "freq", "period", "reporter", "partner"])
    os.makedirs(os.path.dirname(CSV), exist_ok=True)
    out.to_csv(CSV, index=False)
    log(f"{len(jobs)} calls, {failed} failed, {len(out)} rows -> {CSV}")
    return out


def _pct(a, b):
    return None if not a or not b else round((a / b - 1) * 100, 1)


def _kt(kg, nd=0):
    return None if kg is None or pd.isna(kg) else round(float(kg) / 1e6, nd)


def _name(code):
    return NAMES_KO.get(str(code), f"기타({code})")


def _price(g):
    """USD per tonne over rows that report both value and weight."""
    ok = g[g.net_kg.notna() & (g.net_kg > 0) & g.value_usd.notna()]
    return None if ok.empty else round(float(ok.value_usd.sum() / (ok.net_kg.sum() / 1000)), 1)


def _wsum(g):
    """Net weight, or None when no row in the group reports one."""
    w = g.net_kg.dropna()
    return None if w.empty else float(w.sum())


def _window(frame, last, k):
    hi = last - pd.DateOffset(months=12 * (k - 1))
    lo = last - pd.DateOffset(months=12 * k)
    return frame[(frame.month > lo) & (frame.month <= hi)]


def _importer_recent(m, code):
    mine = m[m.reporter == code]
    world = mine[(mine.partner == WORLD) & mine.net_kg.notna()]
    if world.empty:
        return None
    last = world.month.max()
    cur, prev = _window(world, last, 1), _window(world, last, 2)
    if cur.month.nunique() < 12:
        return None
    total = float(cur.net_kg.sum())
    dest = (_window(mine[mine.partner != WORLD], last, 1).groupby("partner").net_kg.sum()
            .sort_values(ascending=False))
    return {
        "last_month": last.strftime("%Y-%m"),
        "total_kt": _kt(total),
        "yoy_pct": _pct(total, float(prev.net_kg.sum())) if prev.month.nunique() == 12 else None,
        "price_usd_t": _price(cur),
        "top_suppliers": [{"country": _name(p), "kt": _kt(v), "share_pct": round(float(v / total * 100), 1)}
                          for p, v in dest.head(TOP).items() if v > 0],
        "series": [{"month": i.strftime("%Y-%m"), "kt": _kt(v, 1)}
                   for i, v in world.groupby("month").net_kg.sum().tail(24).items()],
    }


def summary(frame=None):
    if frame is None:
        frame = pd.read_csv(CSV, dtype=str)
    d = frame.copy()
    for c in ("net_kg", "value_usd"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ("side", "freq", "reporter", "partner", "period"):
        d[c] = d[c].astype(str)

    imp = d[(d.side == "M") & (d.partner == WORLD)]
    annual = []
    for y, g in imp[imp.freq == "A"].groupby("period"):
        row = {"year": int(y)}
        for code, label in IMPORTERS.items():
            gi = g[g.reporter == code]
            row[label] = None if gi.empty else {"kt": _kt(_wsum(gi)), "price_usd_t": _price(gi)}
        annual.append(row)

    m = d[(d.side == "M") & (d.freq == "M")].copy()
    m["month"] = pd.to_datetime(m.period, format="%Y%m")
    recent = {label: _importer_recent(m, code) for code, label in IMPORTERS.items()}

    ex = d[(d.side == "X") & (d.freq == "A") & (d.partner == WORLD) & d.net_kg.notna()]
    exporters = []
    for code, label in EXPORTERS.items():
        g = ex[ex.reporter == code]
        if g.empty:
            continue
        y = g.period.max()
        cur = g[g.period == y]
        prev = g[g.period == str(int(y) - 1)]
        exporters.append({"country": label, "year": int(y), "kt": _kt(cur.net_kg.sum()),
                          "yoy_pct": _pct(cur.net_kg.sum(), prev.net_kg.sum()) if not prev.empty else None,
                          "price_usd_t": _price(cur)})
    exporters.sort(key=lambda r: -(r["kt"] or 0))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hs": HS,
        "annual_imports": annual,
        "recent": recent,
        "exporters": exporters,
        "note_ko": ("UN Comtrade 기준 HS 4401.31(목재펠릿). 한국·일본은 수입국 신고, 수출국 실적은 각국 "
                    "수출 신고(전 세계 합계)입니다. 중량을 신고하지 않은 달은 0으로 세지 않습니다."),
        "source": "UN Comtrade (public preview API)",
    }


def main(argv):
    frame = collect()
    out = summary(frame)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    for label, r in out["recent"].items():
        if r:
            log(f"{label} 12m to {r['last_month']}: {r['total_kt']} kt ({r['yoy_pct']}%), "
                f"${r['price_usd_t']}/t, top {r['top_suppliers'][:3]}")
    log(f"exporters {[(e['country'], e['year'], e['kt']) for e in out['exporters']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
