# Brazil regional yield models

Nine region-crop models, one per guide in `기후 모델링/Regions/브라질`. Each guide
prescribes a different methodology, so each model implements only its own
guide's derived variables — Mato Grosso soy is a sowing-date problem, Paraná
soy an ENSO/drought-index problem, MATOPIBA soy a heat problem, safrinha corn
a water-ledger problem, coffee an autoregressive biennial problem.

```bash
python3 -m brazil.collect        # build training tables
python3 -m brazil.train          # fit + validate, writes models/
python3 -m brazil.backtest       # hold out the last 5 published seasons
python3 -m brazil.predict --year 2026
python3 -m brazil.run_forecast   # writes public/data/brazil_yield_forecast.json
```

## Data

| | source | span | key |
|---|---|---|---|
| Yield | IBGE SIDRA, PAM tables 1612/1613, **state level** | 1974–2024 | none |
| Weather | NASA POWER daily | 1981– | none |
| ENSO | NOAA CPC ONI | 1950– | none |

State-level yield is what makes this possible. FAOSTAT's national series — used
by the older `brazil_soy_model` — averages a Paraná drought against a Mato
Grosso sowing delay and erases the very contrasts these guides exploit.

ET0 is computed here by FAO-56 Penman-Monteith from POWER radiation, wind,
dewpoint and temperature, rather than taken precomputed. That is the equation
`마투그로수/옥수수 §2B` writes out in full.

## Results

Skill is out-of-sample forward chaining with the trend refit inside every
fold, measured against the **best available** trend-only baseline. "Weather
only" holds out the non-weather features (`lag1`, `lag2`) as well, so a crop
cannot claim credit for biological memory or management persistence.

| region-crop | vs trend | weather only | 5-yr holdout MAPE vs trend | verdict |
|---|---:|---:|---:|---|
| parana_soja | +49.0% | +49.0% | 6.9% vs 21.6% | **confirmed by both** |
| mato_grosso_milho | +40.4% | +40.4% | 4.4% vs 8.7% | **confirmed by both** |
| matopiba_algodao | +11.2% | +11.2% | 3.4% vs 2.6% | forward-chaining only |
| parana_trigo | +11.1% | +11.1% | 12.0% vs 13.2% | weak, both positive |
| sp_cafe | +8.6% | +1.6% | 11.3% vs 9.6% | skill is mostly the lags |
| sp_cana | +8.2% | −3.1% | 2.7% vs 2.8% | skill is non-weather |
| parana_milho | −2.8% | −2.8% | 16.7% vs 25.3% | evaluations disagree |
| mato_grosso_soja | −9.4% | −9.4% | 7.8% vs 8.3% | no skill |
| matopiba_soja | −17.7% | −17.7% | 11.7% vs 10.7% | no skill |

Only **Paraná soy** and **Mato Grosso safrinha corn** are confirmed by both
evaluations. Everything else is either weak, contradicted between the two
tests, or not a weather signal at all. Where the two disagree the honest
reading is "not established", not "pick the better number".

The guides' own headline variables are the ones that carry, where anything
carries at all: `spi3_dec_feb` at +18.0% yield per 1σ for Paraná soy,
`precip_silking` and `silking_stress` for safrinha corn,
`flowering_heat_penalty` for cotton, `lag2` and `frost_count` for coffee.

## Things that are not weather

Stated per config in `non_weather_drivers` and published in the forecast JSON,
so a low score reads as "weather does not drive this crop" rather than "the
model is broken":

- **sp_cana** — a ratoon crop replanted every 5–7 years; much of any season is
  the age profile of the standing crop, set by replanting investment and mill
  economics. Detrended yield moves only ~3% a year across the whole record.
- **sp_cafe** — biennial bearing is physiological. The lags are the model's
  strongest features, so most of its skill is biological memory.
- **parana_milho** — SIDRA reports first-season and safrinha corn combined, and
  the area split moves with prices. Part of the target is an acreage decision.
