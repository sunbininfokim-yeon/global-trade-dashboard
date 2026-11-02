"""
Malaysian palm-oil supply from MPOB's monthly industry summary.

Usage: python3 -m palm_oil.mpob          # -> training/mpob_monthly.csv
       python3 -m palm_oil.mpob dump     # print the parsed rows of this year

Source: MPOB Economics & Industry Development Division,
https://bepi.mpob.gov.my/stat/web_report1.php?val=YYYY84, "Summary of the
Malaysian Palm Oil Industry YYYY". One HTML table per year, 13 month columns
from December of the year before to December of the year. Recent months are
marked (p) provisional and (r) revised; a later page wins for a month that
two pages share, so the revised figure replaces the provisional one.

bepi.mpob.gov.my refuses the build container, so this runs in Actions only.

The indicators are context for the forecast, not a model input: no number on
the dashboard moves because of them.
"""

import os
import re
import sys
import urllib.request
from datetime import date
from html.parser import HTMLParser

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MPOB_CSV = os.path.join(HERE, "training", "mpob_monthly.csv")
URL = "https://bepi.mpob.gov.my/stat/web_report1.php?val={year}84"
FIRST_YEAR = 2010

# (section heading, row label) -> column. Matching is case-insensitive, on
# the whole label or the label before " (", so "Palm Oil (CPO+PPO)" matches
# "palm oil" but "Palm Kernel Oil" does not match "palm kernel".
SERIES = {
    ("PRODUCTION", "crude palm oil"): "cpo_production_t",
    ("PRODUCTION", "palm kernel"): "pk_production_t",
    ("CLOSING STOCK", "palm oil"): "palm_oil_stock_t",
    ("EXPORT", "palm oil"): "palm_oil_export_t",
    ("IMPORT", "palm oil"): "palm_oil_import_t",
}
SECTIONS = ("PRODUCTION", "CLOSING STOCK", "OPENING STOCK", "EXPORT", "IMPORT",
            "PRICE", "DOMESTIC", "DISAPPEARANCE", "PLANTED", "YIELD")
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec"]

# PKS (shell) per tonne of palm kernel. Mills recover roughly as much shell
# as kernel from a bunch (each ~5-7% of FFB weight); industry rule of thumb,
# not a measured national ratio. Cross-check: 2025 kernel x 1.1 lands within
# a few % of the CPO x 0.25 figure pks.py uses.
PKS_PER_KERNEL = 1.1
PKS_PER_KERNEL_RANGE = (0.9, 1.3)


def log(msg):
    print(f"[palm-oil:mpob] {msg}", flush=True)


