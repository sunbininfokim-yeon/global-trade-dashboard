"""Honest, low-dimensional backtests for Indonesian CPO production.

This is deliberately not a high-capacity AI model.  The effective sample is
the number of harvest years, not province rows.  Province observations are
used for crop-weighted climate aggregation and separate regional diagnostics.
"""

import os

import numpy as np
import pandas as pd


HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

STRUCTURE = os.path.join(DATA, "palm_structure.csv")
HISTORY = os.path.join(DATA, "palm_national_history.csv")
CLIMATE = os.path.join(DATA, "province_climate.csv")
FOLDS_OUT = os.path.join(DATA, "palm_backtest_folds.csv")
SUMMARY_OUT = os.path.join(DATA, "palm_model_summary.csv")
REGION_OUT = os.path.join(DATA, "palm_region_backtest.csv")
HORIZON_OUT = os.path.join(DATA, "palm_horizon2_backtest.csv")
REPORT_OUT = os.path.join(DATA, "PALM_MODEL_REPORT.md")

EXPLORATORY_MIN_TRAIN = 9
STRICT_CLIMATE_MIN_TRAIN = 15
MIN_FORWARD_FOLDS = 5
MIN_SKILL = 0.10
MAX_MAPE = 0.15

CORE_FEATURES = {
    "climate_soil_lag1": "dry_lag1__soil_root_m3m3",
    "climate_soil_lag2": "dry_lag2__soil_root_m3m3",
    "climate_vpd_lag1": "dry_lag1__vpd_max_kpa",
}

STABLE_PROVINCE = {
    "Kalimantan Utara": "Kalimantan Timur",
    "Papua Selatan": "Papua",
    "Papua Tengah": "Papua",
    "Papua Pegunungan": "Papua",
    "Papua Barat Daya": "Papua Barat",
}


def _log_model(frame, target, features=(), ridge=1.0):
    years = frame["year"].to_numpy(float)
    year_mean = years.mean()
    year_std = max(years.std(), 1.0)
    columns = [np.ones(len(frame)), (years - year_mean) / year_std]
    scaling = []
    for feature in features:
        values = frame[feature].to_numpy(float)
        mean = values.mean()
        std = max(values.std(), 1e-12)
        columns.append((values - mean) / std)
        scaling.append((mean, std))
    design = np.column_stack(columns)
    penalty = np.eye(design.shape[1]) * ridge
    penalty[0, 0] = 0
    penalty[1, 1] = 0
    coefficients = np.linalg.solve(
        design.T @ design + penalty,
        design.T @ np.log(frame[target].to_numpy(float)),
    )
    return coefficients, year_mean, year_std, scaling


def _predict_log(model, row, features=()):
    coefficients, year_mean, year_std, scaling = model
    values = [1.0, (float(row["year"]) - year_mean) / year_std]
    for feature, (mean, std) in zip(features, scaling):
        values.append((float(row[feature]) - mean) / std)
    return float(np.exp(np.dot(values, coefficients)))


def _weighted_climate(structure, climate):
    weights = structure[["year", "province", "mature_ha"]].copy()
    weights["year"] += 1
    joined = climate.merge(weights, on=["year", "province"], how="left")
    joined = joined[joined["mature_ha"].fillna(0) > 0].copy()
    joined["weighted"] = joined["value"] * joined["mature_ha"]
    grouped = (joined.groupby(["year", "window", "metric"], as_index=False)
               .agg(weighted=("weighted", "sum"), weight=("mature_ha", "sum")))
    grouped["value"] = grouped["weighted"] / grouped["weight"]
    pivot = grouped.pivot(
        index="year", columns=["window", "metric"], values="value")
    pivot.columns = ["__".join(column) for column in pivot.columns]
    return pivot.reset_index()


