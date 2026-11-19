"""Northern Sea Route seasons from ice ON the route line, by ship class.

Input: scripts/data/nsr_route_ice/<year>.csv (nsr_route_ice.py) -- per day,
the p90 sea ice concentration (%) of each of six legs along the route.
The route's value for a day is its worst leg; a 5-day centred mean smooths
it, gaps of up to 4 days (every-other-day record before 1987) are filled.

Ship classes (fixed 2026-11-19 before any season was computed). Sea ice
concentration alone cannot say how thick the ice is, so these are
concentration proxies, labelled as such:
  open_water  no ice class        worst leg <= 15 %  (ice edge; open water)
  arc4        Arc4 / Ice class 1A worst leg <= 50 %  (light, broken ice)
  arc7        Arc7 (Yamal LNG)    worst leg <= 80 %  (close ice, no fast ice)
Season = the longest run of passable days from 1 May (open_water from
1 June), joining runs separated by 5 days or less.

Outlook, per class: open date, close date and days of the next unfinished
season. Baseline = linear trend over earlier seasons. Predictors, each
detrended over the earlier years at the same calendar date:
  F  mean worst-leg concentration of the 30 days up to the issue date
  V  PIOMAS pan-Arctic ice volume of the last complete month (thickness
     memory through spring -- Day et al. 2014, Bushuk et al. 2017)
Forward test from 2001; the F+V model is published only when its forward MAE
is at least 10% below the trend's; ranges from the published method's own
forward errors. Skill by issue month is reported for F and for F+V so the
spring gain (or its absence) is visible.

Validation: the first entry and last exit dates of transit voyages that
CHNL (Centre for High North Logistics) published for 2020, 2021 and 2025.
Those voyages include ice-class ships and icebreaker escort, so they bound
the Arc7 season, not the open-water one.
"""
from __future__ import annotations

import csv
import glob
import os
import statistics
from datetime import date, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "nsr_route_ice")
LEGS = [("kara", "카라해"), ("vilkitsky", "빌키츠키 해협"), ("laptev", "랍테프해"),
        ("sannikov", "산니코프 해협"), ("east_siberian", "동시베리아해"), ("long_chukchi", "롱 해협·추코트해")]
CLASSES = [
    ("open_water", "일반 선박 (빙급 없음)", 0.15, (6, 1)),
    ("arc4", "Arc4 빙급 (얇은 얼음)", 0.50, (5, 1)),
    ("arc7", "Arc7 빙급 (야말 LNG선급)", 0.80, (5, 1)),
]
SMOOTH, GAP, WINDOW, FIRST_TEST, PASS = 5, 5, 30, 2001, 0.10
# CHNL transit records: first NSR entry and last NSR exit of transit voyages.
TRANSITS = [
    {"year": 2020, "first_entry": "2020-07-20", "last_exit": "2020-11-17", "n": 64,
     "url": "https://arctic-lio.com/analysys-of-shipping-traffic-in-the-nsr-waters-in-2020/"},
    {"year": 2021, "first_entry": "2021-07-08", "last_exit": None, "n": 85,
     "url": "https://arctic-lio.com/transit-voyages-on-nsr-in-2021/"},
    {"year": 2025, "first_entry": "2025-06-30", "last_exit": "2025-11-17", "n": 103,
     "url": "https://chnl.no/news/main-results-of-nsr-transit-navigation-in-2025/"},
]


def load():
    """{date: {leg: concentration %}} from the yearly CSVs."""
    out = {}
    for p in sorted(glob.glob(os.path.join(DATA, "*.csv"))):
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                vals = {}
                for k, _ in LEGS:
                    try:
                        vals[k] = float(r[k])
                    except (KeyError, ValueError):
                        pass
                if vals:
                    out[date.fromisoformat(r["date"])] = vals
    return out


def worst_series(raw):
    """{date: worst-leg fraction}, gaps <= 4 days filled, 5-day centred mean."""
    pts = {d: max(v.values()) / 100.0 for d, v in raw.items() if len(v) >= len(LEGS) - 1}
    if not pts:
        return {}
    known = sorted(pts)
    filled = dict(pts)
    for a, b in zip(known, known[1:]):
        gap = (b - a).days
        if 1 < gap <= 5:
            for k in range(1, gap):
                filled[a + timedelta(days=k)] = pts[a] + (pts[b] - pts[a]) * k / gap
    days = sorted(filled)
    out, h = {}, SMOOTH // 2
    for d in days:
        w = [filled[d + timedelta(days=k)] for k in range(-h, h + 1) if (d + timedelta(days=k)) in filled]
        if len(w) >= 3:
            out[d] = statistics.fmean(w)
    return out


