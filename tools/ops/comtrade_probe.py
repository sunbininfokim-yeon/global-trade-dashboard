#!/usr/bin/env python3
"""Probe (and warm) the production /api/comtrade proxy.

Two jobs, both through the deployed Worker, which holds the Comtrade key:

1. Annual catch-up. The map's year only moves forward once every commodity
   for the next year is in KV (see advanceComtradePeriod in _worker.js).
   Requesting each commodity x year here fills KV the same way a visitor's
   request would, so the next cron tick can promote without waiting for its
   8-per-tick budget to get through the list.
2. Monthly coverage. How many reporters and partners a Comtrade monthly
   bilateral pull actually returns -- the evidence for whether a monthly world
   map is worth building, per commodity.

Standard library only. Stops at the first 429 so a quota limit is reported,
not hammered.

    python3 tools/ops/comtrade_probe.py [--base URL] [--no-warm] [--no-monthly]
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://global-trade-dashboard.sunbin-info-kim.workers.dev"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Reporters a monthly world map cannot do without, by Comtrade code.
KEY_REPORTERS = {
    842: "USA", 156: "CHN", 76: "BRA", 699: "IND", 276: "DEU", 392: "JPN", 410: "KOR",
    643: "RUS", 682: "SAU", 360: "IDN", 458: "MYS", 36: "AUS", 124: "CAN", 32: "ARG",
}
MONTHLY_HS = {"2709": "원유", "1201": "대두", "7403": "정제 구리", "1511": "팜유"}


def get(base, path, timeout=180):
    req = urllib.request.Request(base + path, headers={"User-Agent": "comtrade-probe/1"})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, dict(r.headers), body, time.time() - started
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(), time.time() - started
    except Exception as e:  # network / timeout
        return 0, {}, str(e).encode(), time.time() - started


def hs_codes():
    src = open(os.path.join(ROOT, "_worker.js"), encoding="utf-8").read()
    block = src[src.index("const COMTRADE_TTL = {"):]
    block = block[:block.index("};")]
    return re.findall(r'^\s*"([0-9,]+)":', block, flags=re.M)


def summarize(body):
    try:
        data = json.loads(body).get("data") or []
    except Exception:
        return None
    rows = [r for r in data if (r.get("primaryValue") or 0) > 0]
    reporters = {r["reporterCode"] for r in rows}
    partners = {r["partnerCode"] for r in rows}
    return {
        "rows": len(rows),
        "reporters": len(reporters),
        "partners": len(partners),
        "key_present": sorted(KEY_REPORTERS[c] for c in reporters if c in KEY_REPORTERS),
        "key_missing": sorted(v for c, v in KEY_REPORTERS.items() if c not in reporters),
        "usd_b": round(sum(r.get("primaryValue") or 0 for r in rows if r.get("flowCode") == "X") / 1e9, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--no-warm", action="store_true")
    ap.add_argument("--no-monthly", action="store_true")
    ap.add_argument("--months", type=int, default=3, help="monthly periods to probe, ending 3 months back")
    args = ap.parse_args()
    out = []
    say = lambda line="": (print(line, flush=True), out.append(line))

    # 1. Where production stands.
    st, hdr, body, _ = get(args.base, "/api/comtrade/status", timeout=60)
    status = None
    try:
        j = json.loads(body)
        if "published" in j:
            status = j
    except Exception:
        pass
    st, hdr, _, _ = get(args.base, "/api/comtrade?hs=2709")
    published = int(hdr.get("X-Comtrade-Period") or hdr.get("x-comtrade-period") or 0)
    say("## 연간 공개 연도")
    say(f"- 현재 기본 연도: **{published or '알 수 없음'}** (HTTP {st})")
    if status:
        say(f"- status: `{json.dumps(status, ensure_ascii=False)}`")
    else:
        say("- `/api/comtrade/status` 없음 (이 변경이 아직 배포되지 않음)")

    year_now = datetime.now(timezone.utc).year
    limited = False

    # 2. Annual catch-up.
    if not args.no_warm and published:
        say("\n## 연간 캐시 채우기")
        say("| HS | 연도 | HTTP | 캐시 | 보고국 | 행 | 초 |")
        say("|---|---|---|---|---|---|---|")
        for year in range(published + 1, year_now):
            for hs in hs_codes():
                st, hdr, body, secs = get(args.base, f"/api/comtrade?hs={hs}&period={year}")
                s = summarize(body) if st == 200 else None
                say(f"| {hs} | {year} | {st} | {hdr.get('X-Cache', hdr.get('x-cache', '-'))} | "
                    f"{s['reporters'] if s else '-'} | {s['rows'] if s else '-'} | {secs:.0f} |")
                if st == 502 and b"429" in body or st == 429:
                    say(f"\n**Comtrade 호출 한도(429)에 걸려 중단.** 남은 항목은 cron이 채운다.")
                    limited = True
                    break
                if hdr.get("X-Cache", hdr.get("x-cache")) != "HIT":
                    time.sleep(3)
            if limited:
                break

    # 3. Monthly bilateral coverage.
    if not args.no_monthly and not limited:
        say("\n## 월별 양자 무역 커버리지 (Comtrade freq=M, 76개 보고국 목록)")
        say("| 품목 | 월 | HTTP | 보고국 | 상대국 | 행 | 수출 합계 $B | 주요국 누락 |")
        say("|---|---|---|---|---|---|---|---|")
        now = datetime.now(timezone.utc)
        months = []
        y, m = now.year, now.month - 3
        for _ in range(args.months):
            while m <= 0:
                y, m = y - 1, m + 12
            months.append(f"{y}{m:02d}")
            m -= 1
        for hs, name in MONTHLY_HS.items():
            for period in months:
                st, hdr, body, secs = get(args.base, f"/api/comtrade?hs={hs}&freq=M&period={period}")
                s = summarize(body) if st == 200 else None
                say(f"| {name} {hs} | {period} | {st} | {s['reporters'] if s else '-'} | "
                    f"{s['partners'] if s else '-'} | {s['rows'] if s else '-'} | {s['usd_b'] if s else '-'} | "
                    f"{', '.join(s['key_missing']) if s else '-'} |")
                if st == 429 or (st == 502 and b"429" in body):
                    say("\n**Comtrade 호출 한도(429)에 걸려 중단.**")
                    limited = True
                    break
                time.sleep(3)
            if limited:
                break

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
