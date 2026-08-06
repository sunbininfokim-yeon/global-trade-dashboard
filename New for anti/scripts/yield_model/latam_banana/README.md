# LatAm banana — reference / risk panel only

**No yield `point` forecast.** Same honesty mode as West Africa cocoa.

Authority: `Regions/중남미/바나나공화국_에콰도르/바나나/`  
Contract: `DATA_LAYOUT.md` §4 / §4b (`forecast_available: false`, `panel_mode: reference`)

## Why not forecast

Cavendish export boxes are dominated by **Black Sigatoka management** and
**storm / TR4 area loss**, not a weather residual we can validate from public
province panels. Farm **YLWS/YLS** weekly series are proprietary (see
`YLWS_ACQUISITION.md`). Until those open up, the dashboard gets:

- FAO / FAO Banana Statistical Compendium style **trade·production notes**
- Disease / hurricane / TR4 **risk narrative**
- Explicit `forecast_available: false`

Farm phenology, soil, or interview microdata are **out of scope** — they do
not move the export-supply story at belt scale for this product.

## Package layout

```text
latam_banana/
  README.md
  METHODOLOGY.md
  YLWS_ACQUISITION.md          ← attempt log + who holds the series
  BANANA_REFERENCE_KO.md
  reference/banana_country_profiles.json
  build_reference.py           → public/data/{country}_yield_forecast.json
```

## Build

```bash
cd "New for anti/scripts/yield_model"
python3 -m latam_banana.build_reference
```

## Countries

Ecuador · Guatemala · Costa Rica · Honduras  
(Colombia / Panama deferred)

UI `CLIMATE_COUNTRIES` is outside Cursor ML scope — JSON only for now.
