"""
World balance for wheat, corn, soybeans, sugar, palm oil and coffee (USDA
PSD), and the main risks.

Usage: python3 scripts/grain_balance/build.py           # fetch PSD, write
       python3 scripts/grain_balance/build.py apply     # rebuild from the slice

The trade view's stat boxes show last season's world production and USDA's
outlook for this one; the card under them lists the risks. Each risk is a
number someone else published or the crop monitor already computed:

  weather   regions whose stage calls are unfavorable for a crop still
            in the field (harvested seasons are already in USDA's numbers)
            (stage_conditions_v1.json); calls whose past record did not
            match the harvest are kept but marked as reference only
  supply    producers with 3%+ of world output that USDA has down 5% or
            more on last season
  stocks    world ending stocks to use below its 5-season average

Writes
  scripts/grain_balance/psd_world.csv     the PSD slice (committed)
  scripts/grain_balance/prices.csv        IMF monthly prices (committed)
  public/data/grain_balance_v1.json
"""

import io
import json
import html
import os
import re
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "public", "data"))
SLICE = os.path.join(HERE, "psd_world.csv")
PRICES = os.path.join(HERE, "prices.csv")
OUT = os.path.join(DATA, "grain_balance_v1.json")
ZIPS = [
    "https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip",
    "https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip",
    "https://apps.fas.usda.gov/psdonline/downloads/psd_sugar_csv.zip",
    "https://apps.fas.usda.gov/psdonline/downloads/psd_coffee_csv.zip",
]
PSD_URL = "https://apps.fas.usda.gov/psdonline/app/index.html#/app/advQuery"
IGC_URL = "https://www.igc.int/en/gmr_summary.aspx"
IGC_WORD = {"wheat": "wheat", "corn": "maize", "soybeans": "soyabean"}
UP = {"rose", "gained", "increased", "climbed", "advanced", "firmed", "rallied", "jumped"}
DOWN = {"dropped", "slumped", "eased", "fell", "declined", "decreased", "lost", "retreated", "slipped"}
ATTRS = ["Production", "Exports", "Ending Stocks", "Domestic Consumption"]
# PSD names some of these differently per commodity (sugar especially).
ATTR_ALIASES = {"Total Sugar  Production": "Production", "Total Sugar Production": "Production",
                "Human Dom. Consumption": "Domestic Consumption"}

# IMF monthly world prices (via FRED) and the month each marketing year starts.
PRICE_IDS = {"wheat": ("PWHEAMTUSDM", 6), "corn": ("PMAIZMTUSDM", 9), "soybeans": ("PSOYBUSDM", 9),
             "sugar": ("PSUGAISAUSDM", 10), "palm_oil": ("PPOILUSDM", 10),
             "coffee": ("PCOFFOTMUSDM", 10)}
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
BAND_PCT = 10.0   # stocks-to-use vs its 5-season average, same fixed band as the palm check

