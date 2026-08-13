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
