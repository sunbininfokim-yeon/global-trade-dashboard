# Thailand yield model — sources

Peer-reviewed / institutional sources that justify region-crop features.
Regions Obsidian notes (`기후 모델링/Regions/태국/`) are operational summaries;
this file is the citation ledger for the code package.

## Sugarcane (Central + Northeast) — `central_ne_sugarcane`

| Source | Institution / venue | What we take |
|--------|---------------------|--------------|
| Pipitpukdee, S., Attavanich, W., & Bejranonda, S. (2020). Climate Change Impacts on Sugarcane Production in Thailand. *Atmosphere*, 11(4), 408. https://doi.org/10.3390/atmos11040408 | Kasetsart-linked applied econ; *Atmosphere* | Growing-season temp, extreme heat, rainfall, **ENSO phase dummies**, irrigation share, tech trend — spatial yield/area models |
| Pattanapanchai, M. et al. (2022). Sugarcane Yield Prediction Using Satellite-Derived Indices and Weather Data in Thailand. *Agronomy*, 12(9), 2005 | Thai agronomy / remote sensing | Early-season moisture stress dominates end-of-year cane yield |
| Promping, T. et al. Agricultural drought characterization for sugarcane management in Thailand. *Engineering and Applied Science Research* (EASR / TCI-ThaiJO) | Thai engineering journal | 12-month standardized ETa (SEaI12) × cane yield / CCS; Nino3.4 fair correlation; El Niño decades worse |
| Kapetch, P., Sansayawichai, T., & Pisancharoen, K. (2014). Effects of Environmental Variability on Sugarcane Production in the North and the Northeast of Thailand. *Thai Agricultural Research Journal*, 32(1), 2–15 | DOA / Thai Agric. Res. | DSSAT-CANEGRO; water × soil drive N/NE yield variance |
| Office of the Cane and Sugar Board (OCSB) | Thai government | Crushing-year production / yield benchmarks (2015/16–2019/20 drought notches cited in Chula thesis) |
| Chulalongkorn thesis (2022). Forecasting cane sugar production under climate change… https://doi.org/10.58837/chula.the.2022.197 | Chula | Documents OCSB yield collapses in El Niño / drought years |

**Features wired:** early/grand-growth GWETROOT, SPI-like 3-month precip, WD, heat×drought days, ONI DJF.  
**Not wired:** OCSB province×mill panel, CCS sweetness, true SPI Gamma fit, SMAP ETa.

## Wet-season rice (Chao Phraya) — `chao_phraya_rice_wet`

| Source | Institution / venue | What we take |
|--------|---------------------|--------------|
| Prabnakorn, S. et al. (2018). Rice yield in response to climate trends and ENSO in Thailand. *Climatic Change*, 150, 397–410 | Peer-reviewed climate–crop | El Niño → delayed monsoon / lower wet-season rice |
| Limsakul, A. et al. (2014). Spatial and temporal variations of ENSO relationships with rainfall and temperature in Thailand. *Journal of Earth Science*, 25, 140–152 | Thai climate science | Strongest ENSO–rainfall signal in north / central plains |
| OAE — Agricultural Statistics of Thailand | Office of Agricultural Economics | Official rice stats (wet/dry split not yet machine-wired here) |

**Features wired:** monsoon onset DOY / delay, mid-season SM & dry spell, harvest extreme-rain days, ONI seasonal window.  
**Label caveat:** FAOSTAT national rice mixes wet+dry and all basins.

## Off-season rice (Chao Phraya irrigated) — `chao_phraya_rice_off`

| Source | Institution / venue | What we take |
|--------|---------------------|--------------|
| TDRI — Chaiyasit technical report on Chao Phraya water / dry-season agriculture | Thailand Development Research Institute | El Niño + low irrigation water at dry-season start cuts area and yield; Bhumibol/Sirikit central |
| Kyaw et al. / Chulalongkorn — Bhumibol–Sirikit operations (AER 2024; Applied Water Science 2024) | Chula water resources | >70% dam release to Greater Chao Phraya irrigation; drought years 2015, 2018–2020 |
| Ekasingh, B. et al. (2007). Impacts of Climate Change on Thai Agriculture | World Bank / SEI | Dry-season CP rice locked to dam irrigation policy |
| RID Daily Reservoir Water Situation; Thaiwater (HAII) | Royal Irrigation Dept / Hydroinformatics | **Authoritative storage series — not yet ingested** |

**Features wired:** `dam_recharge_proxy` = upstream wet-season precip × El Niño penalty; Feb–Mar heat days.  
**Honest gap:** this is **not** RID Nov-1 % live storage. Policy bans hit **area** harder than yield; national FAOSTAT rice is season-imperfect. Forecasts for this key always carry `dam_storage_is_proxy` + low_confidence until RID is wired.

## Natural rubber — `thailand_rubber`

| Source | Institution / venue | What we take |
|--------|---------------------|--------------|
| Makkaew, K. & Sdoodee, S. (2015). The impact of rainfall fluctuation on days and rubber productivity in Songkhla Province. *International Journal of Agricultural Technology*, 11(1) | Prince of Songkla University (Hat Yai) | More rainy days → fewer tapping days → lower dry rubber yield (RRIM600 sites) |
| Thaiburi et al. (2025). Effect of climate variability on rubber production in Thailand. *Journal of Agrometeorology*, 27(4) | National panel FGLS | Rainfall/temp effects differ South vs East vs Northeast |
| FAO / UPM WPP–MPP rubber land potential (East & NE Thailand) | FAO crop modelling lineage | Tapping-day loss improves production-potential validation |

**Features wired:** rainy days ≥1 mm and ≥5 mm in tapping window, wet-season precip, ONI.  
**Not wired:** observed tapping calendars, clone mix, Pestalotiopsis incidence.

## Cassava (Isan) — `isan_cassava` (stub / reference)

CMD (cassava mosaic disease) via whitefly dominates recent export risk (Regions guide). Weather-only ridge withheld; JSON emits `panel_mode: reference`, `point: null`.

## Data stack (all crops)

| Layer | Source |
|-------|--------|
| Daily weather / root-zone wetness | NASA POWER (`GWETROOT`, precip, temp, radiation) |
| Reference ET | FAO-56 Penman–Monteith via `brazil.climate` |
| ENSO | NOAA CPC ONI |
| Yield labels (default) | FAOSTAT Thailand national Yield |
| Yield labels (preferred later) | OAE / OCSB / RID CSVs under `training/labels_official/` |

## Method (project standard)

Thompson-style **tech trend + weather residual**; RidgeCV; forward-chaining skill vs trend-only (`HANDOFF_PROMPT.md`). No LSTM/CNN claims despite Regions narrative diagrams.
