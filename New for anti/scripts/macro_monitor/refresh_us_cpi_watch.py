"""Daily gate for the weekly US CPI monitor and D-3 release brief (Eastern time)."""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from statistics import mean
from tempfile import NamedTemporaryFile
from urllib.request import urlopen
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from build_us_cpi_watch import CONFIG, PUBLIC, ZORI_DATA, build, parse_zori, read_json, shift

CALENDAR = "https://www.bls.gov/schedule/news_release/cpi.htm"
ENERGY = {
    "eia_gasoline": ("EMM_EPM0_PTE_NUS_DPG", "Weekly U.S. All Grades All Formulations Retail Gasoline Prices"),
    "eia_jet": ("EER_EPJK_PF4_RGC_DPG", "Weekly U.S. Gulf Coast Kerosene-Type Jet Fuel Spot Price FOB"),
}


def get(url):
    with urlopen(url, timeout=35) as res:
        return res.read().decode("utf-8-sig")


def releases(html):
    if "Schedule of Releases for the Consumer Price Index" not in html:
        raise ValueError("wrong BLS calendar")
    out = {}
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.I | re.S):
        cells = [" ".join(unescape(re.sub(r"<[^>]+>", " ", x)).split())
                 for x in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.I | re.S)]
        if len(cells) < 2 or not re.fullmatch(r"[A-Za-z]+ \d{4}", cells[0]):
            continue
        ref = datetime.strptime(cells[0], "%B %Y").strftime("%Y-%m")
        month, rest = cells[1].split(" ", 1)
        day = datetime.strptime(month[:3] + " " + rest, "%b %d, %Y").date()
        if ref in out or day.isoformat()[:7] <= ref:
            raise ValueError("ambiguous CPI calendar")
        out[ref] = day.isoformat()
    if not out:
        raise ValueError("empty CPI calendar")
    return out


def plan(days, today, force=False):
    upcoming = sorted((date.fromisoformat(d), ref) for ref, d in days.items()
                      if date.fromisoformat(d) > today)
    if not upcoming:
        raise ValueError("no upcoming CPI release")
    day, ref = upcoming[0]
    delta = (day - today).days
    mode = "pre_release" if delta <= 3 else "weekly" if today.weekday() == 4 or force else None
    return mode, ref, day


def weekly_points(html, key):
    series, title = ENERGY[key]
    if series.lower() + "w.xls" not in html.lower() or title not in html or "Dollars per Gallon" not in html:
        raise ValueError("wrong EIA series")
    points = {}
    for tr in re.findall(r"<tr>(.*?)</tr>", html, re.I | re.S):
        cells = [unescape(v).strip() for v in re.findall(r"<td class='B[635]'>(.*?)</td>", tr)]
        if not cells or not re.fullmatch(r"\d{4}-[A-Za-z]{3}", cells[0]):
            continue
        month = datetime.strptime(cells[0], "%Y-%b")
        for day, value in zip(cells[1::2], cells[2::2]):
            if not re.fullmatch(r"\d+\.\d+", value):
                continue
            when = datetime.strptime(f"{month.year}/{day}", "%Y/%m/%d").date()
            if when in points or when.month != month.month or float(value) <= 0:
                raise ValueError("invalid EIA date/price")
            points[when] = float(value)
    if not points:
        raise ValueError("EIA weekly prices missing")
    return points


def energy_obs(points, ref, today):
    group = lambda month: sorted((d, v) for d, v in points.items()
                                 if d.isoformat()[:7] == month and d <= today)
    rows, prev = group(ref), group(shift(ref, -1))
    if not rows:
        return {"status": "awaiting_target_month", "reference_period": ref}
    last, value = rows[-1]
    # Compare calendar week-of-month slots, never silently compress missing weeks.
    slot = lambda d: (d.day - 1) // 7
    a, b = ({slot(d): v for d, v in seq} for seq in (rows, prev))
    slots = sorted(a.keys() & b.keys())
    pct = (mean(a[i] for i in slots) / mean(b[i] for i in slots) - 1) * 100 if slots else None
    prior = points.get(last - timedelta(days=7))
    limit = min(today, date.fromisoformat(shift(ref, 1) + "-01") - timedelta(days=1))
    return {"status": "stale" if (limit-last).days > 10 else "observed", "reference_period": ref,
            "observed_on": last.isoformat(), "usd_per_gallon": value, "unit": "USD/gallon, NSA",
            "week_over_week_pct": round((value/prior-1)*100, 3) if prior else None,
            "matched_weeks": len(slots), "prior_month_matched_weeks_pct": round(pct, 3) if slots else None}


