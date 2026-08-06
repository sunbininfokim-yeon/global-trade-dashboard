"""
Mekong WS rice — province × year panel + significance diagnostics.

Builds climate features at each of 13 Mekong province points, joins QC'd
Đông Xuân yield labels, then reports:

  · Province FE OLS (within) for climate predictors
  · Forward CV skill vs province-specific linear trend
  · Power caveats (short T)

Usage (from scripts/yield_model):

    python3 -m vietnam.analyze_provincial_panel

Writes (local only — do not commit unless explicitly requested):
  training/labels_official/mekong_rice_ws_provincial_dong_xuan.csv  (QC refresh)
  training/mekong_rice_ws_provincial_panel.csv
  models/mekong_rice_ws_provincial_panel_stats.json
  PANEL_SIGNIFICANCE_KO.md
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.preprocessing import StandardScaler

from . import climate as C
from . import collect as COL
from .regions import (
    COAST_KM_THRESHOLD,
    MEKONG_ALL_PROVINCE_POINTS,
    MEKONG_UPSTREAM_POINTS,
    WS_DRY,
    _mekong_rice,
)

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
LABELS = os.path.join(TRAINING, "labels_official")
MODELS = os.path.join(HERE, "models")
MTN_URL = "https://mtnongnghiep.com/index.php/du-lieu-trong-trot/"

# Theory-expected signs for climate → yield (log residual / within)
THEORY_SIGN = {
    "spei4_ws_min": "+",   # wetter (less drought) → higher yield
    "spi_ws": "+",
    "oni_lag2": "-",       # El Niño → salt/drought stress
    "q_upstream_proxy": "+",
    "salt_proxy": "-",
    "salt_coastal_belt": "-",
    "precip_dry_ws": "+",
    "wd_dry_ws": "-",
    "heat_days_35_ws": "-",
}

PRED_COLS = [
    "spei4_ws_min", "spi_ws", "oni_lag2", "q_upstream_proxy",
    "salt_proxy", "salt_coastal_belt", "precip_dry_ws", "wd_dry_ws",
    "heat_days_35_ws",
]


def log(msg):
    print(f"[prov-panel] {msg}", flush=True)


def _parse_num(x):
    if x is None:
        return None
    s = str(x).strip().replace(",", "").replace(" ", "")
    if s in ("", "-", "—", "n/a", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def scrape_mtn_mekong() -> pd.DataFrame:
    """Parse mtnongnghiep planting table for Mekong-13 Đông Xuân yields."""
    from html.parser import HTMLParser
    import re
    import urllib.request

    log(f"fetching {MTN_URL}")
    req = urllib.request.Request(MTN_URL, headers={"User-Agent": "yield-model-vietnam/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")

    class T(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_tr = False
            self.in_td = False
            self.rows = []
            self.cur = []
            self.cell = ""

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.in_tr = True
                self.cur = []
            elif tag in ("td", "th") and self.in_tr:
                self.in_td = True
                self.cell = ""

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.in_td:
                self.cur.append(self.cell.strip())
                self.in_td = False
            elif tag == "tr" and self.in_tr:
                if self.cur:
                    self.rows.append(self.cur)
                self.in_tr = False

        def handle_data(self, data):
            if self.in_td:
                self.cell += data

    p = T()
    p.feed(html)
    header = p.rows[0]
    i_year = header.index("Năm")
    i_area = next(i for i, c in enumerate(header) if "Diện tích lúa đông xuân" in c)
    i_yld = next(i for i, c in enumerate(header) if "Năng suất lúa đông xuân" in c)
    i_prod = next(i for i, c in enumerate(header) if "Sản lượng lúa đông xuân" in c)

    norm = {
        "An Giang": "An Giang", "Bạc Liêu": "Bac Lieu", "Bac Lieu": "Bac Lieu",
        "Bến Tre": "Ben Tre", "Ben Tre": "Ben Tre", "Cà Mau": "Ca Mau",
        "Ca Mau": "Ca Mau", "Cần Thơ": "Can Tho", "Can Tho": "Can Tho",
        "Đồng Tháp": "Dong Thap", "Dong Thap": "Dong Thap",
        "Hậu Giang": "Hau Giang", "Hau Giang": "Hau Giang",
        "Kiên Giang": "Kien Giang", "Kien Giang": "Kien Giang",
        "Long An": "Long An", "Sóc Trăng": "Soc Trang", "Soc Trang": "Soc Trang",
        "Tiền Giang": "Tien Giang", "Tien Giang": "Tien Giang",
        "Trà Vinh": "Tra Vinh", "Tra Vinh": "Tra Vinh",
        "Vĩnh Long": "Vinh Long", "Vinh Long": "Vinh Long",
    }

    rows = []
    for r in p.rows[1:]:
        if len(r) <= max(i_year, i_area, i_yld, i_prod):
            continue
        prov = r[0].strip()
        if prov not in norm:
            continue
        year = _parse_num(r[i_year])
        yld = _parse_num(r[i_yld])
        area = _parse_num(r[i_area])
        prod = _parse_num(r[i_prod])
        if year is None or yld is None:
            continue
        rows.append({
            "province": norm[prov],
            "year": int(year),
            "yield_ta_ha": float(yld),
            "yield_kg_ha": float(yld) * 100.0,
            "area_thous_ha": area,
            "production_thous_t": prod,
            "source": "mtnongnghiep.com provincial Đông Xuân (GSO-style)",
        })
    return pd.DataFrame(rows)


def apply_yield_qc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag / drop obviously broken yield cells.

    Area columns on MTN are often corrupted for 2017–2020 (prod ≠ area×yield/10);
    we still keep yield when it is in a plausible Mekong WS band.
    """
    out = df.copy()
    notes = []
    keep = []
    for _, row in out.iterrows():
        y = row.yield_ta_ha
        note = ""
        ok = True
        if y < 40.0 or y > 85.0:
            ok = False
            note = f"yield_ta_ha={y} outside [40,85] plausible WS band"
        # Explicit known garbage cells
        if row.province == "Ben Tre" and int(row.year) == 2020 and y < 10:
            ok = False
            note = "Ben Tre 2020 yield 0.4 — MTN cell corrupt"
        if row.province == "Ca Mau" and int(row.year) == 2017 and y <= 30:
            ok = False
            note = "Ca Mau 2017 yield 30 + prod inconsistent — exclude"
        area = row.area_thous_ha
        prod = row.production_thous_t
        area_ok = False
        if area and prod and area > 0 and y > 0:
            implied = area * y / 10.0
            ratio = prod / implied if implied else np.nan
            area_ok = bool(0.7 <= ratio <= 1.3) if not np.isnan(ratio) else False
        keep.append(ok)
        notes.append(note)
        # store
    out["yield_qc_pass"] = keep
    out["qc_note"] = notes
    out["area_qc_pass"] = [
        bool(
            r.area_thous_ha and r.production_thous_t and r.area_thous_ha > 0
            and 0.7 <= (r.production_thous_t / (r.area_thous_ha * r.yield_ta_ha / 10.0)) <= 1.3
        ) if (r.area_thous_ha and r.yield_ta_ha) else False
        for _, r in out.iterrows()
    ]
    return out


