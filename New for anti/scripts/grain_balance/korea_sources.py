"""Where Korea buys its wheat, corn and soybeans, and how those fields look.

UN Comtrade annual imports by partner (reporter Korea 410, HS 1001/1005/1201,
public preview API -- no key; reachable from Actions, not from the dev
container). The tonnage shares are joined with the stage-condition calls of
the regions that grow that crop in each supplier country, so the grain card
can say which share of Korea's supply comes from fields now judged
unfavourable.

Only stdlib. The last good pull is kept in korea_imports.json; a failed pull
reuses it.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import time
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "korea_imports.json")
URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
HS = {"wheat": "1001", "corn": "1005", "soybeans": "1201"}
LOOKBACK_MONTHS = 15     # months asked for (Korea reports within ~2 months)
REFETCH_MONTHS = 4       # the newest months are pulled again for revisions
PAUSE_S = 6              # between preview calls (public rate limit)
# Exporters asked for their shipments to Korea when Korea's own months lag.
MIRROR_FROM = [842, 36, 124, 76, 32, 804, 643, 398, 710, 600, 100, 642]
MIRROR_NEED_SHARE = 10.0
MIN_SHARE = 1.0          # % of Korea's tonnage; smaller suppliers are not listed
TOP = 6

PARTNER_KO = {
    842: "미국", 76: "브라질", 32: "아르헨티나", 36: "호주", 124: "캐나다",
    804: "우크라이나", 643: "러시아", 398: "카자흐스탄", 710: "남아공",
    600: "파라과이", 858: "우루과이", 642: "루마니아", 100: "불가리아",
    348: "헝가리", 703: "슬로바키아", 499: "몬테네그로", 688: "세르비아",
    356: "인도", 156: "중국", 764: "태국", 704: "베트남", 360: "인도네시아",
    484: "멕시코", 251: "프랑스", 250: "프랑스", 276: "독일", 616: "폴란드",
    68: "볼리비아", 792: "튀르키예", 608: "필리핀", 392: "일본",
}

# Supplier -> the stage_conditions regions (and crop keys) growing what Korea
# buys from it. Equal weights inside a country: the monitor has no per-region
# export share, which the card says.
REGIONS = {
    "wheat": {
        842: [("great_plains", "winter_wheat"), ("northern_plains", "spring_wheat")],
        36: [("wa_wheat", "wheat"), ("sa_wheat", "wheat"), ("vic_wheat", "wheat")],
        124: [("sad_sk_wheat_palliser", "spring_wheat")],
        804: [("ukraine_winter_wheat", "winter_wheat")],
        643: [("southern_winter_wheat", "winter_wheat"), ("cbe_winter_wheat", "winter_wheat"),
              ("volga_winter_wheat", "winter_wheat")],
        398: [("kazakhstan_wheat_north", "spring_wheat"), ("kazakhstan_wheat_akmola", "spring_wheat")],
        32: [("pampas_trigo", "wheat")],
    },
    "corn": {
        842: [("corn_belt", "corn")],
        76: [("mato_grosso_soja", "corn_safrinha"), ("parana_soja", "corn")],
        32: [("pampas_maiz", "corn")],
        804: [("ukraine_corn", "corn")],
        643: [("russia_corn_south", "corn"), ("russia_corn_cbe", "corn")],
        124: [("sad_on_corn_southern", "corn"), ("sad_on_corn_western", "corn")],
    },
    "soybeans": {
        842: [("corn_belt", "soybeans")],
        76: [("mato_grosso_soja", "soy"), ("parana_soja", "soy"), ("matopiba_soja", "soy")],
        32: [("pampas_soja", "soy")],
        124: [("sad_mb_soy_redriver", "soy")],
        643: [("russia_soy_amur", "soy"), ("russia_soy_cbe", "soy")],
    },
}


def log(msg):
    print(f"[korea-sources] {msg}", flush=True)


def _get(period, freq="A", reporter="410", flow="M", partner=None):
    params = dict(reporterCode=reporter, period=str(period), cmdCode=",".join(HS.values()),
                  flowCode=flow, partner2Code="0", customsCode="C00", motCode="0")
    if partner:
        params["partnerCode"] = partner
    url = (URL if freq == "A" else URL.replace("/C/A/", "/C/M/")) + "?" + urllib.parse.urlencode(params)
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


def _rows(body):
    """{crop: {partner: tonnes}} from one Comtrade response."""
    per = {}
    for r in body.get("data") or []:
        if str(r.get("reporterCode")) != "410" or r.get("flowCode") != "M":
            continue
        crop = next((k for k, v in HS.items() if r.get("cmdCode") == v), None)
        p = int(r.get("partnerCode") or 0)
        kg = r.get("netWgt") or 0
        if crop and p != 0 and kg:
            per.setdefault(crop, {})
            per[crop][str(p)] = round(per[crop].get(str(p), 0) + kg / 1000)
    return per


def fetch_monthly(cached, today=None):
    """{crop: {YYYYMM: {partner: tonnes}}}. Months already held and older
    than REFETCH_MONTHS are kept; the recent ones are pulled again since
    Korea revises its first reports."""
    today = today or date.today()
    out = {c: dict(v) for c, v in (cached or {}).items()}
    y, m = today.year, today.month
    months = []
    for _ in range(LOOKBACK_MONTHS):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        months.append(f"{y}{m:02d}")
    for i, ym in enumerate(months):
        held = any(ym in out.get(c, {}) for c in HS)
        if held and i >= REFETCH_MONTHS:
            continue
        try:
            body = _get(ym, "M")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            log(f"{ym}: {exc}")
            continue
        got = _rows(body)
        if not got:
            # Not yet released, or the service answered without data: say which.
            log(f"{ym}: no rows (count {body.get('count')}, error {body.get('error') or '-'})")
        for crop, rows in got.items():
            out.setdefault(crop, {})[ym] = rows
        time.sleep(PAUSE_S)
    # Keep two years of months, enough for a 12-month window and its year-ago.
    for c in out:
        out[c] = dict(sorted(out[c].items())[-24:])
    return out


def _months_back(today, n):
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y}{m:02d}")
    return out


def fetch_mirror(cached, today=None):
    """Exporters' own reports of shipments to Korea, for the months Korea's
    reports have not reached Comtrade yet. {crop: {YYYYMM: {exporter: t}}}
    plus {"_reporters": {YYYYMM: [exporters that reported anything]}}."""
    today = today or date.today()
    out = {k: dict(v) for k, v in (cached or {}).items()}
    out.setdefault("_reporters", {})
    for i, ym in enumerate(_months_back(today, LOOKBACK_MONTHS)):
        if ym in out["_reporters"] and i >= REFETCH_MONTHS:
            continue
        try:
            body = _get(ym, "M", reporter=",".join(str(r) for r in MIRROR_FROM), flow="X", partner="410")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            log(f"mirror {ym}: {exc}")
            continue
        reporters, per = set(), {}
        for r in body.get("data") or []:
            if str(r.get("partnerCode")) != "410" or r.get("flowCode") != "X":
                continue
            crop = next((k for k, v in HS.items() if r.get("cmdCode") == v), None)
            rep = str(r.get("reporterCode"))
            kg = r.get("netWgt") or 0
            if crop and kg:
                reporters.add(rep)
                per.setdefault(crop, {})
                per[crop][rep] = round(per[crop].get(rep, 0) + kg / 1000)
        if not reporters:
            log(f"mirror {ym}: no rows (count {body.get('count')}, error {body.get('error') or '-'})")
            time.sleep(PAUSE_S)
            continue
        out["_reporters"][ym] = sorted(reporters, key=int)
        for crop, rows in per.items():
            out.setdefault(crop, {})[ym] = rows
        time.sleep(PAUSE_S)
    for c in out:
        out[c] = dict(sorted(out[c].items())[-24:])
    return out


def fetch(today=None):
    """{crop: {"year": Y, "rows": {partner: tonnes}}}, newest complete year."""
    today = today or date.today()
    out = {}
    for year in range(today.year - 1, today.year - 4, -1):
        try:
            body = _get(year)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            log(f"{year}: {exc}")
            continue
        for crop, rows in _rows(body).items():
            if crop not in out and sum(rows.values()) > 0:
                out[crop] = {"year": year, "rows": rows}
        if len(out) == len(HS):
            break
    return out


def load_or_fetch(offline=False):
    cached = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cached = json.load(f)
    if offline:
        return cached
    fresh = fetch()
    monthly = fetch_monthly(cached.get("monthly"))
    mirror = fetch_mirror(cached.get("mirror"))
    if not fresh and monthly == cached.get("monthly") and mirror == cached.get("mirror"):
        log("Comtrade unavailable; using cached shares")
        return cached
    merged = {**cached, **fresh, "monthly": monthly, "mirror": mirror}
    merged["fetched"] = date.today().isoformat()
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    for crop, months in monthly.items():
        if months:
            log(f"{crop} monthly: {min(months)}..{max(months)} ({len(months)} months)")
    for ym, reps in sorted(mirror.get("_reporters", {}).items()):
        log(f"mirror {ym}: reported by {','.join(PARTNER_KO.get(int(r), r) for r in reps)}")
    for crop in HS:
        if crop in fresh:
            log(f"{crop} {fresh[crop]['year']}: {sum(fresh[crop]['rows'].values()):,.0f} t "
                f"from {len(fresh[crop]['rows'])} partners")
    return merged


def _calls(stage):
    """(region key, crop) -> the current season's call, or None once harvested."""
    out = {}
    for key, entries in (stage.get("regions") or {}).items():
        for e in entries:
            live = any(s.get("state") in ("in_progress", "upcoming") for s in e.get("stages", []))
            ov = e.get("overall") or {}
            out[(key, e.get("crop"))] = {
                "verdict": ov.get("verdict"), "verdict_ko": ov.get("verdict_ko"),
                "reference_only": ov.get("history_check") == "unmatched",
                "season": e.get("season"), "live": live,
            }
    return out


