# Vietnam yield model — regional package (T1 scaffold)

Methodology source (Obsidian): `기후 모델링/Regions/베트남/`  
Master: `베트남_쌀_커피_상세수식.md` · data stack: `베트남_데이터스택_레시피.md`

Code path: `New for anti/scripts/yield_model/vietnam/`

## Run (from `scripts/yield_model`)

```bash
cd "New for anti/scripts/yield_model"
python3 -m vietnam.collect                 # NASA POWER + ONI → training/*.csv
python3 -m vietnam.train                   # ridge CV → models/*.json
python3 -m vietnam.predict --year 2026
python3 -m vietnam.run_forecast            # public/data/vietnam_yield_forecast.json
python3 -m vietnam.collect --stubs         # also build T2 regions
```

Optional official labels: drop `training/labels_official/<region_key>.csv` with
columns `year,yield_kg_ha` before collect/train. Without that file, **labels are
`provisional_synthetic_climate_response`** — not GSO.

## Region-crops

| key | tier | crop | guide focus |
|-----|------|------|-------------|
| `mekong_rice_ws` | T1 | rice | WS salt / ENSO / dry stress; dual flood proxy |
| `central_highlands_coffee` | T1 | coffee | Feb–Apr WD, **irrigation_buffer**, Kath temp |
| `red_river_rice` | T1 | rice | typhoon rain days, flood spell, coastal salt proxy |
| `central_coast_rice` | T2 stub | rice | schema only unless `--stubs` |
| `central_highlands_pepper` | T2 stub | pepper | schema only unless `--stubs` |

## Real vs provisional

| feed | status |
|------|--------|
| NASA POWER daily + GWETROOT | **real** (cached under `cache/`, gitignored) |
| FAO-56 ET0 | **computed** from POWER |
| NOAA ONI | **real** |
| CHIRPS / SMAP / S1 / GEE | **not run** — fall back to POWER precip/SM |
| MRC discharge / field EC | **not available** — salinity **proxy** only |
| Yield labels | **provisional/synthetic** unless override CSV |
| Skill metrics in `models/*.json` | valid only as pipeline self-consistency on those labels |

Never claim official GSO yields or true ECe from this package as currently shipped.

### Salinity proxy (honest)

```
salt_proxy ≈ f(coast_km, dry-season precip, prior wet precip, ONI DJF)
ec_proxy / y_rel_salt  → Maas–Hoffman *shape* on that scaled proxy
```

Not canal EC, not MRC \(Q_\text{river}\). Wire discharge + SIWRP alerts before production.

### Coffee irrigation

`irrigation_buffer_mm` combines literature `irrig_fraction` dummies with days of
root-zone wetness above DOY median (POWER GWETROOT). WD alone is **not** yield
for irrigated robusta (`wd_eff = max(0, WD − I_proxy)`).

## DATA_LAYOUT

Forecast JSON: `public/data/vietnam_yield_forecast.json` with
`forecast_available`, per-region `point` / `range_*` / `skill.low_confidence` /
`provenance.labels_provisional`. Dashboard wiring (`CLIMATE_COUNTRIES`) is a
separate product step.

## Production gaps

1. GSO / MARD **province × season** rice (WS split for Mekong) and coffee yields  
2. MRC dry-season discharge / stage at Tan Chau–Chau Doc  
3. GEE CHIRPS + SMAP L4 + Sentinel-1 planted-area anomaly (2016-style)  
4. IBTrACS for RRD/central coast cyclone exposure (true distance)  
5. Province irrig fractions for coffee \(I_\text{proxy}\) calibration  
6. UI country entry once skill on real labels is re-evaluated  
