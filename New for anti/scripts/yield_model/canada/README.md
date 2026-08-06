# Canada crop-yield models — SAD first, province fallback, else trend

```bash
cd scripts/yield_model
python3 -m canada.collect
python3 -m canada.train
python3 -m canada.run_forecast
```

## Hierarchy (per user request)

1. **SAD / CAR** (`StatsCan 32-10-0002`) with **region-specific** feature packs  
2. If SAD climate fails skill gate → **province** weather (`32-10-0359`) if that beats trend  
3. Else → **log-linear trend only**

## Literature packs

| Regime | Features | Sources |
|---|---|---|
| Palliser / south AB | HSU@29.5, heat×dry, rain, VPD | Morrison 2002; Qian DSSAT |
| Parkland | rain, HSU, frost, SM | Chipanshi ICCYF 2015 |
| Peace | frost, GDD0, HSU | short-season AB |
| MB Red River soy | May excess precip/SM | MASC; Mkhabela SMOS |
| ON corn | GDD10, EDD@29, Jul rain | Schlenker; ON short-season |

## Phase-2 skill (2026-08-06)

Weather models that **beat trend** (≥10% all + recent):

| key | recent skill | RMSE |
|---|---|---|
| sad_sk_canola_palliser | +23.8% | 460 |
| sad_sk_canola_blacksoil | +24.9% | 258 |
| sad_sk_wheat_palliser | +26.3% | 358 |
| sad_ab_canola_south | +23.5% | 525 |

Parkland / Peace / MB / ON / all province tracks → **trend_only**
(province weather never cleared the dual skill gate).

## Data

- Labels: StatsCan SAD kg/ha; SK CD stitch after 2017 redesign  
- Climate: NASA POWER (phase-2 still POWER; SMAP/VSMB next)  
- Output: `public/data/canada_yield_forecast.json` with `hierarchy[]`
