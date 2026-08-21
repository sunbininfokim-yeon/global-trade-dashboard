#!/usr/bin/env python3
"""Build public/data/rig_count_v1.json from Baker Hughes rig count Excel exports.

Baker Hughes publishes the drilling rig count -- the single most-watched
leading indicator of upstream oil and gas activity -- but only as downloadable
Excel workbooks from rigcount.bakerhughes.com, with no public API. Two of the
four workbooks under scripts/rig_count/raw/ (NAM_latest.xlsx, WW_latest.xlsx)
are refreshed automatically by fetch_latest.py (see that file, and
.github/workflows/rig_count_intel.yml for the schedule); the other two are a
one-time historical baseline that never needs re-fetching, see below. Running
this script by hand after `python fetch_latest.py` (or just letting the
scheduled workflow run both) is the whole pipeline.

Two series come out of it:

  global     one number per month, worldwide (North America + International)
  by_country one series per country, keyed by a name app.js's resolveCountry()
             can land on the world basemap

WHY FOUR RAW FILES
------------------
Baker Hughes' "historical" exports are not actually full-history: the current
North America and Worldwide reports only go back to 2024. The longer history
lives in older exports that stop where they were taken. So each series is
stitched from a pair -- a long-history file and a current file -- with the
current file winning wherever the two overlap:

  North America   08-29-2025 ...            2013-01 .. 2025-08   (fallback, static)
                  NAM_latest.xlsx            2024-01 .. present   (preferred, auto-refreshed)
  Worldwide       July-2025 ...             2013-01 .. 2025-07   (fallback, static)
                  WW_latest.xlsx             2024-01 .. present   (preferred, auto-refreshed)

Each workbook's Monthly sheet carries several title rows and a short
rolling-window pivot summary (a handful of recent months by region) above the
real data. That summary block is a spreadsheet template artifact with
inconsistent date columns, not a historical series -- it is ignored entirely
except as a hand-check target (see verify_against_summary()). Everything this
script emits is built from the row-level detail table underneath it.

WHY NOT ADD THE WORLDWIDE FILE'S OWN 'North America' REGION
-----------------------------------------------------------
The Worldwide report has a North America region whose rows restate the same
rigs the North America report breaks out by county. Summing both would double
North America. Global = NAM detail (all of it, i.e. Canada + United States)
+ Worldwide detail where Region != 'North America'. That reproduces Baker
Hughes' own Worldwide summary line exactly (Jan 2026: 742.0 + 1079 = 1821).

KNOWN BREAK IN THE INTERNATIONAL SERIES (Saudi Arabia, 2024-01)
---------------------------------------------------------------
The two Worldwide files disagree on exactly one country over their 19 shared
months: Saudi Arabia. The 2025 export reports it under Rig Status "Active
Rigs" (69 in 2025-07); the 2026 export reports it under "Operating Rigs"
(234 for the same month) -- a definitional change on Baker Hughes' side, not a
data error, and every other country agrees to the decimal. Because the 2026
file wins the overlap, the global and Saudi Arabia series step up by roughly
+165..+220 at 2024-01, where the preferred source changes over. This is
recorded in the output's `notes` so the UI and anyone reading the JSON can see
it rather than reading the jump as a real drilling boom.

RUSSIA IS ABSENT, NOT ZERO
--------------------------
Neither Worldwide file has a 'RUSSIA' row at all (checked directly against
both raw sheets -- the only 'RUSS' substring hit in the whole Country column
is 'BRUNEI DARUSSALAM'). Baker Hughes' only presence in Russia was the
'Sakhalin' row, dropped above, which stopped in 2022-04 when it suspended
Russian operations reporting. So Russia will not appear as a by_country key
at all here -- not as a zero series, absent. A country click handler should
treat a missing key as "no data", same as any other country never surveyed.

COUNTRY KEYS ARE RESOLVED THROUGH THE SAME LOGIC app.js USES AT RUNTIME
-------------------------------------------------------------------------
COUNTRY_RENAMES below turns a Baker Hughes label into a readable candidate
name (e.g. 'SERBIA AND MONTENEGRO' -> 'Serbia'), but a readable name is not
necessarily the string trade.js's resolveCountry() will hand back when a user
clicks that country on the map -- and the JSON key has to be exactly that
string, or the country-view lookup silently finds nothing. canonicalize()
below is a line-for-line port of resolveCountry()'s own algorithm (direct
match against the basemap's 180 country names, then app.js's COUNTRY_ALIASES
table, then its unique-substring-containment fallback), run against a local
snapshot of that basemap's name list -- so every key this script emits is
already the exact string resolveCountry(...).label will produce, with no
fuzzy matching needed on the trade.js side.

This caught two cases neither the renames table nor a plain title-case would:
'Serbia' itself is not a basemap feature -- the actual polygon is named
'Republic of Serbia', so the containment fallback (uniquely, not colliding
with 'Montenegro') is what the key must actually be. Likewise 'TANZANIA'
title-cases to 'Tanzania', but the basemap's feature is 'United Republic of
Tanzania' -- resolveCountry('Tanzania') lands there via the same fallback, so
that is the key here too. BASEMAP_NAMES / COUNTRY_ALIASES / SUPPLEMENTAL_NAMES
below are a snapshot of app.js's own country registry (COUNTRY_ALIASES ~line
1327, SUPPLEMENTAL_POINTS ~line 1411, and the same public basemap URL
app.js's COUNTRIES_GEOJSON constant points at, ~line 1059) as of 2026-08-21;
if that basemap or those tables change, re-sync this snapshot.

ON COMMITTING THE RAW WORKBOOKS
-------------------------------
The four .xlsx files (~21MB) ARE committed alongside this script. Three
reasons: (1) the two FALLBACK files are truly irreplaceable -- there is no
API behind them, Baker Hughes' site serves only the current report, and the
2013-2023 history they carry cannot be re-downloaded once they're gone (the
two PREFERRED files ARE reproducible, via fetch_latest.py, but committing
them too means a fresh clone builds identical output without hitting the
network, and gives every refresh a reviewable diff); (2) .assetsignore
already excludes scripts/** from the served asset bundle, so none of this
reaches a visitor's browser or the Worker's asset budget -- the cost is git
clone size only; (3) it matches the repo's existing habit of parking source
snapshots under a feature's own raw/ folder. If the weight ever becomes a
problem, the fix is git-lfs or pruning old history on the two FALLBACK files
specifically, not the pipeline's only irreplaceable input.

AUTOMATED REFRESH
------------------
fetch_latest.py scrapes the "... - New Report" download links off
rigcount.bakerhughes.com/na-rig-count and /intl-rig-count (the link text is
stable; the underlying /static-files/<uuid> URL changes silently whenever
Baker Hughes publishes a new report) and overwrites NAM_latest.xlsx /
WW_latest.xlsx. It only overwrites a file if the download succeeds and looks
like a real .xlsx (openpyxl can open it, has the expected sheet) -- a bad
fetch (site markup change, network blip) leaves the previous good file in
place rather than corrupting the pipeline's input. See
.github/workflows/rig_count_intel.yml for the schedule (weekly; harmless to
run more often, since a week with no new report just re-downloads the same
file and produces an unchanged, uncommitted diff).

If Baker Hughes ever stops publishing these exports (or blocks scraping),
EIA's API carries an International rig count dataset under its International
category that would cover the non-US series. Not used here -- the Excel path
is richer (86 countries, monthly, back to 2013) and needs no key.

Usage:
    python3 build_rig_count_v1.py [--raw-dir DIR] [--out FILE] [--print-stats]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

try:
    import openpyxl
except ImportError:  # pragma: no cover - dependency hint
    print("openpyxl required:  pip install openpyxl", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent
DEFAULT_RAW = ROOT / "raw"
DEFAULT_OUT = ROOT.parent.parent / "public" / "data" / "rig_count_v1.json"

# (filename, sheet, header row (1-indexed), column count).
#
# The column count is explicit because both sheets carry the pivot summary off
# to the right of the detail table; reading "every non-empty column" would pull
# summary cells into the detail rows. The 2026 Worldwide export has one more
# column than the 2025 one (an added `Rig Status`), which is why this is a
# per-file constant rather than a shared schema.
NAM_FALLBACK = ("08-29-2025 North America Rig Count Report.xlsx", "NAM Monthly", 11, 11)
NAM_PREFERRED = ("NAM_latest.xlsx", "NAM Monthly", 11, 11)
WW_FALLBACK = ("July-2025  WorldWide Rig Count Report.xlsx", "WW Monthly", 12, 7)
WW_PREFERRED = ("WW_latest.xlsx", "WW Monthly", 12, 8)

# Baker Hughes country labels -> a plain English name app.js's resolveCountry()
# resolves to a basemap country. Only entries that need it are listed; anything
# not here is title-cased and handed to the resolver as-is, which covers ~100
# of the 113 labels ('ALGERIA' -> 'Algeria' and so on).
#
# Several of these collapse multiple Baker Hughes rows into one country -- the
# values are summed, not overwritten.
COUNTRY_RENAMES = {
    # Three emirates of one federation. Reported separately because Baker
    # Hughes counts rigs per concession operator, but Abu Dhabi alone is not a
    # country and three near-empty series is not what a map click wants.
    "UAE - ABU DHABI": "United Arab Emirates",
    "UAE - DUBAI": "United Arab Emirates",
    "UAE - SHARJAH": "United Arab Emirates",
    # There is no onshore CHINA row in the international list at all -- Baker
    # Hughes does not survey China's domestic land rigs, so its offshore count
    # IS the China series here (see verify: assert no plain 'CHINA' exists).
    "CHINA OFFSHORE": "China",
    # Both a land and an offshore UK row exist; the country is one country.
    "UNITED KINGDOM OFFSHORE": "United Kingdom",
    "UNITED KINGDOM": "United Kingdom",
    "IVORY COAST - COTE D'IVOIRE": "Ivory Coast",
    "MYANMAR (BURMA)": "Myanmar",
    "BRUNEI DARUSSALAM": "Brunei",
    # Two different countries either side of the Congo river. Spelled out so
    # neither falls through to the resolver's substring matching, where plain
    # 'Congo' is ambiguous between them.
    "CONGO": "Republic of the Congo",
    "CONGO, THE DEMOCRATIC REPUBLIC OF THE": "Democratic Republic of the Congo",
    # The basemap has no accented São Tomé; app.js's SUPPLEMENTAL_POINTS spells
    # it ASCII, and the resolver strips diacritics anyway.
    "SAN TOME PRINCIPE": "Sao Tome and Principe",
    # The state union dissolved in 2006; Baker Hughes kept the label for
    # continuity but the rigs are all in Vojvodina, i.e. Serbia. Left as
    # 'SERBIA AND MONTENEGRO' the resolver's substring fallback lands it on
    # Montenegro (the only unique containment match), which is the one country
    # it definitely is not, so name it explicitly.
    "SERBIA AND MONTENEGRO": "Serbia",
    # NAM sheet spellings.
    "UNITED STATES": "United States of America",
    "CANADA": "Canada",
}

# Baker Hughes rows that are not countries and are dropped rather than mapped.
COUNTRY_DROPS = {
    # A Russian island region, not a country: Baker Hughes used it as its only
    # window into Russia and stopped reporting it in 2022-04 after suspending
    # Russian operations. Publishing ~14 rigs as "Russia" would understate the
    # country by two orders of magnitude, and 'Sakhalin' resolves to nothing.
    "Sakhalin",
}

# === Basemap resolution (mirrors app.js resolveCountry(), see module docstring) ===
#
# A snapshot of the 180 country names app.js's own basemap fetch
# (COUNTRIES_GEOJSON, https://raw.githubusercontent.com/johan/world.geo.json/
# master/countries.geo.json) resolves against, taken 2026-08-21. Antarctica is
# in the raw file but never a rig country; harmless to leave in.
BASEMAP_NAMES = [
    "Afghanistan", "Albania", "Algeria", "Angola", "Antarctica", "Argentina",
    "Armenia", "Australia", "Austria", "Azerbaijan", "Bangladesh", "Belarus",
    "Belgium", "Belize", "Benin", "Bermuda", "Bhutan", "Bolivia",
    "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria",
    "Burkina Faso", "Burundi", "Cambodia", "Cameroon", "Canada",
    "Central African Republic", "Chad", "Chile", "China", "Colombia",
    "Costa Rica", "Croatia", "Cuba", "Cyprus", "Czech Republic",
    "Democratic Republic of the Congo", "Denmark", "Djibouti",
    "Dominican Republic", "East Timor", "Ecuador", "Egypt", "El Salvador",
    "Equatorial Guinea", "Eritrea", "Estonia", "Ethiopia", "Falkland Islands",
    "Fiji", "Finland", "France", "French Guiana",
    "French Southern and Antarctic Lands", "Gabon", "Gambia", "Georgia",
    "Germany", "Ghana", "Greece", "Greenland", "Guatemala", "Guinea",
    "Guinea Bissau", "Guyana", "Haiti", "Honduras", "Hungary", "Iceland",
    "India", "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy",
    "Ivory Coast", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya",
    "Kosovo", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho",
    "Liberia", "Libya", "Lithuania", "Luxembourg", "Macedonia", "Madagascar",
    "Malawi", "Malaysia", "Mali", "Malta", "Mauritania", "Mexico", "Moldova",
    "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia",
    "Nepal", "Netherlands", "New Caledonia", "New Zealand", "Nicaragua",
    "Niger", "Nigeria", "North Korea", "Northern Cyprus", "Norway", "Oman",
    "Pakistan", "Panama", "Papua New Guinea", "Paraguay", "Peru",
    "Philippines", "Poland", "Portugal", "Puerto Rico", "Qatar",
    "Republic of Serbia", "Republic of the Congo", "Romania", "Russia",
    "Rwanda", "Saudi Arabia", "Senegal", "Sierra Leone", "Slovakia",
    "Slovenia", "Solomon Islands", "Somalia", "Somaliland", "South Africa",
    "South Korea", "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname",
    "Swaziland", "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan",
    "Thailand", "The Bahamas", "Togo", "Trinidad and Tobago", "Tunisia",
    "Turkey", "Turkmenistan", "Uganda", "Ukraine", "United Arab Emirates",
    "United Kingdom", "United Republic of Tanzania", "United States of America",
    "Uruguay", "Uzbekistan", "Vanuatu", "Venezuela", "Vietnam", "West Bank",
    "Western Sahara", "Yemen", "Zambia", "Zimbabwe",
]

# Snapshot of app.js's COUNTRY_ALIASES (~line 1327). Only entries that could
# plausibly matter for a Baker Hughes label are exercised by this script, but
# copied in full so this stays a faithful mirror rather than a hand-trimmed
# subset that silently drifts from the real one.
BASEMAP_ALIASES = {
    "usa": "United States of America", "us": "United States of America",
    "united states": "United States of America", "america": "United States of America",
    "uk": "United Kingdom", "great britain": "United Kingdom", "england": "United Kingdom",
    "russian federation": "Russia",
    "korea rep": "South Korea", "republic of korea": "South Korea", "korea south": "South Korea",
    "dem peoples rep of korea": "North Korea", "korea north": "North Korea",
    "iran islamic republic of": "Iran", "iran islamic rep": "Iran",
    "viet nam": "Vietnam",
    "syrian arab republic": "Syria",
    "lao peoples dem rep": "Laos", "lao pdr": "Laos",
    "united republic of tanzania": "Tanzania",
    "bolivia plurinational state of": "Bolivia",
    "venezuela bolivarian rep of": "Venezuela",
    "republic of moldova": "Moldova",
    "czechia": "Czech Republic",
    "cote d ivoire": "Ivory Coast", "cote divoire": "Ivory Coast",
    "congo dr": "Democratic Republic of the Congo",
    "dr congo": "Democratic Republic of the Congo",
    "congo dem rep": "Democratic Republic of the Congo",
    "democratic republic of congo": "Democratic Republic of the Congo",
    "congo rep": "Republic of the Congo",
    "burma": "Myanmar",
    "uae": "United Arab Emirates",
    "north macedonia": "Macedonia",
    "eswatini": "Swaziland",
    "brunei darussalam": "Brunei",
    "cabo verde": "Cape Verde",
    "turkiye": "Turkey",
    "netherlands kingdom of the": "Netherlands",
    "china hong kong sar": "Hong Kong",
    "china macao sar": "Macau",
    "other asia nes": "Taiwan",
}

# Snapshot of app.js's SUPPLEMENTAL_POINTS keys (~line 1411) -- places the
# basemap has no polygon for but resolveCountry() still resolves by name.
SUPPLEMENTAL_NAMES = [
    "Singapore", "Hong Kong", "Macau", "Taiwan", "Bahrain", "Malta",
    "Trinidad and Tobago", "Mauritius", "Cape Verde", "Maldives", "Barbados",
    "Bahamas", "Seychelles", "Comoros", "Sao Tome and Principe",
]

def _norm(s: str) -> str:
    """Port of app.js's normCountryName()."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _build_basemap_index():
    by_key: dict[str, str] = {}
    records: list[str] = []

    def put(k, key):
        n = _norm(k)
        if n and n not in by_key:
            by_key[n] = key

    for name in BASEMAP_NAMES:
        records.append(name)
        put(name, name)
    for alias, target in BASEMAP_ALIASES.items():
        hit = by_key.get(_norm(target))
        if hit:
            put(alias, hit)
    for name in SUPPLEMENTAL_NAMES:
        if _norm(name) not in by_key:
            records.append(name)
            by_key[_norm(name)] = name
    return by_key, records