# Trade view key -> (PSD commodity, Korean label, stage_conditions crops)
CROPS = {
    "wheat": ("Wheat", "밀", {"winter_wheat", "spring_wheat", "wheat"}),
    "corn": ("Corn", "옥수수", {"corn", "corn_safrinha"}),
    "soybeans": ("Oilseed, Soybean", "대두", {"soy", "soybeans"}),
    "sugar": ("Sugar, Centrifugal", "설탕", {"sugarcane"}),
    "palm_oil": ("Oil, Palm", "팜유", set()),
    "coffee": ("Coffee, Green", "커피", {"coffee"}),
}
# PSD units: 1000 t, except coffee in 1000 60-kg bags.
UNITS = {"coffee": "kbag60"}
# China's stocks are held back from trade for grains; elsewhere the world
# figure is the headline.
EX_CHINA = {"wheat", "corn", "soybeans"}
SUPPLY_DROP_PCT = -5.0
SUPPLY_MIN_SHARE = 3.0   # % of world output; smaller producers are noise here
TOP_PRODUCERS = 8
COUNTRY_KO = {
    "United States": "미국", "China": "중국", "Brazil": "브라질", "European Union": "EU",
    "India": "인도", "Russia": "러시아", "Argentina": "아르헨티나", "Ukraine": "우크라이나",
    "Canada": "캐나다", "Australia": "호주", "Kazakhstan": "카자흐스탄", "Pakistan": "파키스탄",
    "Turkey": "튀르키예", "Turkiye": "튀르키예", "Paraguay": "파라과이", "Indonesia": "인도네시아",
    "Mexico": "멕시코", "South Africa": "남아공", "Iran": "이란", "United Kingdom": "영국",
    "Egypt": "이집트", "Nigeria": "나이지리아", "Bolivia": "볼리비아", "Uruguay": "우루과이",
    "Ethiopia": "에티오피아", "Serbia": "세르비아", "Philippines": "필리핀", "Vietnam": "베트남",
    "Tanzania": "탄자니아", "Uzbekistan": "우즈베키스탄", "Morocco": "모로코",
    "Thailand": "태국", "Malaysia": "말레이시아", "Colombia": "콜롬비아", "Honduras": "온두라스",
    "Guatemala": "과테말라", "Peru": "페루", "Uganda": "우간다", "Cote d'Ivoire": "코트디부아르",
    "Papua New Guinea": "파푸아뉴기니", "Japan": "일본", "Korea, South": "한국",
}


def log(msg):
    print(f"[grain-balance] {msg}", flush=True)


def fetch():
    parts = []
    attrs = set(ATTRS) | set(ATTR_ALIASES)
    for url in ZIPS:
        req = urllib.request.Request(url, headers={"User-Agent": "grain-balance/1.0"})
        with urllib.request.urlopen(req, timeout=600) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        df = pd.read_csv(z.open(name), encoding="latin-1", low_memory=False)
        commodities = [c[0] for c in CROPS.values()]
        part = df[df.Commodity_Description.isin(commodities) & (df.Market_Year >= 1995)]
        for c, g in part.groupby("Commodity_Description"):
            log(f"{c} attributes: {sorted(g.Attribute_Description.unique())}")
        parts.append(part[part.Attribute_Description.isin(attrs)])
    out = pd.concat(parts, ignore_index=True)[
        ["Commodity_Description", "Country_Name", "Market_Year", "Calendar_Year",
         "Month", "Attribute_Description", "Value"]]
    if out.empty:
        raise SystemExit("PSD returned no rows")
    out.to_csv(SLICE, index=False)
    log(f"{len(out)} rows -> {SLICE}")
    return out


def normalize(df):
    df = df.copy()
    df["Attribute_Description"] = df["Attribute_Description"].replace(ATTR_ALIASES)
    return df