def block(crop, imports, stage, names):
    """The card section for one crop, or None."""
    src = imports.get(crop)
    if not src or not src.get("rows"):
        return None
    annual = {int(k): v for k, v in src["rows"].items()}
    annual_total = sum(annual.values())
    basis = "annual"
    window = last_12_months((imports.get("monthly") or {}).get(crop) or {})
    if window:
        basis = "korea"
    else:
        window = mirror_window(imports.get("mirror") or {}, crop, annual)
        if window:
            basis = "mirror"
    if window:
        rows, period = window
    else:
        rows, period = annual, None
    total = sum(rows.values())
    calls = _calls(stage)
    partners, exposed, covered = [], 0.0, 0.0
    for p, t in sorted(rows.items(), key=lambda kv: -kv[1]):
        share = t / total * 100
        if share < MIN_SHARE or len(partners) >= TOP:
            continue
        regions = []
        for key, c in REGIONS.get(crop, {}).get(p, []):
            call = calls.get((key, c))
            if not call:
                continue
            regions.append({"key": key, "region_ko": names.get(key, ("", key))[1],
                            "season": call["season"], "verdict": call["verdict"],
                            "verdict_ko": call["verdict_ko"],
                            "reference_only": call["reference_only"],
                            "harvested": not call["live"]})
        # Only growing seasons with a record that matched past harvests count.
        live = [r for r in regions if not r["harvested"]]
        if live:
            covered += share
            bad = sum(1 for r in live if r["verdict"] == "unfavorable" and not r["reference_only"])
            exposed += share * bad / len(live)
        prior = annual.get(p, 0) / annual_total * 100 if annual_total else None
        partners.append({"code": p, "country_ko": PARTNER_KO.get(p, str(p)),
                         "tonnes": round(t), "share_pct": round(share, 1),
                         "change_pp": None if period is None or prior is None else round(share - prior, 1),
                         "regions": regions})
    if period:
        span = f"{period[0][:4]}.{period[0][4:]}~{period[1][:4]}.{period[1][4:]}"
        label = f"최근 12개월({span})"
        src_ko = (f"UN Comtrade 한국 월간 수입 {span} (HS {HS[crop]}, 순중량) · 변화는 {src['year']}년 연간 대비"
                  if basis == "korea" else
                  f"UN Comtrade 수출국 신고(한국행 수출) {span} (HS {HS[crop]}, 순중량, 한국 월간 신고가 아직 없음) · "
                  f"변화는 {src['year']}년 한국 연간 수입 대비 · 주요 수출국 {len(MIRROR_FROM)}곳만 집계")
    else:
        label, src_ko = f"{src['year']}년", f"UN Comtrade 한국 수입 {src['year']}년 (HS {HS[crop]}, 순중량)"
    return {
        "year": src["year"],
        "period": None if period is None else {"from": period[0], "to": period[1]},
        "basis": basis,
        "label_ko": label,
        "total_kt": round(total / 1000),
        "partners": partners,
        "exposed_pct": round(exposed, 1),
        "covered_pct": round(covered, 1),
        "source_ko": src_ko,
    }


