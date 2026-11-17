"""Northern Sea Route open season from NSIDC regional daily sea ice extent.

Fixed 2026-11-17, before any season was computed:

  Data     NSIDC Sea Ice Index (G02135) regional daily extent, the
           spreadsheet NSIDC publishes next to the pan-Arctic files
           (N_Sea_Ice_Index_Regional_Daily_Data_G02135_v*.xlsx). Regions are
           the NSIDC-MASIE seas; the route crosses four of them, west to east:
           Kara, Laptev, East Siberian, Chukchi.
  Scale    each sea's extent is divided by its own full-ice extent (the 95th
           percentile of every daily value on record), so 1 = ice-covered and
           0 = ice-free. Before 1988 the record is every other day; the gaps
           are filled linearly. A 5-day centred mean smooths single-day noise.
  Open     a sea is open on a day when its fraction is at or below 15%. The
           route is open when all four seas are open the same day (the most
           closed sea decides). The season is the longest run of open days
           between 1 June and 31 December, joining runs separated by 5 days
           or less. Opening = its first day, closing = the day after its last.
           A year with no open day has a season of 0 days.
  Outlook  for the next season not yet finished: open days, opening date and
           closing date.
             baseline   linear trend over all earlier seasons (from 1979)
             predictor  F = mean route fraction of the 30 days up to the issue
                        date, detrended; it carries skill only while the ice
                        is melting or refreezing
             test       forward from 2001 at the same calendar date; each year
                        from a model trained on the years before it
             rule       the predictor model is published only when its forward
                        MAE beats the trend's by 10% or more; ranges are the
                        68th and 95th percentiles of the published method's
                        forward absolute errors
           During an open season the opening date is the observed one.

What this is not: a navigation permit. Real transits also depend on ice
class, Russian NSR administration permits, icebreaker escort, insurance and
sanctions. The 15% line is the conventional ice-edge threshold, so "open"
here means ice-free water along all four seas -- ships with ice class can go
earlier and later.
"""
from __future__ import annotations

import io
import json
import os
import re
import statistics
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "public", "data", "sea_route_v1.json"))
DIR = "https://noaadata.apps.nsidc.org/NOAA/G02135/seaice_analysis/"
GUESSES = [DIR + "N_Sea_Ice_Index_Regional_Daily_Data_G02135_v4.0.xlsx",
           DIR + "N_Sea_Ice_Index_Regional_Daily_Data_G02135_v3.0.xlsx"]

SEAS = [("kara", "카라해", ("kara",)),
        ("laptev", "랍테프해", ("laptev",)),
        ("east_siberian", "동시베리아해", ("east-siberian", "east siberian", "e-siberian", "esiberian", "east_siberian")),
        ("chukchi", "추코트해", ("chukchi",))]
OPEN = 0.15
SMOOTH = 5
GAP = 5
WINDOW = 30
FIRST_TEST = 2001
PASS = 0.10
FIRST_SEASON = 1979


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "global-trade-dashboard"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


# ---------------------------------------------------------------- parsing
def parse_sheet(rows):
    """Rows of a 'month, day, 1978, 1979, ...' sheet -> {date: km2}."""
    out, years, mcol, dcol = {}, None, None, None
    for row in rows:
        cells = list(row)
        if years is None:
            yrs = {}
            for j, c in enumerate(cells):
                s = str(c).strip() if c is not None else ""
                if re.fullmatch(r"(19|20)\d\d(\.0)?", s):
                    yrs[j] = int(float(s))
                elif s.lower().startswith("month"):
                    mcol = j
                elif s.lower().startswith("day"):
                    dcol = j
            if len(yrs) >= 10:
                years = yrs
                mcol = 0 if mcol is None else mcol
                dcol = 1 if dcol is None else dcol
            continue
        try:
            m, d = int(cells[mcol]), int(cells[dcol])
        except (TypeError, ValueError, IndexError):
            # NSIDC fills the month only on the first day of each month
            try:
                d = int(cells[dcol])
                m = last_m
            except (TypeError, ValueError, IndexError, NameError):
                continue
        last_m = m
        for j, y in years.items():
            if j >= len(cells) or cells[j] in (None, ""):
                continue
            try:
                v = float(cells[j])
                day = date(y, m, d)
            except (TypeError, ValueError):
                continue
            if v >= 0:
                out[day] = v
    return out


