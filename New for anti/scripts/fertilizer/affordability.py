"""Nitrogen affordability for next season's US corn planting.

Urea costs per tonne of corn (World Bank Pink Sheet, monthly) over the winter
buying window (Sep of year Y-1 .. Feb of year Y), against the corn share of
US corn + soybean area in year Y (USDA PSD, area harvested). Corn needs
nitrogen and soybeans fix their own, so dear urea should tilt planting toward
soybeans. The soybean/corn price ratio over the same window is the usual
driver of that split, so it is controlled for.

Pre-registered check (set before the first run): the urea/corn coefficient is
negative with |t| >= 2, and its sign holds when each year is left out in
turn. Pass -> the card reads it as a planting signal; fail -> reference only.

Only reachable from Actions (World Bank, USDA). Area is cached in
us_area.csv so `prices.py apply` rebuilds offline.
"""

import io
import os
import urllib.request
import zipfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
AREA_CSV = os.path.join(HERE, "us_area.csv")
PSD_ZIP = "https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip"
WINDOW = [9, 10, 11, 12, 1, 2]       # Sep(Y-1) .. Feb(Y)
FIRST_YEAR = 1980
T_MIN = 2.0


def log(msg):
    print(f"[fertilizer-ratio] {msg}", flush=True)


def fetch_area():
    req = urllib.request.Request(PSD_ZIP, headers={"User-Agent": "fertilizer-prices/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    name = next(n for n in z.namelist() if n.endswith(".csv"))
    df = pd.read_csv(z.open(name), encoding="latin-1", low_memory=False)
    us = df[(df.Country_Name == "United States")
            & df.Commodity_Description.isin(["Corn", "Oilseed, Soybean"])
            & (df.Attribute_Description == "Area Harvested")]
    out = us.pivot_table(index="Market_Year", columns="Commodity_Description",
                         values="Value", aggfunc="last").rename(
        columns={"Corn": "corn_kha", "Oilseed, Soybean": "soy_kha"}).reset_index()
    out = out.rename(columns={"Market_Year": "year"}).dropna()
    out.to_csv(AREA_CSV, index=False)
    log(f"US area {int(out.year.min())}..{int(out.year.max())} -> {AREA_CSV}")
    return out


def load_area(offline=False):
    if not offline:
        try:
            return fetch_area()
        except Exception as exc:  # noqa: BLE001 - keep the cached table
            log(f"PSD unavailable ({exc}); using {AREA_CSV}")
    if os.path.exists(AREA_CSV):
        return pd.read_csv(AREA_CSV)
    return None


def window_means(prices):
    """Per planting year Y: mean urea/maize and soy/maize over Sep(Y-1)..Feb(Y)."""
    p = prices.dropna(subset=["urea", "maize"]).copy()
    p["y"] = p.month.str[:4].astype(int)
    p["m"] = p.month.str[5:7].astype(int)
    p = p[p.m.isin(WINDOW)]
    p["plant"] = np.where(p.m >= 9, p.y + 1, p.y)
    p["urea_corn"] = p.urea / p.maize
    p["soy_corn"] = p.soybeans / p.maize if "soybeans" in p else np.nan
    g = p.groupby("plant").agg(urea_corn=("urea_corn", "mean"), soy_corn=("soy_corn", "mean"),
                               months=("m", "size"))
    return g


def _ols(y, X):
    X = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(y) - X.shape[1]
    s2 = resid @ resid / dof
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    return beta, se


def backtest(win, area):
    a = area.set_index("year").sort_index()
    share = a.corn_kha / (a.corn_kha + a.soy_kha) * 100
    full = win[win.months == len(WINDOW)]
    d = pd.DataFrame({"share": share, "uc": np.log(full.urea_corn), "sc": np.log(full.soy_corn)}).dropna()
    d = d[d.index >= FIRST_YEAR]
    dd = d.diff().dropna()
    if len(dd) < 15:
        return None
    y = dd.share.values
    X = dd[["uc", "sc"]].values
    beta, se = _ols(y, X)
    signs = []
    for i in range(len(dd)):
        keep = np.arange(len(dd)) != i
        b, _ = _ols(y[keep], X[keep])
        signs.append(b[1] < 0)
    t = beta[1] / se[1]
    passed = bool(beta[1] < 0 and abs(t) >= T_MIN and all(signs))
    # Share points for a 10% rise in urea/corn, soy/corn held.
    per10 = float(beta[1] * np.log(1.1))
    return {
        "years": f"{int(dd.index.min())}-{int(dd.index.max())}", "n": int(len(dd)),
        "coef_share_pp_per_10pct": round(per10, 2), "t": round(float(t), 2),
        "soy_corn_coef_per_10pct": round(float(beta[2] * np.log(1.1)), 2),
        "soy_corn_t": round(float(beta[2] / se[2]), 2),
        "leave_one_out_sign_held": bool(all(signs)), "passed": passed,
        "rule_ko": f"요소/옥수수 계수 음수, |t| ≥ {T_MIN:g}, 한 해씩 빼도 부호 유지 (콩/옥수수 가격비 통제)",
    }


def build(prices, offline=False):
    if "maize" not in prices:
        return None
    win = window_means(prices)
    if win.empty:
        return None
    area = load_area(offline)
    bt = backtest(win, area) if area is not None else None
    cur_year = int(win.index.max())
    cur = win.loc[cur_year]
    full = win[(win.months == len(WINDOW)) & (win.index >= FIRST_YEAR)]
    hist = full.urea_corn
    rank = round(float((hist < cur.urea_corn).mean() * 100)) if len(hist) else None
    last = prices.dropna(subset=["urea", "maize"]).iloc[-1]
    out = {
        "planting_year": cur_year,
        "window_ko": f"{cur_year - 1}년 9월~{cur_year}년 2월",
        "months_in": int(cur.months),
        "urea_per_corn": round(float(cur.urea_corn), 2),
        "soy_per_corn": None if pd.isna(cur.soy_corn) else round(float(cur.soy_corn), 2),
        "prev_urea_per_corn": round(float(win.loc[cur_year - 1].urea_corn), 2) if cur_year - 1 in win.index else None,
        "prev_soy_per_corn": round(float(win.loc[cur_year - 1].soy_corn), 2) if cur_year - 1 in win.index else None,
        "avg_10y": round(float(hist.iloc[-10:].mean()), 2) if len(hist) >= 10 else None,
        "pct_rank": rank,
        "latest": {"month": last.month, "urea_usd_t": round(float(last.urea), 1),
                   "maize_usd_t": round(float(last.maize), 1),
                   "ratio": round(float(last.urea / last.maize), 2)},
        "history": [{"year": int(y), "urea_per_corn": round(float(v), 2)} for y, v in hist.iloc[-20:].items()],
        "backtest": bt,
    }
    if bt:
        log(f"backtest {bt['years']} n={bt['n']}: urea/corn {bt['coef_share_pp_per_10pct']:+.2f}pp per +10% "
            f"(t {bt['t']}), soy/corn {bt['soy_corn_coef_per_10pct']:+.2f}pp (t {bt['soy_corn_t']}), "
            f"LOO sign {bt['leave_one_out_sign_held']} -> {'pass' if bt['passed'] else 'reference only'}")
    log(f"{cur_year} planting: urea/corn {out['urea_per_corn']} ({out['months_in']} months), "
        f"prev {out['prev_urea_per_corn']}, 10y avg {out['avg_10y']}, rank {rank}%")
    return out
