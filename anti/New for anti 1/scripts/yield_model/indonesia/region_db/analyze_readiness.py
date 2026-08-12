"""Produce anti-overfit readiness diagnostics for the BPS province panel.

Province rows from the same harvest year are not treated as independent
seasons.  Weather-model sample gates are therefore based on distinct years,
while the province rows are used only for spatial coverage and concentration.
"""

import os
import sqlite3

import numpy as np
import pandas as pd

from indonesia.model import forward_validate


HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DATABASE = os.path.join(DATA, "indonesia_crop_panel.sqlite")

MIN_WEATHER_SEASONS = 25
MIN_TREND_TRAIN = 10
MIN_FORWARD_FOLDS = 5
MAX_TREND_MAPE = 0.15

CROPS = {
    "oil_palm": {"label": "팜유", "product": "CPO", "windows": 2,
                 "core_features": 3},
    "coffee": {"label": "커피", "product": "coffee beans", "windows": 3,
               "core_features": 4},
    "rubber": {"label": "고무", "product": "dry rubber", "windows": 2,
               "core_features": 4},
}

VARIABLES = [
    ("oil_palm", "core", "soil_root_m3m3", "dry_lag1",
     "수확 1년 전 건기 근권 토양수분", "대체로 +",
     "수분 스트레스와 착과·과실 발달의 지연 효과"),
    ("oil_palm", "core", "soil_root_m3m3", "dry_lag2",
     "수확 2년 전 건기 근권 토양수분", "대체로 +",
     "다년생 팜의 2년 지연 개화·착과 반응"),
    ("oil_palm", "core", "vpd_max_kpa", "dry_lag1",
     "수확 1년 전 건기 최대 VPD", "대체로 -",
     "고온·건조 복합 대기수요 스트레스"),
    ("oil_palm", "diagnostic", "precip_mm", "dry_lag1",
     "수확 1년 전 건기 강수량", "비선형 가능",
     "토양수분과 중복되는지 확인하는 보조 변수"),
    ("oil_palm", "diagnostic", "solar_mj_m2_day", "dry_lag1",
     "수확 1년 전 일사량", "불명확",
     "광합성·연무의 제한적 대리변수"),
    ("coffee", "core", "soil_root_m3m3", "preflower",
     "개화 전 근권 토양수분", "비선형 가능",
     "건기 스트레스 후 강우에 의한 개화 동조"),
    ("coffee", "core", "vpd_max_kpa", "preflower",
     "개화 전 최대 VPD", "과도하면 -",
     "개화 전 수분 스트레스 강도"),
    ("coffee", "core", "precip_mm", "flowering",
     "개화기 강수량", "비선형 가능",
     "개화 유도와 과습 피해를 함께 점검"),
    ("coffee", "core", "fungal_risk_days", "wet_season",
     "우기 곰팡이 위험일", "대체로 -",
     "18–30°C이면서 일강수 1mm 이상인 기상 대리변수"),
    ("coffee", "diagnostic", "wet_days", "wet_season",
     "우기 강우일수", "과도하면 -",
     "총강수와 다른 지속성 신호인지 확인"),
    ("coffee", "diagnostic", "solar_mj_m2_day", "wet_season",
     "우기 일사량", "대체로 +",
     "과습·운량과 광합성 환경의 보조 지표"),
    ("rubber", "core", "wet_days", "tapping",
     "채취기 강우일수", "대체로 -",
     "비로 인해 실제 수액 채취 가능한 일수가 감소"),
    ("rubber", "core", "fungal_risk_days", "tapping",
     "채취기 곰팡이 위험일", "대체로 -",
     "병 발생 자체가 아닌 기상 위험 대리변수"),
    ("rubber", "core", "soil_root_m3m3", "dry_lag",
     "전년 건기 근권 토양수분", "대체로 +",
     "나무 활력과 다음 채취기의 지연 반응"),
    ("rubber", "core", "vpd_max_kpa", "dry_lag",
     "전년 건기 최대 VPD", "대체로 -",
     "고온·건조 복합 스트레스"),
    ("rubber", "diagnostic", "precip_mm", "tapping",
     "채취기 총강수", "대체로 -",
     "강우일수와 중복되는지 확인하는 보조 변수"),
]


