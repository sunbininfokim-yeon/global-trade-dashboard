# Ethiopia Arabica coffee model

National FAOSTAT yield is modeled from production-weighted regional weather,
a two-year bearing-cycle proxy and lagged harvested-area growth. Oromia,
South-West Ethiopia, Sidama and South Ethiopia represent about 93% of output.

The model does **not** pretend to observe tree age. USDA/FAS reports that about
70% of trees are old and 15% of MY 2025/26 harvested area had been stumped,
with rates of 19% in Oromia, 14% in South Ethiopia and 13% in Sidama. These are
one recent cross-section, not an annual history, so they remain an external
structural scenario rather than a fitted coefficient.

Validation freezes feature selection at 2014 and opens 2015-2024 once. A
forecast is published only when weather+cycle beats both refitted trend by at
least 10% and cycle-only by at least 2% in the holdout.

A shallow gradient-boosted tree is also selected only on pre-2015 folds and
evaluated once on the same untouched holdout. It cannot be adopted merely for
improving in-sample fit.

## Current result

- Selected Ridge: rain + heat + lag-2 yield cycle + lagged area growth.
- Untouched 2015-2024: skill versus trend **-0.1%**; no incremental gain over
  cycle-only. The Ridge coefficients shrink essentially to zero.
- Boosted tree: development skill **-6.3%**, holdout skill **-6.9%**, rejected.
- The payload is therefore `panel_mode: reference` and publishes no point or
  interval. USDA outlook, regional shares, stumping context and climate-risk
  anomalies remain available.
- Current risk windows are coverage-gated against the latest CHIRPS and
  ERA5-Land image dates. A partial two-month rainfall sum is emitted as null,
  never mislabelled as an extreme drought.

Sources:

- https://ourworldindata.org/grapher/coffee-yields
- https://ourworldindata.org/grapher/coffee-bean-production
- https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=Coffee+Annual_Addis+Ababa_Ethiopia_ET2026-0005.pdf
- https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY
- https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR
