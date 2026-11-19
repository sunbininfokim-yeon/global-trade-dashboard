"""World Bank monthly fertilizer prices for the urea and potash trade views.

Usage: python3 scripts/fertilizer/prices.py          # fetch, write
       python3 scripts/fertilizer/prices.py apply    # rebuild from prices.csv

The Pink Sheet (CMO historical data, monthly) is the free benchmark series:
urea and potassium chloride (each at the grade and port the sheet names),
with DAP and TSP for context. The
workbook link moves now and then, so the commodity-markets page is read for
the current one and the last known URL is the fallback.

Writes
  scripts/fertilizer/prices.csv              monthly USD/t (committed)
  public/data/fertilizer_prices_v1.json
"""

import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "public", "data"))
CSV = os.path.join(HERE, "prices.csv")
OUT = os.path.join(DATA, "fertilizer_prices_v1.json")

PAGE = "https://www.worldbank.org/en/research/commodity-markets"
FALLBACK = ("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-"
            "0050012026/related/CMO-Historical-Data-Monthly.xlsx")
UA = {"User-Agent": "Mozilla/5.0 (compatible; fertilizer-prices/1.0)"}

# Column in the "Monthly Prices" sheet (matched on its leading words) -> key.
SERIES = {
    "urea": ("Urea", "요소"),
    "potash": ("Potassium chloride", "염화칼륨"),
    "dap": ("DAP", "인산이암모늄(DAP)"),
    "tsp": ("TSP", "중과석(TSP)"),
}
# Trade view -> the series its card leads with.
VIEWS = {"urea": "urea", "potash": "potash"}


def log(msg):
    print(f"[fertilizer] {msg}", flush=True)


def _get(url, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def workbook_url():
    try:
        html = _get(PAGE, 60).decode("utf-8", "replace")
        m = re.search(r'https://thedocs\.worldbank\.org/[^"\']*CMO-Historical-Data-Monthly\.xlsx', html)
        if m:
            return m.group(0)
        log("commodity-markets page has no monthly workbook link; using the last known URL")
    except Exception as exc:  # noqa: BLE001
        log(f"commodity-markets page unavailable ({exc}); using the last known URL")
    return FALLBACK


def fetch():
    url = workbook_url()
    log(f"workbook {url}")
    raw = pd.read_excel(io.BytesIO(_get(url)), sheet_name="Monthly Prices", header=None)
    # The header row is the one whose first cells name the series; dates look
    # like 1960M01 in the first column below it.
    head = None
    for i in range(min(15, len(raw))):
        cells = [str(v) for v in raw.iloc[i].tolist()]
        if any(c.strip().startswith("Urea") for c in cells):
            head = i
            break
    if head is None:
        raise RuntimeError("no Urea column in Monthly Prices")
    names = [str(v).strip() for v in raw.iloc[head].tolist()]
    cols = {}
    for key, (word, _) in SERIES.items():
        hit = [j for j, n in enumerate(names) if n.lower().startswith(word.lower())]
        if hit:
            cols[key] = hit[0]
        else:
            log(f"{key}: no column starting with {word!r}")
    rows = []
    for i in range(head + 1, len(raw)):
        stamp = str(raw.iat[i, 0]).strip()
        m = re.fullmatch(r"(\d{4})M(\d{2})", stamp)
        if not m:
            continue
        rec = {"month": f"{m.group(1)}-{m.group(2)}"}
        for key, j in cols.items():
            rec[key] = pd.to_numeric(raw.iat[i, j], errors="coerce")
        rows.append(rec)
    df = pd.DataFrame(rows).dropna(how="all", subset=list(cols))
    log(f"{len(df)} months, {df.month.min()} .. {df.month.max()}, columns "
        + ", ".join(f"{k}={names[j]!r}" for k, j in cols.items()))
    return df


def summary(df, key):
    s = df[["month", key]].dropna()
    if len(s) < 25:
        return None
    s = s.set_index("month")[key]
    last_m = s.index[-1]
    last = float(s.iloc[-1])

    def chg(back):
        if len(s) <= back:
            return None
        base = float(s.iloc[-1 - back])
        return round((last / base - 1) * 100, 1) if base else None

    five = s.iloc[-61:-1]
    rank = float((s.iloc[-121:] <= last).mean() * 100) if len(s) >= 121 else None
    return {
        "label_ko": SERIES[key][1],
        "month": last_m, "usd_t": round(last, 1),
        "mom_pct": chg(1), "yoy_pct": chg(12),
        "avg_5y_usd_t": round(float(five.mean()), 1),
        "vs_5y_pct": round((last / float(five.mean()) - 1) * 100, 1),
        "pct_rank_10y": None if rank is None else round(rank),
        "series": [{"month": m, "usd_t": round(float(v), 1)} for m, v in s.iloc[-36:].items()],
    }


def main(argv):
    if argv[:1] == ["apply"]:
        df = pd.read_csv(CSV, dtype={"month": str})
    else:
        try:
            df = fetch()
            df.to_csv(CSV, index=False)
        except Exception as exc:  # keep the committed series
            log(f"fetch failed ({exc}); using {CSV}")
            df = pd.read_csv(CSV, dtype={"month": str})
    series = {}
    for key in SERIES:
        if key in df:
            s = summary(df, key)
            if s:
                series[key] = s
                log(f"{key}: {s['month']} ${s['usd_t']}/t, m/m {s['mom_pct']}%, y/y {s['yoy_pct']}%, "
                    f"vs 5y {s['vs_5y_pct']}%")
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_ko": "세계은행 원자재 가격(Pink Sheet) 월간, 미국 달러/톤",
        "url": PAGE,
        "views": VIEWS,
        "series": series,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
        f.write("\n")
    log(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