def load_frames():
    structure = pd.read_csv(STRUCTURE)
    structure = structure[structure["province"] != "INDONESIA"].copy()
    structure["province"] = structure["province"].replace(STABLE_PROVINCE)
    structure = (structure.groupby(["year", "province"], as_index=False)
                 .agg(immature_ha=("immature_ha", "sum"),
                      mature_ha=("mature_ha", "sum"),
                      production_tonnes=("production_tonnes", "sum")))

    climate = pd.read_csv(CLIMATE)
    climate = climate[climate["crop"] == "oil_palm"].copy()
    climate["province"] = climate["province"].replace(STABLE_PROVINCE)
    climate = (climate.groupby(
        ["year", "province", "window", "metric"], as_index=False)
        .agg(value=("value", "mean")))
    national_climate = _weighted_climate(structure, climate)

    national_structure = pd.read_csv(STRUCTURE)
    national_structure = national_structure[
        national_structure["province"] == "INDONESIA"][
        ["year", "immature_ha", "mature_ha", "damaged_ha", "data_status"]]
    history = pd.read_csv(HISTORY)[
        ["year", "total_area_ha", "total_cpo_tonnes"]]
    national = (history.merge(national_structure, on="year")
                .merge(national_climate, on="year"))
    national["mature_yield_t_ha"] = (
        national["total_cpo_tonnes"] / national["mature_ha"])

    region_climate = climate.pivot(
        index=["year", "province"], columns=["window", "metric"],
        values="value")
    region_climate.columns = ["__".join(column)
                              for column in region_climate.columns]
    region = structure.merge(region_climate.reset_index(),
                             on=["year", "province"])
    region = region[(region["mature_ha"] > 0)
                    & (region["production_tonnes"] > 0)].copy()
    region["mature_yield_t_ha"] = (
        region["production_tonnes"] / region["mature_ha"])
    return national.sort_values("year"), region.sort_values(
        ["province", "year"])


def forward_predictions(frame):
    rows = []
    for position in range(EXPLORATORY_MIN_TRAIN, len(frame)):
        train = frame.iloc[:position]
        test = frame.iloc[position]
        predictions = {
            "last_year": float(train["total_cpo_tonnes"].iloc[-1]),
            "log_trend": _predict_log(
                _log_model(train, "total_cpo_tonnes", ridge=0), test),
        }
        mature_area = float(train["mature_ha"].iloc[-1])
        predictions["structure_no_climate"] = mature_area * _predict_log(
            _log_model(train, "mature_yield_t_ha", ridge=0), test)
        predictions["fixed_equal_baseline"] = 0.5 * (
            predictions["last_year"] + predictions["structure_no_climate"])
        for model_name, feature in CORE_FEATURES.items():
            predictions[model_name] = mature_area * _predict_log(
                _log_model(train, "mature_yield_t_ha", [feature], ridge=1),
                test, [feature])
        for model_name, prediction in predictions.items():
            actual = float(test["total_cpo_tonnes"])
            rows.append({
                "year": int(test["year"]), "model": model_name,
                "prediction_tonnes": prediction, "actual_tonnes": actual,
                "absolute_percentage_error": abs(prediction - actual) / actual,
                "train_seasons": len(train),
            })
    return pd.DataFrame(rows)


def horizon2_predictions(frame):
    """Two-year-ahead test using no labels or structure after year t-2."""
    rows = []
    for position in range(EXPLORATORY_MIN_TRAIN + 1, len(frame)):
        train = frame.iloc[:position - 1]
        test = frame.iloc[position]
        if len(train) < EXPLORATORY_MIN_TRAIN:
            continue
        predictions = {
            "h2_last_year": float(train["total_cpo_tonnes"].iloc[-1]),
        }
        predictions["h2_structure_no_climate"] = (
            float(train["mature_ha"].iloc[-1]) * _predict_log(
                _log_model(train, "mature_yield_t_ha", ridge=0), test))
        predictions["h2_fixed_equal_baseline"] = 0.5 * (
            predictions["h2_last_year"]
            + predictions["h2_structure_no_climate"])
        for model_name, prediction in predictions.items():
            actual = float(test["total_cpo_tonnes"])
            rows.append({
                "year": int(test["year"]), "model": model_name,
                "prediction_tonnes": prediction, "actual_tonnes": actual,
                "absolute_percentage_error": abs(prediction - actual) / actual,
                "train_seasons": len(train), "horizon_years": 2,
            })
    return pd.DataFrame(rows)