PUBLISH_ZORI = False


def rate_events(events, key, ref, today):
    matched = []
    for event in events:
        if event["source_id"] != key:
            continue
        approved, effective = (date.fromisoformat(event[k]) for k in ("approved_on", "effective_on"))
        url = urlsplit(event["source_url"])
        if (url.scheme != "https" or not (url.hostname or "").endswith(".gov")
                or not all(event.get(k) for k in ("jurisdiction", "provider", "applies_to"))
                or approved > effective):
            raise ValueError("invalid reviewed rate order")
        if approved <= today and effective <= today and effective.isoformat()[:7] == ref:
            matched.append(event)
    return {"status": "observed" if matched else "no_verified_event", "reference_period": ref,
            "scope": "local_orders_not_national_price_index", "events": matched}


def refresh(today, force=False, fetch=get):
    try:
        calendar = releases(fetch(CALENDAR))
        mode, ref, day = plan(calendar, today, force)
        calendar_status = "live"
    except (ValueError, OSError):
        saved = read_json(CONFIG / "cpi_release_fallback.json")
        age = (today - date.fromisoformat(saved["checked_on"])).days
        if not 0 <= age <= 21:
            raise ValueError("BLS unavailable and verified fallback expired; refresh fallback")
        mode, ref, day = plan(saved["releases"], today, force)
        calendar_status = "verified_fallback:" + saved["checked_on"]
    if not mode:
        return None
    macro = read_json(PUBLIC / "macro_monitor_v1.json")
    levels = parse_zori(fetch(ZORI_DATA).splitlines())
    levels = {m: v for m, v in levels.items() if m <= min(ref, today.isoformat()[:7])}
    if not levels:
        raise ValueError("no dated national ZORI data")
    report = build(macro, read_json(CONFIG / "cpi_structure.map.json"),
                   read_json(PUBLIC / "us_cpi_api_history_v1.json"), levels, include_research=False)
    if ref <= report["reference_period"]:
        raise ValueError("target CPI already published; check calendar")
    events = read_json(CONFIG / "cpi_reviewed_rate_orders.json")["orders"]
    for row in report["external_prices"]:
        key = row["id"]
        if key in ENERGY:
            row["observation"] = energy_obs(weekly_points(fetch(row["source_url"]), key), ref, today)
        if key.endswith("_rate_actions"):
            row["observation"] = rate_events(events, key, ref, today)
        if key == "zori" and row["observation"]["reference_period"] < shift(ref, -2):
            row["observation"]["status"] = "stale"
    # Zillow's redistribution terms are not confirmed (#1149 README): the published file keeps the source link
    # and drops the values. Set PUBLISH_ZORI = True once the terms allow it.
    if not PUBLISH_ZORI:
        for row in report["external_prices"]:
            if row["id"] == "zori":
                row["observation"] = {"status": "source_link_only", "withheld": "redistribution_terms_unconfirmed"}
        if isinstance(report.get("zori_research"), dict):
            report["zori_research"]["diagnostic"] = None
    report["briefing"] = {"mode": mode, "as_of_eastern": today.isoformat(), "release_date": day.isoformat(),
                          "target_reference_period": ref, "calendar_source": CALENDAR,
                          "calendar_status": calendar_status,
                          "hide_on_or_after_eastern": min(day, today + timedelta(days=8)).isoformat(),
                          "news_ids": [r["id"] for r in report["external_prices"]
                                       if r["observation"]["status"] == "observed"]}
    return report


def save(report, out):
    if out.exists():
        old = read_json(out)
        if (old.get("schema_version") != report["schema_version"] or
                old["briefing"]["as_of_eastern"] > report["briefing"]["as_of_eastern"]):
            raise ValueError("refusing incompatible or older write")
        if old == report:
            return
    with NamedTemporaryFile("w", dir=out.parent, encoding="utf-8", delete=False) as tmp:
        path = Path(tmp.name)
        try:
            json.dump(report, tmp, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            tmp.close()
            path.replace(out)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="refresh even outside scheduled windows")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = refresh(datetime.now(ZoneInfo("America/New_York")).date(), args.force)
        if report:
            save(report, args.out)
        print("refreshed" if report else "not due")
    except (ValueError, OSError, KeyError) as exc:
        sys.exit(f"CPI monitor refresh failed: {exc}")
