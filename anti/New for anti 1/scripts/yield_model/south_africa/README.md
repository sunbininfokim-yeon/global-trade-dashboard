# South Africa commercial maize belt

## Forecast target

The model forecasts harvest-year commercial maize yield in kg/ha. The label is
CEC commercial production divided by commercial planted area, republished in
the SAGIS historic workbook. It is not a province forecast: Free State, North
West and Mpumalanga provide a fixed mean-2023-2025-production-weighted climate proxy
for the national commercial crop.

## Season and features

- Planting rain: October-December before harvest year
- Critical rain: January-February in harvest year
- Extreme degree days: daily Tmax above 29 C, January-February
- Root-zone soil moisture: ERA5-Land layers 1-3, depth weighted to 0-100 cm
- VPD: daily Tmax and 2 m dewpoint, January-February

Climate comes from Earth Engine and always initializes as:

```python
import ee
ee.Initialize(project="climate-project-504313")
```

CHIRPS is used for rain and ERA5-Land Daily Aggregated for temperature, VPD and
soil moisture. Each feature is converted to a z anomaly against the previous
20 seasons, requiring at least 10 prior seasons. The current season never
enters its own normal.

## Validation

The response is log yield minus a log-linear technology trend. Four small,
pre-registered Ridge feature sets are compared using only 2007-2015 forward
folds. The selected set is then evaluated once on an untouched 2016-2025
holdout. The operational forecast equally weights a full-history trend and a
rolling 20-season trend to reduce sensitivity to recent trend flattening. The
trend is re-fitted inside every fold. Weather is operational only if it improves
both development and holdout RMSE by at least 10%.

The 2025/26 CEC estimate is excluded from training and included only as an
external comparison. Training currently ends with final 2024/25 data.

The forecast JSON also converts yield to total commercial production using the
CEC planted-area estimate. CEC production itself remains excluded from model
training and is shown only as an external comparison.

## Boosted-tree challenger

An intentionally shallow, strongly regularised `GradientBoostingRegressor` is
tested as an XGBoost-family challenger. Depth, tree count and feature set are
selected on 2007-2015 only; 2016-2025 stays untouched. It is adopted only if
holdout skill is at least 10% and holdout RMSE is at least 5% below Ridge.
The first six-location run selected a 60-stump model on development data but
scored -6.1% on holdout versus +15.3% for Ridge, so it was rejected as overfit.
The complete comparison is saved to `models/boosted_tree_challenger.json`.

## Run

From `scripts/yield_model`:

```bash
../../../.venv/bin/python -m south_africa.run_forecast --year 2026
```

Outputs:

- `south_africa/training/commercial_maize_belt.csv`
- `south_africa/models/commercial_maize_belt.json`
- `public/data/south_africa_yield_forecast.json`

Raw downloads and Earth Engine tables live in `south_africa/cache/` and are
not committed.

## Sources

- [SAGIS historic CEC information](https://www.sagis.org.za/non-sagis-historic-info/)
- [South Africa Crop Estimates](https://www.nda.gov.za/index.php/publication/320-crop-estimates)
- [Earth Engine CHIRPS Daily](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY)
- [Earth Engine ERA5-Land Daily Aggregated](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR)