def build_climate_panel(years: list[int]) -> pd.DataFrame:
    """Per-province POWER climate features for requested harvest years."""
    oni = COL.load_oni()
    dailies = {}
    for p in MEKONG_ALL_PROVINCE_POINTS:
        log(f"weather {p['name']}")
        dailies[p["name"]] = COL.point_weather(p)
    dailies_up = {p["name"]: COL.point_weather(p) for p in MEKONG_UPSTREAM_POINTS}

    rows = []
    for p in MEKONG_ALL_PROVINCE_POINTS:
        for year in years:
            feats = _mekong_rice(dailies[p["name"]], year, p)
            feats["province"] = p["name"]
            feats["year"] = year
            feats["oni_lag2"] = COL.oni_lag2(oni, year)
            feats["oni_djf"] = COL.oni_djf(oni, year)
            feats.update(COL.upstream_q_features(dailies_up, year))
            oni_s = feats.get("oni_lag2")
            if oni_s is None:
                oni_s = feats.get("oni_djf") or 0.0
            feats = COL.apply_salt_with_oni(
                feats, oni_s, q_upstream=feats.get("q_upstream_proxy"))
            # coastal-belt salt after ONI-aware rebuild
            coast = float(p.get("coast_km", 50.0))
            salt = feats.get("salt_proxy", 0.0)
            feats["salt_coastal_belt"] = (
                float(salt) if coast <= COAST_KM_THRESHOLD else 0.0)
            rows.append(feats)
    return pd.DataFrame(rows)


