# Uganda green-coffee yield model

This pipeline forecasts **national calendar-year green-coffee yield**, not
district production. Uganda has spatially distinct Robusta and Arabica belts,
but no consistent public annual district-yield panel was found. Seven coffee
locations therefore supply a fixed national climate proxy; they are not seven
separately trained models.

## Target and climate

- Target: FAOSTAT QCL green-coffee yield, 1961–2024, retrieved through the
  reproducible OWID Grapher API. The model/satellite overlap is 1982–2024.
- Rain: CHIRPS Daily in Google Earth Engine.
- Heat, VPD and 0–100 cm root-zone moisture: ERA5-Land Daily Aggregated.
- Geometry: four Robusta and three Arabica locations with 30 km buffers.
  Weights preserve USDA/FAS's approximate 85%/15% species mix; they are not
  claimed as district production shares.

All Earth Engine calls use existing local authentication:

```python
import ee
ee.Initialize(project="climate-project-504313")
```

## Validation contract

1. Weather anomalies use only the preceding 20 years.
2. Feature-set selection uses forward folds ending in 2014.
3. 2015–2024 is an untouched ten-season holdout.
4. A weather model is operational only if both development and holdout skill
   beat refitted trend by at least 10%; otherwise the published point falls
   back to the trend ensemble and the weather estimate remains diagnostic.
5. Uncertainty comes from absolute errors in the untouched holdout.
6. A shallow gradient-boosted tree is evaluated as a nonlinear challenger
   under the same development/holdout separation. It is not called XGBoost and
   is adopted only with at least 10% holdout skill and a 5% RMSE improvement.

## Scientific and operational limits

- Uganda's two harvest cycles do not align perfectly with FAOSTAT calendar
  years or the October-start USDA marketing year.
- Tree age, pruning, fertilizer, disease, prices and improved-seedling rollout
  are missing. USDA explicitly attributes recent production growth partly to
  management and maturing seedlings.
- A defensible age component would require annual regional cohorts for new
  planting, mortality, replanting and stumping. Canopy change, NDVI recovery
  and seedling distributions can only be proxies until those cohorts are
  independently validated; shade-tree change and pruning create similar
  satellite signatures.
- The 2025 study by Lwiza & Barkley finds a nonlinear Robusta response, with
  yield losses above 28 C and positive precipitation effects. The pipeline
  therefore tests heat and moisture features, but does not treat coefficients
  from national annual data as causal.
- USDA/FAS production outlooks are external comparisons only and never labels.

## Current validation result

- Selected linear feature set: long-rains precipitation + Tmax excess above
  28 C.
- Untouched 2015–2024 Ridge holdout: RMSE 21.5 kg/ha versus 20.7 kg/ha for
  refitted trend, skill **-3.9%**. The weather model is rejected.
- Gradient-boosted challenger: development skill +8.3%, untouched holdout
  skill **-86.7%** and RMSE 38.6 kg/ha. It is rejected as overfit/no gain.
- No 2026 point is published. The 538 kg/ha trend extension is retained only
  inside `model_diagnostics` and explicitly labelled **not a forecast**. The
  dashboard payload is a reference panel with official outlooks, rejection
  evidence, non-weather drivers and climate-risk indicators.

## Run

```bash
cd "New for anti"
../.venv/bin/python -m scripts.yield_model.uganda.run_forecast
```

Sources:

- FAOSTAT/OWID yield API: https://ourworldindata.org/grapher/coffee-yields
- USDA/FAS Uganda Coffee Annual: https://www.fas.usda.gov/data/uganda-coffee-annual-9
- CHIRPS Daily: https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY
- ERA5-Land Daily Aggregated: https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR
- Lwiza & Barkley (2025): https://doi.org/10.1007/s10113-025-02370-4
