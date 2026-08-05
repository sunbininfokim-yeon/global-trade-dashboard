# China regional production models

Six field models, one per guide in `기후 모델링/Regions/중국`, plus an import-demand
model from the seventh (macro) guide.

```bash
python3 -m china.collect        # build training tables
python3 -m china.train          # fit + validate, writes models/
python3 -m china.imports        # the macro import-demand guide
python3 -m china.predict --year 2026
python3 -m china.run_forecast   # writes public/data/china_yield_forecast.json
```

## The headline result

**No model in this package beats a trend-only baseline out of sample.** Not one
of the six yield/area models, and not the import models either.

An earlier version of this file claimed soybean imports as a success at +25.4%.
That claim was wrong and is retracted. It came from a 13-feature set found by
searching, and it survives no scrutiny: the guide's own pre-registered
specification scores −18.6%, hog-cycle variables alone −0.2%, and adding five
more plausible predictors to the winning set collapses it to −0.0%. Fifteen
forward folds against eighteen-odd tried combinations will produce a +20%
somewhere by luck. `imports.py` now fixes the feature set in advance and only
fits the trend form, so this cannot recur.

The field models fail for a reason worth stating before any methodology,
because no amount of better feature engineering would fix it.

The targets barely move.

| target | year-on-year volatility |
|---|---:|
| China rice yield (PSD) | 1.6% |
| China wheat yield (PSD) | 3.7% |
| China vegetables (FAOSTAT) | 3.7% |
| China corn yield (PSD) | 5.9% |
| China soybean yield (PSD) | 6.6% |
| **Brazil, Paraná soy (SIDRA)** | **24.5%** |
| **Brazil, Paraná wheat (SIDRA)** | **21.9%** |

Two things compound. Aggregating a continent cancels regional weather: a
drought in Henan is averaged against a good year in Xinjiang before the number
is published. And the series is an *estimate*, not a survey — PSD's Chinese
wheat yields land on round 10 kg/ha steps and repeat the same increment year
after year (26 distinct year-on-year changes across 41 transitions, against
40 out of 40 for a Brazilian state).

After a log technology trend absorbs the doubling of Chinese yields since 1982,
what remains is a residual of a few percent that is mostly revision and
rounding noise. There is close to nothing left for weather to explain, and a
model that claimed otherwise would be fitting the noise.

## Why the labels are national

`data.stats.gov.cn` returns HTTP 403 to this machine — a WAF URL ACL, not a
rate limit, so no key or backoff would help. Province-level official yields are
simply not obtainable, and every guide's provincial question has to be answered
against a national series.

That is also, independently, what the guides asked for. 동북3성 §1 calls the NBS
figures "훼손되어 있을 확률이 높습니다" and says to put USDA FAS at the top of the
feature stack; 장강 §4 says to scrape USDA/ECMWF rather than trust 통계국; 허난 §4
points out that Beijing reported a 0.9% wheat decline in 2023 while importing
record volumes of milling wheat. USDA PSD is that recommended source. It is
just national.

The cost differs sharply by config, and is carried in each one as
`region_share`:

| config | region's share of the national target |
|---|---|
| `henan_wheat` | Huang-Huai-Hai ≈ 75% — nearly a regional target |
| `northeast_soy` | ≈ 40% |
| `northeast_corn` | ≈ 30% |
| `yangtze_rice` | majority, but mixed with two other cropping systems |
| `south_china_rice_area` | minority; most movement is elsewhere and is policy |
| `shandong_vegetables` | ≈ 10% — the weakest match in the set |

## Data

| | source | span | key |
|---|---|---|---|
| Grain & oilseed targets | USDA PSD bulk CSV, national | 1960–2026 | none |
| Vegetable target | FAOSTAT bulk CSV, national | 1961–2024 | none |
| Weather | NASA POWER daily, 27 points | 1981– | none |
| ENSO | NOAA CPC ONI | 1950– | none |
| Trade | UN Comtrade via this repo's Worker proxy | 2000– | held server-side |

