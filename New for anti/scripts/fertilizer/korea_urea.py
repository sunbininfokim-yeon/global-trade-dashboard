"""Where Korea buys its urea, and how much hangs on China.

UN Comtrade public preview (no key; Actions only): Korea's (410) annual
imports of HS 310210 by partner for the last several years, so the card can
show the supplier mix and how the China share moved since the 2021 shortage
(the urea-solution crisis followed China's export inspections that autumn).
HS 310210 covers fertilizer and technical grade alike, so it includes the
urea that becomes vehicle urea solution.

Korea's own 2026 months are not in Comtrade yet, so the year-to-date line
uses China's report of its urea shipments to Korea, against the same months
a year earlier.

The last good pull is kept in korea_urea.json; a failed pull reuses it.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "korea_urea.json")
BASE = "https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS"
HS = "310210"
YEARS = 7
PAUSE_S = 6
CHINA = 156
TOP = 6
PARTNER_KO = {
    156: "중국", 682: "사우디아라비아", 360: "인도네시아", 458: "말레이시아", 512: "오만",
    634: "카타르", 784: "아랍에미리트", 704: "베트남", 392: "일본", 643: "러시아",
    48: "바레인", 414: "쿠웨이트", 364: "이란", 818: "이집트", 840: "미국", 842: "미국",
    804: "우크라이나", 76: "브라질", 586: "파키스탄", 608: "필리핀", 764: "태국",
    496: "몽골", 398: "카자흐스탄", 233: "에스토니아", 528: "네덜란드", 276: "독일",
}


def log(msg):
    print(f"[korea-urea] {msg}", flush=True)


def _get(freq, period, reporter, flow, partner=None):
    params = dict(reporterCode=str(reporter), period=str(period), cmdCode=HS, flowCode=flow,
                  partner2Code="0", customsCode="C00", motCode="0")
    if partner is not None:
        params["partnerCode"] = str(partner)
    url = BASE.format(freq=freq) + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "global-trade-dashboard"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(20 * (attempt + 1))
    return {}


def _tonnes(body, key="partnerCode"):
    out = {}
    for r in body.get("data") or []:
        code = int(r.get(key) or 0)
        kg = r.get("netWgt") or 0
        if code and kg:
            out[str(code)] = out.get(str(code), 0) + round(kg / 1000)
    return out


def fetch(cached, today=None):
    today = today or date.today()
    out = {"annual": dict(cached.get("annual") or {}), "china_monthly": dict(cached.get("china_monthly") or {})}
    for year in range(today.year - 1, today.year - 1 - YEARS, -1):
        # Settled years are kept; the newest two are pulled again for revisions.
        if str(year) in out["annual"] and year < today.year - 2:
            continue
        try:
            rows = _tonnes(_get("A", year, 410, "M"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            log(f"{year}: {exc}")
            continue
        if rows:
            out["annual"][str(year)] = rows
        else:
            log(f"{year}: no Korea rows yet")
        time.sleep(PAUSE_S)
    # China's own report of urea shipped to Korea, this year and last, by month.
    y, m = today.year, today.month
    for _ in range(14):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        ym = f"{y}{m:02d}"
        if ym in out["china_monthly"] and (today.year * 12 + today.month) - (y * 12 + m) > 4:
            continue
        try:
            body = _get("M", ym, CHINA, "X", partner=410)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            log(f"China {ym}: {exc}")
            continue
        rows = body.get("data") or []
        if rows:
            out["china_monthly"][ym] = round(sum((r.get("netWgt") or 0) for r in rows) / 1000)
        time.sleep(PAUSE_S)
    out["china_monthly"] = dict(sorted(out["china_monthly"].items())[-26:])
    out["fetched"] = today.isoformat()
    return out


def load(offline=False):
    cached = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cached = json.load(f)
    if offline:
        return cached
    fresh = fetch(cached)
    if fresh.get("annual"):
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(fresh, f, indent=1, sort_keys=True)
            f.write("\n")
        return fresh
    log("Comtrade unavailable; using cached")
    return cached


def summarize(data):
    annual = data.get("annual") or {}
    years = sorted(annual, key=int)
    if not years:
        return None
    latest = years[-1]
    rows = {int(k): v for k, v in annual[latest].items()}
    total = sum(rows.values())
    if not total:
        return None
    partners = [{"code": p, "country_ko": PARTNER_KO.get(p, str(p)), "tonnes": t,
                 "share_pct": round(t / total * 100, 1)}
                for p, t in sorted(rows.items(), key=lambda kv: -kv[1])[:TOP]]
    hhi = round(sum((t / total * 100) ** 2 for t in rows.values()))
    trend = []
    for y in years:
        r = {int(k): v for k, v in annual[y].items()}
        tot = sum(r.values())
        if tot:
            trend.append({"year": int(y), "total_kt": round(tot / 1000),
                          "china_pct": round(r.get(CHINA, 0) / tot * 100, 1)})
    out = {"year": int(latest), "total_kt": round(total / 1000), "partners": partners,
           "china_pct": round(rows.get(CHINA, 0) / total * 100, 1), "hhi": hhi,
           "trend": trend,
           "source_ko": f"UN Comtrade 한국 수입 (HS {HS}, 비료용·산업용(요소수 원료) 포함, 순중량)"}
    ytd = china_ytd(data.get("china_monthly") or {})
    if ytd:
        out["china_ytd"] = ytd
    return out


def china_ytd(monthly):
    """China-reported shipments to Korea for this year's reported months vs
    the same months a year before."""
    if not monthly:
        return None
    last = max(monthly)
    year = int(last[:4])
    cur = {k: v for k, v in monthly.items() if k.startswith(str(year))}
    prev = {f"{year - 1}{k[4:]}": monthly.get(f"{year - 1}{k[4:]}") for k in cur}
    if not cur or any(v is None for v in prev.values()):
        return None
    a, b = sum(cur.values()), sum(prev.values())
    return {"year": year, "through": last, "months": len(cur), "kt": round(a / 1000, 1),
            "prev_kt": round(b / 1000, 1),
            "change_pct": round((a / b - 1) * 100, 1) if b else None}
