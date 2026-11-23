"""Brazil's own monthly export statistics to Korea (ComexStat, MDIC).

Brazil reaches Comtrade months late and unevenly, and the mirror window in
korea_sources.py needs every 10%+ supplier to have reported a month before
it can show Korea's latest 12 months -- Brazil is 38% of Korea's soybeans
and 8% of its corn. ComexStat publishes the same customs data early in the
following month with no key. Each month ComexStat has published is merged
into the mirror as Brazil's report, including zero for months with no
shipment to Korea (absent from Comtrade, they used to block the window).

Only Actions can reach the API; failures leave the mirror as it was.
"""

import json
import urllib.error
import urllib.request
from datetime import date

URL = "https://api-comexstat.mdic.gov.br/general?language=en"
HEADINGS = {"1001": "wheat", "1005": "corn", "1201": "soybeans"}
BRAZIL = "76"


def log(msg):
    print(f"[comexstat] {msg}", flush=True)


def _months_ago(today, n):
    y, m = today.year, today.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def _field(row, *names):
    low = {k.lower(): v for k, v in row.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def is_south_korea(name):
    n = (name or "").lower()
    return ("korea" in n or "coreia" in n) and not any(
        w in n for w in ("north", "norte", "democratic", "democrática", "dem."))


def parse(body):
    """{YYYYMM: {crop: tonnes to Korea}} for every month in the response, so
    a published month with no Korea row reads as zero."""
    rows = (body.get("data") or {}).get("list") if isinstance(body.get("data"), dict) else body.get("data")
    out = {}
    for r in rows or []:
        y, m = _field(r, "year", "coAno"), _field(r, "monthNumber", "month", "coMes")
        if y is None or m is None:
            continue
        m = str(m).split(".")[0][:2]
        if not m.isdigit():
            continue
        ym = f"{int(y)}{int(m):02d}"
        month = out.setdefault(ym, {c: 0 for c in HEADINGS.values()})
        code = str(_field(r, "headingCode", "coSh4", "heading") or "")[:4]
        crop = HEADINGS.get(code)
        country = _field(r, "country", "noPais", "noPaisIng")
        if crop and is_south_korea(str(country)):
            kg = float(_field(r, "metricKG", "kgLiquido") or 0)
            month[crop] += round(kg / 1000)
    return out


def fetch(today=None, months=15):
    today = today or date.today()
    body = {"flow": "export", "monthDetail": True,
            "period": {"from": _months_ago(today, months), "to": _months_ago(today, 1)},
            "filters": [{"filter": "heading", "values": list(HEADINGS)}],
            "details": ["country", "heading"], "metrics": ["metricKG"]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json",
                                          "User-Agent": "global-trade-dashboard"})
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = json.load(r)
    got = parse(payload)
    if not got:
        log(f"no months parsed; response keys {list(payload)[:6]}, "
            f"sample {json.dumps(payload)[:400]}")
    return got


def merge(mirror, brazil):
    """Write Brazil's months into the mirror cache in place. Returns months set."""
    reps = mirror.setdefault("_reporters", {})
    for ym, crops in brazil.items():
        if ym not in reps:
            # Nothing else known for that month; adding Brazil alone would
            # let a later window treat the others as reported.
            continue
        for crop, t in crops.items():
            rows = mirror.setdefault(crop, {}).setdefault(ym, {})
            if t:
                rows[BRAZIL] = t
            else:
                rows.pop(BRAZIL, None)
        reps[ym] = sorted(set(reps[ym]) | {BRAZIL}, key=int)
    return sorted(ym for ym in brazil if ym in reps)


def load(mirror):
    try:
        brazil = fetch()
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        log(f"unavailable ({exc}); mirror unchanged")
        return []
    done = merge(mirror, brazil)
    for ym in done:
        log(f"{ym}: Brazil to Korea " + ", ".join(f"{c} {t:,} t" for c, t in brazil[ym].items()))
    return done