def palm_risks():
    """Palm has no stage calendar; its weather call is the one each palm
    forecast publishes (weather_conditions)."""
    import glob
    label = {}
    try:
        with open(os.path.join(DATA, "climate_registry_v1.json"), encoding="utf-8") as f:
            for c in json.load(f).get("countries", {}).values():
                label[c.get("data_file", "")] = c.get("label_ko", "")
    except OSError:
        pass
    risks, tally = [], {"unfavorable": 0, "neutral": 0, "favorable": 0}
    for path in sorted(glob.glob(os.path.join(DATA, "*_yield_forecast.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                regions = json.load(f).get("regions", {})
        except (OSError, ValueError):
            continue
        for key, e in regions.items():
            wc = e.get("weather_conditions") or {}
            if not key.endswith("_palm_oil") or wc.get("verdict") not in tally:
                continue
            tally[wc["verdict"]] += 1
            if wc["verdict"] != "unfavorable":
                continue
            country = label.get(os.path.basename(path), key.split("_")[0])
            risks.append({"kind": "weather", "country_ko": country, "region_ko": "",
                          "crop_ko": "팜유", "season": e.get("season"),
                          "reason": [wc.get("reason_ko", "")],
                          "reference_only": wc.get("history_check") == "unmatched",
                          "text_ko": f"{country} 팜유: 날씨 불리"})
    return risks, tally


def world(g):
    """World totals by year: PSD's own World row when present, else the sum."""
    names = set(g.Country_Name)
    w = g[g.Country_Name == "World"] if "World" in names else g[g.Country_Name != "World"]
    return w.pivot_table(index="Market_Year", columns="Attribute_Description",
                         values="Value", aggfunc="sum").sort_index()


def season_label(y):
    return f"{y}/{str(y + 1)[-2:]}"


def region_names():
    """stage_conditions region key -> (country label, region label)."""
    out = {}
    try:
        with open(os.path.join(DATA, "climate_registry_v1.json"), encoding="utf-8") as f:
            reg = json.load(f)
    except OSError:
        return out
    for c in reg.get("countries", {}).values():
        for r in c.get("regions", []):
            for k in [r.get("key")] + list(r.get("crops_region_keys") or []):
                if k:
                    out.setdefault(k, (c.get("label_ko", ""), r.get("label_ko", k)))
    return out


def weather_risks(crops):
    try:
        with open(os.path.join(DATA, "stage_conditions_v1.json"), encoding="utf-8") as f:
            sc = json.load(f)
    except OSError:
        return [], {}
    names = region_names()
    risks, tally = [], {"unfavorable": set(), "neutral": set(), "favorable": set()}
    for key, entries in sc.get("regions", {}).items():
        for e in entries:
            if e.get("crop") not in crops:
                continue
            # A season already harvested is in the numbers, not a risk.
            if not any(s.get("state") in ("in_progress", "upcoming")
                       for s in e.get("stages", [])):
                continue
            ov = e.get("overall") or {}
            v = ov.get("verdict")
            country, region = names.get(key, ("", key))
            if v in tally:
                tally[v].add((country, region))
            if v != "unfavorable":
                continue
            bad = [s["name_ko"] for s in e.get("stages", [])
                   if s.get("status") == "unfavorable"]
            risks.append({
                "kind": "weather",
                "country_ko": country,
                "region_ko": region,
                "crop_ko": e.get("label_ko", ""),
                "season": e.get("season"),
                "stages_ko": bad,
                "reason": [s.get("reason_ko", "") for s in e.get("stages", [])
                           if s.get("status") == "unfavorable"][:2],
                "reference_only": ov.get("history_check") == "unmatched",
                "text_ko": f"{country} {region}: {'·'.join(bad)} 불리",
            })
    # Several monitor keys can share one area (Australia's winter crops are
    # one calendar for wheat, barley and canola): keep one line per area.
    seen, unique = set(), []
    for r in sorted(risks, key=lambda r: r["reference_only"]):
        if r["text_ko"] not in seen:
            seen.add(r["text_ko"])
            unique.append(r)
    # Calls whose past record matched the harvest come first.
    unique.sort(key=lambda r: (r["reference_only"], r["country_ko"]))
    return unique, {k: len(v) for k, v in tally.items()}


def igc_summary():
    """The IGC Grain Market Report summary page: report date, and per crop
    the GOI sub-index move and the sentences that mention the crop. Prose
    only -- the tables are in the members' report -- so this is what IGC
    says, kept in English, beside USDA's numbers."""
    try:
        req = urllib.request.Request(IGC_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
    except Exception as exc:
        log(f"IGC summary unavailable ({exc})")
        return None
    t = re.sub(r"(?s)<(script|style).*?</\1>", " ", raw)
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))
    m = re.search(r"IGC Grain Market Report - (\d{1,2} \w+ \d{4})", t)
    body = t.split("HIGHLIGHTS", 1)[-1].split("This page is currently", 1)[0]
    body = body.replace("(see chart)", " ")
    sentences = [x.strip() for x in re.split(r"(?<=[.])\s+(?=[A-Z])", body) if x.strip()]
    out = {"report_date": m.group(1) if m else None, "url": IGC_URL, "crops": {}}
    for key, word in IGC_WORD.items():
        hits = [x for x in sentences if word in x.lower()]
        sub = None
        for x in hits:
            mm = re.search(rf"GOI {word}s? sub-Index (\w+) by (?:a net )?(\d+(?:\.\d+)?)%", x, re.I)
            if mm and mm.group(1).lower() in UP | DOWN:
                v = float(mm.group(2))
                sub = v if mm.group(1).lower() in UP else -v
        out["crops"][key] = {"goi_change_pct": sub, "sentences_en": hits[:4]}
    if not any(c["sentences_en"] for c in out["crops"].values()):
        log("IGC summary had no crop sentences")
        return None
    return out


def crop_block(key, g, release):
    commodity, label, stage_crops = CROPS[key]
    w = world(g)
    w = w[w["Production"].notna()]
    cur = int(w.index.max())
    prev = cur - 1
    stu = (w["Ending Stocks"] / w["Domestic Consumption"] * 100).round(1)
    stu_avg = float(stu.loc[cur - 5:cur - 1].mean())
    p_cur, p_prev = float(w.loc[cur, "Production"]), float(w.loc[prev, "Production"])

    by = g[(g.Country_Name != "World") & (g.Attribute_Description == "Production")
           & g.Market_Year.isin([prev, cur])].pivot_table(
        index="Country_Name", columns="Market_Year", values="Value", aggfunc="sum")
    by = by.dropna().sort_values(cur, ascending=False)
    producers = []
    for name, row in by.head(TOP_PRODUCERS).iterrows():
        chg = (row[cur] / row[prev] - 1) * 100 if row[prev] else None
        producers.append({"country": name, "country_ko": COUNTRY_KO.get(name, name),
                          "production_kt": round(float(row[cur])),
                          "prev_kt": round(float(row[prev])),
                          "change_pct": None if chg is None else round(chg, 1),
                          "share_pct": round(float(row[cur]) / p_cur * 100, 1)})

    risks = []
    for p in producers:
        if (p["change_pct"] is not None and p["change_pct"] <= SUPPLY_DROP_PCT
                and p["share_pct"] >= SUPPLY_MIN_SHARE):
            risks.append({"kind": "supply", "country_ko": p["country_ko"],
                          "text_ko": f"{p['country_ko']} 생산 {p['change_pct']:+.0f}% "
                                     f"(세계의 {p['share_pct']:.0f}%)"})
    if stu.loc[cur] < stu_avg * 0.95:
        risks.append({"kind": "stocks",
                      "text_ko": f"세계 기말재고율 {stu.loc[cur]:.1f}% · 5년 평균 {stu_avg:.1f}%보다 낮음"})
    wx, tally = palm_risks() if key == "palm_oil" else weather_risks(stage_crops)

    return {
        "label_ko": label,
        "unit": UNITS.get(key, "kt"),
        "release": release,
        "url": PSD_URL,
        "prev": {"season": season_label(prev), "production_kt": round(p_prev),
                 "ending_stocks_kt": round(float(w.loc[prev, "Ending Stocks"])),
                 "stocks_to_use_pct": float(stu.loc[prev])},
        "current": {"season": season_label(cur), "production_kt": round(p_cur),
                    "change_pct": round((p_cur / p_prev - 1) * 100, 1),
                    "exports_kt": round(float(w.loc[cur, "Exports"])),
                    "ending_stocks_kt": round(float(w.loc[cur, "Ending Stocks"])),
                    "stocks_to_use_pct": float(stu.loc[cur]),
                    "stocks_to_use_5y_avg_pct": round(stu_avg, 1)},
        "producers": producers,
        "risks": risks + wx,
        "weather_tally": tally,
    }


WORKER_FRED = ("https://global-trade-dashboard.sunbin-info-kim.workers.dev/api/macro"
               "?source=fred&limit=10000&series_id={}")


def fred_series(sid):
    """FRED CSV, retried; GitHub's runners often time out there, so the
    dashboard Worker's FRED route is the fallback (curl: the Worker answers
    Python's default client with 403). Same as macro_monitor."""
    import subprocess
    import time
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(FRED_CSV.format(sid), headers={"User-Agent": "grain-balance/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                f = pd.read_csv(io.BytesIO(r.read()))
            f.columns = ["date", "price"]
            return f
        except Exception as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    proc = subprocess.run(["curl", "-sS", "-L", "-m", "60", "-A", "grain-balance/1.0",
                           WORKER_FRED.format(sid)], capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"FRED {sid}: {last}; worker rc={proc.returncode}")
    doc = json.loads(proc.stdout)
    if isinstance(doc, dict) and "body" in doc:
        doc = doc["body"]
    obs = [(o["date"][:10], o["value"]) for o in (doc or {}).get("observations") or []
           if o.get("value") not in (None, "", ".")]
    if not obs:
        raise RuntimeError(f"FRED {sid}: {last}; worker returned nothing")
    return pd.DataFrame(obs, columns=["date", "price"])


def fetch_prices():
    frames = []
    for key, (sid, _) in PRICE_IDS.items():
        try:
            f = fred_series(sid)
        except Exception as exc:  # one series down must not drop the rest
            log(f"price {sid} unavailable ({exc})")
            continue
        f["crop"] = key
        frames.append(f)
    if not frames:
        raise RuntimeError("no price series")
    out = pd.concat(frames, ignore_index=True)
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out = out.dropna().sort_values(["crop", "date"])
    out.to_csv(PRICES, index=False)
    log(f"{len(out)} price rows -> {PRICES}")
    return out


def _check_verdict(ample, neutral, tight, corr):
    """supported: tight > neutral > ample and the gap moves against price
    (corr <= -0.2). tight_only: tight years rose clearly more than both
    others (10+ points) with the same corr, while ample and neutral did not
    separate. Anything else: none. The palm check's bare `a < n < t` passed
    gaps of a few tenths of a point, so the size and corr floors are added."""
    if None in (neutral, tight) or corr > -0.2:
        return "none"
    others = [v for v in (ample, neutral) if v is not None]
    if ample is not None and ample < neutral < tight and tight - ample >= 10:
        return "supported"
    if all(tight - v >= 10 for v in others):
        return "tight_only"
    return "none"


def price_check(key, g, prices):
    """Did tight stocks line up with rising prices?

    For each marketing year, stocks-to-use against its own 5-season average
    is classed ample (> +10%), tight (< -10%) or neutral, and the IMF world
    price averaged over that marketing year is compared with the year
    before. Ex-China is the headline: China holds about half the world's
    wheat and corn stocks and does not export them. Final USDA estimates are
    used, so this checks whether the signal and the price agree, not
    whether an early-season estimate called the price.
    """
    import numpy as np

    sid, start = PRICE_IDS[key]
    pr = prices[prices.crop == key].copy()
    pr["date"] = pd.to_datetime(pr["date"])
    pr["my"] = pr.date.dt.year - (pr.date.dt.month < start)
    full = pr.groupby("my").price.agg(["mean", "count"])
    full = full[full["count"] == 12]["mean"]
    chg = (full / full.shift(1) - 1) * 100

    def stu_table(frame):
        w = frame.pivot_table(index="Market_Year", columns="Attribute_Description",
                              values="Value", aggfunc="sum").sort_index()
        return w["Ending Stocks"] / w["Domestic Consumption"] * 100

    out = {}
    bases = [("world", g[g.Country_Name != "World"])]
    if key in EX_CHINA:
        bases.insert(0, ("ex_china", g[~g.Country_Name.isin(["China", "World"])]))
    for basis, frame in bases:
        stu = stu_table(frame)
        rows = []
        for y in stu.index:
            past = stu.loc[y - 5:y - 1]
            if len(past) < 5 or y not in chg.index or pd.isna(chg.get(y)):
                continue
            gap = (stu.loc[y] / past.mean() - 1) * 100
            v = "ample" if gap > BAND_PCT else "tight" if gap < -BAND_PCT else "neutral"
            rows.append({"season": season_label(int(y)), "stu_pct": round(float(stu.loc[y]), 1),
                         "stu_vs_5y_pct": round(float(gap), 1), "verdict": v,
                         "price_change_pct": round(float(chg[y]), 1)})
        if len(rows) < 10:
            continue
        t = pd.DataFrame(rows)
        classes = {v: {"n": int(len(x)), "mean_change_pct": round(float(x.price_change_pct.mean()), 1),
                       "rose_share": round(float((x.price_change_pct > 0).mean()), 2)}
                   for v, x in t.groupby("verdict")}
        corr = float(np.corrcoef(t.stu_vs_5y_pct, t.price_change_pct)[0, 1])
        a, n, ti = (classes.get(k, {}).get("mean_change_pct") for k in ("ample", "neutral", "tight"))
        out[basis] = {"seasons": [rows[0]["season"], rows[-1]["season"]], "n": len(rows),
                      "classes": classes, "corr_gap_vs_change": round(corr, 2),
                      "verdict": _check_verdict(a, n, ti, corr),
                      "rows": rows}
    if not out:
        return None
    return {"price": f"IMF {sid} (FRED), marketing-year average from month {start}",
            "band_pct": BAND_PCT, "headline": "ex_china" if "ex_china" in out else "world", **out}


def release_of(df):
    last = df.sort_values(["Calendar_Year", "Month"]).iloc[-1]
    return f"{int(last.Calendar_Year)}년 {int(last.Month)}월 USDA WASDE"


def main(argv):
    if argv[:1] == ["apply"]:
        df = pd.read_csv(SLICE)
    else:
        try:
            df = fetch()
        except Exception as exc:  # keep the committed slice
            log(f"PSD fetch failed ({exc}); using {SLICE}")
            df = pd.read_csv(SLICE)
    release = release_of(df)
    df = normalize(df)
    prices = None
    if argv[:1] != ["apply"]:
        try:
            prices = fetch_prices()
        except Exception as exc:
            log(f"FRED prices unavailable ({exc}); using {PRICES}")
    if prices is None and os.path.exists(PRICES):
        prices = pd.read_csv(PRICES)
    crops = {}
    for key, (commodity, _, _) in CROPS.items():
        g = df[df.Commodity_Description == commodity]
        if g.empty:
            log(f"{key}: no PSD rows ({commodity})")
            continue
        try:
            crops[key] = crop_block(key, g, release)
        except (KeyError, ValueError) as exc:
            log(f"{key}: skipped ({exc!r}); attributes {sorted(g.Attribute_Description.unique())}")
            continue
        c = crops[key]
        if prices is not None and (prices.crop == key).any():
            pc = price_check(key, g, prices)
            if pc:
                c["price_check"] = pc
                for b in ("ex_china", "world"):
                    if b in pc:
                        log(f"{key} price check {b}: " + ", ".join(
                            f"{v} n={x['n']} {x['mean_change_pct']:+.1f}%" for v, x in pc[b]["classes"].items())
                            + f", corr {pc[b]['corr_gap_vs_change']}, {pc[b]['verdict']}")
        log(f"{key}: {c['prev']['season']} {c['prev']['production_kt']:,} -> "
            f"{c['current']['season']} {c['current']['production_kt']:,} kt, "
            f"{len(c['risks'])} risks")
    igc = igc_summary()
    if igc:
        for key, c in crops.items():
            if key not in igc["crops"]:
                continue
            c["igc"] = {"report_date": igc["report_date"], "url": igc["url"],
                        **igc["crops"].get(key, {})}
        log(f"IGC {igc['report_date']}: " + ", ".join(
            f"{k} {v['goi_change_pct']}" for k, v in igc["crops"].items()))
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_ko": f"{release} (PSD) · 국제곡물이사회(IGC) 시황 요약 · 날씨 리스크는 작황 모니터 생육 단계 판정",
        "crops": crops,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
        f.write("\n")
    log(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