def season(series, year, thr, start_md, upto=None):
    d, end = date(year, *start_md), date(year, 12, 31)
    if upto:
        end = min(end, upto)
    runs, start, last = [], None, None
    while d <= end:
        x = series.get(d)
        if x is not None and x <= thr:
            if start is None or (d - last).days > GAP + 1:
                if start is not None:
                    runs.append((start, last))
                start = d
            last = d
        d += timedelta(days=1)
    if start is not None:
        runs.append((start, last))
    if not runs:
        return None, None, 0
    s, e = max(runs, key=lambda r: (r[1] - r[0]).days)
    still_open = upto is not None and e >= upto - timedelta(days=1) and upto < date(year, 12, 31)
    return s, (None if still_open else e + timedelta(days=1)), (e - s).days + 1


def doy(d):
    return d.timetuple().tm_yday


def _shift(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def window_mean(series, end):
    v = [series[end - timedelta(days=k)] for k in range(WINDOW) if (end - timedelta(days=k)) in series]
    return statistics.fmean(v) if len(v) >= WINDOW // 3 else None


def preds(series, volume, issue):
    out = {}
    f = window_mean(series, issue)
    if f is not None:
        out["F"] = f
    if volume:
        y, m = issue.year, issue.month - 1
        if m == 0:
            y, m = y - 1, 12
        if (y, m) in volume:
            out["V"] = volume[(y, m)]
    return out


def _detrend(xs, ys, x_new):
    b = np.polyfit(xs, ys, 1)
    return np.asarray(ys, float) - np.polyval(b, xs), float(np.polyval(b, x_new))


def predict(series, volume, table, issue, target, cols):
    lead = target - issue.year
    rows = []
    for t, y in sorted(table.items()):
        if t >= target or y is None:
            continue
        p = preds(series, volume, _shift(issue, t - target))
        if all(c in p for c in cols):
            rows.append((t, y, [p[c] for c in cols]))
    if len(rows) < 12:
        return None
    yrs = np.array([r[0] for r in rows], float)
    y_res, y_tr = _detrend(yrs, [r[1] for r in rows], target)
    if not cols:
        return y_tr
    now = preds(series, volume, issue)
    if not all(c in now for c in cols):
        return None
    X, xnow = [], []
    for j, c in enumerate(cols):
        xr, xt = _detrend(yrs - lead, [r[2][j] for r in rows], issue.year)
        if np.std(xr) < 1e-6:
            continue
        X.append(xr)
        xnow.append(now[c] - xt)
    if not X:
        return y_tr
    A = np.column_stack(X + [np.ones(len(rows))])
    beta, *_ = np.linalg.lstsq(A, y_res, rcond=None)
    return y_tr + float(np.dot(np.append(xnow, 1.0), beta))


def backtest(series, volume, table, md, lead, cols):
    errs = []
    for t in sorted(table):
        if t < FIRST_TEST or table[t] is None:
            continue
        try:
            issue = date(t - lead, *md)
        except ValueError:
            issue = date(t - lead, md[0], 28)
        p = predict(series, volume, table, issue, t, cols)
        if p is not None:
            errs.append((t, p, table[t]))
    return errs


def _mae(e):
    return statistics.fmean(abs(p - a) for _, p, a in e) if e else None


def forecast(series, volume, table, issue, target, lo, hi):
    lead = target - issue.year
    md = (issue.month, issue.day)
    full = ["F", "V"] if volume else ["F"]
    te, fe = backtest(series, volume, table, md, lead, []), backtest(series, volume, table, md, lead, full)
    mt, mf = _mae(te), _mae(fe)
    skill = (1 - mf / mt) if (mt and mf) else None
    use = skill is not None and skill >= PASS
    errs = fe if use else te
    p = predict(series, volume, table, issue, target, full if use else [])
    if p is None or not errs:
        return None
    a = sorted(abs(x - y) for _, x, y in errs)
    q = lambda f: a[min(len(a) - 1, int(round(f * (len(a) - 1))))]
    clip = lambda v: max(lo, min(hi, v))
    return {"point": round(clip(p), 1),
            "range_68": [round(clip(p - q(.68)), 1), round(clip(p + q(.68)), 1)],
            "range_95": [round(clip(p - q(.95)), 1), round(clip(p + q(.95)), 1)],
            "method": ("추세 + 현재 항로 얼음" + (" + 얼음 부피" if volume else "")) if use else "추세",
            "skill_vs_trend": round(skill, 3) if skill is not None else None,
            "n_test_years": len(errs)}


def md_ko(y, n):
    d = date(y, 1, 1) + timedelta(days=int(round(n)) - 1)
    return f"{d.month}월 {d.day}일"


def class_block(series, volume, thr, start_md, last, issue):
    first_year = max(1979, min(series).year)
    table = []
    for y in range(first_year, last.year + 1):
        upto = last if y == last.year else None
        if upto and upto < date(y, *start_md):
            break
        s, e, n = season(series, y, thr, start_md, upto)
        table.append({"year": y, "open": s.isoformat() if s else None,
                      "close": e.isoformat() if e else None, "days": n})
    cur = table[-1] if table and table[-1]["year"] == last.year else None
    if cur is None:
        status = "not_yet"
    elif cur["open"] and not cur["close"]:
        status = "open"
    elif not cur["open"] and last < date(last.year, 10, 15):
        status = "not_yet"
    else:
        status = "closed"
    target = last.year if status in ("open", "not_yet") else last.year + 1
    done = {r["year"]: r for r in table if r["year"] < target}
    tabs = {"days": {y: r["days"] for y, r in done.items()},
            "open": {y: doy(date.fromisoformat(r["open"])) for y, r in done.items() if r["open"]},
            "close": {y: doy(date.fromisoformat(r["close"])) for y, r in done.items() if r["close"]}}
    out = {"target_year": target, "status": status}
    out["days"] = forecast(series, volume, tabs["days"], issue, target, 0, 245)
    out["open"] = None if status == "open" else forecast(series, volume, tabs["open"], issue, target, 121, 365)
    out["open_observed"] = cur["open"] if status == "open" else None
    out["close"] = forecast(series, volume, tabs["close"], issue, target, 121, 366)
    for k in ("open", "close"):
        if out.get(k):
            o = out[k]
            o["date_ko"] = md_ko(target, o["point"])
            o["range_68_ko"] = [md_ko(target, v) for v in o["range_68"]]
    by_month = []
    for m in (4, 5, 6, 7, 8):
        row = {"issue": f"{m}월 1일"}
        for name in ("open", "close", "days"):
            te = backtest(series, volume, tabs[name], (m, 1), 0, [])
            fF = backtest(series, volume, tabs[name], (m, 1), 0, ["F"])
            fV = backtest(series, volume, tabs[name], (m, 1), 0, ["F", "V"]) if volume else []
            if te:
                row[name] = {"mae_trend": round(_mae(te), 1),
                             "skill_F": round(1 - _mae(fF) / _mae(te), 3) if fF else None,
                             "skill_FV": round(1 - _mae(fV) / _mae(te), 3) if fV else None}
        by_month.append(row)
    out["skill_by_issue_month"] = by_month
    last10 = [done[y]["days"] > 0 for y in sorted(done)[-10:]]
    out["opened_last10"] = f"최근 {len(last10)}년 중 {sum(last10)}년 열림"
    ys = sorted(tabs["days"])
    recent = [tabs["days"][y] for y in ys[-10:]]
    out["last10_mean_days"] = round(statistics.fmean(recent), 1) if recent else None
    return {"seasons": table, "outlook": out}


def build(volume=None, today=None):
    raw = load()
    series = worst_series(raw)
    if len(series) < 3000:
        return None
    last = max(series)
    issue = today or last
    classes = []
    for cid, label, thr, start in CLASSES:
        b = class_block(series, volume, thr, start, last, issue)
        b.update(id=cid, label_ko=label, max_concentration=thr)
        classes.append(b)
    # Validation against CHNL transit records.
    val = []
    for t in TRANSITS:
        row = dict(t)
        for c in classes:
            s = next((r for r in c["seasons"] if r["year"] == t["year"]), None)
            if s:
                row[c["id"]] = {"open": s["open"], "close": s["close"]}
        val.append(row)
    last_raw = raw[max(raw)]
    return {
        "latest_date": last.isoformat(),
        "latest_legs": [{"id": k, "name_ko": n, "concentration": last_raw.get(k)} for k, n in LEGS],
        "latest_worst": round(series[last], 3),
        "classes": classes,
        "validation": val,
        "note_ko": ("항로선 위 6개 구간(카라해·빌키츠키 해협·랍테프해·산니코프 해협·동시베리아해·롱 해협/추코트해)의 "
                    "해빙 농도(NSIDC 25km 격자)로 판정합니다. 가장 얼음이 많은 구간이 기준을 넘지 않아야 열림입니다. "
                    "선급 기준은 농도만 본 근사치로, 얼음 두께·정착빙·쇄빙선 호위·러시아 허가는 반영하지 않았습니다."),
        "years": {str(y): [[doy(d), round(series[d], 3)] for d in sorted(series) if d.year == y]
                  for y in (last.year, last.year - 1, 2012, 2020)},
    }
