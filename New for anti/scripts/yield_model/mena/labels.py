"""
Yield labels for MENA training tables.

T1 region-crops prefer FAOSTAT national wheat in
`training/labels_official/{key}.csv` when collect has fetched them.

Override schema: `year,yield_kg_ha` plus optional `label_source`, `label_note`.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OFFICIAL_DIR = os.path.join(HERE, "training", "labels_official")

LABEL_SOURCE_SYNTHETIC = "provisional_synthetic_climate_response"
LABEL_SOURCE_OFFICIAL = "official_csv_override"
LABEL_SOURCE_FAOSTAT = "faostat_national_wheat"


def load_official(key: str) -> pd.DataFrame | None:
    path = os.path.join(OFFICIAL_DIR, f"{key}.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    if "year" not in df.columns or "yield_kg_ha" not in df.columns:
        raise ValueError(f"{path} needs year,yield_kg_ha")
    cols = ["year", "yield_kg_ha"]
    for optional in ("label_source", "label_note"):
        if optional in df.columns:
            cols.append(optional)
    out = df[cols].copy()
    if "label_source" not in out.columns:
        out["label_source"] = LABEL_SOURCE_OFFICIAL
    else:
        out["label_source"] = out["label_source"].fillna(LABEL_SOURCE_OFFICIAL)
    return out


def synthetic_yields(cfg, feature_df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """
    Build a demo yield series from the guide's own stress features plus noise.

    Intentionally imperfect so ridge skill measures scaffold consistency, not
    a self-fulfilling simulator.
    """
    rng = np.random.default_rng(seed + abs(hash(cfg.key)) % 10_000)
    years = feature_df.year.values.astype(int)
    n = len(years)

    t0 = years.min()
    trend = cfg.yield_base_kg_ha * np.exp(cfg.yield_growth * (years - t0))

    def z(col, default=0.0):
        if col not in feature_df.columns:
            return np.full(n, default)
        s = feature_df[col].astype(float)
        mu, sd = s.mean(), s.std()
        if sd is None or sd == 0 or np.isnan(sd):
            return np.zeros(n)
        return ((s - mu) / sd).fillna(0.0).values

    if cfg.key.startswith("egypt"):
        stress = (0.12 * z("wd_eff") + 0.10 * z("salt_proxy")
                  + 0.06 * z("edd_heading") + 0.05 * z("oni_ndj")
                  - 0.04 * z("nile_inflow_proxy"))
    else:
        stress = (0.14 * z("spei_like_6") + 0.10 * z("wd_gs")
                  + 0.08 * z("edd_heading") + 0.06 * z("oni_ndj")
                  + 0.05 * z("iod_ond") - 0.04 * z("y_w_proxy"))

    crisis = np.zeros(n)
    for y, hit in ((2016, 0.10), (2020, 0.08), (1998, 0.06)):
        crisis[years == y] += hit

    noise = rng.normal(0.0, 0.045, size=n)
    mult = np.clip(1.0 - 0.10 * stress - crisis + noise, 0.55, 1.25)
    yld = trend * mult

    return pd.DataFrame({
        "year": years,
        "yield_kg_ha": yld,
        "label_source": LABEL_SOURCE_SYNTHETIC,
    })


def attach_labels(cfg, feature_df: pd.DataFrame) -> pd.DataFrame:
    official = load_official(cfg.key)
    if official is not None:
        return feature_df.merge(official, on="year", how="left")
    labels = synthetic_yields(cfg, feature_df)
    return feature_df.merge(labels, on="year", how="left")
