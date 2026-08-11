"""Chronological multi-model validation for PortWatch capacity signals."""

from __future__ import annotations

import math
import os
import statistics
import warnings
from typing import Any


FEATURE_NAMES = [
    "symmetric_gap_7_vs_prior_28",
    "symmetric_gap_3_vs_prior_14",
    "symmetric_week_over_week_gap",
    "volatility_cv_14",
    "zero_capacity_share_14",
]
PURGE_GAP_SAMPLES = 7


def _symmetric_gap(current: float, baseline: float) -> float:
    """Bound capacity change to [-2, 2], with positive values denoting stress."""

    denominator = abs(current) + abs(baseline)
    return 0.0 if denominator == 0 else 2.0 * (baseline - current) / denominator


def _bounded_symmetric_gap(value: float) -> float:
    return max(-2.0, min(2.0, value))


def _symmetric_to_shortfall(value: float) -> float:
    """Convert a symmetric gap back to a bounded display-oriented shortfall."""

    bounded = max(-1.99, min(1.99, value))
    ratio = (2.0 - bounded) / (2.0 + bounded)
    return max(-1.0, min(1.0, 1.0 - ratio))


def _features_at(values: list[float], stop: int) -> list[float] | None:
    if stop < 35:
        return None
    prior_28 = values[stop - 35 : stop - 7]
    current_7 = values[stop - 7 : stop]
    prior_14 = values[stop - 17 : stop - 3]
    current_3 = values[stop - 3 : stop]
    previous_7 = values[stop - 14 : stop - 7]
    recent_14 = values[stop - 14 : stop]
    means = [
        statistics.fmean(prior_28),
        statistics.fmean(prior_14),
        statistics.fmean(previous_7),
        statistics.fmean(recent_14),
    ]
    if any(value == 0 for value in means):
        return None
    return [
        _symmetric_gap(statistics.fmean(current_7), means[0]),
        _symmetric_gap(statistics.fmean(current_3), means[1]),
        _symmetric_gap(statistics.fmean(current_7), means[2]),
        min(2.0, statistics.pstdev(recent_14) / abs(means[3])),
        sum(value == 0 for value in recent_14) / 14.0,
    ]


def build_supervised_samples(values: list[float], forward_window: int = 7) -> tuple[list[list[float]], list[float]]:
    features: list[list[float]] = []
    targets: list[float] = []
    for stop in range(35, len(values) - forward_window + 1):
        row = _features_at(values, stop)
        baseline = values[stop - 35 : stop - 7]
        if row is None:
            continue
        baseline_mean = statistics.fmean(baseline)
        if baseline_mean == 0:
            continue
        future = values[stop : stop + forward_window]
        features.append(row)
        targets.append(_symmetric_gap(statistics.fmean(future), baseline_mean))
    return features, targets


def _metric_row(name: str, actual: Any, predicted: Any, cv_mae: float | None = None) -> dict[str, Any]:
    import numpy as np

    errors = np.asarray(actual) - np.asarray(predicted)
    mae = float(np.mean(np.abs(errors)))
    rmse = float(math.sqrt(np.mean(errors**2)))
    denominator = float(np.sum((np.asarray(actual) - np.mean(actual)) ** 2))
    r2 = None if denominator == 0 else float(1.0 - np.sum(errors**2) / denominator)
    stress_threshold = _symmetric_gap(0.90, 1.0)
    stress_actual = np.asarray(actual) >= stress_threshold
    stress_predicted = np.asarray(predicted) >= stress_threshold
    directional = float(np.mean(stress_actual == stress_predicted))
    return {
        "model": name,
        "cv_mae_symmetric_gap": cv_mae,
        "test_mae_symmetric_gap": mae,
        "test_rmse_symmetric_gap": rmse,
        "test_r2": r2,
        "stress_direction_accuracy": directional,
    }