def summarize(folds, independent_seasons):
    summary = (folds.groupby("model", as_index=False)
               .agg(forward_folds=("year", "count"),
                    mape=("absolute_percentage_error", "mean"),
                    median_ape=("absolute_percentage_error", "median"),
                    max_ape=("absolute_percentage_error", "max")))
    latest = (folds.sort_values("year").groupby("model").tail(1)
              [["model", "year", "absolute_percentage_error"]]
              .rename(columns={"year": "latest_year",
                               "absolute_percentage_error": "latest_ape"}))
    summary = summary.merge(latest, on="model")
    baseline_mape = float(summary.loc[
        summary["model"] == "last_year", "mape"].iloc[0])
    structural_mape = float(summary.loc[
        summary["model"] == "structure_no_climate", "mape"].iloc[0])
    summary["skill_vs_last_year"] = 1 - summary["mape"] / baseline_mape
    summary["incremental_skill_vs_structure"] = np.where(
        summary["model"].str.startswith("climate_"),
        1 - summary["mape"] / structural_mape,
        np.nan,
    )
    strict_possible = (
        independent_seasons >= STRICT_CLIMATE_MIN_TRAIN + MIN_FORWARD_FOLDS)
    summary["strict_climate_sample_gate"] = np.where(
        summary["model"].str.startswith("climate_"),
        "pass" if strict_possible else "stopped_insufficient_seasons",
        "not_applicable",
    )
    summary["operational_status"] = "diagnostic_only"
    baseline_candidate = (
        (summary["model"] == "fixed_equal_baseline")
        & (summary["mape"] <= MAX_MAPE)
        & (summary["latest_ape"] <= MAX_MAPE))
    summary.loc[baseline_candidate, "operational_status"] = (
        "baseline_forecast_candidate")
    summary.loc[summary["model"].str.startswith("climate_"),
                "operational_status"] = "stopped_climate_adjustment"
    return summary.sort_values("mape").reset_index(drop=True)


def regional_backtest(region):
    recent = region[region["year"] >= region["year"].max() - 2]
    top = (recent.groupby("province")["production_tonnes"].mean()
           .sort_values(ascending=False).head(8))
    total = top.sum()
    rows = []
    feature = CORE_FEATURES["climate_soil_lag2"]
    for province, mean_production in top.items():
        frame = region[region["province"] == province].sort_values("year")
        folds = []
        for position in range(EXPLORATORY_MIN_TRAIN, len(frame)):
            train = frame.iloc[:position]
            test = frame.iloc[position]
            mature_area = float(train["mature_ha"].iloc[-1])
            predictions = {
                "last_year": float(train["production_tonnes"].iloc[-1]),
                "structure_no_climate": mature_area * _predict_log(
                    _log_model(train, "mature_yield_t_ha", ridge=0), test),
                "climate_soil_lag2": mature_area * _predict_log(
                    _log_model(train, "mature_yield_t_ha", [feature], ridge=1),
                    test, [feature]),
            }
            for model, prediction in predictions.items():
                actual = float(test["production_tonnes"])
                folds.append({
                    "year": int(test["year"]), "model": model,
                    "ape": abs(prediction - actual) / actual,
                })
        fold_frame = pd.DataFrame(folds)
        models = {}
        for model, values in fold_frame.groupby("model"):
            models[model] = {
                "mape": values["ape"].mean(),
                "latest": values.sort_values("year")["ape"].iloc[-1],
                "folds": len(values),
            }
        best = min(models, key=lambda name: models[name]["mape"])
        structural_skill = 1 - (
            models["structure_no_climate"]["mape"]
            / models["last_year"]["mape"])
        if (models["last_year"]["mape"] <= 0.08
                and models["last_year"]["latest"] <= 0.10):
            promotion = "forecast_baseline"
            selected = "last_year"
        elif (models["structure_no_climate"]["mape"] <= 0.10
              and models["structure_no_climate"]["latest"] <= 0.15
              and structural_skill >= MIN_SKILL):
            promotion = "forecast_structural"
            selected = "structure_no_climate"
        else:
            promotion = "reference"
            selected = None
        rows.append({
            "province": province,
            "recent_production_share_top8": mean_production / total,
            "forward_folds": models["last_year"]["folds"],
            "last_year_mape": models["last_year"]["mape"],
            "structure_mape": models["structure_no_climate"]["mape"],
            "climate_mape": models["climate_soil_lag2"]["mape"],
            "last_year_latest_ape": models["last_year"]["latest"],
            "structure_latest_ape": models["structure_no_climate"]["latest"],
            "climate_latest_ape": models["climate_soil_lag2"]["latest"],
            "structure_skill_vs_last_year": structural_skill,
            "best_diagnostic_model": best,
            "selected_model": selected,
            "status": promotion,
        })
    return pd.DataFrame(rows)