def parse_workbook(blob):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    names = wb.sheetnames
    print("sheets:", names[:60])
    seas = {}
    for key, _, pats in SEAS:
        cand = [n for n in names if any(p in n.lower() for p in pats) and "extent" in n.lower()]
        if not cand:
            raise SystemExit(f"{key}: extent 시트 없음 ({names})")
        series = parse_sheet(wb[cand[0]].iter_rows(values_only=True))
        print(f"{key}: sheet {cand[0]!r}, {len(series)} days, {min(series)}..{max(series)}")
        seas[key] = series
    return seas


# ---------------------------------------------------------------- seasons
def fractions(series):
    """{date: fraction 0..1}, gaps filled, 5-day centred mean."""
    full = float(np.percentile(list(series.values()), 95))
    d0, d1 = min(series), max(series)
    days, vals, d, prev = [], [], d0, None
    known = sorted(series)
    i = 0
    while d <= d1:
        if d in series:
            v = series[d]
        else:
            while i + 1 < len(known) and known[i + 1] < d:
                i += 1
            a, b = known[i], known[min(i + 1, len(known) - 1)]
            if a < d < b and (b - a).days <= 4:
                v = series[a] + (series[b] - series[a]) * (d - a).days / (b - a).days
            else:
                v = None
        days.append(d)
        vals.append(None if v is None else min(1.0, v / full))
        d += timedelta(days=1)
    out, h = {}, SMOOTH // 2
    for k, day in enumerate(days):
        w = [x for x in vals[max(0, k - h):k + h + 1] if x is not None]
        if len(w) >= 3:
            out[day] = statistics.fmean(w)
    return out, full


def route_fraction(fr):
    common = set.intersection(*(set(f) for f in fr.values()))
    return {d: max(fr[k][d] for k in fr) for d in sorted(common)}


def season(route, year, upto=None):
    """(opening date, closing date or None if still open, days) for a year."""
    d, end = date(year, 6, 1), date(year, 12, 31)
    if upto:
        end = min(end, upto)
    runs, start, last = [], None, None
    while d <= end:
        x = route.get(d)
        if x is not None and x <= OPEN:
            if start is None or (last and (d - last).days > GAP + 1):
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


# ---------------------------------------------------------------- outlook
def _trend(years, ys, x):
    b = np.polyfit(years, ys, 1)
    return np.asarray(ys) - np.polyval(b, years), float(np.polyval(b, x))


def window_mean(route, end):
    v = [route[end - timedelta(days=k)] for k in range(WINDOW) if (end - timedelta(days=k)) in route]
    return statistics.fmean(v) if len(v) >= WINDOW // 3 else None