def last_12_months(months):
    """(partner tonnes summed, (first, last)) over the newest 12 consecutive
    months, or None when the run is shorter."""
    keys = sorted(k for k, v in months.items() if v)
    if len(keys) < 12:
        return None
    run = [keys[-1]]
    for k in reversed(keys[:-1]):
        y, m = int(run[-1][:4]), int(run[-1][4:])
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        if k != f"{y}{m:02d}":
            break
        run.append(k)
        if len(run) == 12:
            break
    if len(run) < 12:
        return None
    total = {}
    for k in run:
        for p, t in months[k].items():
            total[int(p)] = total.get(int(p), 0) + t
    return total, (run[-1], run[0])


def mirror_window(mirror, crop, annual):
    """12 consecutive months of exporter reports in which every supplier with
    >= MIRROR_NEED_SHARE % of Korea's last annual tonnage reported something
    (a supplier missing would read as a share collapse)."""
    reps = mirror.get("_reporters") or {}
    months = mirror.get(crop) or {}
    total = sum(annual.values()) or 1
    need = {str(p) for p, t in annual.items() if t / total * 100 >= MIRROR_NEED_SHARE
            and int(p) in MIRROR_FROM}
    ok = {ym: months.get(ym, {}) for ym, r in reps.items() if need <= set(r)}
    return last_12_months(ok)