def safe_corr(left, right):
    left = np.asarray(left, float)
    right = np.asarray(right, float)
    valid = np.isfinite(left) & np.isfinite(right)
    if valid.sum() < 3 or np.std(left[valid]) == 0 or np.std(right[valid]) == 0:
        return np.nan
    return float(np.corrcoef(left[valid], right[valid])[0, 1])


def national_series(connection, observations):
    printed = pd.read_sql_query(
        "SELECT crop, year, area_ha, production_tonnes, data_status "
        "FROM national_totals WHERE category='total'", connection)
    fallback = (observations.groupby(["crop", "year"], as_index=False)
                .agg(fallback_area=("area_ha", "sum"),
                     fallback_production=("production_tonnes", "sum")))
    result = fallback.merge(printed, on=["crop", "year"], how="left")
    result["area_ha"] = result["area_ha"].fillna(result["fallback_area"])
    result["production_tonnes"] = result["production_tonnes"].fillna(
        result["fallback_production"])
    result["data_status"] = result["data_status"].fillna("province_sum_fallback")
    return result.sort_values(["crop", "year"]).reset_index(drop=True)


def stable_panel(observations):
    frame = observations.copy()
    frame["stable_province"] = frame["province"].replace(
        {"Kalimantan Utara": "Kalimantan Timur"})
    return (frame.groupby(["crop", "year", "stable_province"], as_index=False)
            .agg(area_ha=("area_ha", lambda value: value.sum(min_count=1)),
                 production_tonnes=(
                     "production_tonnes", lambda value: value.sum(min_count=1))))


def common_provinces(frame):
    sets = [set(group["stable_province"])
            for _, group in frame.groupby("year")]
    return set.intersection(*sets) if sets else set()


def trend_diagnostics(frame):
    usable = frame.dropna(subset=["production_tonnes"]).sort_values("year")
    if len(usable) < MIN_TREND_TRAIN + MIN_FORWARD_FOLDS:
        return None
    return forward_validate(
        usable, "production_tonnes", [], min_train=MIN_TREND_TRAIN,
        degree=1, window=None)


def detrended_cv(frame):
    usable = frame.dropna(subset=["production_tonnes"]).sort_values("year")
    years = usable["year"].to_numpy(float)
    values = usable["production_tonnes"].to_numpy(float)
    if len(values) < 3 or np.any(values <= 0):
        return np.nan
    trend = np.poly1d(np.polyfit(years, np.log(values), 1))
    residual = values - np.exp(trend(years))
    return float(np.std(residual, ddof=1) / np.mean(values))


def fmt_pct(value):
    return "—" if pd.isna(value) else "{:.1f}%".format(value * 100)


def fmt_corr(value):
    return "—" if pd.isna(value) else "{:+.3f}".format(value)


