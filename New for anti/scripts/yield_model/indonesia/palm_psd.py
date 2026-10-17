"""
Indonesian palm oil from USDA PSD: a label with year-to-year signal.

Usage: python3 -m indonesia.palm_psd fetch      # PSD slice -> training/psd_palm_indonesia.csv
       python3 -m indonesia.palm_psd evaluate   # climate-vs-trend test, both labels

Why: the oil-palm model trains on FAOSTAT "Oil palm fruit", whose recent
yield and area are flagged estimated/imputed. That series is close to a
straight line (latest trend error 0.5%), so no weather variable can explain
anything in it -- the climate candidate scored 0.0% against the trend. The
market quantity is crude palm oil, and USDA FAS PSD publishes Indonesia's
production and harvested area each month with the current marketing year
included. Its dips line up with the known El Nino droughts (2015/16, 2019/20,
2023/24), which is the signal the dry-season features are meant to carry.

Year mapping: PSD market year M for Indonesian palm oil runs October M to
September M+1, so most of it falls in calendar year M+1; it is labelled M+1
here, the year whose dry-season lags (June-October of M and M-1) the existing
features describe.

The evaluation runs indonesia.model.train_target on both labels with the same
features, so the two can be compared directly. Two anomaly baselines are
reported: the package's 20 prior seasons, and an expanding prior window from
10 seasons. Both use only earlier years.

Writes training/palm_psd_experiment.json.
"""

import io
import json
import os
import sys
import urllib.request
import zipfile

import numpy as np
import pandas as pd

from . import climate as C
from .model import train_target
from .regions import BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
PSD_CSV = os.path.join(TRAINING, "psd_palm_indonesia.csv")
URL = "https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip"


def log(msg):
    print(f"[palm-psd] {msg}", flush=True)


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r:
        blob = r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(name) as f:
            d = pd.read_csv(f, low_memory=False)
    d = d[(d.Country_Name == "Indonesia") & (d.Commodity_Description == "Oil, Palm")]
    log(f"attributes: {sorted(d.Attribute_Description.unique())}")
    keep = ["Market_Year", "Calendar_Year", "Month", "Attribute_Description",
            "Unit_Description", "Value"]
    d = d[keep].sort_values(["Attribute_Description", "Market_Year"])
    d.to_csv(PSD_CSV, index=False)
    log(f"wrote {len(d)} rows, market years {d.Market_Year.min()}-{d.Market_Year.max()}")


def psd_labels():
    d = pd.read_csv(PSD_CSV)
    wide = d.pivot_table(index="Market_Year", columns="Attribute_Description",
                         values="Value", aggfunc="last")
    out = pd.DataFrame({"year": wide.index + 1})
    out["psd_production_kt"] = wide["Production"].values
    out["psd_area_kha"] = wide["Area Harvested"].values
    out["psd_yield_t_ha"] = out.psd_production_kt / out.psd_area_kha
    return out[out.psd_production_kt > 0]


def evaluate():
    cfg = BY_KEY["indonesia_oil_palm"]
    t = pd.read_csv(os.path.join(TRAINING, "indonesia_oil_palm.csv"))
    raw = ["soil_dry_lag1", "soil_dry_lag2", "precip_dry_lag1", "vpd_dry_lag1",
           "solar_haze_lag1", "dry_spell_lag1"]
    base = t[["year", "oni_season"] + raw + ["yield_kg_ha", "production_tonnes"]].copy()
    base = base.sort_values("year").reset_index(drop=True)
    base["oni_lag2"] = base.oni_season.shift(1)
    base = base.merge(psd_labels(), on="year", how="left")
    report = {"label_years": {
        "faostat": [int(base.dropna(subset=['yield_kg_ha']).year.min()),
                    int(base.dropna(subset=['yield_kg_ha']).year.max())],
        "psd": [int(base.dropna(subset=['psd_production_kt']).year.min()),
                int(base.dropna(subset=['psd_production_kt']).year.max())]}}
    for anom_name, window, min_hist in (("prior20", 20, 20), ("expanding10", 60, 10)):
        f = C.trailing_anomalies(base, raw, window=window, min_history=min_hist)
        core = [c + "_anom" for c in cfg.core] + ["oni_season", "oni_lag2"]
        allf = [c + "_anom" for c in raw] + ["oni_season", "oni_lag2"]
        enso = ["oni_season", "oni_lag2"]
        sets = {"trend_only": [], "core": core, "all": allf, "enso": enso}
        for target in ("yield_kg_ha", "production_tonnes",
                       "psd_yield_t_ha", "psd_production_kt"):
            r = train_target(f, target, sets, min_train=10)
            if r is None:
                continue
            gate = r["climate_gate"]
            per_set = {}
            for name, v in r["validation"].items():
                fs = name.split("__")[0]
                if fs == "trend_only":
                    continue
                if fs not in per_set or v["recent_rmse"] < per_set[fs]["recent_rmse"]:
                    per_set[fs] = {"config": name, "recent_rmse": v["recent_rmse"],
                                   "skill_recent": v["skill_vs_trend"],
                                   "skill_all": 1 - v["rmse"] / v["baseline_rmse"],
                                   "n": v["n_folds"], "years": v["years"]}
            key = f"{anom_name}:{target}"
            report[key] = {"selected": r["configuration"],
                           "beats_trend": r["beats_trend"],
                           "climate_gate": gate,
                           "forecast_gate": r["forecast_gate"],
                           "best_per_feature_set": per_set}
            log(f"{key:34} seasons={gate['available_seasons']:2d} "
                f"cand={gate['candidate_configuration']} "
                f"skill={gate['candidate_skill_vs_trend'] if gate['candidate_skill_vs_trend'] is None else round(gate['candidate_skill_vs_trend'], 3)} "
                f"-> {gate['status']}; forecast {r['forecast_gate']['status']}")
            for fs, v in per_set.items():
                log(f"    {fs:6} {v['config']:28} n={v['n']} {v['years']} "
                    f"recent {v['skill_recent']:+.1%}  all {v['skill_all']:+.1%}")
    with open(os.path.join(TRAINING, "palm_psd_experiment.json"), "w") as fh:
        json.dump(report, fh, indent=2, default=float)


if __name__ == "__main__":
    {"fetch": fetch, "evaluate": evaluate}[sys.argv[1]]()