def _make_models(random_state: int) -> dict[str, Any]:
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return {
        "linear": make_pipeline(StandardScaler(), LinearRegression()),
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "random_forest": RandomForestRegressor(
            n_estimators=30,
            max_depth=5,
            min_samples_leaf=5,
            random_state=random_state,
            n_jobs=1,
        ),
        "gradient_boosting": GradientBoostingRegressor(
            n_estimators=40,
            max_depth=2,
            min_samples_leaf=5,
            learning_rate=0.04,
            loss="huber",
            random_state=random_state,
        ),
    }


def _walk_forward_backtest(x: Any, y: Any, *, random_state: int) -> dict[str, Any]:
    """Expanding-window backtest with a seven-sample leakage purge."""

    import numpy as np

    fold_count = 4
    block_size = min(56, max(28, len(x) // 10))
    first_test = len(x) - fold_count * block_size
    if first_test - PURGE_GAP_SAMPLES < 100:
        return {
            "status": "insufficient_history",
            "fold_count": 0,
            "purge_gap_samples": PURGE_GAP_SAMPLES,
        }

    model_names = ["persistence", "zero_shortfall", *_make_models(random_state).keys()]
    actual_by_model: dict[str, list[float]] = {name: [] for name in model_names}
    predicted_by_model: dict[str, list[float]] = {name: [] for name in model_names}
    fold_mae_by_model: dict[str, list[float]] = {name: [] for name in model_names}
    fold_rows: list[dict[str, Any]] = []

    for fold in range(fold_count):
        test_start = first_test + fold * block_size
        test_end = min(len(x), test_start + block_size)
        train_end = test_start - PURGE_GAP_SAMPLES
        x_train, y_train = x[:train_end], y[:train_end]
        x_test, y_test = x[test_start:test_end], y[test_start:test_end]
        predictions: dict[str, Any] = {
            "persistence": x_test[:, 0],
            "zero_shortfall": np.zeros_like(y_test),
        }
        for name, model in _make_models(random_state + fold).items():
            model.fit(x_train, y_train)
            predictions[name] = model.predict(x_test)

        fold_metrics: dict[str, float] = {}
        for name, predicted in predictions.items():
            actual_by_model[name].extend(float(value) for value in y_test)
            predicted_by_model[name].extend(float(value) for value in predicted)
            mae = float(np.mean(np.abs(y_test - predicted)))
            fold_mae_by_model[name].append(mae)
            fold_metrics[name] = mae
        fold_rows.append(
            {
                "fold": fold + 1,
                "train_count": len(x_train),
                "purged_count": PURGE_GAP_SAMPLES,
                "test_count": len(x_test),
                "model_mae_symmetric_gap": fold_metrics,
            }
        )

    model_rows = []
    for name in model_names:
        row = _metric_row(name, actual_by_model[name], predicted_by_model[name])
        baseline_fold_mae = [
            min(
                fold_mae_by_model["persistence"][index],
                fold_mae_by_model["zero_shortfall"][index],
            )
            for index in range(fold_count)
        ]
        row.update(
            {
                "mean_fold_mae_symmetric_gap": float(statistics.fmean(fold_mae_by_model[name])),
                "fold_wins_vs_best_simple_baseline": sum(
                    mae < baseline_fold_mae[index]
                    for index, mae in enumerate(fold_mae_by_model[name])
                ) if name not in {"persistence", "zero_shortfall"} else None,
            }
        )
        model_rows.append(row)

    return {
        "status": "completed",
        "method": f"four-fold expanding-window backtest with non-overlapping {block_size}-sample test blocks",
        "fold_count": fold_count,
        "purge_gap_samples": PURGE_GAP_SAMPLES,
        "total_test_predictions": fold_count * block_size,
        "folds": fold_rows,
        "models": model_rows,
    }


def analyze_capacity_series(values: list[float], *, random_state: int = 42) -> dict[str, Any]:
    """Compare ML regressors, classify regimes and score the latest anomaly."""

    # Avoid a noisy macOS physical-core probe in joblib. Every estimator below
    # is intentionally single-process because each chokepoint sample is small.
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
    warnings.filterwarnings(
        "ignore",
        message="Could not find the number of physical cores",
        category=UserWarning,
    )
    try:
        import numpy as np
        from sklearn.cluster import KMeans
        from sklearn.ensemble import IsolationForest
        from sklearn.inspection import permutation_importance
        from sklearn.model_selection import TimeSeriesSplit, cross_val_score
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        return {
            "status": "dependency_missing",
            "forecast_use": "descriptive_only",
            "missing_dependency": str(exc),
        }

    features, targets = build_supervised_samples(values)
    if len(features) < 100:
        return {
            "status": "insufficient_history",
            "forecast_use": "descriptive_only",
            "sample_count": len(features),
            "minimum_sample_count": 100,
        }

    x = np.asarray(features, dtype=float)
    y = np.asarray(targets, dtype=float)
    test_start = max(80, int(len(x) * 0.8))
    test_start = min(test_start, len(x) - 20)
    train_end = test_start - PURGE_GAP_SAMPLES
    x_train, x_test = x[:train_end], x[test_start:]
    y_train, y_test = y[:train_end], y[test_start:]
    cv = TimeSeriesSplit(n_splits=3, gap=PURGE_GAP_SAMPLES)

    models = _make_models(random_state)
    comparisons = [
        _metric_row("persistence", y_test, x_test[:, 0], cv_mae=None),
        _metric_row("zero_shortfall", y_test, np.zeros_like(y_test), cv_mae=None),
    ]
    fitted: dict[str, Any] = {}
    cv_scores: dict[str, float] = {}
    for name, model in models.items():
        scores = cross_val_score(
            model,
            x_train,
            y_train,
            scoring="neg_mean_absolute_error",
            cv=cv,
        )
        cv_mae = float(-np.mean(scores))
        model.fit(x_train, y_train)
        fitted[name] = model
        cv_scores[name] = cv_mae
        comparisons.append(_metric_row(name, y_test, model.predict(x_test), cv_mae=cv_mae))

    selected_name = min(cv_scores, key=cv_scores.get)
    selected_model = fitted[selected_name]
    selected_metrics = next(row for row in comparisons if row["model"] == selected_name)
    persistence_metrics = comparisons[0]
    beats_persistence = (
        selected_metrics["test_mae_symmetric_gap"]
        <= persistence_metrics["test_mae_symmetric_gap"] * 0.95
    )
    best_simple_baseline_mae = min(
        row["test_mae_symmetric_gap"] for row in comparisons[:2]
    )
    beats_best_simple_baseline = (
        selected_metrics["test_mae_symmetric_gap"]
        <= best_simple_baseline_mae * 0.95
    )
    positive_r2 = (selected_metrics["test_r2"] or 0.0) > 0.0
    walk_forward = _walk_forward_backtest(x, y, random_state=random_state)
    backtest_selected = next(
        (row for row in walk_forward.get("models", []) if row["model"] == selected_name),
        None,
    )
    backtest_baselines = [
        row
        for row in walk_forward.get("models", [])
        if row["model"] in {"persistence", "zero_shortfall"}
    ]
    backtest_beats_best_simple = False
    backtest_positive_r2 = False
    if backtest_selected and len(backtest_baselines) == 2:
        best_backtest_baseline_mae = min(
            row["test_mae_symmetric_gap"] for row in backtest_baselines
        )
        backtest_beats_best_simple = (
            backtest_selected["test_mae_symmetric_gap"]
            <= best_backtest_baseline_mae * 0.95
        )
        backtest_positive_r2 = (backtest_selected["test_r2"] or 0.0) > 0.0
    eligible = (
        beats_best_simple_baseline
        and positive_r2
        and backtest_beats_best_simple
        and backtest_positive_r2
        and len(y_test) >= 20
    )

    importance = permutation_importance(
        selected_model,
        x_test,
        y_test,
        scoring="neg_mean_absolute_error",
        n_repeats=3,
        random_state=random_state,
    )
    feature_importance = sorted(
        [
            {"feature": feature, "importance": float(max(0.0, score))}
            for feature, score in zip(FEATURE_NAMES, importance.importances_mean)
        ],
        key=lambda row: row["importance"],
        reverse=True,
    )

    final_features = _features_at(values, len(values))
    candidate_prediction = None
    candidate_shortfall = None
    prediction_interval = None
    if final_features is not None:
        full_model = models[selected_name]
        full_model.fit(x, y)
        candidate_prediction = _bounded_symmetric_gap(
            float(full_model.predict(np.asarray([final_features]))[0])
        )
        candidate_shortfall = _symmetric_to_shortfall(candidate_prediction)
        residuals = y_test - selected_model.predict(x_test)
        prediction_interval = {
            "p10_symmetric_gap": _bounded_symmetric_gap(
                candidate_prediction + float(np.quantile(residuals, 0.10))
            ),
            "p90_symmetric_gap": _bounded_symmetric_gap(
                candidate_prediction + float(np.quantile(residuals, 0.90))
            ),
            "method": "holdout residual empirical interval on symmetric gap scale",
        }

    scaler = StandardScaler()
    regime_x = scaler.fit_transform(x[:, [0, 3]])
    kmeans = KMeans(n_clusters=3, n_init=10, random_state=random_state).fit(regime_x)
    cluster_means = {
        cluster: float(np.mean(x[kmeans.labels_ == cluster, 0]))
        for cluster in range(3)
    }
    ordered_clusters = sorted(cluster_means, key=cluster_means.get)
    regime_names = {
        ordered_clusters[0]: "above_baseline_flow",
        ordered_clusters[1]: "normal_variation",
        ordered_clusters[2]: "capacity_stress",
    }
    current_regime = None
    anomaly_output = None
    if final_features is not None:
        current_pair = scaler.transform(np.asarray([[final_features[0], final_features[3]]]))
        current_cluster = int(kmeans.predict(current_pair)[0])
        current_regime = {
            "label": regime_names[current_cluster],
            "cluster": current_cluster,
            "cluster_mean_symmetric_gap": cluster_means[current_cluster],
        }
        isolation = IsolationForest(
            n_estimators=50,
            contamination=0.10,
            random_state=random_state,
        ).fit(x)
        historical_anomaly = -isolation.decision_function(x)
        current_score = float(-isolation.decision_function(np.asarray([final_features]))[0])
        percentile = float(np.mean(historical_anomaly <= current_score))
        anomaly_output = {
            "score": current_score,
            "historical_percentile": percentile,
            "is_anomaly_at_90pct": percentile >= 0.90,
            "method": "IsolationForest contamination=0.10",
        }

    return {
        "status": "ml_candidate_validated" if eligible else "ml_does_not_beat_baseline",
        "forecast_use": "eligible_exploratory" if eligible else "descriptive_only",
        "sample_count": len(x),
        "train_count": len(x_train),
        "purged_count": PURGE_GAP_SAMPLES,
        "test_count": len(x_test),
        "target_scale": "symmetric capacity gap in [-2, 2]; positive means shortfall",
        "feature_names": FEATURE_NAMES,
        "model_selection": "lowest three-split TimeSeriesSplit CV MAE on training window",
        "selected_model": selected_name,
        "beats_persistence_by_5pct": beats_persistence,
        "beats_best_simple_baseline_by_5pct": beats_best_simple_baseline,
        "backtest_beats_best_simple_baseline_by_5pct": backtest_beats_best_simple,
        "backtest_positive_r2": backtest_positive_r2,
        "models": comparisons,
        "walk_forward_backtest": walk_forward,
        "feature_importance": feature_importance,
        "candidate_next_7d_symmetric_gap": candidate_prediction,
        "candidate_next_7d_shortfall_fraction": candidate_shortfall,
        "published_next_7d_shortfall_fraction": candidate_shortfall if eligible else None,
        "candidate_prediction_interval": prediction_interval,
        "current_regime": current_regime,
        "current_anomaly": anomaly_output,
        "warning": "Exploratory ML with purged chronological validation; no causal claim. Candidate is unpublished unless it beats both simple baselines by 5% and has positive R2 in both holdout and walk-forward backtests.",
    }
