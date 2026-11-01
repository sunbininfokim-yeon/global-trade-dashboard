"""
MODIS NDVI correction for the China models: australia.ndvi with China's sites,
windows and trend base.

Usage: python3 -m china.ndvi [--shard K --shards N --out FILE]
       python3 -m china.ndvi merge FILE [FILE ...]
       python3 -m china.ndvi backtest

None of the China weather models beats a trend (see README), so the base the
NDVI has to improve on is the trend alone: the best trend-only form from the
model's own validation, refit each season on earlier seasons only. NDVI looks
at the crop rather than at the weather, which is the one route the README
left open. The labels are still national USDA estimates, so this can only
work where the region is most of the crop and the estimate actually moves.

Fixed before any NDVI was read:

- configs: the four yield targets. south_china_rice_area is an area target
  (NDVI does not count hectares) and shandong_vegetables is greenhouse output
  (MODIS sees plastic), so both are left out.
- windows, within the harvest year: winter wheat 15 Mar-15 May (jointing to
  grain fill; harvest is early June), rice and the Northeast summer crops
  July-August (heading / silking to grain fill). "half" is the first half.
- sites: every weather point is a city, so each moves 20-40 km onto the
  cropland around it (paddy plains for rice, the plain for wheat and the
  Northeast). Nenjiang is a small town in its farmland and stays.

The test and the switch-on rule are australia.ndvi's, unchanged.
"""

import os

import numpy as np
import pandas as pd

from australia import ndvi as N

WHEAT = ((3, 15), (5, 15))
SUMMER = ((7, 1), (8, 31))

WINDOWS = {
    "henan_wheat": WHEAT,
    "yangtze_rice": SUMMER,
    "northeast_corn": SUMMER,
    "northeast_soy": SUMMER,
}

SITES = {
    # Northeast
    "Harbin": (46.10, 126.80),
    "Jiamusi": (46.85, 130.70),
    "Qiqihar": (47.60, 124.30),
    "Changchun": (43.75, 125.05),
    "Siping": (43.30, 124.20),
    "Shenyang": (42.00, 123.00),
    # Huang-Huai-Hai plain
    "Zhengzhou": (34.85, 114.10),
    "Zhoukou": (33.75, 114.95),
    "Shangqiu": (34.55, 115.95),
    "Xinxiang": (35.25, 114.20),
    "Jining": (35.55, 116.30),
    "Handan": (36.55, 114.85),
    "Bengbu": (33.10, 117.20),
    "Xuzhou": (34.40, 116.85),
    # Yangtze paddy plains
    "Changsha": (28.75, 112.55),
    "Nanchang": (28.55, 116.20),
    "Wuhan": (30.45, 113.55),
    "Hefei": (32.05, 117.00),
    "Nanjing": (32.75, 119.75),
    "Chengdu": (30.80, 103.75),
}


class China(N.Country):
    def window_for(self, cfg):
        return WINDOWS[cfg.key]

    def base_forecasts(self, cfg):
        return trend_base(cfg)


def china():
    from .regions import BY_KEY
    return China("china", [BY_KEY[k] for k in WINDOWS], SITES, SUMMER)


def trend_base(cfg):
    """year -> (truth, trend forecast from earlier seasons), and False (the
    weather model is never the base here: it does not beat the trend)."""
    import json

    from . import train as T
    with open(os.path.join(T.MODELS, f"{cfg.key}.json"), encoding="utf-8") as f:
        art = json.load(f)
    fwd = {k: v for k, v in art["validation"].items() if k.endswith("_forward")}
    best = min(fwd.values(), key=lambda v: v["baseline_rmse"])
    degree, window = best["degree"], best["window"]
    frame = pd.read_csv(os.path.join(T.TRAINING, f"{cfg.key}.csv")).dropna(subset=["target"])
    years = frame.year.values.astype(float)
    values = frame.target.values.astype(float)
    out = {}
    for y, v in zip(years, values):
        prior = years < y
        if y < 2001 or prior.sum() < T.MIN_TRAIN:
            continue
        trend = T.fit_trend(years[prior], values[prior], degree, window)
        out[int(y)] = (float(v), float(np.exp(trend(y))))
    return out, False


def apply(row, adj):
    """Re-centre a China row on trend x NDVI. The published point is the
    trend times a weather effect the model cannot back up, so a live NDVI
    correction replaces that effect rather than stacking on it."""
    if not adj:
        return row
    point = float(row["trend"]) * float(np.exp(adj["log_adjustment"]))
    shift = point - float(row["point"])
    row["point"] = round(point, 1)
    for key in ("range_68", "range_95"):
        row[key] = [round(v + shift, 1) for v in row[key]]
    row["presentation"] = "trend x NDVI"
    row["ndvi"] = adj
    return row


if __name__ == "__main__":
    N.cli(china())