def _ols_with_cluster_se(y, X, clusters):
    """
    OLS + province-clustered (CRVE) SEs. No statsmodels dependency.
    X must include intercept column if wanted.
    """
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    n, k = X.shape
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta
    # Cluster-robust meat
    meat = np.zeros((k, k))
    groups = defaultdict(list)
    for i, g in enumerate(clusters):
        groups[g].append(i)
    G = len(groups)
    for idx in groups.values():
        Xi = X[idx]
        ri = resid[idx]
        score = Xi.T @ ri
        meat += np.outer(score, score)
    # Bread
    XtX_inv = np.linalg.pinv(X.T @ X)
    # small-sample cluster correction
    scale = (G / (G - 1)) * ((n - 1) / (n - k)) if G > 1 and n > k else 1.0
    V = scale * XtX_inv @ meat @ XtX_inv
    se = np.sqrt(np.clip(np.diag(V), 0, None))
    # two-sided normal p ≈ erfc(|z|/√2); T short → treat cautiously
    from math import erfc, sqrt
    z = np.divide(beta, se, out=np.full_like(beta, np.nan), where=se > 0)
    p = np.array([
        erfc(abs(float(zi)) / sqrt(2.0)) if np.isfinite(zi) else float("nan")
        for zi in z
    ])
    return beta, se, p, resid, G


def province_fe_ols(panel: pd.DataFrame, preds: list[str]):
    """Within (province demean) OLS + cluster SE by province."""
    df = panel.dropna(subset=preds + ["yield_kg_ha", "province", "year"]).copy()
    df["log_y"] = np.log(df.yield_kg_ha.astype(float))
    # Also demean year common shock optionally via two-way FE lite:
    # first demean province, then demean year on residuals — Frisch-Waugh for TWFE
    # Simple province FE:
    for col in ["log_y"] + preds:
        df[f"dm_{col}"] = df[col] - df.groupby("province")[col].transform("mean")

    y = df["dm_log_y"].values
    X = df[[f"dm_{c}" for c in preds]].values
    # no intercept after demeaning
    beta, se, p, resid, G = _ols_with_cluster_se(y, X, df.province.values)
    # R2 within
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    coefs = []
    for i, name in enumerate(preds):
        sign_ok = None
        th = THEORY_SIGN.get(name)
        if th == "+" and beta[i] > 0:
            sign_ok = True
        elif th == "-" and beta[i] < 0:
            sign_ok = True
        elif th in ("+", "-"):
            sign_ok = False
        coefs.append({
            "feature": name,
            "coef": float(beta[i]),
            "se_cluster_province": float(se[i]),
            "p_approx": float(p[i]),
            "theory_sign": th,
            "sign_matches_theory": sign_ok,
            "ci95": [float(beta[i] - 1.96 * se[i]), float(beta[i] + 1.96 * se[i])],
        })
    return {
        "n": int(len(df)),
        "n_provinces": int(df.province.nunique()),
        "n_years": int(df.year.nunique()),
        "years": sorted(int(y) for y in df.year.unique()),
        "within_r2": float(r2),
        "cluster_G": int(G),
        "coefs": coefs,
    }


