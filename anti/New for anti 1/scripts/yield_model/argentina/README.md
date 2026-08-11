# Argentina regional yield models

Six region-crop models, one per guide in `기후 모델링/Regions/아르헨티나`, plus the
soil-moisture channel from `클로드_작업지시서/0803_아르헨티나_수분의존작물_위성데이터_통합_지시서.md`.
Each guide prescribes a different methodology, so each model implements only its
own guide's derived variables — Pampas soy is an FAO Ky water-deficit problem,
Pampas corn an ENSO × IOD problem with an unobserved sowing date, Pampas wheat a
frost problem, northern soy a heat-count problem on a planting-relative window,
Chaco cotton a heat × dryness product masked by degree-day phenology.

```bash
python3 -m argentina.collect        # build training tables
python3 -m argentina.train          # fit + validate, writes models/
python3 -m argentina.predict --year 2026
python3 -m argentina.run_forecast   # writes public/data/argentina_yield_forecast.json
```

Shared machinery is imported from `brazil/` rather than duplicated: FAO-56 ET0,
degree-day phenology, SPI and the whole validation harness. Only what the
Argentine guides ask for that the Brazilian ones did not lives in `climate_ar.py`.

## Data

| | source | span | key |
|---|---|---|---|
| Yield | MAGyP Estimaciones Agrícolas, **department level** | 1969–2024 | none |
| Weather | NASA POWER daily | 1981– | none |
| Soil moisture | NASA POWER GWETROOT / GWETTOP | 1981– | none |
| ENSO | NOAA CPC ONI | 1950– | none |
| IOD | NOAA PSL HadISST DMI | 1870– | none |

MAGyP publishes everything as one 15 MB CSV — every crop, every department,
every campaign — so ingestion is download-once-and-slice rather than SIDRA's
one-series-per-call. Three things about it drive the code:

- **Harvest year is not `anio`.** Summer crops sown in November of `anio` are
  harvested in `anio + 1`; wheat sown in June of `anio` is cut in December of
  `anio` itself. Campaign 2022/23 makes it concrete: soybeans harvested March
  2023 at 1,711 kg/ha, wheat harvested December 2022 at 2,277 kg/ha, both La
  Niña casualties one calendar year apart.
- **Yield is rebuilt from components**, `sum(produccion)/sum(superficie_cosechada)`,
  never a mean of departmental yields — that would weight a 500 ha department
  like a 500,000 ha one.
- **Abandonment** (sown minus harvested) has no SIDRA equivalent and is carried
  through to the published JSON. See "The target hides its own worst seasons".

## Results

Forward chaining with the trend refit inside every fold, scored against the
**best available** trend-only baseline. `MAPE` is RMSE over the last ten
seasons' mean yield.

| region-crop | seasons | vs trend (all folds) | recent 10 | MAPE vs trend-only | chosen set | verdict |
|---|---:|---:|---:|---|---|---|
| pampas_soja | 41 | +41.2% | **+52.0%** | 10.1% vs 17.2% | soil | **strong** |
| pampas_maiz | 41 | +38.6% | **+49.0%** | 9.8% vs 16.0% | weather | **strong** |
| chaco_algodon | 41 | +13.6% | +18.2% | 17.6% vs 20.4% | soil | usable |
| norte_soja | 31 | +11.7% | +6.4% | 17.1% vs 19.3% | weather | weak but positive |
| pampas_trigo | 41 | +6.4% | +0.5% | 15.6% vs 16.7% | enso | no real skill |
| tucuman_cana | — | — | — | — | — | **not trainable** |

Pampas soy and corn are the strongest models in this repository — better than
Paraná soy (+49.0%), which was the best of the Brazilian nine. That is not a
better method; it is a better problem. The Pampas is a single rainfed plain
with a hard ENSO signal, and MAGyP's department-level series resolves it.