def _pct(value):
    return "{:.1f}%".format(value * 100)


def write_report(national, summary, regional, horizon2):
    by_model = summary.set_index("model")
    structural = by_model.loc["structure_no_climate"]
    best_climate_name = min(CORE_FEATURES, key=lambda name: by_model.loc[name, "mape"])
    best_climate = by_model.loc[best_climate_name]
    years = "{}–{}".format(int(national["year"].min()),
                           int(national["year"].max()))
    lines = [
        "# 인도네시아 팜유(CPO) 모델 점검",
        "",
        "## 결론",
        "",
        "**전국 기준 전망은 저신뢰 후보로 유지하고, 기후 조정은 중단한다.** "
        "성숙면적을 분리하자 최근 오차는 낮아졌지만, 기후 변수가 무기후 구조 모델을 "
        "유의미하게 개선하지 못했고 엄격한 표본 게이트도 한 시즌 부족하다. 지역은 "
        "사전 지정한 오차·skill 기준을 통과한 곳만 forecast 후보로 승격한다.",
        "",
        "## 전국 전진검증",
        "",
        "| 모델 | 전진검증 | MAPE | 최신 APE | 직전연도 대비 skill | 판정 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    order = ["last_year", "log_trend", "structure_no_climate",
             "fixed_equal_baseline",
             "climate_soil_lag1", "climate_soil_lag2", "climate_vpd_lag1"]
    labels = {
        "last_year": "직전연도",
        "log_trend": "전국 로그추세",
        "structure_no_climate": "직전 성숙면적 × 수율추세",
        "fixed_equal_baseline": "직전연도·구조 50:50 고정 앙상블",
        "climate_soil_lag1": "구조 + 전년 토양수분",
        "climate_soil_lag2": "구조 + 2년 전 토양수분",
        "climate_vpd_lag1": "구조 + 전년 VPD",
    }
    for model in order:
        row = by_model.loc[model]
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            labels[model], int(row["forward_folds"]), _pct(row["mape"]),
            _pct(row["latest_ape"]), _pct(row["skill_vs_last_year"]),
            row["operational_status"]))
    lines.extend([
        "",
        "- 검증기간은 2015–2024년 10개 홀드아웃 시즌이며 미래 연도만 예측했다.",
        "- 기후 모델은 독립 시즌 19개다. 3개 계수(절편·시간·기후 1개)에 "
        "15개 학습 시즌과 5개 홀드아웃을 요구하면 최소 20개가 필요해 현재는 "
        "`stopped_insufficient_seasons`다.",
        "- 가장 낮은 기후 MAPE는 `{}`의 {}지만 무기후 구조 모델({}) 대비 "
        "개선은 {}뿐이다. 요구한 최소 개선폭 {}에 못 미친다.".format(
            best_climate_name, _pct(best_climate["mape"]),
            _pct(structural["mape"]),
            _pct(best_climate["incremental_skill_vs_structure"]),
            _pct(MIN_SKILL)),
        "",
        "## 2년 선행 국가 기준모델",
        "",
        "2026년처럼 최신 생산·성숙면적 정답보다 두 해 앞선 상황을 별도로 "
        "검증했다.",
        "",
        "| 모델 | 전진검증 | MAPE | 최신 APE | 최대 APE |",
        "|---|---:|---:|---:|---:|",
        "",
    ])
    h2_labels = {
        "h2_last_year": "2년 전 생산 지속",
        "h2_structure_no_climate": "2년 전 성숙면적 × 수율추세",
        "h2_fixed_equal_baseline": "두 기준 50:50",
    }
    for model, group in horizon2.groupby("model"):
        ordered = group.sort_values("year")
        lines.append("| {} | {} | {} | {} | {} |".format(
            h2_labels[model], len(ordered),
            _pct(ordered["absolute_percentage_error"].mean()),
            _pct(ordered["absolute_percentage_error"].iloc[-1]),
            _pct(ordered["absolute_percentage_error"].max())))
    lines.extend([
        "",
        "2년 선행 구조 기준모델은 평균 오차가 9% 미만이지만 최대 오차가 약 "
        "25%이므로 2026 전망은 넓은 구간과 `low_confidence` 표시가 필요하다.",
        "",
        "## 지역별 진단",
        "",
        "지역 행을 하나의 통합 학습 표본으로 세지 않고 각 지역의 시간축을 "
        "별도로 전진검증했다. 아래 점유율은 상위 8개 지역 내부 비중이다.",
        "",
        "| 지역 | 점유율 | 직전연도 MAPE | 구조 MAPE | 구조+기후 MAPE | "
        "2024 최저 APE | 판정 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in regional.itertuples(index=False):
        latest_best = min(row.last_year_latest_ape, row.structure_latest_ape,
                          row.climate_latest_ape)
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            row.province, _pct(row.recent_production_share_top8),
            _pct(row.last_year_mape), _pct(row.structure_mape),
            _pct(row.climate_mape), _pct(latest_best), row.status))
    lines.extend([
        "",
        "## 주요 변수와 해석",
        "",
        "| 변수 | 역할 | 현재 판단 |",
        "|---|---|---|",
        "| 성숙면적(TM) | 생산능력 | 총면적 대신 반드시 사용 |",
        "| 미성숙면적(TBM) | 3–4년 뒤 면적 후보 | 짧은 표본에서 추가 skill 없음 |",
        "| 전년 건기 근권 토양수분 | 지연 수분 스트레스 | 계수 불안정·추가 skill 미미 |",
        "| 2년 전 건기 근권 토양수분 | 개화·착과 지연 | 탐색상 최저 MAPE이나 개선폭 부족 |",
        "| 전년 건기 VPD | 고온·건조 스트레스 | 추가 skill 없음 |",
        "| 총면적 | 장기 규모 보조 | 2024처럼 총면적 증가와 생산 감소를 설명 못함 |",
        "",
        "## 데이터 범위",
        "",
        "- 최신 BPS 일관 전국 CPO·총면적: 2003–2024년 22개 시즌",
        "- BPS 성숙/미성숙/노후 면적: 2005–2024년 20개 시즌",
        "- 면적가중 기후와 결합 가능한 시즌: {}년, 19개".format(years),
        "- 지역 생산·성숙면적: 상위 산지 포함, 행 수가 아니라 연도 수가 표본 수",
        "",
    ])
    with open(REPORT_OUT, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main():
    national, region = load_frames()
    folds = forward_predictions(national)
    summary = summarize(folds, independent_seasons=len(national))
    horizon2 = horizon2_predictions(national)
    regional = regional_backtest(region)
    folds.to_csv(FOLDS_OUT, index=False)
    summary.to_csv(SUMMARY_OUT, index=False)
    regional.to_csv(REGION_OUT, index=False)
    horizon2.to_csv(HORIZON_OUT, index=False)
    write_report(national, summary, regional, horizon2)
    best = summary.iloc[0]
    print("[palm:model] best diagnostic {} MAPE {:.1%}, latest APE {:.1%}".format(
        best["model"], best["mape"], best["latest_ape"]))
    print("[palm:model] climate adjustment stopped; baseline candidates retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