def forward_cv_vs_province_trend(panel: pd.DataFrame, preds: list[str],
                                 min_train_years: int = 4):
    """
    Forward year CV: train on years < t, predict all provinces in year t.
    Baseline = province-specific linear trend fitted on train years only.
    Model = trend + ridge on climate residuals (pooled after province demean
    in train, applied to test).
    """
    df = panel.dropna(subset=preds + ["yield_kg_ha"]).copy()
    years = sorted(df.year.unique())
    truth, pred_m, pred_b, used = [], [], [], []

    for t in years:
        train = df[df.year < t]
        test = df[df.year == t]
        if train.year.nunique() < min_train_years or test.empty:
            continue

        # province trends
        trend_pred = {}
        for prov, g in train.groupby("province"):
            if len(g) < 2:
                # fallback global mean growth
                lr = LinearRegression().fit(
                    train.year.values.reshape(-1, 1),
                    np.log(train.yield_kg_ha.values))
            else:
                lr = LinearRegression().fit(
                    g.year.values.reshape(-1, 1),
                    np.log(g.yield_kg_ha.values))
            trend_pred[prov] = lr

        # residual ridge on demeaned climate
        tr = train.copy()
        tr["log_y"] = np.log(tr.yield_kg_ha)
        tr["trend"] = [
            float(trend_pred[p].predict([[y]])[0])
            for p, y in zip(tr.province, tr.year)
        ]
        tr["resid"] = tr.log_y - tr.trend
        # province demean features + resid for FE-like
        for c in preds:
            tr[f"dm_{c}"] = tr[c] - tr.groupby("province")[c].transform("mean")
        tr["dm_resid"] = tr.resid - tr.groupby("province")["resid"].transform("mean")

        Xtr = tr[[f"dm_{c}" for c in preds]].values
        ytr = tr["dm_resid"].values
        scaler = StandardScaler().fit(Xtr)
        model = RidgeCV(alphas=np.logspace(-3, 3, 13)).fit(
            scaler.transform(Xtr), ytr)

        for _, row in test.iterrows():
            prov = row.province
            if prov not in trend_pred:
                continue
            base_log = float(trend_pred[prov].predict([[row.year]])[0])
            # demean features using train province means
            means = train[train.province == prov][preds].mean()
            if means.isna().any():
                continue
            x = (row[preds].values.astype(float) - means.values.astype(float))
            adj = float(model.predict(scaler.transform(x.reshape(1, -1)))[0])
            # add back train residual mean for province (≈0 after demean)
            truth.append(float(row.yield_kg_ha))
            pred_m.append(float(np.exp(base_log + adj)))
            pred_b.append(float(np.exp(base_log)))
            used.append(int(row.year))

    if not truth:
        return None
    truth = np.array(truth)
    pred_m = np.array(pred_m)
    pred_b = np.array(pred_b)
    rmse_m = float(np.sqrt(np.mean((truth - pred_m) ** 2)))
    rmse_b = float(np.sqrt(np.mean((truth - pred_b) ** 2)))
    skill = 1 - rmse_m / rmse_b if rmse_b > 0 else float("nan")
    return {
        "n_fold_obs": int(len(truth)),
        "years_evaluated": sorted(set(used)),
        "rmse_model": rmse_m,
        "rmse_province_trend": rmse_b,
        "skill_vs_province_trend": float(skill),
        "mae_model": float(np.mean(np.abs(truth - pred_m))),
        "mae_trend": float(np.mean(np.abs(truth - pred_b))),
    }


def coverage_table(labels: pd.DataFrame) -> dict:
    years = sorted(labels.year.unique())
    provs = sorted(labels.province.unique())
    mat = {}
    for p in provs:
        mat[p] = {}
        for y in years:
            sub = labels[(labels.province == p) & (labels.year == y)]
            if sub.empty:
                mat[p][str(y)] = "—"
            elif not bool(sub.iloc[0].yield_qc_pass):
                mat[p][str(y)] = "drop"
            else:
                mat[p][str(y)] = "ok"
    return {"years": [int(y) for y in years], "provinces": provs, "cells": mat}


