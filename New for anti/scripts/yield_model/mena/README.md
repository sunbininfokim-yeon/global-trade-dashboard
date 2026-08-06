# MENA yield model — regional wheat package (T1 scaffold)

Methodology source (Obsidian): `기후 모델링/Regions/중동_북아프리카_MENA/`  
Master: `MENA_밀_작황_방법론.md` · data stack: `MENA_데이터스택_레시피.md`  
Egypt trend-only narrative: `docs/literature/mena/WHY_EGYPT_TREND_ONLY.md`

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

## Region-crops

| key | tier | crop | guide focus |
|-----|------|------|-------------|
| `egypt_nile_wheat` | T1 | wheat | **ops = trend_only** (WHY doc) |
| `morocco_atlantic_wheat` | T1 | wheat | GSR Nov–Apr, SPEI-like, French–Schultz y_w |
| `algeria_hauts_wheat` | T1 | wheat | Hauts Plateaux rainfed (same scaffold) |
| `tunisia_wheat` | T2 stub | wheat | schema only unless `--stubs` |

## Operational policy

- **Maghreb (Morocco / Algeria):** keep the simple rainfed Ridge — publish weather residual when `beats_trend`.
- **Egypt Nile:** train/record the irrigated scaffold for diagnostics, but **do not publish weather residual**. `predict` sets `operational_mode: trend_only` when `beats_trend` is false.

## Real vs provisional

| feed | status |
|------|--------|
| NASA POWER daily + GWETROOT | **real** (`cache/`, gitignored) |
| FAO-56 ET0 | **computed** |
| NOAA ONI / HadISST DMI | **real** |
| FAOSTAT Wheat (national) | **real** → `labels_season_imperfect` |
| Nile inflow / salinity | **proxy** only |
| CHIRPS / ERA5 / GRACE / G-REALM / GEE | **not run** |

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

## DATA_LAYOUT

`public/data/mena_yield_forecast.json` — `country: MENA`, per-region
`point` / `range_*` / `skill.low_confidence` /
`provenance.operational_mode` (`trend_only` | `weather_residual`).

## Production gaps

1. CAPMAS / MAPMDREF governorate yield panels  
2. USDA G-REALM Lake Nasser / NASA GRACE (Egypt weather re-enable gate)  
3. GEE CHIRPS + SoilGrids join  
4. Field EC for Delta coast  
5. Tunisia real labels (T2)  
6. UI `CLIMATE_COUNTRIES` entry  
