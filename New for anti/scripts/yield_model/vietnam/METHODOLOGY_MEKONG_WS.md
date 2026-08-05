# Mekong WS rice — feature ↔ paper map (2026-08-05)

Honest scope: these are **season-aligned proxies** from open weather/ENSO feeds.
MRC gauged discharge and field EC are **not** wired (portal request / 403).

| Feature | Role in pipeline | Primary citation |
|---------|------------------|------------------|
| `spei4_ws_min` | Min of 4-month climatic water-balance z-score over **Jan–Apr** (WS growth) | Yen et al. 2024, IOP Conf. Ser. Earth Environ. Sci. **1345** 012010 — [10.1088/1755-1315/1345/1/012010](https://doi.org/10.1088/1755-1315/1345/1/012010) (Ben Tre; SPEI-4min + QTCmin/STVmax) |
| `spi_ws` | Dry-window precip z vs climatology (Dec–Apr) | Loc et al. 2022, *Water* **14**(21):3499 — [10.3390/w14213499](https://doi.org/10.3390/w14213499) (SPI_WS + salinity); also *Climate* 2023 SPI-3/6 season defs — [10.3390/cli11010013](https://doi.org/10.3390/cli11010013) |
| `oni_lag2` | ONI OND(y−1)+NDJ(y) — ~2-month lead into mid dry season | Atmospheres 2026 teleconnections — [10.3390/atmos17060541](https://doi.org/10.3390/atmos17060541); AF-1022 asymmetric ENSO — [10.18805/IJARE.AF-1022](https://doi.org/10.18805/ijare.af-1022) |
| `q_upstream_proxy` | POWER Pakse wet precip + Tan Chau dry SM/precip (stand-in for **QTCmin**) | Yen et al. 2024 (QTCmin); Eslami et al. 2021 *ESurf* — [10.5194/esurf-9-953-2021](https://doi.org/10.5194/esurf-9-953-2021) (dry-season SWI ↔ low Q) |
| `salt_proxy` / `y_rel_salt` | Coast × dry moisture × wet memory × ONI × Q-proxy; Maas–Hoffman **shape** on scaled `ec_proxy` | Vault master + Maas & Hoffman 1977; CTU J. Sci. 2019 salinization on west-coast WS — [10.22144/ctu.jvn.2019.149](https://doi.org/10.22144/ctu.jvn.2019.149) |
| `salt_x_coast` / `salt_coastal_belt` | Coastal vs inland heterogeneity (≤40 km belt) | Loc et al. 2022; CTU 2019 coastal agro-ecology; VHLSS DID saline impact — [PMC10520798](https://pmc.ncbi.nlm.nih.gov/articles/PMC10520798/) |
| `sample_weight` (train) | ×3 on GSO/MTN official WS years 2017+ | Gap note: 2017–2024-only n≈8 too thin for default CV — ablation artifact separate |
| *(blocked)* MRC Tan Chau / Chau Doc discharge | Would replace `q_upstream_proxy` | MRC Data Portal time-series request — not open CSV here |
| *(blocked)* Sentinel-1 WS area anomaly | Area vs yield separation | Hoang-Phi et al. 2020 *Remote Sensing* — [10.3390/rs12193196](https://doi.org/10.3390/rs12193196) |

## Ablations

1. **Production:** full labelled span + official-year sample weights  
2. **`mekong_rice_ws_ablation_official2017.json`:** years ≥2017 only, `min_train=4` — exploratory; do not treat as production skill