def write_ko_report(path, cov, fe, cv, n_raw, n_qc):
    lines = []
    lines.append("# Mekong WS 성단위 패널 — 유의성 판단 (로컬)")
    lines.append("")
    lines.append("**커밋/푸시 없음** — 분석 산출물만 로컬 작성.")
    lines.append("")
    lines.append("## 1. 패널 커버리지")
    lines.append("")
    lines.append(f"- 출처: [mtnongnghiep.com trồng trọt]({MTN_URL}) "
                 "provincial Đông Xuân (GSO-style). GSO V0617 API 미노출 · "
                 "연감 PDF 자동추출은 이번 세션에서 차단됨.")
    lines.append(f"- 원본 province-years: **{n_raw}** → QC 통과: **{n_qc}**")
    lines.append(f"- 연도: {cov['years'][0]}–{cov['years'][-1]} (T={len(cov['years'])})")
    lines.append(f"- 성: Mekong 13 ({len(cov['provinces'])})")
    lines.append("")
    lines.append("| province | " + " | ".join(str(y) for y in cov["years"]) + " |")
    lines.append("|---| " + " | ".join(["---"] * len(cov["years"])) + " |")
    for p in cov["provinces"]:
        cells = [cov["cells"][p][str(y)] for y in cov["years"]]
        lines.append(f"| {p} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("`drop` = yield QC 실패 (비현실 수율/오염 셀). `—` = 원천 결측.")
    lines.append("")

    # Verdict
    skill = (cv or {}).get("skill_vs_province_trend")
    theory_hits = sum(1 for c in fe["coefs"] if c["sign_matches_theory"] is True)
    theory_n = sum(1 for c in fe["coefs"] if c["sign_matches_theory"] is not None)
    sig05 = [c["feature"] for c in fe["coefs"] if c["p_approx"] < 0.05]
    sig10 = [c["feature"] for c in fe["coefs"] if c["p_approx"] < 0.10]

    if skill is not None and skill > 0.05 and len(sig10) >= 2:
        verdict = "조건부로 가능"
        reason = ("패널 n은 확보됐으나 T가 짧아 계수 유의성은 약하고, "
                  "CV skill이 소폭 양수인 수준 — 탐색적·조건부 해석만.")
    elif skill is not None and skill > -0.05 and theory_hits >= theory_n * 0.5:
        verdict = "조건부로 가능"
        reason = ("성×연 패널로 부호·이질성 탐색은 가능하나, "
                  "짧은 T·공통충격(ONI) 검출력 부족으로 ‘통계적으로 유의하다’고 "
                  "단정하기는 어려움.")
    else:
        verdict = "현재 데이터로는 불가"
        reason = ("T≈8·QC 후 n≈100 수준으로는 기후 계수 유의성·예측 skill을 "
                  "동시에 뒷받침하기 부족.")

    # refine with actual numbers after we know them — written after compute
    lines.append("## 2. 판정")
    lines.append("")
    lines.append(f"**{verdict}** — {reason}")
    lines.append("")
    lines.append("## 3. 주요 통계")
    lines.append("")
    lines.append(f"| 항목 | 값 |")
    lines.append(f"|---|---|")
    lines.append(f"| FE n (province-years) | {fe['n']} |")
    lines.append(f"| N provinces / T years | {fe['n_provinces']} / {fe['n_years']} |")
    lines.append(f"| Within R² | {fe['within_r2']:.3f} |")
    if cv:
        lines.append(f"| Forward CV n | {cv['n_fold_obs']} "
                     f"(years {cv['years_evaluated']}) |")
        lines.append(f"| RMSE model / province trend | "
                     f"{cv['rmse_model']:.1f} / {cv['rmse_province_trend']:.1f} kg/ha |")
        lines.append(f"| Skill vs province trend | "
                     f"{cv['skill_vs_province_trend']:+.1%} |")
    lines.append(f"| p<0.05 (cluster SE) | {', '.join(sig05) or '없음'} |")
    lines.append(f"| p<0.10 | {', '.join(sig10) or '없음'} |")
    lines.append(f"| 이론 부호 일치 | {theory_hits}/{theory_n} |")
    lines.append("")
    lines.append("### Province FE 계수")
    lines.append("")
    lines.append("| feature | coef | SE (prov cluster) | p≈ | theory | match |")
    lines.append("|---|---:|---:|---:|:---:|:---:|")
    for c in fe["coefs"]:
        m = {True: "✓", False: "✗", None: "—"}[c["sign_matches_theory"]]
        lines.append(
            f"| {c['feature']} | {c['coef']:+.4f} | {c['se_cluster_province']:.4f} | "
            f"{c['p_approx']:.3f} | {c['theory_sign']} | {m} |")
    lines.append("")
    lines.append("### Power / 해석 주의")
    lines.append("")
    lines.append("- T=8은 성 FE + 연도 공통충격(ONI, Q-proxy) 분리에 매우 약함.")
    lines.append("- Cluster SE는 G=13으로 근사 p-value — 소표본에서 과소/과대 가능.")
    lines.append("- 면적 컬럼은 2017–2020 다수 오염 → **수율만** 분석에 사용.")
    lines.append("- 지역 집계 모델 skill(−4.6%)과 별개: 성 패널은 이질성 신호 탐색용.")
    lines.append("")
    lines.append("## 4. 다음으로 추론을 강하게 만들 것")
    lines.append("")
    lines.append("1. GSO 연감/V0617에서 **2010–2016** Đông Xuân 성 수율 확보 (T≥12–15)")
    lines.append("2. Ben Tre·Ca Mau 결측/오염 셀을 성 통계연감으로 보정")
    lines.append("3. MRC Tan Chau 유량으로 `q_upstream_proxy` 대체")
    lines.append("4. 연도 FE 또는 ENSO 이벤트 케이스 스터디와 병행")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return verdict, reason


def main():
    os.makedirs(MODELS, exist_ok=True)
    os.makedirs(LABELS, exist_ok=True)

    # 1) Labels
    try:
        raw = scrape_mtn_mekong()
        log(f"scraped {len(raw)} rows from MTN")
    except Exception as e:  # noqa: BLE001
        log(f"scrape failed ({e}); using existing CSV")
        raw = pd.read_csv(
            os.path.join(LABELS, "mekong_rice_ws_provincial_dong_xuan.csv"))
        if "yield_kg_ha" not in raw.columns:
            raw["yield_kg_ha"] = raw["yield_ta_ha"] * 100.0

    labeled = apply_yield_qc(raw)
    label_path = os.path.join(LABELS, "mekong_rice_ws_provincial_dong_xuan.csv")
    # keep backward-compatible columns + qc
    labeled.sort_values(["province", "year"]).to_csv(label_path, index=False)
    log(f"wrote {label_path} ({labeled.yield_qc_pass.sum()}/{len(labeled)} QC pass)")

    qc = labeled[labeled.yield_qc_pass].copy()
    years = sorted(int(y) for y in qc.year.unique())

    # 2) Climate
    clim = build_climate_panel(years)
    panel = qc.merge(clim, on=["province", "year"], how="inner")
    panel_path = os.path.join(TRAINING, "mekong_rice_ws_provincial_panel.csv")
    panel.to_csv(panel_path, index=False)
    log(f"panel {panel.shape} → {panel_path}")

    # 3) Stats
    # Prefer lean predictor set to limit overfitting with short T
    preds = [c for c in [
        "spei4_ws_min", "spi_ws", "oni_lag2", "q_upstream_proxy",
        "salt_coastal_belt", "precip_dry_ws", "heat_days_35_ws",
    ] if c in panel.columns]

    fe = province_fe_ols(panel, preds)
    cv = forward_cv_vs_province_trend(panel, preds, min_train_years=4)
    cov = coverage_table(labeled)

    report_path = os.path.join(HERE, "PANEL_SIGNIFICANCE_KO.md")
    verdict, reason = write_ko_report(
        report_path, cov, fe, cv, len(labeled), int(labeled.yield_qc_pass.sum()))

    # Re-write report with refined verdict using actual skill
    skill = (cv or {}).get("skill_vs_province_trend")
    theory_hits = sum(1 for c in fe["coefs"] if c["sign_matches_theory"] is True)
    theory_n = sum(1 for c in fe["coefs"] if c["sign_matches_theory"] is not None)
    n_sig10 = sum(1 for c in fe["coefs"] if c["p_approx"] < 0.10)

    if skill is not None and skill > 0.02 and n_sig10 >= 1 and theory_hits >= 3:
        verdict = "조건부로 가능"
        reason = (f"QC 패널 n={fe['n']}(T={fe['n_years']})에서 이론 부호 "
                  f"{theory_hits}/{theory_n}, CV skill {skill:+.1%}. "
                  "탐색·이질성 분석은 가능하나 T 짧아 강한 유의 단정은 보류.")
    elif skill is not None and skill > -0.08 and theory_hits >= theory_n * 0.4:
        verdict = "조건부로 가능"
        reason = (f"패널은 쓸 수 있으나 CV skill {skill:+.1%}, "
                  f"cluster p<0.10 계수 {n_sig10}개 — "
                  "‘유의하다’기보다 ‘방향성 탐색 가능’ 수준.")
    else:
        verdict = "현재 데이터로는 불가"
        reason = (f"CV skill {skill}, 유의 계수 부족, T={fe['n_years']} — "
                  "기후→수율 유의성 주장에 부족.")

    # patch verdict lines in report
    text = open(report_path, encoding="utf-8").read()
    import re
    text = re.sub(
        r"## 2\. 판정\n\n\*\*[^*]+\*\* — [^\n]+",
        f"## 2. 판정\n\n**{verdict}** — {reason}",
        text,
        count=1,
    )
    open(report_path, "w", encoding="utf-8").write(text)

    stats = {
        "verdict": verdict,
        "verdict_reason": reason,
        "coverage": cov,
        "n_raw": int(len(labeled)),
        "n_qc": int(labeled.yield_qc_pass.sum()),
        "province_fe": fe,
        "forward_cv": cv,
        "predictors": preds,
        "label_source": MTN_URL,
        "commit_policy": "no_commit_per_user_request",
    }
    stats_path = os.path.join(MODELS, "mekong_rice_ws_provincial_panel_stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    log(f"stats → {stats_path}")
    log(f"VERDICT: {verdict}")
    if cv:
        log(f"  skill={cv['skill_vs_province_trend']:+.1%}  "
            f"within_R2={fe['within_r2']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