The guides' own headline variables carry where anything carries:
`heat_x_drought` (−7.1% yield per 1σ) and `sm_summer` for Pampas soy,
`tmax_dec_jan` and `heat_wave_duration` for corn, `add_flowering_doy` and
`combined_stress` for cotton, `precip_rep` and `spi_dec_jan` for northern soy.

## What each data feed actually bought

The 0803 지시서 asks for this table. Cumulative rungs, one shared trend form,
same forward chaining. `marginal` is the gain over the rung below.

| region-crop | trend MAPE | weather | +ENSO marginal | +GWETROOT marginal |
|---|---:|---:|---:|---:|
| pampas_soja | 17.2% | +37.2% | **−16.7%** | **+19.9%** |
| pampas_maiz | 16.0% | +38.6% | −2.4% | −11.1% |
| chaco_algodon | 20.4% | +10.6% | −0.7% | +3.9% |
| norte_soja | 19.3% | +11.7% | −8.4% | −15.4% |
| pampas_trigo | 16.7% | +1.8% | **+4.7%** | −3.5% |

Two results worth stating plainly.

**ENSO indices mostly hurt once observed local weather is in the model.** Four of
five marginals are negative. ONI acts on Argentine yield *through* local rainfall
and temperature, and those are already measured directly; adding the index adds a
noisy proxy for information the model has, and spends degrees of freedom it does
not have (19 forward folds). Podestá et al. (1999) is not wrong — the
teleconnection is real — but its value is **lead time before the season**, not
explanation alongside observed weather. The exception is wheat, which is also the
model with no skill.

**Soil moisture splits the set in half.** Soy and cotton gain (+19.9%, +3.9%);
corn and northern soy lose (−11.1%, −15.4%) because their rainfall and
water-balance features already carry the same information. The ablation rungs are
therefore offered to model selection, not only to this report — otherwise corn
would be stuck on +30.1% when weather alone gives it +38.6%.

## Thresholds that do not transfer

Three separate variables specified as absolute thresholds turned out to be
constants on this data. It is the same mistake three times, in three different
sources, and it is worth naming:

| variable | as written | fired |
|---|---|---|
| `Climate_Shock_Index` (팜파스/옥수수 §2A) | ONI < −0.5 **and** DMI > 0.4 | **0 of 42 seasons** |
| `FII` (팜파스/밀 §2A) | Σ max(0, 0 − Tmin) at anthesis | 2 of 42 seasons |
| `heat_x_drought`, `dry_spell`, `harvest_wet_days` (0803 §A–C) | SMAP < 0.3 / < 0.2 / > 0.8 | **0 / 0 / ~0 days in 45 years** |

- The **shock index** never fires because a strongly positive dipole and a La
  Niña are themselves negatively associated — the guide's worst case is close to
  mutually exclusive at those thresholds. ONI and DMI are carried separately.
- **FII** never fires because POWER's gridded 2 m minimum cannot see radiative
  canopy frost. Over the fixed 10–25 October window, the two southern wheat
  stations register 1 and 3 sub-zero days in 42 years and the three northern ones
  register none. `fii` is kept at the guide's 0 °C and `fii_proxy` raises the
  threshold to 3 °C over a wider window. This variable needs station minima
  (INTA SIGA, SMN) to be modelled properly, and until it has them, Pampas wheat
  is not really being modelled by its own guide.
- The **SMAP thresholds** never fire because GWETROOT is a wetness *fraction* of
  plant-available capacity, not volumetric water content. Its p05–p95 at
  Pergamino is 0.57–0.73, and it varies more between stations (0.37–0.59 at
  Junín) than between years. Fixed by converting to a per-point day-of-year
  climatological percentile and thresholding there, which keeps what the sheet
  means by "dry for this place at this time of year".

## The target hides its own worst seasons

Argentine yield is computed over *harvested* area. A field written off before
harvest leaves the average entirely, so the surviving fields — the better ones —
are what the number reports. The 2022/23 drought abandoned 10% of Pampas soy
area and 24% of Pampas corn area; those crops are missing from the yield they
would have dragged down.

