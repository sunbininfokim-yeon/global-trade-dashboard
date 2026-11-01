#!/usr/bin/env python3
"""Does heavy rain in Indonesia's coal belt cut its coal exports?

GS Global sells Indonesian coal (off-take from BSSR, South Kalimantan) to
Korean power plants. Kalimantan coal moves pit -> river barge -> ship, and
wet months flood pits, close haul roads and slow barges on the Barito and
Mahakam. This module tests that link on public data before anything is
shown as a risk read-out.

Data
  labels  Indonesia's monthly coal exports (HS 2701, net weight), UN Comtrade.
          With COMTRADE_API_KEY the keyed endpoint is used, otherwise the
          public preview. China's and India's monthly imports from Indonesia
          are collected too, as a cross-check that the label is not a
          reporting artefact.
  rain    NASA POWER daily precipitation at six mining / barge points,
          summed by month, as a z-score against the same calendar month
          (2001-2020). Weighted to roughly match output shares.
  enso    Nino 3.4 monthly anomaly from public/data/sst_regions_v1.json.

Test, fixed before looking at the data (2026-11-01)
  r_t     log(tonnes per day) minus a centred 13-month median (t excluded),
          then minus its calendar-month mean. Diagnostic only: it uses the
          following six months, so it measures the dent, not a forecast.
  x_t     coal-belt rain z of month t.
  Pass when all three hold:
    1. corr(r, x) <= -0.15
    2. circular-shift p < 0.05: the rain series is rotated by whole years
       (keeps season and autocorrelation) and the correlation recomputed;
       p = share of rotations at least as negative.
    3. leave-one-year-out correlation stays negative for every year.
  Excluded months: 2022-01..02 (export ban), 2020-04..06 (COVID demand).
  ENSO is reported, not tested: corr(Nino3.4, rain z) and the mean r in
  months with Nino3.4 <= -0.5 (La Nina).

Run (needs Comtrade and NASA POWER, i.e. a GitHub runner):
  python3 coal_weather.py labels
  python3 coal_weather.py rain
  python3 coal_weather.py analyze
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
PUBLIC = HERE.parents[1] / "public" / "data"
SST_FILE = PUBLIC / "sst_regions_v1.json"
OUT_FILE = PUBLIC / "coal_weather_risk_v1.json"

FIRST_YEAR = 2010
RAIN_START = date(2001, 1, 1)
BASELINE = (2001, 2020)

# Indonesia exports; China and India import from Indonesia (mirror check).
SERIES = {
    "idn_exports": dict(reporterCode="360", flowCode="X", partnerCode="0"),
    "chn_from_idn": dict(reporterCode="156", flowCode="M", partnerCode="360"),
    "ind_from_idn": dict(reporterCode="699", flowCode="M", partnerCode="360"),
}

# Weights roughly follow output: East Kalimantan ~half, South Kalimantan
# ~a third, South Sumatra the rest. Fixed before the test.
POINTS = [
    dict(name="kutai_timur", region="East Kalimantan", lat=0.55, lon=117.45, w=0.25),
    dict(name="kutai_kartanegara", region="East Kalimantan", lat=-0.40, lon=117.00, w=0.25),
    dict(name="tabalong_balangan", region="South Kalimantan (BSSR)", lat=-2.05, lon=115.45, w=0.15),
    dict(name="tanah_bumbu", region="South Kalimantan", lat=-3.40, lon=115.80, w=0.10),
    dict(name="barito_lower", region="South Kalimantan barge route", lat=-3.10, lon=114.70, w=0.10),
    dict(name="muara_enim", region="South Sumatra", lat=-3.70, lon=103.80, w=0.15),
]

EXCLUDE = {"2020-04", "2020-05", "2020-06", "2022-01", "2022-02"}
PASS_CORR = -0.15
PASS_P = 0.05


def log(msg: str) -> None:
    print(f"[coal_weather] {msg}", flush=True)


def _get(url: str, headers: dict | None = None, attempts: int = 5) -> dict:
    delay = 15
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "coal-weather/1.0", **(headers or {})})
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read())
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            if attempt == attempts - 1:
                raise
            log(f"retry {attempt + 1} in {delay}s after {exc}")
            time.sleep(delay)
            delay = min(delay * 2, 240)
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------- labels

def _months(year: int) -> list[str]:
    return [f"{year}{m:02d}" for m in range(1, 13)]


def comtrade_year(series: dict, year: int, key: str | None) -> dict[str, float]:
    params = dict(series, period=",".join(_months(year)), cmdCode="2701",
                  partner2Code="0", customsCode="C00", motCode="0")
    if key:
        url = "https://comtradeapi.un.org/data/v1/get/C/M/HS?" + urlencode(params)
        body = _get(url, {"Ocp-Apim-Subscription-Key": key})
    else:
        url = "https://comtradeapi.un.org/public/v1/preview/C/M/HS?" + urlencode(params)
        body = _get(url)
    out = {}
    for row in body.get("data") or []:
        if row.get("cmdCode") != "2701" or str(row.get("partner2Code")) != "0":
            continue
        kg = row.get("netWgt")
        if isinstance(kg, (int, float)) and kg > 0:
            p = str(row["period"])
            out[f"{p[:4]}-{p[4:6]}"] = float(kg) / 1000.0
    return out


def collect_labels() -> None:
    key = os.getenv("COMTRADE_API_KEY") or os.getenv("COMTRADE_SUBSCRIPTION_KEY")
    log("Comtrade " + ("keyed endpoint" if key else "public preview"))
    path = DATA / "labels.csv"
    old = pd.read_csv(path, dtype={"month": str}) if path.exists() else pd.DataFrame(columns=["month", "series", "tonnes"])
    rows = {(r.month, r.series): r.tonnes for r in old.itertuples()}
    this_year = date.today().year
    for name, series in SERIES.items():
        for year in range(FIRST_YEAR, this_year + 1):
            have = sum((f"{year}-{m:02d}", name) in rows for m in range(1, 13))
            if have == 12 and year < this_year - 1:
                continue  # settled years are not re-read
            try:
                got = comtrade_year(series, year, key)
            except Exception as exc:  # noqa: BLE001 - keep what we have
                log(f"{name} {year}: {exc}")
                continue
            for month, tonnes in got.items():
                rows[(month, name)] = tonnes
            log(f"{name} {year}: {len(got)} months")
            time.sleep(1.5 if key else 6)
    frame = pd.DataFrame([dict(month=m, series=s, tonnes=round(t, 1)) for (m, s), t in rows.items()])
    frame.sort_values(["series", "month"]).to_csv(path, index=False)
    log(f"wrote {path.name}: {len(frame)} rows")


# ---------------------------------------------------------------- rain

def power_monthly(point: dict) -> pd.Series:
    url = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR&community=AG"
           f"&longitude={point['lon']}&latitude={point['lat']}"
           f"&start={RAIN_START:%Y%m%d}&end={date.today():%Y%m%d}&format=JSON")
    log(f"POWER {point['name']}")
    values = _get(url)["properties"]["parameter"]["PRECTOTCORR"]
    s = pd.Series(values, dtype=float)
    s.index = pd.to_datetime(s.index, format="%Y%m%d")
    s = s[s > -900]
    by_month = s.groupby(s.index.to_period("M"))
    total, days = by_month.sum(), by_month.count()
    full = days >= days.index.days_in_month - 1  # allow one missing day
    return total[full]


def collect_rain() -> None:
    cols = {}
    for point in POINTS:
        cols[point["name"]] = power_monthly(point)
    frame = pd.DataFrame(cols)
    frame.index = frame.index.astype(str)
    frame.index.name = "month"
    frame.round(1).to_csv(DATA / "rain_monthly.csv")
    log(f"wrote rain_monthly.csv: {len(frame)} months, last {frame.dropna().index.max()}")


# ---------------------------------------------------------------- analysis

def rain_z(rain: pd.DataFrame) -> pd.Series:
    """Weighted coal-belt rain z-score vs the same calendar month."""
    rain = rain.copy()
    cal = pd.Index([m[5:7] for m in rain.index])
    years = pd.Index([int(m[:4]) for m in rain.index])
    base = (years >= BASELINE[0]) & (years <= BASELINE[1])
    z = pd.DataFrame(index=rain.index)
    for p in POINTS:
        col = rain[p["name"]]
        mu = col[base].groupby(cal[base]).mean()
        sd = col[base].groupby(cal[base]).std()
        z[p["name"]] = (col.values - mu.reindex(cal).values) / sd.reindex(cal).values
    w = pd.Series({p["name"]: p["w"] for p in POINTS})
    ok = z.notna().all(axis=1)
    return (z[ok] * w).sum(axis=1) / w.sum()


def residuals(tonnes: pd.Series) -> pd.Series:
    """log tonnes/day minus centred 13-month median (t excluded), de-seasoned."""
    idx = pd.PeriodIndex(tonnes.index, freq="M")
    rate = np.log(tonnes.values / idx.days_in_month.values)
    s = pd.Series(rate, index=idx).sort_index()
    s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))
    out = {}
    for i, month in enumerate(s.index):
        if np.isnan(s.iloc[i]):
            continue
        nb = s.iloc[max(0, i - 6):i].tolist() + s.iloc[i + 1:i + 7].tolist()
        nb = [v for v in nb if not np.isnan(v)]
        if len(nb) >= 10:
            out[str(month)] = s.iloc[i] - float(np.median(nb))
    r = pd.Series(out)
    cal = pd.Index([m[5:7] for m in r.index])
    return r - r.groupby(cal).transform("mean")


def corr(a: pd.Series, b: pd.Series) -> float:
    return float(np.corrcoef(a.values, b.values)[0, 1])


def circular_p(r: pd.Series, x_full: pd.Series, observed: float) -> tuple[float, int]:
    """Rotate the whole rain series by k*12 months; share of rotations as negative."""
    months = list(x_full.index)
    n = len(months)
    rotations = range(12, n - 11, 12)
    vals = []
    for k in rotations:
        shifted = pd.Series(np.roll(x_full.values, k), index=months)
        joined = pd.concat([r, shifted], axis=1, join="inner").dropna()
        vals.append(corr(joined.iloc[:, 0], joined.iloc[:, 1]))
    vals = np.array(vals)
    return float((np.sum(vals <= observed) + 1) / (len(vals) + 1)), len(vals)


def assess(tonnes: pd.Series, x: pd.Series, nino: pd.Series | None) -> dict:
    r = residuals(tonnes)
    r = r[~r.index.isin(EXCLUDE)]
    joined = pd.concat([r.rename("r"), x.rename("x")], axis=1, join="inner").dropna()
    if len(joined) < 60:
        return dict(n=len(joined), passed=False, reason="too few months")
    c = corr(joined.r, joined.x)
    lag = pd.concat([r.rename("r"), x.shift(1).rename("x1")], axis=1, join="inner").dropna()
    c_lag = corr(lag.r, lag.x1)
    p, n_rot = circular_p(joined.r, x, c)
    years = sorted({m[:4] for m in joined.index})
    loyo = {y: round(corr(joined.r[~joined.index.str.startswith(y)], joined.x[~joined.index.str.startswith(y)]), 3)
            for y in years}
    wet = joined[joined.x >= 1.0]
    dry = joined[joined.x < 1.0]
    out = dict(
        n=len(joined), first=joined.index.min(), last=joined.index.max(),
        corr=round(c, 3), corr_prev_month_rain=round(c_lag, 3),
        circular_p=round(p, 3), rotations=n_rot,
        loyo_max=max(loyo.values()), loyo=loyo,
        wet_months=len(wet),
        wet_mean_pct=round(100 * (np.exp(wet.r.mean()) - 1), 1) if len(wet) else None,
        other_mean_pct=round(100 * (np.exp(dry.r.mean()) - 1), 1),
        slope_pct_per_z=round(100 * (np.exp(np.polyfit(joined.x, joined.r, 1)[0]) - 1), 2),
    )
    # Wet-season only (Nov-Mar), where the mechanism should bite hardest.
    wet_season = joined[[m[5:7] in {"11", "12", "01", "02", "03"} for m in joined.index]]
    out["corr_wet_season"] = round(corr(wet_season.r, wet_season.x), 3)
    if nino is not None:
        jn = pd.concat([joined, nino.rename("n34")], axis=1, join="inner").dropna()
        xn = pd.concat([x.rename("x"), nino.rename("n34")], axis=1, join="inner").dropna()
        la = jn[jn.n34 <= -0.5]
        out["enso"] = dict(
            corr_nino_rain=round(corr(xn.x, xn.n34), 3),
            corr_nino_exports=round(corr(jn.r, jn.n34), 3),
            la_nina_months=len(la),
            la_nina_mean_pct=round(100 * (np.exp(la.r.mean()) - 1), 1) if len(la) else None,
        )
    out["passed"] = bool(c <= PASS_CORR and p < PASS_P and out["loyo_max"] < 0)
    return out


def load_nino() -> pd.Series | None:
    try:
        payload = json.loads(SST_FILE.read_text(encoding="utf-8"))
        region = next(r for r in payload["regions"] if r["id"] == "nino34")
        return pd.Series({m: float(v) for m, v in region["series"]})
    except (OSError, StopIteration, KeyError, ValueError):
        return None


def risk_level(z: float) -> str:
    if z >= 1.5:
        return "high"
    if z >= 0.75:
        return "elevated"
    return "normal"


def analyze() -> dict:
    labels = pd.read_csv(DATA / "labels.csv", dtype={"month": str})
    rain = pd.read_csv(DATA / "rain_monthly.csv", dtype={"month": str}).set_index("month")
    x = rain_z(rain)
    nino = load_nino()
    results = {}
    for name in SERIES:
        s = labels[labels.series == name].set_index("month").tonnes
        if len(s) >= 60:
            results[name] = assess(s, x, nino)
            log(f"{name}: {json.dumps({k: v for k, v in results[name].items() if k != 'loyo'})}")
        else:
            results[name] = dict(n=int(len(s)), passed=False, reason="too few months")
    primary = results.get("idn_exports", {})
    passed = bool(primary.get("passed"))
    recent = [dict(month=m, rain_z=round(float(v), 2),
                   by_point={p["name"]: (None if pd.isna(rain.at[m, p["name"]]) else float(rain.at[m, p["name"]]))
                             for p in POINTS})
              for m, v in x.tail(6).items()]
    latest = recent[-1] if recent else None
    payload = dict(
        schema_version="coal_weather_risk_v1",
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status="validated" if passed else "not_validated",
        method_ko=("석탄 산지(동·남칼리만탄, 남수마트라) 6곳의 월 강수를 같은 달 평년(2001~2020)과 비교한 z값. "
                   "인도네시아 월별 석탄 수출(UN Comtrade, HS 2701)의 추세 대비 편차와의 관계를 사전에 정한 기준으로 검증."),
        points=[{k: p[k] for k in ("name", "region", "lat", "lon", "w")} for p in POINTS],
        test=dict(pass_rule=f"corr <= {PASS_CORR}, circular-shift p < {PASS_P}, leave-one-year-out all negative",
                  excluded_months=sorted(EXCLUDE), results=results),
        latest=(dict(latest, risk=risk_level(latest["rain_z"]) if passed else None) if latest else None),
        recent=recent,
        nino34_latest=(dict(month=nino.index[-1], value=round(float(nino.iloc[-1]), 2)) if nino is not None else None),
    )
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"wrote {OUT_FILE.name}: status={payload['status']}")
    return payload


def main(argv: list[str]) -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    cmd = argv[1] if len(argv) > 1 else "analyze"
    if cmd == "labels":
        collect_labels()
    elif cmd == "rain":
        collect_rain()
    elif cmd == "analyze":
        analyze()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
