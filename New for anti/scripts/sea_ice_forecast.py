"""September Arctic sea ice extent outlook, recomputed every day from the
data that exists on that day.

Method, from the literature (fixed 2026-11-16, before any skill was run):

  Target     September monthly-mean extent (NSIDC Sea Ice Index), the target
             of the Sea Ice Outlook (SIPN/ARCUS). Before 30 Sep the target is
             this year's September, after it next year's.
  Baseline   linear trend of September extent over all earlier years. The
             SIO's own verification (Bushuk et al. 2023, GRL, 2008-2022)
             shows most outlooks struggle to beat this outside June-August.
  Predictors (each detrended over the earlier years, same calendar window)
    E  mean extent of the 30 days up to the issue date. Persistence of the
       extent anomaly is the main source of skill from June on; Petty et al.
       (2017, Earth's Future) get skilful spring forecasts from passive-
       microwave ice observations alone.
    V  PIOMAS ice volume of the last complete month (UW Polar Science
       Center). Thickness carries memory through the spring barrier
       (Day et al. 2014; Bushuk et al. 2017); volume is its pan-Arctic
       summary. Optional: used only when the file can be read.
  Model      OLS of the detrended September extent on the detrended
             predictors, trained on every earlier year only.
  Test       forward, target years 2001 to last: each year predicted from a
             model trained on the years before it, at the same calendar
             issue date.
  Rule       the full model (E, plus V when present) is published only when
             its forward MAE is at least 10% below the trend's at that issue
             date; otherwise the trend is published. The 68% and 95% ranges
             are the 68th and 95th percentiles of the published method's own
             forward absolute errors.

Not used, though the papers show skill: melt-pond fraction in May
(Schroeder et al. 2014, Nature Climate Change) and melt onset dates
(Petty 2017) -- neither is published as a simple, automatically updated
series.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

import numpy as np

FIRST_TEST = 2001
PASS = 0.10
WINDOW = 30


def september_means(daily):
    out = {}
    for d, x in daily.items():
        if d.month == 9:
            out.setdefault(d.year, []).append(x)
    return {y: statistics.fmean(v) for y, v in out.items() if len(v) >= 10}


def window_mean(daily, end, days=WINDOW):
    vals = [daily[end - timedelta(days=k)] for k in range(days) if (end - timedelta(days=k)) in daily]
    return statistics.fmean(vals) if len(vals) >= days // 3 else None


def _shift(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def _detrend(xs, ys, x_new):
    b = np.polyfit(xs, ys, 1)
    return np.asarray(ys) - np.polyval(b, xs), float(np.polyval(b, x_new))


def predictors(daily, volume, issue):
    """{name: value} known on `issue`."""
    out = {}
    e = window_mean(daily, issue)
    if e is not None:
        out["E"] = e
    if volume:
        y, m = issue.year, issue.month - 1
        if m == 0:
            y, m = y - 1, 12
        v = volume.get((y, m))
        if v is not None:
            out["V"] = v
    return out


def _predict(daily, volume, sept, issue, target, cols):
    """Point forecast for `target` September made on `issue`, from years before `target`."""
    lead = target - issue.year           # 0 before October, 1 after
    rows = []
    for t in sorted(sept):
        if t >= target:
            continue
        p = predictors(daily, volume, _shift(issue, t - target))
        if all(c in p for c in cols):
            rows.append((t, sept[t], [p[c] for c in cols]))
    if len(rows) < 12:
        return None
    years = np.array([r[0] for r in rows], float)
    y = np.array([r[1] for r in rows], float)
    y_res, y_tr = _detrend(years, y, target)
    if not cols:
        return y_tr
    now = predictors(daily, volume, issue)
    if not all(c in now for c in cols):
        return None
    X, xnow = [], []
    for j, c in enumerate(cols):
        xs = np.array([r[2][j] for r in rows], float)
        # the predictor's own year is target - lead for the issue date
        xr, xtr = _detrend(years - lead, xs, issue.year)
        X.append(xr)
        xnow.append(now[c] - xtr)
    X = np.column_stack(X + [np.ones(len(rows))])
    beta, *_ = np.linalg.lstsq(X, y_res, rcond=None)
    return y_tr + float(np.dot(np.append(xnow, 1.0), beta))


def backtest(daily, volume, sept, issue_md, lead, cols):
    """Forward absolute errors at a calendar issue date (month, day)."""
    errs = []
    for target in sorted(sept):
        if target < FIRST_TEST:
            continue
        try:
            issue = date(target - lead, *issue_md)
        except ValueError:
            issue = date(target - lead, issue_md[0], 28)
        p = _predict(daily, volume, sept, issue, target, cols)
        if p is not None:
            errs.append((target, p, sept[target]))
    return errs


def _mae(errs):
    return statistics.fmean(abs(p - a) for _, p, a in errs) if errs else None


def outlook(daily, volume=None, today=None):
    sept = september_means(daily)
    issue = today or max(daily)
    target = issue.year if issue < date(issue.year, 9, 30) else issue.year + 1
    lead = target - issue.year
    full = ["E", "V"] if volume else ["E"]
    md = (issue.month, issue.day)

    trend_err = backtest(daily, volume, sept, md, lead, [])
    full_err = backtest(daily, volume, sept, md, lead, full)
    e_err = backtest(daily, volume, sept, md, lead, ["E"]) if volume else full_err
    mt, mf = _mae(trend_err), _mae(full_err)
    skill = (1 - mf / mt) if (mt and mf) else None
    use_full = skill is not None and skill >= PASS
    errs = full_err if use_full else trend_err
    point = _predict(daily, volume, sept, issue, target, full if use_full else [])
    trend_point = _predict(daily, volume, sept, issue, target, [])
    a = sorted(abs(p - x) for _, p, x in errs)
    q = (lambda f: a[min(len(a) - 1, int(round(f * (len(a) - 1))))]) if a else (lambda f: None)
    r68, r95 = q(0.68), q(0.95)

    # Skill by lead time: 1st of each month before the target September.
    by_month = []
    for m in (1, 3, 5, 6, 7, 8, 9):
        te = backtest(daily, volume, sept, (m, 1), 0, [])
        fe = backtest(daily, volume, sept, (m, 1), 0, full)
        if te and fe:
            by_month.append({"issue": f"{m}월 1일", "mae_trend": round(_mae(te), 3),
                             "mae_model": round(_mae(fe), 3),
                             "skill": round(1 - _mae(fe) / _mae(te), 3)})

    rec = min(sept.values()) if sept else None
    return {
        "target": f"{target}년 9월 평균 면적",
        "target_year": target,
        "issued": issue.isoformat(),
        "method": ("추세 + 현재 면적" + (" + 얼음 부피(PIOMAS)" if volume else "")) if use_full else "추세",
        "point": round(point, 2) if point is not None else None,
        "trend_point": round(trend_point, 2) if trend_point is not None else None,
        "range_68": [round(point - r68, 2), round(point + r68, 2)] if point is not None and r68 is not None else None,
        "range_95": [round(point - r95, 2), round(point + r95, 2)] if point is not None and r95 is not None else None,
        "skill_vs_trend": round(skill, 3) if skill is not None else None,
        "skill_e_only": (round(1 - _mae(e_err) / mt, 3) if (e_err and mt) else None),
        "mae_trend": round(mt, 3) if mt else None,
        "mae_published": round(_mae(errs), 3) if errs else None,
        "n_test_years": len(errs),
        "volume_used": bool(volume),
        "skill_by_issue_month": by_month,
        "record_september": round(rec, 2) if rec else None,
        "backtest_last": [{"year": t, "pred": round(p, 2), "actual": round(x, 2)} for t, p, x in errs[-8:]],
    }


def parse_piomas_monthly(text):
    """'Year Jan ... Dec' rows of volume in 10^3 km^3; missing as negative/blank."""
    out = {}
    for line in text.splitlines():
        p = line.replace(",", " ").split()
        if len(p) < 2 or not p[0].isdigit() or len(p[0]) != 4:
            continue
        for m, raw in enumerate(p[1:13], start=1):
            try:
                v = float(raw)
            except ValueError:
                continue
            if 0 < v < 60:
                out[(int(p[0]), m)] = v
    return out