class _Rows(HTMLParser):
    """Every <tr> as a list of cell texts."""

    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            span = dict(attrs).get("colspan")
            self._span = int(span) if span and span.isdigit() else 1

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            text = " ".join("".join(self._cell).split())
            self._row.extend([text] + [""] * (self._span - 1))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _number(text):
    text = re.sub(r"\((p|r|e)\)", "", text, flags=re.I).replace(",", "").strip()
    if not text or text in ("-", "--", "n.a.", "na"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _section(label):
    upper = label.upper()
    for name in SECTIONS:
        if upper.startswith(name):
            return name
    return None


def parse(html, year):
    """Long rows (date, column, value, provisional) from one year's page."""
    rows = _Rows()
    rows.feed(html)
    out, section, flagged = [], None, [False] * 13
    for row in rows.rows:
        label = row[0].strip()
        values = row[1:]
        # The month header marks provisional months, e.g. "Sep (p)".
        if not label and any(v[:3].lower() in MONTHS for v in values if v):
            flagged = [bool(re.search(r"\((p|e)\)", v, re.I)) for v in values[:13]]
            flagged += [False] * (13 - len(flagged))
            continue
        numbers = [_number(v) for v in values]
        heading = _section(label)
        if heading and not any(n is not None for n in numbers):
            section = heading
            continue
        if heading:
            # A heading row that also carries numbers, e.g. "PRODUCTION" with
            # the CPO total on it, is not one of ours: keep the section only.
            section = heading
            continue
        if section is None:
            continue
        name = label.lower()
        column = next((c for (s, l), c in SERIES.items()
                       if s == section and (name == l or name.startswith(l + " ("))), None)
        if column is None:
            continue
        # Months run Dec(Y-1), Jan(Y) ... Dec(Y); later cells beyond 13 are
        # totals or averages.
        for i, (raw, value) in enumerate(zip(values[:13], numbers[:13])):
            if value is None:
                continue
            month = date(year - 1, 12, 1) if i == 0 else date(year, i, 1)
            out.append({"date": month, "column": column, "value": value,
                        "provisional": flagged[i] or bool(re.search(r"\((p|e)\)", raw, re.I)),
                        "page": year})
    return out


def fetch_year(year):
    req = urllib.request.Request(URL.format(year=year),
                                 headers={"User-Agent": "Mozilla/5.0 yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", errors="replace")


def tidy(long_rows):
    """Wide monthly frame; for a month on two pages the later page wins."""
    d = pd.DataFrame(long_rows)
    d = d.sort_values(["date", "column", "page"])
    d = d.groupby(["date", "column"]).last().reset_index()
    wide = d.pivot(index="date", columns="column", values="value")
    wide.columns.name = None
    prov = d.groupby("date").provisional.any().rename("provisional")
    wide = wide.join(prov).reset_index()
    wide["date"] = pd.to_datetime(wide.date).dt.strftime("%Y-%m")
    return wide


def collect(today=None):
    today = today or date.today()
    rows, got = [], []
    for year in range(FIRST_YEAR, today.year + 1):
        try:
            parsed = parse(fetch_year(year), year)
        except Exception as exc:  # one bad year must not lose the rest
            log(f"{year}: fetch failed: {exc}")
            continue
        if not parsed:
            log(f"{year}: no matching rows")
            continue
        rows.extend(parsed)
        got.append(year)
    if not rows:
        raise SystemExit("MPOB: nothing parsed")
    wide = tidy(rows)
    missing = [c for c in SERIES.values() if c not in wide.columns]
    # A page without the kernel row only loses the PKS line, not the run.
    missing = [c for c in missing if c != "pk_production_t"]
    if missing:
        raise SystemExit(f"MPOB: rows not found: {', '.join(missing)}")
    os.makedirs(os.path.dirname(MPOB_CSV), exist_ok=True)
    wide.to_csv(MPOB_CSV, index=False)
    log(f"pages {got[0]}-{got[-1]} ({len(got)}), months {wide.date.iloc[0]}"
        f"..{wide.date.iloc[-1]} -> {MPOB_CSV}")
    return wide


# --------------------------------------------------------------- indicators

def _pct(a, b):
    if a is None or b is None or pd.isna(a) or pd.isna(b) or b == 0:
        return None
    return round((a / b - 1) * 100, 1)


def _kt(v):
    return None if v is None or pd.isna(v) else round(float(v) / 1000, 0)


def indicators(frame=None):
    """Latest-month supply read-out, or None without data.

    Stocks against the same month's 5-year average is the market's usual
    yardstick: high stocks mean ample supply (bearish CPO), low stocks tight.
    The verdict thresholds (±10%) are fixed here, not fitted.
    """
    if frame is None:
        if not os.path.exists(MPOB_CSV):
            return None
        frame = pd.read_csv(MPOB_CSV)
    d = frame.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.dropna(subset=["palm_oil_stock_t"]).sort_values("date").reset_index(drop=True)
    if d.empty:
        return None
    last = d.iloc[-1]
    month, year = last.date.month, last.date.year
    by = d.set_index("date")

    def at(y, m, col):
        key = pd.Timestamp(y, m, 1)
        return by[col].get(key) if col in by and key in by.index else None

    stock = last.palm_oil_stock_t
    past = [at(year - k, month, "palm_oil_stock_t") for k in range(1, 6)]
    past = [v for v in past if v is not None and not pd.isna(v)]
    avg5 = sum(past) / len(past) if len(past) >= 3 else None
    prev = d.iloc[-2] if len(d) >= 2 else None

    def ytd(col, y):
        s = by[col] if col in by else pd.Series(dtype=float)
        s = s[(s.index.year == y) & (s.index.month <= month)]
        return s.sum() if len(s) == month else None

    def last3(col, y):
        s = by[col] if col in by else pd.Series(dtype=float)
        end = pd.Timestamp(y, month, 1)
        s = s[(s.index > end - pd.DateOffset(months=3)) & (s.index <= end)]
        return s.sum() if len(s) == 3 else None

    vs5 = _pct(stock, avg5)
    if vs5 is None:
        verdict = "neutral"
    elif vs5 >= 10:
        verdict = "ample"
    elif vs5 <= -10:
        verdict = "tight"
    else:
        verdict = "neutral"
    verdict_ko = {"ample": "공급 여유", "tight": "공급 빠듯", "neutral": "평년 수준"}[verdict]

    prod3 = _pct(last3("cpo_production_t", year), last3("cpo_production_t", year - 1))
    exp3 = _pct(last3("palm_oil_export_t", year), last3("palm_oil_export_t", year - 1))
    mom = _pct(stock, None if prev is None else prev.palm_oil_stock_t)

    parts = []
    if vs5 is not None:
        parts.append(f"재고가 같은 달 5년 평균보다 {vs5:+.0f}%")
    if prod3 is not None:
        parts.append(f"최근 3개월 생산 전년비 {prod3:+.0f}%")
    if exp3 is not None:
        parts.append(f"수출 {exp3:+.0f}%")
    series = []
    for _, r in d.tail(13).iterrows():
        pk = r.get("pk_production_t")
        series.append({
            "month": r.date.strftime("%Y-%m"),
            "stock_kt": _kt(r.get("palm_oil_stock_t")),
            "production_kt": _kt(r.get("cpo_production_t")),
            "export_kt": _kt(r.get("palm_oil_export_t")),
            "pks_kt": _kt(None if pk is None or pd.isna(pk) else pk * PKS_PER_KERNEL),
        })
    return {
        "month": last.date.strftime("%Y-%m"),
        "month_ko": f"{year}년 {month}월",
        "provisional": bool(last.get("provisional", False)),
        "stock_kt": _kt(stock),
        "stock_5y_avg_kt": _kt(avg5),
        "stock_vs_5y_pct": vs5,
        "stock_mom_pct": mom,
        "production_kt": _kt(last.get("cpo_production_t")),
        "production_3m_yoy_pct": prod3,
        "production_ytd_yoy_pct": _pct(ytd("cpo_production_t", year),
                                       ytd("cpo_production_t", year - 1)),
        "export_kt": _kt(last.get("palm_oil_export_t")),
        "export_3m_yoy_pct": exp3,
        "export_ytd_yoy_pct": _pct(ytd("palm_oil_export_t", year),
                                   ytd("palm_oil_export_t", year - 1)),
        "import_kt": _kt(last.get("palm_oil_import_t")),
        "pks": _pks(by, year, month, last12=lambda c, y: _sum12(by, c, y, month),
                    last3=last3, ytd=ytd),
        "verdict": verdict,
        "verdict_ko": verdict_ko,
        "reason_ko": ", ".join(parts) if parts else None,
        "series": series,
        "applied_to_forecast": False,
        "note_ko": ("MPOB 월간 통계(말레이시아 팜유 재고·생산·수출). 재고가 5년 평균보다 "
                    "10% 넘게 많으면 공급 여유, 10% 넘게 적으면 빠듯으로 본다. 예측치에는 "
                    "반영하지 않는다."),
        "source": "MPOB, Summary of the Malaysian Palm Oil Industry",
        "url": URL.format(year=year),
    }


def _sum12(by, col, year, month):
    if col not in by:
        return None
    end = pd.Timestamp(year, month, 1)
    s = by[col][(by.index > end - pd.DateOffset(months=12)) & (by.index <= end)].dropna()
    return s.sum() if len(s) == 12 else None


def _pks(by, year, month, last12, last3, ytd):
    """Monthly PKS estimate from MPOB palm kernel output, or None."""
    col = "pk_production_t"
    if col not in by or pd.isna(by[col].get(pd.Timestamp(year, month, 1))):
        return None
    pk = by[col][pd.Timestamp(year, month, 1)]
    t12, p12 = last12(col, year), last12(col, year - 1)
    k = PKS_PER_KERNEL
    out = {
        "month_kt": _kt(pk * k),
        "kernel_month_kt": _kt(pk),
        "last12_kt": _kt(None if t12 is None else t12 * k),
        "last12_range_kt": (None if t12 is None else
                            [_kt(t12 * PKS_PER_KERNEL_RANGE[0]), _kt(t12 * PKS_PER_KERNEL_RANGE[1])]),
        "last12_yoy_pct": _pct(t12, p12),
        "m3_yoy_pct": _pct(last3(col, year), last3(col, year - 1)),
        "ytd_yoy_pct": _pct(ytd(col, year), ytd(col, year - 1)),
        "ratio_to_kernel": k,
    }
    parts = [f"최근 12개월 PKS 약 {out['last12_kt'] / 10:,.0f}만 t" if out["last12_kt"] else None,
             f"전년비 {out['last12_yoy_pct']:+.1f}%" if out["last12_yoy_pct"] is not None else None,
             f"최근 3개월 {out['m3_yoy_pct']:+.1f}%" if out["m3_yoy_pct"] is not None else None]
    out["summary_ko"] = ", ".join(p for p in parts if p)
    out["note_ko"] = ("MPOB 월별 팜커널 생산 × 1.1(껍질/커널, 업계 경험치 0.9~1.3)로 환산한 실측 기반 "
                      "추정. 커널 생산은 공식 통계, 비율은 추정이다.")
    return out


def main(argv):
    if argv[:1] == ["dump"]:
        year = date.today().year
        rows = _Rows()
        rows.feed(fetch_year(year))
        for r in rows.rows:
            print(" | ".join(r))
        return 0
    collect()
    print(indicators())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