Wind and radiation are kept in the weather cache, unlike the Brazil pipeline
which discards them after computing ET0. Henan's 干热风 index needs wind inside
a three-way conjunction and Shandong's greenhouse index needs radiation
directly.

## Results

Forward chaining, trend refit inside every fold, scored against the best
available trend-only baseline over the most recent folds.

| model | target | vs trend | verdict |
|---|---|---:|---|
| import_soybeans | soybean imports, 1000 MT | −18.0% | no skill (pre-registered set) |
| import_corn | corn imports, 1000 MT | −29.6% | no skill; only 17 years |
| shandong_vegetables | yield, kg/ha | −56.6% | no skill |
| northeast_corn | yield, kg/ha | −76.0% | no skill |
| south_china_rice_area | area, 1000 ha | −107.7% | no skill |
| henan_wheat | yield, kg/ha | −119.5% | no skill |
| northeast_soy | yield, kg/ha | −135.0% | no skill |
| yangtze_rice | yield, kg/ha | −159.7% | no skill |

The negative numbers are large because the trend baselines are extraordinarily
good — Chinese national wheat is predicted to within ~163 kg/ha by a trend
alone, on a 5,900 kg/ha crop. Relative skill against a near-perfect baseline
punishes any deviation heavily. The honest reading is not "these models are
badly broken" but "there was nothing to add".

**The import models were expected to do better and did not.** Their target is
counted at the dock rather than estimated and swings genuinely from year to
year, so the variance problem that sinks the yield models does not apply. What
sinks these instead is sample size: 30 annual observations for soybeans and 17
for corn, against a trend that already explains most of a series which
quadrupled. Thirty rows cannot separate a feed-demand signal from a trend.

The hog inventory the guide centres its framework on **is** implemented here —
USDA PSD estimates China's sow and total swine herd even though China no longer
publishes it usefully — and it does not help. That is a result about annual
resolution, not about the guide's reasoning: the hog cycle is real, but at one
observation a year there is not enough of it to fit.

## The features are not the problem

Before concluding that the weather signal is absent rather than that the
formulas are wrong, each guide's headline variable was checked against events
it is supposed to detect. Two bugs were found this way and fixed:

- **Henan pre-harvest rain** was computed over June alone. The 2023 Henan 수발아
  disaster — the event the whole guide is built around — fell on 25–31 May and
  ranked 30th of 42 seasons. The guide says "5월 하순~6월 초"; on the correct
  25 May–10 June window, 2023 ranks 4th.
- **Northeast frost penalty** used a maturity threshold of 1600 GDD against a
  region that accumulates ~1410 on average, so the crop never reached maturity,
  every October frost scored as damage, and the variable degenerated into a
  proxy for warming (its six largest values were all 1984–93). Corrected to
  1300 for corn and 1100 for soy, it now ranges 0.01–1.85 with genuine
  zero-damage seasons.

After the fixes the variables behave: Yangtze `heat_penalty` ranks 1994, 2022
and 2013 as its three worst heat seasons, which is what the record says.
`dhw_days` picks out 2000 and 2007. The physics is firing; the target is not
responding, because the target is a smoothed national aggregate.

## Things that are not weather

Stated per config in `non_weather_drivers` and published in the forecast JSON:

- **shandong_vegetables** — output is set by how much greenhouse structure
  exists, which is an investment series. The guide says so itself in §1:
  protected crops are largely insulated from outside weather.
- **south_china_rice_area** — cropping intensity is set by the minimum purchase
  price, rural wages, urbanisation, and since 2021 the 退林还耕 campaign. Policy
  dominates weather by a wide margin here.
- **northeast_corn / northeast_soy** — the 2016 end of corn stockpiling and the
  repeatedly retuned Heilongjiang rotation subsidy move area and yield directly.