def _shift(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def predict(route, table, issue, target, use_f):
    lead = target - issue.year
    rows = []
    for t, y in sorted(table.items()):
        if t >= target or y is None:
            continue
        f = window_mean(route, _shift(issue, t - target)) if use_f else 0.0
        if f is not None:
            rows.append((t, y, f))
    if len(rows) < 12:
        return None
    yrs = np.array([r[0] for r in rows], float)
    y_res, y_tr = _trend(yrs, [r[1] for r in rows], target)
    if not use_f:
        return y_tr
    fnow = window_mean(route, issue)
    if fnow is None:
        return None
    f_res, f_tr = _trend(yrs - lead, [r[2] for r in rows], issue.year)
    if np.std(f_res) < 1e-6:
        return y_tr
    X = np.column_stack([f_res, np.ones(len(rows))])
    beta, *_ = np.linalg.lstsq(X, y_res, rcond=None)
    return y_tr + float(beta[0] * (fnow - f_tr) + beta[1])


def backtest(route, table, md, lead, use_f):
    errs = []
    for t in sorted(table):
        if t < FIRST_TEST or table[t] is None:
            continue
        try:
            issue = date(t - lead, *md)
        except ValueError:
            issue = date(t - lead, md[0], 28)
        p = predict(route, table, issue, t, use_f)
        if p is not None:
            errs.append((t, p, table[t]))
    return errs


def _mae(e):
    return statistics.fmean(abs(p - a) for _, p, a in e) if e else None


def forecast(route, table, issue, target, lo=None, hi=None):
    lead = target - issue.year
    md = (issue.month, issue.day)
    te, fe = backtest(route, table, md, lead, False), backtest(route, table, md, lead, True)
    mt, mf = _mae(te), _mae(fe)
    skill = (1 - mf / mt) if (mt and mf) else None
    use = skill is not None and skill >= PASS
    errs = fe if use else te
    p = predict(route, table, issue, target, use)
    if p is None:
        return None
    a = sorted(abs(x - y) for _, x, y in errs)
    q = lambda f: a[min(len(a) - 1, int(round(f * (len(a) - 1))))]
    clip = lambda v: max(lo, min(hi, v)) if lo is not None else v
    return {"point": round(clip(p), 1),
            "range_68": [round(clip(p - q(.68)), 1), round(clip(p + q(.68)), 1)],
            "range_95": [round(clip(p - q(.95)), 1), round(clip(p + q(.95)), 1)],
            "method": "추세 + 현재 얼음" if use else "추세",
            "skill_vs_trend": round(skill, 3) if skill is not None else None,
            "mae_trend": round(mt, 1) if mt else None,
            "n_test_years": len(errs)}


def doy_to_md(y, n):
    d = date(y, 1, 1) + timedelta(days=int(round(n)) - 1)
    return f"{d.month}월 {d.day}일"


# ---------------------------------------------------------------- main
def build(seas, today=None):
    fr, full = {}, {}
    for k, s in seas.items():
        fr[k], full[k] = fractions(s)
    route = route_fraction(fr)
    last = max(route)
    issue = today or last
    first_year = max(FIRST_SEASON, min(route).year)

    table = []
    for y in range(first_year, last.year + 1):
        upto = last if y == last.year else None
        if upto and upto < date(y, 6, 1):
            break
        s, e, n = season(route, y, upto)
        per = {}
        for k in fr:
            ss, ee, nn = season(fr[k], y, upto)
            per[k] = {"open": ss.isoformat() if ss else None, "close": ee.isoformat() if ee else None, "days": nn}
        table.append({"year": y, "open": s.isoformat() if s else None,
                      "close": e.isoformat() if e else None, "days": n,
                      "final": upto is None or e is not None,
                      "seas": per})

    # This year's season status.
    cur = table[-1] if table and table[-1]["year"] == last.year else None
    status = "closed"
    if cur is None:
        status = "not_yet"                       # before 1 June
    elif cur["open"] and not cur["close"]:
        status = "open"
    elif cur and not cur["open"] and last < date(last.year, 12, 31):
        status = "not_yet" if last < date(last.year, 10, 15) else "closed"
    # target = the season not finished yet
    if status in ("open", "not_yet"):
        target = last.year
    else:
        target = last.year + 1
    done = {r["year"]: r for r in table if r["year"] < target}
    days_tab = {y: r["days"] for y, r in done.items()}
    open_tab = {y: doy(date.fromisoformat(r["open"])) for y, r in done.items() if r["open"]}
    close_tab = {y: doy(date.fromisoformat(r["close"])) for y, r in done.items() if r["close"]}

    out = {"target_year": target, "issued": issue.isoformat(), "status": status}
    out["days"] = forecast(route, days_tab, issue, target, 0, 214)
    if status == "open":
        out["open_observed"] = cur["open"]
        out["open"] = None
    else:
        out["open"] = forecast(route, open_tab, issue, target, 152, 365)
    out["close"] = forecast(route, close_tab, issue, target, 152, 366)
    for k in ("open", "close"):
        o = out.get(k)
        if o:
            o["date_ko"] = doy_to_md(target, o["point"])
            o["range_68_ko"] = [doy_to_md(target, v) for v in o["range_68"]]
            o["range_95_ko"] = [doy_to_md(target, v) for v in o["range_95"]]
    n_closed = sum(1 for r in done.values() if r["days"] == 0)
    out["years_never_open"] = n_closed
    last10 = [done[y]["days"] > 0 for y in sorted(done)[-10:]]
    out["opened_last10"] = f"최근 {len(last10)}년 중 {sum(last10)}년 열림"

    # Season-length trend over all finished seasons.
    ys = sorted(days_tab)
    slope = float(np.polyfit(ys, [days_tab[y] for y in ys], 1)[0]) if len(ys) > 10 else None
    recent = [days_tab[y] for y in ys[-10:]]
    early = [days_tab[y] for y in ys[:10]]

    def series(y):
        return [[doy(d), round(route[d], 3)] for d in sorted(route) if d.year == y]

    return {
        "schema_version": "sea-route-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_date": last.isoformat(),
        "seas": [{"id": k, "name_ko": n, "full_extent_km2": round(full[k])} for k, n, _ in SEAS if k in fr],
        "rule": {"open_fraction": OPEN, "smooth_days": SMOOTH, "join_gap_days": GAP,
                 "note_ko": ("네 바다(카라·랍테프·동시베리아·추코트) 각각의 해빙 면적이 그 바다가 꽉 얼었을 때의 15% "
                             "이하로 떨어진 날을 '열림'으로 보고, 네 바다가 동시에 열린 가장 긴 기간을 항로 시즌으로 잡았습니다 "
                             "(5일 평균, 5일 이하 틈은 이어 붙임). 빙급 선박·쇄빙선 호위·러시아 허가·제재는 반영하지 않았습니다.")},
        "latest_fraction": {k: round(fr[k][max(fr[k])], 3) for k in fr},
        "latest_route_fraction": round(route[last], 3),
        "seasons": table,
        "trend": {"days_per_decade": round(slope * 10, 1) if slope is not None else None,
                  "first10_mean_days": round(statistics.fmean(early), 1) if early else None,
                  "last10_mean_days": round(statistics.fmean(recent), 1) if recent else None,
                  "first10": f"{ys[0]}-{ys[min(9, len(ys) - 1)]}" if ys else None,
                  "last10": f"{ys[-10]}-{ys[-1]}" if len(ys) >= 10 else None},
        "outlook": out,
        "years": {str(y): series(y) for y in (last.year, last.year - 1, 2012, 2020) if any(d.year == y for d in route)},
    }


def main():
    urls = list(GUESSES)
    try:
        listing = fetch(DIR).decode("utf-8", "replace")
        names = sorted(set(re.findall(r'N_Sea_Ice_Index_Regional_Daily_Data_G02135_v[\d.]+\.xlsx', listing)), reverse=True)
        print("listing:", names)
        urls = [DIR + n for n in names] + urls
    except OSError as e:
        print(f"목록 실패: {e}", file=sys.stderr)
    blob, src = None, None
    for u in urls:
        try:
            blob, src = fetch(u), u
            break
        except OSError as e:
            print(f"{u}: {e}", file=sys.stderr)
    if not blob:
        raise SystemExit("NSIDC 해역별 파일을 받지 못함")
    doc = build(parse_workbook(blob))
    doc["source"] = "NSIDC Sea Ice Index (G02135) regional daily extent"
    doc["source_url"] = src
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    o = doc["outlook"]
    print(f"최신 {doc['latest_date']} 항로 {doc['latest_route_fraction']} 각 바다 {doc['latest_fraction']}")
    for r in doc["seasons"][-12:]:
        print(r["year"], r["open"], r["close"], r["days"], {k: v["days"] for k, v in r["seas"].items()})
    print("추세", doc["trend"])
    print("전망", json.dumps(o, ensure_ascii=False))


if __name__ == "__main__":
    main()