_BASEMAP_BY_KEY, _BASEMAP_RECORDS = _build_basemap_index()


def canonicalize(name: str) -> str | None:
    """Port of app.js's resolveCountry(name)?.label.

    Returns the exact string trade.js will compute when a user clicks this
    country on the live map, or None if even the containment fallback can't
    place it (ambiguous or no match at all) -- callers should drop those
    rather than emit a key nothing will ever look up.
    """
    n = _norm(name)
    if not n:
        return None
    hit = _BASEMAP_BY_KEY.get(n) or _BASEMAP_BY_KEY.get(_norm(BASEMAP_ALIASES.get(n, "")))
    if hit:
        return hit
    partial = [r for r in _BASEMAP_RECORDS if _norm(r) in n or n in _norm(r)]
    return partial[0] if len(partial) == 1 else None

# Sparklines need a shape, not two dots. Countries Baker Hughes touched for a
# month or two (Faroe Islands 2014, Bahamas 2021, Sao Tome 2022 -- one rig each)
# would render as a flat two-point line or, below two points, as nothing at all
# inside an otherwise-empty card.
MIN_MONTHS = 12


def read_detail(path: Path, sheet: str, header_row: int, ncols: int) -> list[dict]:
    """Row dicts from a Monthly sheet's detail table, below the header noise."""
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = book[sheet]
        rows = ws.iter_rows(min_row=header_row, values_only=True)
        header = [c for c in next(rows)][:ncols]
        out = []
        for raw in rows:
            raw = raw[:ncols]
            if all(c is None for c in raw):
                continue
            out.append(dict(zip(header, raw)))
        return out
    finally:
        book.close()