- **henan_wheat** — the guide's own example is the trap: a tonnage series cannot
  represent a *quality* failure, so the 2023 sprouting disaster, which sent
  milling-wheat imports to a record, is largely invisible in this target by
  construction.

## Known departures from the guides

- **Sentinel-1 SAR planted-area recalculation** (동북3성 §2A) is not implemented.
  Area is taken as published and only yield is modelled.
- **CNN-LSTM double-cropping classification** (화남 §3) is not implemented.
  National harvested area stands in as an aggregate proxy for cropping
  intensity — a much weaker instrument, and a screening indicator rather than a
  compliance measurement.
- **Swin-UNet greenhouse mapping** (산둥 §2A) is not implemented. Greenhouse
  expansion is left entirely to the technology trend. This is the largest
  departure in the set.
- **SIF** (허난 §2A) is omitted: the satellite record starts in 2007 and would
  halve the series.
- **Dynamic NDVI crop calendar** (장강 §3) is replaced by a fixed July–August
  heading window; MODIS starts in 2000.
- **Sentinel-1 inundation masking** (장강 §2B) is replaced by the heaviest 7-day
  rainfall total, named `max_7day_rain`.
- **Temporal Fusion Transformer, hog inventory, NLP policy scoring** (거시 §3)
  are not implemented — ~40 annual rows cannot support a TFT, and China does not
  publish herd numbers at usable frequency. Soybean-meal consumption is the
  feed-demand proxy.
- **Robust loss weighting** (동북3성 §4, 허난 §4) is deliberately not implemented.
  It asks for down-weighting seasons where the official yield diverges from
  USDA's. Here USDA *is* the label, so there is no divergence left to
  down-weight; the guides' intent is satisfied by the choice of source.

## Design decisions worth knowing

- Features are computed **per point, then production-weighted** — never the
  reverse. This matters more here than in Brazil because nearly every China
  variable is a threshold *conjunction*: a regional mean of temperature,
  humidity and wind almost never satisfies `Tmax ≥ 30 AND RH ≤ 30 AND wind ≥ 3`
  simultaneously, even in a week when half the North China Plain sat under a
  dry-hot wind.
- The target column is `target`, not `yield_kg_ha`. `south_china_rice_area`
  targets **harvested area**, because abandoning the second rice crop *raises*
  yield per harvested hectare and so is invisible in a yield series — area
  counts each crop separately and can see it.
- Winter wheat rolls over to the next season in **October**, when the crop is
  sown, not in August when it is harvested. Rolling over at harvest spent two
  months forecasting a crop that did not exist yet.
- Import models carry a **regime restriction**: soybeans from 1996 (China was a
  net exporter before liberalisation) and corn from 2009. A log trend fitted
  across five orders of magnitude produced a baseline RMSE of 298,000 thousand
  MT against a series whose maximum is 113,000.
- Same-year domestic consumption is **excluded** from the import features. On a
  balance sheet imports ≈ consumption − production + stock change, so including
  it would recover an accounting identity and report it as forecasting skill.

## Season availability

Three models decline to forecast for part of the year, by design. Northeast soy
and corn need September–October frost data; South China needs the late-September
cold-dew window. Before those months have happened the features do not exist and
the model returns "season has no observed weather yet" rather than a number
manufactured from climatology.

## What would actually change the answer

Not better features, and not more of them — adding features is what produced
the false positive above.

Two things would:

**Province-level or satellite-derived yields**, restoring the variance that
national aggregation destroys. This is what the guides' satellite methods were
designed to produce. `satellite.py` is the first step: MODIS NDVI/EVI/LST,
cropland-masked, per region, 2001 onward.

**Monthly rather than annual resolution** for the import models. Comtrade
serves monthly trade and the Worker proxy already accepts `freq=M`, which would
turn 30 observations into roughly 360. The guide asks for a 3-6 month forecast
horizon anyway, so monthly is the native resolution of the question.
