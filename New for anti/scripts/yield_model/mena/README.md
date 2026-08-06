# MENA yield model — regional wheat package (T1 scaffold)

Methodology source (Obsidian): `기후 모델링/Regions/중동_북아프리카_MENA/`  
Master: `MENA_밀_작황_방법론.md` · data stack: `MENA_데이터스택_레시피.md`

Code path: `New for anti/scripts/yield_model/mena/`

## Run (from `scripts/yield_model`)

```bash
cd "New for anti/scripts/yield_model"
python3 -m mena.collect                 # NASA POWER + ONI + DMI + FAOSTAT → training/*.csv
python3 -m mena.train                   # ridge CV → models/*.json
python3 -m mena.predict --year 2026
python3 -m mena.run_forecast            # public/data/mena_yield_forecast.json
python3 -m mena.collect --stubs         # also build T2 Tunisia stub
```

Optional labels: drop `training/labels_official/<region_key>.csv` with
columns `year,yield_kg_ha` (+ optional `label_source`). Collect fetches
FAOSTAT national wheat for Egypt / Morocco / Algeria automatically — see
`training/labels_official/README.md`.

## Region-crops

| key | tier | crop | guide focus |
|-----|------|------|-------------|
| `egypt_nile_wheat` | T1 | wheat | wd_eff, salt proxy, Blue Nile inflow proxy |
| `morocco_atlantic_wheat` | T1 | wheat | GSR Nov–Apr, SPEI-like, French–Schultz y_w |
| `algeria_hauts_wheat` | T1 | wheat | Hauts Plateaux rainfed (same scaffold) |
| `tunisia_wheat` | T2 stub | wheat | schema only unless `--stubs` |

## Real vs provisional

| feed | status |
|------|--------|
| NASA POWER daily + GWETROOT | **real** (cached under `cache/`, gitignored) |
| FAO-56 ET0 | **computed** from POWER |
| NOAA ONI | **real** |
| NOAA PSL HadISST DMI | **real** |
| FAOSTAT Wheat yield (Egypt/Morocco/Algeria) | **real** at national scale |
| CHIRPS / ERA5 / GRACE / G-REALM / GEE | **not run** — fall back to POWER |
| Nile inflow / salinity | **proxy** only |
| Skill metrics in `models/*.json` | FAOSTAT national → `labels_season_imperfect` |

Never claim governorate×season truth from this package: labels are FAOSTAT
national wheat. Maghreb skill may be low → trend-only + `low_confidence`.

### Egypt irrigation honesty

```
wd_eff = max(0, WD − irrigation_buffer)
irrigation_buffer ≈ γ·(SM retention days)   # not AQUASTAT depth
nile_inflow_proxy = Blue Nile JJAS precip   # not G-REALM stage
salt_proxy ≈ f(coast_km, dry moisture, ONI, inflow memory)
```

### Maghreb rainfed honesty

```
y_w_proxy ≈ WUE × max(0, GSR_NovApr + stored_Oct − Ec)
spei_like_6 / spi_gs = simplified drought indices on POWER balance
```

Not APSIM/ICARDA calibrated potential yield.

## DATA_LAYOUT

Forecast JSON: `public/data/mena_yield_forecast.json` with
`forecast_available`, `country: MENA`, per-region `point` / `range_*` /
`skill.low_confidence` / `provenance.labels_season_imperfect`.

## Production gaps

1. CAPMAS / MAPMDREF governorate yield panels  
2. USDA G-REALM Lake Nasser / NASA GRACE Nile moisture  
3. GEE CHIRPS + SoilGrids 250m point join  
4. Field EC / salinity sensors for Delta coast  
5. Tunisia real labels (T2 stub)  
6. UI country entry once skill on real labels is re-evaluated
