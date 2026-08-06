# MENA wheat yield model — configuration

Code: `New for anti/scripts/yield_model/mena/`  
Egypt narrative: [`WHY_EGYPT_TREND_ONLY.md`](./WHY_EGYPT_TREND_ONLY.md)

## Region-crops (T1)

| key | operational point |
|-----|-------------------|
| `egypt_nile_wheat` | **trend_only** (weather skill fails) |
| `morocco_atlantic_wheat` | weather residual |
| `algeria_hauts_wheat` | weather residual |
| `tunisia_wheat` | T2 stub |

## Model

- Ridge on `log(yield) − trend`; forward-chaining CV
- `beats_trend` false → publish trend as `point`, `weather_effect_pct = 0`
- Maghreb kept simple (no DL)

## Data

NASA POWER · ONI · HadISST DMI · FAOSTAT national Wheat
