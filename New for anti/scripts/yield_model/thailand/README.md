# Thailand yield model

Methodology: `기후 모델링/Regions/태국/` + peer-reviewed ledger in **[SOURCES.md](SOURCES.md)**.  
Code path: `New for anti/scripts/yield_model/thailand/`

## Run (from `scripts/yield_model`)

```bash
cd "New for anti/scripts/yield_model"
PYTHONPATH=. python3 -m thailand.collect                 # POWER + ONI + FAOSTAT
PYTHONPATH=. python3 -m thailand.train                   # ridge CV → models/*.json
PYTHONPATH=. python3 -m thailand.predict --year 2026
PYTHONPATH=. python3 -m thailand.run_forecast            # → public/data/thailand_yield_forecast.json
```

Optional official labels: drop `training/labels_official/<region_key>.csv`
with `year,yield_kg_ha` (+ optional `label_source`).

## Region-crops

| key | tier | crop | literature focus |
|-----|------|------|------------------|
| `central_ne_sugarcane` | T1 | sugarcane | SM / SPI-like precip / ENSO (Pipitpukdee 2020; Pattanapanchai 2022) |
| `chao_phraya_rice_wet` | T1 | rice | monsoon onset + ENSO (Prabnakorn 2018) |
| `chao_phraya_rice_off` | T1 | rice | dam **proxy** + heat (TDRI / RID mechanism — storage not wired) |
| `thailand_rubber` | T1 | rubber | rainy / tapping days (Makkaew & Sdoodee 2015, PSU) |
| `isan_cassava` | T2 stub | cassava | CMD disease — reference panel only |

## Satellite NDVI correction

`ndvi.py` collects MODIS MOD13Q1 NDVI at the 24 weather points (via
`argentina.ndvi`, every month), and `ndvi_backtest.py` tests it as a forward
correction on each model's out-of-sample forecast, with Argentina's rule: a
window goes live only if it beats the forecast by at least 5% with both the
75th-percentile and median summaries. Windows were fixed before the test.

| region | base | full window | half window | live |
|---|---|---|---|---|
| sugarcane (May-Oct) | model | -7.7% | +3.0% | no |
| wet rice (Aug-Oct) | trend | +14.5% | +15.3% | yes |
| off rice (Jan-Mar) | trend | +16.6% | +8.1% | yes |
| rubber (Jun-Oct) | trend | -15.9% | -14.9% | no |

Skill is RMSE reduction over 11 (wet rice) or 16 seasons through 2024, and
survives dropping any single season (worst case +11% / +5%). Off-season rice
has the expected sign: a greener dry-season crop (more dam water) means a
yield above trend, and 2015-16, the drought with empty dams, carries much of
it. Wet-season rice has the opposite sign, a greener August-October meaning
yield below trend; the likeliest reading is that NDVI there tracks cloud and
flooding more than canopy. Both forecast the same FAOSTAT national number.

`run_forecast.py` applies the live correction once at least half the window
has been seen and records it under `ndvi`. Models that do not beat the trend
publish the trend (`point_basis: "trend"`), which is also the base the
correction was scored against. The weekly workflow
`thailand_yield_forecast.yml` refreshes NDVI, re-scores and rewrites the JSON.

## Honest gaps

1. **RID Bhumibol + Sirikit Nov-1 storage** not ingested → off-season rice uses `dam_recharge_proxy`
2. FAOSTAT **national** rice/cane/rubber — not OAE wet-only or OCSB mill panels
3. No GEE SMAP / CHIRPS in this path (POWER GWETROOT stand-in)
4. Cassava CMD incidence not modelled

## DATA_LAYOUT

Forecast JSON: `public/data/thailand_yield_forecast.json` with
`forecast_available`, per-region `point` / `range_*` / `skill.low_confidence` /
`provenance.sources` / `dam_storage_is_proxy`. Dashboard `CLIMATE_COUNTRIES`
wiring is a separate product step (UI owned elsewhere).