def main():
    connection = sqlite3.connect(DATABASE)
    observations = pd.read_sql_query(
        "SELECT crop, year, province, area_ha, production_tonnes, data_status "
        "FROM observations WHERE category='total'", connection)
    climate = pd.read_sql_query(
        "SELECT crop, year, province, COUNT(*) AS cells "
        "FROM climate_observations GROUP BY crop, year, province", connection)
    national = national_series(connection, observations)
    connection.close()

    stable = stable_panel(observations)
    readiness = []
    concentration = []

    for crop, metadata in CROPS.items():
        series = national[national["crop"] == crop].copy()
        spatial = stable[stable["crop"] == crop].copy()
        years = sorted(series["year"].astype(int).unique())
        common = common_provinces(spatial)
        expected_cells = metadata["windows"] * 7
        complete_climate = climate[
            (climate["crop"] == crop) & (climate["cells"] == expected_cells)]
        complete_keys = set(zip(
            complete_climate["year"].astype(int), complete_climate["province"]))
        expected_keys = {(int(year), province)
                         for year in years for province in common}
        complete_region_years = len(expected_keys & complete_keys)

        score = trend_diagnostics(series)
        if score is None:
            trend_status = "stopped_insufficient_history"
            folds = 0
            recent_mape = np.nan
            latest_ape = np.nan
        else:
            folds = score["n_folds"]
            recent_mape = score["recent_baseline_mape"]
            latest_ape = score["latest_baseline_ape"]
            trend_status = (
                "trend_only_diagnostic_pass"
                if (score["recent_folds"] >= MIN_FORWARD_FOLDS
                    and recent_mape <= MAX_TREND_MAPE
                    and latest_ape <= MAX_TREND_MAPE)
                else "stopped_poor_recent_backtest")

        available = len(years)
        required = max(
            MIN_WEATHER_SEASONS,
            5 * (metadata["core_features"] + 1),
        )
        climate_status = (
            "eligible_for_forward_test" if available >= required
            else "stopped_insufficient_independent_seasons")
        overall = (
            "trend_only_diagnostic_candidate"
            if trend_status == "trend_only_diagnostic_pass"
            else "stopped_no_operational_model")

        level_corr = safe_corr(series["area_ha"], series["production_tonnes"])
        positive = series[(series["area_ha"] > 0)
                          & (series["production_tonnes"] > 0)]
        growth_corr = safe_corr(
            np.diff(np.log(positive["area_ha"].to_numpy(float))),
            np.diff(np.log(positive["production_tonnes"].to_numpy(float))),
        )
        preliminary = int((series["data_status"] != "final").sum())
        readiness.append({
            "crop": crop,
            "crop_ko": metadata["label"],
            "product": metadata["product"],
            "first_year": min(years),
            "last_year": max(years),
            "independent_seasons": available,
            "stable_regions": len(common),
            "stable_region_years": len(expected_keys),
            "complete_climate_region_years": complete_region_years,
            "core_weather_features": metadata["core_features"],
            "required_independent_seasons": required,
            "climate_gate_status": climate_status,
            "trend_forward_folds": folds,
            "trend_recent_mape": recent_mape,
            "trend_latest_ape": latest_ape,
            "trend_gate_status": trend_status,
            "overall_status": overall,
            "detrended_production_cv": detrended_cv(series),
            "area_production_level_corr": level_corr,
            "area_production_growth_corr": growth_corr,
            "nonfinal_or_fallback_years": preliminary,
        })

        recent_years = years[-3:]
        recent = spatial[spatial["year"].isin(recent_years)]
        shares = (recent.groupby("stable_province", as_index=False)
                  .agg(mean_production_tonnes=("production_tonnes", "mean")))
        denominator = shares["mean_production_tonnes"].sum()
        shares["share"] = shares["mean_production_tonnes"] / denominator
        shares = shares.sort_values("share", ascending=False).head(8)
        for rank, row in enumerate(shares.itertuples(index=False), start=1):
            concentration.append({
                "crop": crop,
                "crop_ko": metadata["label"],
                "years": "{}-{}".format(min(recent_years), max(recent_years)),
                "rank": rank,
                "province": row.stable_province,
                "mean_production_tonnes": row.mean_production_tonnes,
                "production_share": row.share,
            })

    readiness_frame = pd.DataFrame(readiness)
    concentration_frame = pd.DataFrame(concentration)
    variable_frame = pd.DataFrame(VARIABLES, columns=[
        "crop", "role", "metric", "window", "variable_ko",
        "expected_relation", "mechanism",
    ])
    variable_frame["spatial_support"] = (
        "GAUL 2015 province mean; no crop mask")

    readiness_frame.to_csv(
        os.path.join(DATA, "model_readiness.csv"), index=False)
    concentration_frame.to_csv(
        os.path.join(DATA, "production_concentration.csv"), index=False)
    variable_frame.to_csv(
        os.path.join(DATA, "variable_spec.csv"), index=False)

    lines = [
        "# 인도네시아 지역 패널 모델 준비도",
        "",
        "지역 행 수를 독립 표본으로 세지 않고, 같은 수확연도의 공동 충격을 "
        "고려해 **서로 다른 연도 수**로 기후 모델 표본 게이트를 판정했다. "
        "현재 결과는 운영 예측이 아니라 데이터·모델 착수 여부 감사다.",
        "",
        "## 작물별 판정",
        "",
        "| 작물(목표) | 기간 | 독립 시즌 | 안정 지역 | 완전 기후 지역×년 | "
        "기후 게이트 | 추세 최근 MAPE | 최신 APE | 최종 판정 |",
        "|---|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for row in readiness:
        lines.append(
            "| {crop_ko} ({product}) | {first_year}–{last_year} | "
            "{independent_seasons}/{required_independent_seasons} | "
            "{stable_regions} | {complete_climate_region_years}/"
            "{stable_region_years} | {climate_gate_status} | {recent} | "
            "{latest} | {overall_status} |".format(
                recent=fmt_pct(row["trend_recent_mape"]),
                latest=fmt_pct(row["trend_latest_ape"]), **row))

    lines.extend([
        "",
        "- `stable_regions`는 모든 연도에 계속 등장하는 공통 지역 수다. "
        "북칼리만탄 생산량은 2015 GAUL 경계와 맞추기 위해 동칼리만탄에 합쳤다.",
        "- 팜유의 목표는 CPO이며 FAOSTAT의 oil-palm fruit/FFB와 같은 값으로 "
        "결합하지 않는다.",
        "- 추세 MAPE와 APE는 사전 지정한 전체기간 로그선형 추세의 "
        "전진검증 결과다. 기후 모델 정확도가 아니다.",
        "",
        "## 상관관계 진단",
        "",
        "| 작물 | 면적–생산량 수준 상관 | 연간 증감률 상관 | 추세제거 생산량 CV |",
        "|---|---:|---:|---:|",
    ])
    for row in readiness:
        lines.append("| {} | {} | {} | {} |".format(
            row["crop_ko"], fmt_corr(row["area_production_level_corr"]),
            fmt_corr(row["area_production_growth_corr"]),
            fmt_pct(row["detrended_production_cv"])))
    lines.extend([
        "",
        "수준 상관이 높아도 생산량 ≈ 재배면적 × 생산성이라는 구조와 공통 "
        "시간추세가 만든 결과일 수 있다. 따라서 기후 인과성으로 해석하지 않고, "
        "연간 증감률·추세잔차·전진검증을 별도로 본다.",
        "",
        "## 최근 3년 평균 상위 생산지역",
        "",
    ])
    for crop, metadata in CROPS.items():
        subset = concentration_frame[concentration_frame["crop"] == crop]
        items = ["{} {:.1f}%".format(row.province, row.production_share * 100)
                 for row in subset.head(5).itertuples(index=False)]
        lines.append("- **{}:** {}".format(metadata["label"], ", ".join(items)))
    lines.extend([
        "",
        "## 현재 결론",
        "",
        "세 작물 모두 기후 조정 모델의 최소 25개 독립 시즌을 충족하지 "
        "못한다. 팜유와 고무는 단순 추세도 최근·최신 오차 게이트를 넘었고, "
        "커피는 추세 전진검증 자체에 필요한 연도가 부족하다. 따라서 지역별 "
        "모델, 통합 패널 기후 모델, 올해 운영 예측값을 모두 중단 상태로 둔다. "
        "다음 우선순위는 더 오래된 BPS/농업부 생산량 확보, 작물 재배지 마스크, "
        "팜 수령·재식재 및 고무 가격·채취강도 같은 비기후 변수를 추가하는 것이다.",
        "",
    ])
    with open(os.path.join(DATA, "MODEL_READINESS.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    print("[bps:readiness] " + os.path.join(DATA, "MODEL_READINESS.md"))
    print(readiness_frame[[
        "crop", "independent_seasons", "required_independent_seasons",
        "stable_regions", "complete_climate_region_years",
        "climate_gate_status", "trend_gate_status", "overall_status",
    ]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
