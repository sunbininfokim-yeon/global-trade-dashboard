# West Africa cocoa data and feasibility pipeline

This package audits whether the ideas in
`기후 모델링/Regions/서아프리카/코트디부아르_가나/코코아` can be supported by
real data. It does **not** begin by naming a preferred machine-learning model.

## Analysis objectives

The original guide combines four distinct questions. They are kept separate here:

1. **Biological production and market receipts** — country production, regional
   production, and graded cocoa purchases.
2. **Cocoa area and canopy condition** — where cocoa is planted and whether its
   vegetation/water state is changing.
3. **Climate and disease pressure** — Harmattan water stress and weather that is
   conducive to black pod. The latter is a risk proxy, not observed disease loss.
4. **Forest/regulatory and export availability** — forest-loss exposure,
   traceability and trade. EUDR eligibility is not subtracted from biological
   production without farm polygons and due-diligence records.

## What is implemented

```bash
cd "New for anti/scripts/yield_model"

# One-time environment setup from this yield_model directory
../../../.venv/bin/python -m pip install -r west_africa/requirements.txt

# No Earth Engine or climate download: source catalogue + official labels
../../../.venv/bin/python -m west_africa.collect

# NASA POWER at the main cocoa-region points and merged screening tables
../../../.venv/bin/python -m west_africa.collect --climate

# Existing Earth Engine authentication and fixed Cloud project
../../../.venv/bin/python -m west_africa.earth_engine

# Feasibility decisions from the collected tables
../../../.venv/bin/python -m west_africa.audit

# Quantitative screen: does climate beat a time-trend in forward validation?
../../../.venv/bin/python -m west_africa.screen

# Ghana-only hard forecast gate. Exit 2 means forecast was intentionally abandoned.
../../../.venv/bin/python -m west_africa.ghana_forecast

# Create country-separated, credential-free snapshots suitable for GitHub.
../../../.venv/bin/python -m west_africa.publish_datasets

# Local unit tests
../../../.venv/bin/python -m unittest west_africa.test_west_africa
```

Earth Engine is always initialized as:

```python
import ee
ee.Initialize(project="climate-project-504313")
```

No authentication flow or new credential creation is included.

## Outputs

- `data/source_catalog.{csv,json}` — African, US, European and international sources.
- `data/faostat_cocoa_country_year.csv` — long national area/yield/production series.
- `data/civ_regional_cocoa.csv` — current Conseil Café-Cacao regional snapshots.
- `data/ghana_regional_purchases.csv` — COCOBOD regional crop-year purchases.
- `data/cocoa_country_climate.csv` — production-weighted climate screening features.
- `data/earth_engine_status.json` — verified collection access for S1/S2/SMAP/CHIRPS,
  ERA5-Land and Hansen forest change.
- `training/*.csv` — climate and labels joined without silently changing target meanings.
- `training/ghana_cocoa_regional_purchases.csv` — six Ghana regions with their own
  climate and COCOBOD purchase labels for year-blocked panel screening.
- `data/model_feasibility.json` — explicit trainable/proxy/scenario-only decisions.
- `models/feasibility_screen.json` — all predeclared climate screens versus trend.
- `models/ghana_forecast_decision.json` — hard go/no-go decision using only COCOBOD labels.
- `datasets/ghana/` and `datasets/cote_divoire/` — country-separated GitHub snapshots.
- `datasets/manifest.json` — file sizes and SHA-256 checksums for the published snapshot.
- `MODEL_REVIEW_KO.md` — Korean model decision, evidence table and next-data priorities.

## Empirical screen result

The collected tables make several experiments possible, but they do **not yet validate
an operational climate-yield model**. With expanding-window, year-blocked validation:

- Côte d'Ivoire FAOSTAT production and yield did not pass the predeclared 10% skill gate.
- Ghana FAOSTAT production passed for one combined climate feature set, but this signal
  did not reproduce against COCOBOD national purchases or the six-region purchase panel.
- Ghana FAOSTAT yield and both COCOBOD purchase screens did not pass.

This means the pipeline is usable for data-quality work, monitoring and further model
research, while production forecasts should remain disabled. The next decisive inputs
are vintage-consistent crop-year production/yield labels, validated cocoa polygons and
farm/region management or disease observations—not a more complex algorithm applied to
the same labels.

## Why the targets are not merged

`production`, `purchases`, `exports`, and `EUDR-eligible supply` are different
quantities. Stocks, unofficial cross-border flows, grading, domestic processing and
traceability can make them diverge. The package preserves a `measure`, `source`,
`crop_year` and alignment warning so a later model cannot silently treat them as one label.

The first NASA POWER table joins FAOSTAT calendar year to the cocoa year ending in
September only as a **provisional screening alignment**. A final operational forecast
must use vintage-consistent national crop-year labels from COCOBOD, Conseil Café-Cacao,
USDA FAS or licensed ICCO history.

## Current scientific boundary

- Long country series make a national climate-production screen possible.
- COCOBOD regional purchases may support a regional market-receipts screen if the live
  history remains complete after collection.
- Côte d'Ivoire's open regional production table currently has only 2022 and 2023, so
  it can weight current geography but cannot train a regional time-series model.
- Sentinel imagery and published cocoa maps support area/forest monitoring, not direct
  yield labels.
- Black pod and CSSVD require observed incidence or loss records before a disease-loss
  model can be called validated.
- Harmattan dust must come from CAMS or an aerosol product. ERA5-Land does not contain
  an explicit dust variable.