def period(row: dict) -> str | None:
    """'2026-07' from a row's Year/Month, or None when either is unusable."""
    try:
        year = int(row["Year"])
        month = int(row["Month"])
    except (TypeError, ValueError, KeyError):
        return None
    if not (1 <= month <= 12) or not (1900 <= year <= 2100):
        return None
    return f"{year:04d}-{month:02d}"


def sum_by(rows, key) -> dict:
    """Sum 'Rig Count Value' by key(row), skipping rows that key to None.

    Values are summed as floats with no intermediate rounding: Baker Hughes
    reports monthly averages, so a single county-month is routinely 4.75 rigs
    and rounding before the sum would drift the national total by several rigs.
    """
    totals: dict = defaultdict(float)
    for row in rows:
        k = key(row)
        if k is None:
            continue
        value = row.get("Rig Count Value")
        if value is None:
            continue
        try:
            totals[k] += float(value)
        except (TypeError, ValueError):
            continue
    return totals


def prefer(preferred: dict, fallback: dict) -> dict:
    """Merge two {period: value} maps, letting the newer export win overlaps."""
    merged = dict(fallback)
    merged.update(preferred)
    return merged


def canonical_country(name: str) -> str | None:
    """Baker Hughes country label -> output key, or None to drop the rows.

    Two steps: COUNTRY_RENAMES (or a title-cased fallback) turns the raw label
    into a readable candidate, then canonicalize() pins that candidate to the
    exact string app.js's resolveCountry() will produce at runtime -- see the
    module docstring for why that second step is not optional (Serbia and
    Tanzania both need it; most candidates already equal their canonical form
    and pass through unchanged).
    """
    label = str(name or "").strip()
    if not label or label in COUNTRY_DROPS:
        return None
    candidate = COUNTRY_RENAMES.get(label, label.title())
    resolved = canonicalize(candidate)
    if resolved is None:
        print(f"WARN [country] '{label}' -> '{candidate}' does not resolve on the "
              "live basemap -- dropped", file=sys.stderr)
    return resolved