- **matopiba_algodao** — the 1999→2000 jump is a change of production system,
  not a good weather year.

## What the literature says about the two weak crops

Before spending effort on satellite feeds, we checked how specialists model
these crops. Both weak results are the expected result, not a defect here.

**Sugarcane — climate alone does not forecast it, for anyone.** Dias &
Sentelhas (*Field Crops Research*, 2017) ran the three standard simulators —
FAO-AZM, DSSAT/CANEGRO and APSIM-Sugarcane, including the CANEGRO our guide
prescribes — against commercially managed Brazilian fields. All three
performed weakly, MAE above 29 t/ha with R² below 0.54, and the authors
attribute this to *"the lack of coefficients accounting for crop
management"*. Adding `kdec`, a ratoon-decline management factor, moved them to
MAE 13–15 t/ha and R² 0.58–0.72. Operational São Paulo forecasting systems
(Marin et al.) likewise combine Canegro output with agronomic inputs including
variety and ratoon stage, not climate alone. Our own `weather_skill` of −3.1%
is the same conclusion reached by a different route.

**Cotton — satellite greenness is not the missing piece.** Johnson (ORNL)
compared MODIS NDVI yield models against simple trend analysis across US
crops: NDVI is transformative for corn (R² 0.93 vs 0.48 for trend) but for
upland cotton *"poor performance across all methods, remote sensing adds
little value"*. Meanwhile the dominant non-weather driver in Brazilian cotton
is the boll weevil, which can take up to 70% of a crop and whose pressure
depends on planting-date coordination and control programmes. Roughly 92% of
Brazil's cotton area is rainfed, so the 2000 regime break was relocation,
cultivars, scale and management — not irrigation.

**Where satellite data would actually pay: corn.** The same ORNL comparison
that rules NDVI out for cotton is the strongest possible case for it on corn.
Mato Grosso safrinha corn is already the second-best model here, and Paraná
corn is one of the disagreements. If satellite effort is spent, it belongs
there, not on cotton or cane.

## Known departures from the guides

- **CWSI** (MATOPIBA soy) needs satellite canopy temperature. Replaced by a
  Tmax×VPD stress proxy and named as such.
- **DSSAT-CANEGRO** (sugarcane) is not runnable without the simulator and its
  calibrated genetic coefficients, so `Y_sim` is absent and the trend carries
  the baseline. The largest departure in the set.
- **FHB logistic coefficients** (wheat) are not given in the guide, so the
  weather features are fed to the yield model directly rather than through a
  calibrated `P(Epidemic)`. Anthesis is fixed at September.
- **NDVI** (Mato Grosso soy §3B, sugarcane §3B) is omitted: MODIS starts in
  2000 and would cut the record roughly in half.
- **Fibre quality** (cotton) has no open series, so the guide's two-output
  structure collapses to yield alone.

## Design decisions worth knowing

- Features are computed **per point, then production-weighted** — never the
  reverse. Averaging weather first erases the threshold exceedances
  (Tmax > 35, Tmin ≤ 1, rain > 300 mm) most of these guides are built on.
- The target is **log(yield)**, per `마투그로수/대두 §3A`, with the trend form
  (linear, quadratic, or a 10/20-year trailing window) chosen out of sample.
  Brazilian state yields have quadrupled since the 1980s, so absolute
  detrending would treat a 10% drought in 1985 as a fifth of the same drought
  today.
- Model and baseline are selected **independently**: the best model against the
  best trend, not against whichever trend flatters it. An earlier version let
  cane score +61.5% for correcting a baseline that ran 4,038 kg/ha high.
- `matopiba_algodao` trains from 2000 only. Pre-2000 is a different farming
  system (741 kg/ha, 30% scatter) and fitting across the break corrupted the
  trend, the scaling and the coefficients at once.

## Wheat

`parana_trigo` declines to forecast the current season until its September
anthesis window has passed. That is intended behaviour, not a failure.
