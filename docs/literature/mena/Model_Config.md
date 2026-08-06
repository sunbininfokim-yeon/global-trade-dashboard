# MENA wheat yield model — configuration

Code: `New for anti/scripts/yield_model/mena/`

## Region-crops (T1)

| key | points | label | core features |
|-----|--------|-------|---------------|
| `egypt_nile_wheat` | 6 Nile Delta/Middle Egypt | FAOSTAT Egypt | wd_eff, salt_proxy, nile_inflow_proxy, oni_ndj |
| `morocco_atlantic_wheat` | 5 Atlantic plains | FAOSTAT Morocco | y_w_proxy, spei_like_6, spi_gs, edd_heading |
| `algeria_hauts_wheat` | 4 Hauts Plateaux | FAOSTAT Algeria | y_w_proxy, spei_like_6, wd_gs, iod_ond |
| `tunisia_wheat` | T2 stub | — | schema only |

Upstream inflow: `BLUE_NILE_POINTS` (3) → `nile_inflow_proxy` (JJAS precip).

## Model

- Ridge on `log(yield) − trend(year)`; forward-chaining CV
- Season roll: October (`current_season`)
- `low_confidence` when `beats_trend` false or `labels_season_imperfect`

## Data feeds

| feed | source |
|------|--------|
| Weather | NASA POWER v1 cache |
| ENSO | NOAA CPC ONI |
| IOD | NOAA PSL HadISST DMI |
| Labels | FAOSTAT Wheat (national) |

## References

- ICARDA Maghreb rainfed wheat G×E×M
- French & Schultz (1984) water-limited yield scaffold
- Schlenker & Roberts (2009) EDD heat penalty
- Obsidian: `Regions/중동_북아프리카_MENA/MENA_밀_작황_방법론.md`