This caps how much skill any of these models can show, because the weather
features see a disaster the target only partly records. `abandonment` is
therefore carried in every training table and published in the forecast JSON —
but it is **excluded from the features**, since it is measured at harvest, at
the same moment as the yield it would "predict". Using it would post-dict.

## Known departures from the guides

- **DSSAT / APSIM / CANEGRO** are not runnable without the simulators and their
  calibrated coefficients. `WDEF` is taken from this pipeline's own bucket
  balance instead (ET_act/ET_c over silking — the same definition, cruder soil
  physics); wheat's two-stage delta model collapses to one regression; cane has
  no `Y_sim` at all.
- **SMAP** (0803 §1) starts in 2015 and needs a Google Earth Engine project.
  POWER's GWETROOT is the sheet's own stated fallback and keeps 42 seasons.
- **SAWHC** (팜파스/옥수수 §3A) is one constant per region, so it rescales every
  season identically and cannot do the work the guide wants from it.
- **Sowing dates** are fixed calendar dates everywhere. MAGyP publishes area and
  production but not planting progress by department. For corn this is the
  guide's own headline variable — the early/late split — so both calendars are
  built and offered, but their mix is unobserved.
- **Spatial fixed effects / embeddings** (팜파스/대두 §3B, 북부/대두 §3) are
  replaced by production-weighting five or six stations. Between-province
  contrast survives; department-level soil and management effects do not.
- **Fibre quality** (면화) has no open series, so the two-output structure
  collapses to lint yield alone.

## Things that are not weather

Stated per config in `non_weather_drivers` and published in the forecast JSON,
so a low score reads as "weather does not drive this crop" rather than "the model
is broken":

- **pampas_maiz** — MAGyP reports one combined corn figure per department, and
  the early/late sowing split moves with December rainfall *and* the corn/soy
  price ratio. Part of this target is a sowing decision.
- **norte_soja** — a frontier crop. Area has expanded roughly twentyfold since
  the 1980s onto newly cleared, progressively more marginal Chaco land, so
  average yield moves with *where* the crop is grown. Training starts at 1995.
- **chaco_algodon** — area collapsed from ~700k ha in the late 1990s to ~150k ha
  in the mid-2000s and has swung with the cotton/soy price ratio since, while the
  crop shifted from smallholder rainfed to mechanised narrow-row production.
- **tucuman_cana** — a ratoon crop cut for five to seven years before replanting,
  so much of a season is the age profile of the standing crop.

## Sugarcane is not trainable, and why

MAGyP's estimaciones series stops at campaign 2004/05 for cane and has a
1998–2002 hole, leaving 16 usable seasons after the POWER record opens — below
the 27 the validation harness requires. FAOSTAT's national series was checked as
a substitute and **rejected**: its 2015–2024 stretch is a monotonic 46 → 28 t/ha
decline with no year-to-year structure, and it correlates 0.46 with the MAGyP
Tucumán figures over their overlap. That is an area-reporting artefact, not a
yield history.

The config, the ingestion path and the map marker all exist. Pointing
`magyp.region_yield` at an EEAOC Tucumán series revives it.

## Wheat declines to forecast for most of the year

`pampas_trigo` refuses to publish a number until its mid-October anthesis window
has passed, rather than filling the gap with climatology. Between January and
October the dashboard shows the region with `forecast_available: false` and the
reason. That is intended behaviour, and the same rule Paraná wheat follows.

## Automation

`.github/workflows/argentina_yield_forecast.yml` runs Mondays 10:00 UTC:
re-forecasts from fresh POWER weather, checks whether MAGyP has published a new
campaign, and rebuilds the training tables and models if so. The cache
(`cache/`, ~94 MB) is gitignored and regenerates on demand; the training tables,
model artifacts and the forecast JSON are committed.