def month_range(start: str, end: str) -> list[str]:
    """Every 'YYYY-MM' from start to end inclusive."""
    y0, m0 = (int(x) for x in start.split("-"))
    y1, m1 = (int(x) for x in end.split("-"))
    out = []
    while (y0, m0) <= (y1, m1):
        out.append(f"{y0:04d}-{m0:02d}")
        m0 += 1
        if m0 == 13:
            y0, m0 = y0 + 1, 1
    return out


def densify(series: dict) -> list[dict]:
    """{period: value} -> a gap-free oldest-first list between its own endpoints.

    Baker Hughes omits a country-month entirely when it had no rigs, so a raw
    key list has holes (Djibouti reports 82 of 151 months). Plotting only the
    reported months would compress a two-year drilling gap into one flat
    segment and mis-date every point after it, so interior holes are filled
    with 0 -- which is what an omitted month means. Deliberately NOT extended
    past the last reported month: a country Baker Hughes stopped surveying has
    an unknown rig count, not a zero one.
    """
    if not series:
        return []
    periods = sorted(series)
    return [
        {"period": p, "value": round(series.get(p, 0.0), 2)}
        for p in month_range(periods[0], periods[-1])
    ]


def verify_against_summary(raw_dir: Path, global_series: dict) -> list[str]:
    """Cross-check the built global total against the WW sheet's own pivot.

    The pivot block above the detail table is not used to build anything, but
    its 'Worldwide' row is Baker Hughes' own published total for a few recent
    months -- the ideal independent check that the NAM + non-NAM-region sum is
    assembled right (and, in particular, that nothing is double counted).
    """
    name, sheet, header_row, _ = WW_PREFERRED
    book = openpyxl.load_workbook(raw_dir / name, read_only=True, data_only=True)
    try:
        ws = book[sheet]
        head = [list(r) for r in ws.iter_rows(min_row=1, max_row=header_row - 1, values_only=True)]
    finally:
        book.close()

    # Locate the pivot: the row whose first non-empty cell is 'Region' carries
    # the month headers, and 'Worldwide' the totals, at the same column offsets.
    months, totals = None, None
    for row in head:
        labelled = [(i, c) for i, c in enumerate(row) if c is not None]
        if not labelled:
            continue
        i, first = labelled[0]
        if first == "Region":
            months = {i: c for i, c in labelled[1:]}
        elif first == "Worldwide":
            totals = {i: c for i, c in labelled[1:]}
    if not months or not totals:
        return ["summary pivot not found in %s -- skipped cross-check" % name]

    problems = []
    for col, when in months.items():
        if not hasattr(when, "year") or col not in totals:
            continue
        p = f"{when.year:04d}-{when.month:02d}"
        published = float(totals[col])
        built = global_series.get(p)
        if built is None:
            problems.append(f"{p}: published {published:.1f}, not in built series")
        elif abs(built - published) > 0.5:
            problems.append(f"{p}: built {built:.1f} != published {published:.1f}")
    return problems


