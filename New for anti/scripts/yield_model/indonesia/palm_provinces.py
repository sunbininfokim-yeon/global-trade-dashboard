"""Indonesia CPO yield by province: does last year's dry season move it?

Specification fixed on 2026-11-01 before any skill was computed:

  provinces  the eight with >= 3% of 2021-23 CPO (about 90% of output):
             Riau, Kalimantan Tengah, Kalimantan Barat, Sumatera Utara,
             Kalimantan Timur (+ Utara), Sumatera Selatan, Jambi, Sumatera Barat
  label      log(CPO tonnes / planted ha), BPS province tables (region_db)
  trend      per province, linear in year over the trailing 10 seasons
             before the forecast year (BPS revised area/production in 2018;
             a short window lets the trend move with that instead of a dummy
             picked after seeing the data)
  weather    the three "core" rows of region_db/data/variable_spec.csv:
             dry-season (Jun-Oct) root-zone soil moisture one and two years
             before harvest, and dry-season max VPD one year before,
             each z-scored within province on the training seasons only
  model      pooled OLS of the trend residual on the three z-scores
             (3 coefficients shared by all provinces)
  test       forward: every harvest year 2011-2023 trained only on earlier
             years; leave-one-year-out (LOO) over all years as a second view.
             Score = MAE of the production-weighted national yield deviation.
  pass       both forward and LOO MAE >= 10% below trend-only
             (same rule as the Russia core spec, #778)

Nino 3.4 (Jun-Oct of the year before harvest) is scored the same way as a
diagnostic only; it does not decide anything.

Run from scripts/yield_model:  python3 -m indonesia.palm_provinces
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "region_db", "data")
OUT = os.path.join(HERE, "training", "palm_provinces_backtest.json")
SST = os.path.join(HERE, "..", "..", "..", "public", "data", "sst_regions_v1.json")

PROVINCES = ["Riau", "Kalimantan Tengah", "Kalimantan Barat", "Sumatera Utara",
             "Kalimantan Timur", "Sumatera Selatan", "Jambi", "Sumatera Barat"]
ISLAND = {p: ("Kalimantan" if p.startswith("Kalimantan") else "Sumatra") for p in PROVINCES}
CORE = [("soil_root_m3m3", "dry_lag1"), ("soil_root_m3m3", "dry_lag2"), ("vpd_max_kpa", "dry_lag1")]
TREND_YEARS = 10
FIRST_TEST = 2011
PASS = 0.10


def load_panel() -> pd.DataFrame:
    obs = pd.read_csv(os.path.join(DATA, "province_observations.csv"))
    obs = obs[(obs["crop"] == "oil_palm") & (obs["category"] == "total")].copy()
    obs.loc[obs.province == "Kalimantan Utara", "province"] = "Kalimantan Timur"
    g = (obs.groupby(["province", "year"])[["area_ha", "production_tonnes"]]
         .sum(min_count=1).reset_index())
    g = g[g.province.isin(PROVINCES)].dropna(subset=["area_ha", "production_tonnes"])
    g["ly"] = np.log(g.production_tonnes / g.area_ha)

    clim = pd.read_csv(os.path.join(DATA, "province_climate.csv"))
    clim = clim[clim["crop"] == "oil_palm"]
    for metric, window in CORE:
        col = f"{metric}:{window}"
        part = clim[(clim.metric == metric) & (clim.window == window)][["province", "year", "value"]]
        g = g.merge(part.rename(columns={"value": col}), on=["province", "year"], how="left")
    nino = _nino_lag1()
    g["nino34:dry_lag1"] = g.year.map(nino)
    return g.sort_values(["province", "year"]).reset_index(drop=True)


def _nino_lag1() -> dict:
    try:
        with open(SST, encoding="utf-8") as f:
            series = next(r for r in json.load(f)["regions"] if r["id"] == "nino34")["series"]
    except (OSError, StopIteration, KeyError):
        return {}
    s = dict(series)
    out = {}
    for year in range(1983, 2031):
        vals = [s.get(f"{year - 1}-{m:02d}") for m in range(6, 11)]
        if None not in vals:
            out[year] = float(np.mean(vals))
    return out


def _trend_pred(hist: pd.DataFrame, year: int) -> float:
    h = hist[hist.year >= year - TREND_YEARS]
    if len(h) < 5:
        return np.nan
    b = np.polyfit(h.year, h.ly, 1)
    return float(np.polyval(b, year))


def _residuals(train: pd.DataFrame) -> pd.Series:
    """In-sample residual of each training row from its own trailing trend."""
    out = pd.Series(np.nan, index=train.index)
    for p, rows in train.groupby("province"):
        for i, row in rows.iterrows():
            hist = rows[rows.year < row.year]
            out[i] = row.ly - _trend_pred(hist, row.year)
    return out


def _zscore(train: pd.DataFrame, test: pd.DataFrame, cols: list[str]):
    tr, te = train.copy(), test.copy()
    for c in cols:
        stats = train.groupby("province")[c].agg(["mean", "std"])
        for frame in (tr, te):
            m = frame.province.map(stats["mean"])
            s = frame.province.map(stats["std"]).replace(0, np.nan)
            frame[c] = (frame[c] - m) / s
    return tr, te


def predict_year(panel: pd.DataFrame, year: int, cols: list[str], train_years) -> pd.DataFrame:
    train = panel[panel.year.isin(train_years)].copy()
    test = panel[panel.year == year].copy()
    test["trend"] = [
        _trend_pred(panel[(panel.province == r.province) & (panel.year < year) & panel.year.isin(train_years)], year)
        if year > min(train_years) else np.nan for r in test.itertuples()]
    # LOO needs a trend for the held-out year too: use the trailing window of
    # the other years before it (never the year itself).
    train["resid"] = _residuals(train)
    fit = train.dropna(subset=["resid"] + cols)
    test["pred"] = test.trend
    if cols and len(fit) >= 5 * (len(cols) + 1):
        trz, tez = _zscore(fit, test, cols)
        X = np.column_stack([trz[cols].values, np.ones(len(trz))])
        beta, *_ = np.linalg.lstsq(X, trz.resid.values, rcond=None)
        adj = np.column_stack([tez[cols].fillna(0).values, np.ones(len(tez))]) @ beta
        test["pred"] = test.trend + adj
        test.attrs["beta"] = dict(zip(cols + ["const"], np.round(beta, 4)))
    return test


def national_error(test: pd.DataFrame, col: str) -> float:
    """Production-weighted national yield deviation, as a log ratio."""
    t = test.dropna(subset=[col])
    actual = (t.production_tonnes).sum() / t.area_ha.sum()
    pred = (np.exp(t[col]) * t.area_ha).sum() / t.area_ha.sum()
    return float(np.log(pred / actual))


def evaluate(panel: pd.DataFrame, cols: list[str], mode: str) -> dict:
    years = sorted(panel.year.unique())
    rows = []
    for year in years:
        if mode == "forward":
            if year < FIRST_TEST:
                continue
            train_years = [y for y in years if y < year]
        else:
            if year < years[0] + 5:
                continue
            train_years = [y for y in years if y != year]
        test = predict_year(panel, year, cols, train_years)
        if test.trend.isna().any():
            continue
        rows.append(dict(year=int(year), trend=national_error(test, "trend"),
                         model=national_error(test, "pred"),
                         island={isl: dict(trend=national_error(test[test.province.map(ISLAND) == isl], "trend"),
                                           model=national_error(test[test.province.map(ISLAND) == isl], "pred"))
                                 for isl in ("Sumatra", "Kalimantan")},
                         beta=test.attrs.get("beta")))
    t = np.array([abs(r["trend"]) for r in rows])
    m = np.array([abs(r["model"]) for r in rows])
    out = dict(n=len(rows), mae_trend_pct=round(100 * t.mean(), 2), mae_model_pct=round(100 * m.mean(), 2),
               skill=round(1 - m.mean() / t.mean(), 3))
    for isl in ("Sumatra", "Kalimantan"):
        ti = np.array([abs(r["island"][isl]["trend"]) for r in rows])
        mi = np.array([abs(r["island"][isl]["model"]) for r in rows])
        out[f"skill_{isl.lower()}"] = round(1 - mi.mean() / ti.mean(), 3)
    out["years"] = [dict(year=r["year"], trend_pct=round(100 * r["trend"], 1), model_pct=round(100 * r["model"], 1))
                    for r in rows]
    out["last_beta"] = rows[-1]["beta"] if rows else None
    return out


def main() -> dict:
    panel = load_panel()
    core = [f"{m}:{w}" for m, w in CORE]
    result = dict(spec=__doc__.split("Run from")[0].strip(), provinces=PROVINCES,
                  seasons=[int(panel.year.min()), int(panel.year.max())])
    for name, cols in (("core", core), ("nino_diagnostic", ["nino34:dry_lag1"])):
        result[name] = dict(forward=evaluate(panel, cols, "forward"), loo=evaluate(panel, cols, "loo"))
        f, l = result[name]["forward"], result[name]["loo"]
        print(f"[palm_provinces] {name}: forward skill {f['skill']:+.3f} "
              f"(MAE {f['mae_model_pct']}% vs trend {f['mae_trend_pct']}%, n={f['n']}), "
              f"LOO {l['skill']:+.3f}; Sumatra {f['skill_sumatra']:+.3f}, Kalimantan {f['skill_kalimantan']:+.3f}")
    c = result["core"]
    result["passed"] = bool(c["forward"]["skill"] >= PASS and c["loo"]["skill"] >= PASS)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"[palm_provinces] passed={result['passed']}")
    return result


if __name__ == "__main__":
    main()
