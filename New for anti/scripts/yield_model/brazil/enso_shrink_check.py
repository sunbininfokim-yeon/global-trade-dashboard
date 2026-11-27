"""Should the El Nino analog shift shrink when few seasons carry it?

Run: python -m brazil.enso_shrink_check  (writes condition/enso_shrink_check.json)

Tested 2026-11-26 because 2027 sowing Nino3.4 (+2.59) is beyond the record and
the shift rests on ~2.8 effective seasons (1998, 2016, 2024).

Variants, forward chained on the published trend form:
  none  shift as published
  k1/k2 shift * n_eff / (n_eff + k)   (pull toward zero when evidence is thin)
  beyond_half  halve the shift only when Nino3.4 is outside the past record

Result: every shrink lowers skill in both regions that earn the shift
(MT soja +5.1% -> +4.1% at k2, MT milho +9.5% -> +7.3%) and helps nowhere
that matters. The Brazil backtest has no season that was beyond its own
high record; India east rice has one (2015: Nino3.4 1.27 vs record 1.19),
where the shift said -6% and the crop came in -19% vs trend -- shrinking
would have been further off. So the point is left unshrunk and the card
says how few seasons it rests on instead.
"""
import json
import os

import numpy as np
import pandas as pd

from brazil import enso_analog as E
from brazil.train import fit_trend

VARIANTS = {
    "none": lambda s, info, past, now: s,
    "k1": lambda s, info, past, now: s * info["effective_seasons"] / (info["effective_seasons"] + 1),
    "k2": lambda s, info, past, now: s * info["effective_seasons"] / (info["effective_seasons"] + 2),
    "beyond_half": lambda s, info, past, now: s * (0.5 if now > past.max() or now < past.min() else 1),
}


def score(key, shrink, series):
    df = pd.read_csv(os.path.join(E.HERE, "training", f"{key}.csv")).dropna(subset=["yield_kg_ha"])
    crop = key.rsplit("_", 1)[-1]
    df["n34"] = [E.sowing_nino34(series, int(y), crop) for y in df.year]
    df = df.dropna(subset=["n34"]).reset_index(drop=True)
    y, Y, n = df.year.values.astype(float), df.yield_kg_ha.values.astype(float), df.n34.values
    degree, window = E.model_trend(key)
    truth, base, adj, beyond = [], [], [], []
    for i, t in enumerate(y):
        tr = y < t
        if tr.sum() < E.DIRECT_MIN_PAST:
            continue
        s, info = E.direct_adjust(y[tr], Y[tr], n[tr], n[i], degree, window)
        s = shrink(s, info, n[tr], n[i])
        b = float(np.exp(fit_trend(y[tr], Y[tr], degree, window)(t)))
        truth.append(Y[i]); base.append(b); adj.append(b * np.exp(s))
        if n[i] > n[tr].max() or n[i] < n[tr].min():
            beyond.append(int(t))
    truth, base, adj = map(np.array, (truth, base, adj))

    def sk(sl=slice(None)):
        return round(float(1 - np.sqrt(np.mean((truth[sl] - adj[sl]) ** 2))
                           / np.sqrt(np.mean((truth[sl] - base[sl]) ** 2))), 4)

    return {"skill": sk(), "skill_last10": sk(slice(-10, None)), "beyond_record_seasons": beyond}


def main():
    series = E.load_nino34()
    out = {key: {v: score(key, f, series) for v, f in VARIANTS.items()}
           for key in ("mato_grosso_soja", "mato_grosso_milho", "parana_soja", "matopiba_soja")}
    path = os.path.join(E.HERE, "condition", "enso_shrink_check.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"decision": "no shrink; card shows effective seasons", "regions": out}, f, indent=1)
    for key, r in out.items():
        print(key, {v: (x["skill"], x["skill_last10"]) for v, x in r.items()})


if __name__ == "__main__":
    main()
