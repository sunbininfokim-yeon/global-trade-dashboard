# Australian grain sorghum — model comparison

## Product conclusion

The experiment does **not** show that XGBoost is generally better than a
statistical model.  Model complexity is selected separately by region using
the same forward years, inputs and trend-only baseline.

| region | Ridge full/recent skill | XGBoost | two-layer MLP | decision |
|---|---:|---:|---:|---|
| NSW | +13.9% / +15.0% | **+18.8% / +19.6%** | +12.7% / +15.6% | Ridge production baseline; XGBoost challenger |
| Queensland | **+13.6% / +14.0%** | +3.0% / +3.2% | −4.7% / −2.1% | retain Ridge; reject XGBoost and MLP |

The production Ridge screen for NSW reports +15.6% full skill because its
pre-registered ablation omits the unhelpful ONI feature.  The table above fixes
all nine features across algorithms so it compares model structure rather than
feature selection.

All scores use 12 expanding-window predictions after at least 20 earlier
seasons.  The technology trend and feature scaling are refitted inside each
outer fold.  XGBoost and MLP settings are selected using inner time-series
splits only.  The MLP prediction averages five random seeds.

## Why the algorithms separate by region

NSW consistently selected the same strongly regularised depth-1 XGBoost model
in all 12 folds and beat trend in 10/12 years.  This is evidence for a few
stable threshold/asymmetric responses, not evidence that a large tree ensemble
is required.  In particular, flowering heat and heat × dryness add predictive
skill beyond water and rainfall alone.

Queensland selected different tree settings as the training endpoint moved,
and XGBoost beat trend in only 6/12 years.  State aggregation mixes Central and
southern Queensland, planting dates, hybrids and management systems.  With 32
complete seasons, a nonlinear learner can turn that heterogeneity into unstable
splits.  Penalised Ridge pools the distributed signal and has lower variance.

The two-layer MLP has far more effective flexibility than the sample supports.
It does not beat XGBoost in NSW and loses to trend in Queensland.  Deep learning
is rejected until spatial crop labels provide many more independent examples.

## Scientific basis and limits

Australian APSIM and field research identifies extreme heat and water stress
around flowering and grain fill as key constraints.  The current screen uses a
broad fixed flowering window because observed field phenology is unavailable.
It must not be described as causal attribution or farm-level prediction.

- Lobell et al.-style Australian APSIM heat-risk implementation:
  https://doi.org/10.1016/j.fcr.2017.06.012
- GRDC / NSW DPI / UQ northern sorghum agronomy trials:
  https://grdc.com.au/__data/assets/pdf_file/0029/577802/Paper-Serafin-Loretta-Optimising-sorghum-July-2022.pdf

Both state models pass the +10% gate but remain `low_confidence` because recent
skill is below +20%.  The 2027 forecast is withheld until the September–October
pre-sowing moisture window begins.

## Reproduce the optional comparison

The production pipeline has no XGBoost dependency.  For the experiment only:

```bash
python3 -m pip install xgboost==2.1.4
python3 -m australia.experiments.sorghum_model_compare
```

macOS XGBoost also requires the OpenMP runtime (`libomp`).