def build(raw_dir: Path) -> dict:
    # Each workbook is read once and its rows reused for both the global
    # total and the by-country breakdown -- the NAM files are 8-12MB each, so
    # parsing them twice (once per aggregation) roughly doubled build time for
    # no reason.
    nam_pref_rows = read_detail(raw_dir / NAM_PREFERRED[0], *NAM_PREFERRED[1:])
    nam_fall_rows = read_detail(raw_dir / NAM_FALLBACK[0], *NAM_FALLBACK[1:])
    nam = prefer(sum_by(nam_pref_rows, period), sum_by(nam_fall_rows, period))

    ww_pref = read_detail(raw_dir / WW_PREFERRED[0], *WW_PREFERRED[1:])
    ww_fall = read_detail(raw_dir / WW_FALLBACK[0], *WW_FALLBACK[1:])
    # Guard the CHINA OFFSHORE decision: if Baker Hughes ever adds an onshore
    # China row, 'CHINA OFFSHORE' -> 'China' silently stops being China's whole
    # series and starts being half of it (still summed correctly, but the
    # comment above lies), so fail loudly instead.
    if any(str(r.get("Country", "")).strip() == "CHINA" for r in ww_pref + ww_fall):
        raise SystemExit("a plain 'CHINA' row appeared -- revisit the CHINA OFFSHORE mapping")

    def international(rows):
        return [r for r in rows if str(r.get("Region", "")).strip() != "North America"]

    intl = prefer(
        sum_by(international(ww_pref), period),
        sum_by(international(ww_fall), period),
    )

    # Only months both halves cover: the North America export runs a month
    # ahead of the Worldwide one (2026-08 vs 2026-07), and a "global" total
    # missing every international rig would read as a 1000-rig collapse.
    shared = sorted(set(nam) & set(intl))
    global_series = {p: nam[p] + intl[p] for p in shared}

    def country_key(row):
        p = period(row)
        c = canonical_country(row.get("Country"))
        return (c, p) if c and p else None

    # {country: {period: value}}, fallback values first so the preferred
    # export's own entries simply overwrite them -- the same prefer() rule as
    # the global series (newer file wins any (country, period) it covers),
    # just applied per country instead of to one flat period map.
    by_country: dict = defaultdict(dict)
    for preferred_rows, fallback_rows in (
        (nam_pref_rows, nam_fall_rows),
        (international(ww_pref), international(ww_fall)),
    ):
        for (c, p), v in sum_by(fallback_rows, country_key).items():
            by_country[c][p] = v
        for (c, p), v in sum_by(preferred_rows, country_key).items():
            by_country[c][p] = v

    out_countries = {}
    dropped_short = []
    for name, series in sorted(by_country.items()):
        points = densify(series)
        if len(points) < MIN_MONTHS or not any(p["value"] for p in points):
            dropped_short.append((name, len(points)))
            continue
        out_countries[name] = points

    global_points = [{"period": p, "value": round(global_series[p], 2)} for p in shared]
    return {
        "generated_at": date.today().isoformat(),
        "source": (
            "Baker Hughes (rigcount.bakerhughes.com), manually exported reports -- see "
            "scripts/rig_count/raw/. No live API; refresh by re-exporting from Baker "
            "Hughes and re-running build_rig_count_v1.py. (A documented fallback if "
            "Baker Hughes exports become unavailable: EIA's own API has an "
            "International rig count dataset under its International category -- not "
            "used here since the Excel path already covers this.)"
        ),
        "unit": "rigs (monthly average; Baker Hughes reports fractional counts)",
        "data_quality_notes": [
            "Saudi Arabia's methodology changed from 'Active Rigs' to 'Operating Rigs' "
            "in Baker Hughes' own reporting starting ~2024 (2025-07: 69 under the old "
            "method vs 234 under the new one, every other country matching to the "
            "decimal across the overlap), producing a real level shift of roughly "
            "+165..+220 rigs in Saudi Arabia's series -- and therefore the global "
            "total -- at 2024-01, unrelated to actual drilling activity. Not smoothed "
            "or corrected here; the newer methodology is used throughout per the "
            "standard newer-file-wins merge rule below.",
            "Global = North America report detail (Canada + United States) + Worldwide "
            "report detail excluding its own North America region, which restates the "
            "same rigs and would double count.",
            "For each (country, year, month) covered by both a fallback and a "
            "preferred export, the preferred (newer) export's value wins; a month "
            "covered by only one file uses that file's value.",
            "Russia has no by_country entry: Baker Hughes has not published a Russia "
            "row in either Worldwide export since suspending Russian operations "
            "reporting in 2022-04 (its only prior window, a 'Sakhalin' sub-region "
            "row, is dropped rather than misattributed to all of Russia). Absent, "
            "not zero.",
            "A month absent from a country's series between its first and last "
            "reported month means zero rigs and is filled with 0; the series is not "
            "extended past the last month Baker Hughes reported it.",
            "Global stops at the last month both source reports cover.",
            "by_country keys are pinned to exactly what app.js's resolveCountry() "
            "resolves the country to on the live basemap, not just a title-cased "
            "label -- see canonicalize() above. Serbia and Tanzania both differ from "
            "their plain-English name because of this (their basemap features are "
            "'Republic of Serbia' and 'United Republic of Tanzania').",
        ],
        "coverage": {
            "global_first": global_points[0]["period"] if global_points else None,
            "global_last": global_points[-1]["period"] if global_points else None,
            "countries": len(out_countries),
            "dropped_short_series": [f"{n} ({m}m)" for n, m in dropped_short],
        },
        "global": global_points,
        "by_country": out_countries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build rig_count_v1.json from Baker Hughes exports")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    doc = build(args.raw_dir)
    problems = verify_against_summary(args.raw_dir, {p["period"]: p["value"] for p in doc["global"]})
    for line in problems:
        print(f"WARN [summary cross-check] {line}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )

    if args.print_stats:
        print(f"wrote {args.out}")
        cov = doc["coverage"]
        print(f"  global {cov['global_first']} .. {cov['global_last']} "
              f"({len(doc['global'])} months), latest {doc['global'][-1]['value']}")
        print(f"  countries: {cov['countries']}")
        if cov["dropped_short_series"]:
            print(f"  dropped (<{MIN_MONTHS} months): {', '.join(cov['dropped_short_series'])}")
        by_period = {p["period"]: p["value"] for p in doc["global"]}
        if "2026-01" in by_period:
            print(f"  sanity check 2026-01 global = {by_period['2026-01']} (expect 1821, "
                  "NAM 742.0 + non-NAM 1079 per Baker Hughes' own Worldwide pivot)")
        for name in ("United States of America", "Saudi Arabia", "China",
                     "United Arab Emirates", "Republic of Serbia", "Russia"):
            pts = doc["by_country"].get(name)
            if pts:
                print(f"  {name}: {pts[0]['period']}..{pts[-1]['period']} latest {pts[-1]['value']}")
            else:
                print(f"  {name}: (no data)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
