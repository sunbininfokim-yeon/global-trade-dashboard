"""
Throwaway experiment: does modelling states individually beat modelling the
production-weighted average?

Not production code -- this only measures, it changes nothing.

Three designs, all scored the same way: forward-chaining, and the error is
always on the production-weighted Corn Belt aggregate, since that is the
number the dashboard reports.

  A) aggregate  - current approach. One row per year (34), target is the
                  weighted-average yield.
  B) panel      - one row per state-year (8 x 34 = 272). Each state gets its
                  own technology trend; a single weather model is shared
                  across states. Predictions are re-aggregated by weight.
  C) per-state  - a separate weather model per state, then re-aggregated.
"""

import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, "/Users/yeoninair/Documents/New for anti/New for anti/scripts/yield_model")
from collect_us_cornbelt import (  # noqa: E402
    CLIMATOLOGY_YEARS, CROPS, STATES, END_YEAR, START_YEAR,
    load_oni, growing_season_oni, nass_yields, power_weather,
    season_features, to_anomalies,
)

ALPHAS = np.logspace(-2, 4, 40)
CORE = ["july_edd_anom", "julaug_edd_anom", "julaug_vpd_anom",
        "julaug_precip_anom", "preseason_precip_anom", "julaug_soil_anom",
        "oni_growing"]


def build_panel(crop):
    """One row per state-year, with anomaly features and that state's yield."""
    spec = CROPS[crop]
    oni = load_oni()
    rows = []
    for st in STATES:
        wx = power_weather(st)
        raw = {y: f for y in range(START_YEAR, END_YEAR + 1)
               if (f := season_features(wx, y, spec))}
        anoms = to_anomalies(raw)
        ys = nass_yields(crop, st).set_index("year")["yield"].to_dict()
        for y, a in anoms.items():
            if y not in ys:
                continue
            r = {k: v for k, v in a.items() if k != "year"}
            r.update({"year": y, "state": st["code"], "weight": st["weight"],
                      "yield": ys[y], "oni_growing": growing_season_oni(oni, y)})
            rows.append(r)
    return pd.DataFrame(rows).dropna(subset=["yield"])


def agg_truth(panel):
    """Production-weighted aggregate yield per year."""
    g = panel.groupby("year").apply(
        lambda d: np.average(d["yield"], weights=d.weight), include_groups=False)
    return g.to_dict()


def score(name, truth, pred, base):
    truth, pred, base = np.array(truth), np.array(pred), np.array(base)
    rmse = float(np.sqrt(np.mean((truth - pred) ** 2)))
    brmse = float(np.sqrt(np.mean((truth - base) ** 2)))
    dt, dp = truth - base, pred - base
    ss = float(np.sum((dt - dp) ** 2)); st = float(np.sum((dt - dt.mean()) ** 2))
    print(f"  {name:12} RMSE={rmse:6.2f}  skill vs trend={1 - rmse / brmse:+6.1%}  "
          f"detrended R2={1 - ss / st:+.3f}")
    return rmse


def run(crop, feats, min_train=20):
    panel = build_panel(crop)
    years = sorted(panel.year.unique())
    truth_map = agg_truth(panel)
    feats = [f for f in feats if f in panel.columns]
    panel = panel.dropna(subset=feats)

    res = {k: {"truth": [], "pred": [], "base": []} for k in ("A", "B", "C")}

    for ty in years:
        tr_years = [y for y in years if y < ty]
        if len(tr_years) < min_train:
            continue

        cur = panel[panel.year == ty]
        if cur.empty:
            continue
        w = cur.weight.values
        truth = truth_map[ty]

        # ---- per-state trends, shared by B and C, and aggregated for A ----
        state_trend_now, state_resid_hist = {}, {}
        for st in STATES:
            h = panel[(panel.state == st["code"]) & (panel.year < ty)]
            if len(h) < 10:
                continue
            k, b = np.polyfit(h.year, h["yield"], 1)
            state_trend_now[st["code"]] = k * ty + b
            state_resid_hist[st["code"]] = h["yield"].values - (k * h.year.values + b)

        # ---------------- A: aggregate ----------------
        agg_hist = pd.DataFrame({
            "year": tr_years,
            "y": [truth_map[y] for y in tr_years],
        })
        aggX_hist = (panel[panel.year < ty]
                     .groupby("year")
                     .apply(lambda d: pd.Series(
                         {f: np.average(d[f], weights=d.weight) for f in feats}),
                         include_groups=False)
                     .loc[tr_years])
        ka, ba = np.polyfit(agg_hist.year, agg_hist.y, 1)
        base_a = ka * ty + ba
        sc = StandardScaler().fit(aggX_hist.values)
        m = RidgeCV(alphas=ALPHAS).fit(sc.transform(aggX_hist.values),
                                       agg_hist.y.values - (ka * agg_hist.year.values + ba))
        x_now = np.array([[np.average(cur[f], weights=w) for f in feats]])
        pred_a = base_a + float(m.predict(sc.transform(x_now))[0])
        res["A"]["truth"].append(truth); res["A"]["pred"].append(pred_a); res["A"]["base"].append(base_a)

        # ---------------- B: pooled panel, shared weather model ----------------
        hist = panel[panel.year < ty]
        hist = hist[hist.state.isin(state_resid_hist)]
        resid = np.concatenate([state_resid_hist[s] for s in
                                [st["code"] for st in STATES if st["code"] in state_resid_hist]])
        Xb = np.vstack([hist[hist.state == st["code"]][feats].values
                        for st in STATES if st["code"] in state_resid_hist])
        scb = StandardScaler().fit(Xb)
        mb = RidgeCV(alphas=ALPHAS).fit(scb.transform(Xb), resid)

        pb, bb, ww = [], [], []
        for _, row in cur.iterrows():
            if row.state not in state_trend_now:
                continue
            r = float(mb.predict(scb.transform(row[feats].values.reshape(1, -1)))[0])
            pb.append(state_trend_now[row.state] + r)
            bb.append(state_trend_now[row.state])
            ww.append(row.weight)
        if pb:
            res["B"]["truth"].append(truth)
            res["B"]["pred"].append(float(np.average(pb, weights=ww)))
            res["B"]["base"].append(float(np.average(bb, weights=ww)))

        # ---------------- C: independent model per state ----------------
        pc, bc, wc = [], [], []
        for _, row in cur.iterrows():
            s = row.state
            if s not in state_trend_now:
                continue
            h = panel[(panel.state == s) & (panel.year < ty)]
            scc = StandardScaler().fit(h[feats].values)
            mc = RidgeCV(alphas=ALPHAS).fit(scc.transform(h[feats].values), state_resid_hist[s])
            r = float(mc.predict(scc.transform(row[feats].values.reshape(1, -1)))[0])
            pc.append(state_trend_now[s] + r)
            bc.append(state_trend_now[s])
            wc.append(row.weight)
        if pc:
            res["C"]["truth"].append(truth)
            res["C"]["pred"].append(float(np.average(pc, weights=wc)))
            res["C"]["base"].append(float(np.average(bc, weights=wc)))

    print(f"=== {crop.upper()} ({len(res['A']['truth'])} test seasons, "
          f"{len(feats)} features) ===")
    labels = {"A": "aggregate", "B": "panel", "C": "per-state"}
    for k in ("A", "B", "C"):
        if res[k]["truth"]:
            score(labels[k], res[k]["truth"], res[k]["pred"], res[k]["base"])
    print()


if __name__ == "__main__":
    for crop in ("corn", "soybeans"):
        run(crop, CORE)
