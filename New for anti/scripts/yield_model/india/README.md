# India regional yield models

Three region-crop models, one per guide in `기후 모델링/Regions/인도`. Unlike
Brazil's nine, these three share even less methodology with each other:
Punjab wheat is a pure terminal-heat problem on an irrigated crop, Madhya
Pradesh soybean is a monsoon-*timing* problem on a rainfed one, and
Vidarbha/Gujarat cotton is a two-sided drought/pest problem the guide says a
linear model cannot represent at all. Each `build` function in `regions.py`
implements only its own guide's derived variables.

```bash
python3 -m india.collect        # build training tables
python3 -m india.train          # fit + validate, writes models/
python3 -m india.backtest       # hold out the last 5 published seasons
python3 -m india.predict --year 2026
python3 -m india.run_forecast   # writes public/data/india_yield_forecast.json
```

## Data

| | source | span | key |
|---|---|---|---|
| Yield | ICRISAT District Level Database, **district level** | 1990–2019 (596 districts, 20 states) | none |
| Weather | NASA POWER daily | 1984– (radiation opens later than meteorology) | none |
| ENSO | NOAA CPC ONI | 1950– | none |
| IOD | NOAA PSL HadISST Dipole Mode Index | 1870– | none |

**The labelled record is 30 seasons**, and ICRISAT's 1990 start is what binds
— not NASA POWER's 1984 radiation start. Thirty annual rows is thin: it is why
every guide's prescribed ML method is replaced by a regularised linear model
here (see Known departures), and it is why a negative result should be read as
"this did not survive at this sample size", not as "the methodology is wrong".
The series also ends in 2019, so seasons from 2020 on are unlabelled and can be
forecast but not scored.

District-level yield is what makes the region-specific methodologies
possible, the same argument `brazil/README.md` makes for IBGE SIDRA's state
level over FAOSTAT's national series -- only sharper here, because India spans
more agro-climatic zones than Brazil. Madhya Pradesh alone is over half of
India's soybean; a national average would blend a Punjab heatwave, a Malwa
monsoon failure and a Vidarbha dry spell into one number in which all three
cancel.

ICRISAT was chosen over the obvious alternatives:

- **FAOSTAT / USDA PSD** report India as one national figure, which cannot
  support any of these three guides.
- **data.gov.in** carries the official DES series but registration requires an
  Indian mobile number, so it is not obtainable from outside India.
- **ICRISAT DLD** needs no key and no registration, and is *district* level --
  finer than state. That matters most for cotton, where the guide names
  Vidarbha and Marathwada specifically rather than Maharashtra as a whole, and
  a state average would fold in the irrigated sugar belt around Kolhapur and
  Pune, a different farming system entirely.

Region yield is production-weighted by *actual* area, not by a fixed or
estimated weight:

    yield_region(y) = sum_d production_d(y) / sum_d area_d(y)

Both columns are published per district per year, so a district that did not
grow the crop in a given year contributes zero to both sums and drops out on
its own -- no weight has to be guessed.

ET0 is computed here by FAO-56 Penman-Monteith from POWER radiation, wind,
dewpoint and temperature, rather than taken precomputed, the same choice
Brazil's package makes and for the same reason: it is the FAO reference method
and the cotton guide's Moisture_Deficit needs it directly.

### Why the yield table is committed rather than fetched

`india/data/icrisat_apy.csv` is checked in, unlike every other input here.
That is deliberate.

The API serves one ~13 MB JSON blob with no server-side filter, and the
upstream server throttles to roughly 60-70 KB/s while enforcing a hard
per-request timeout near 90 seconds. The arithmetic does not work: an ordinary
connection cannot finish 13 MB inside 90 seconds, so the response is cut off
every time. Four attempts from a home connection all died with `IncompleteRead`
at the *identical* byte offset (6,078,207), which is what ruled out packet loss
and identified the timeout. Range requests are not honoured either -- a ranged
request restarts from zero rather than resuming -- so retrying cannot make
progress, it can only repeat.

A GitHub Actions runner has enough bandwidth to finish inside the same window;
in practice it took 50 seconds. So the fetch runs once from CI
(`.github/workflows/india_icrisat_fetch.yml`, manual `workflow_dispatch`) and
the tidy table is committed. `load_raw()` reads that file first and never
touches the network again, for anyone.

`_download()` still verifies the received length against `Content-Length`
before parsing, and that guard earns its place: a parallel fetcher that lacked
it silently committed a 6.15 MB fragment of the same dataset, which failed to
parse at all. Do not remove the check when re-running the snapshot.

## Results

*(fill in after `india.train` and `india.backtest` have been run against a
successful ICRISAT pull -- see the table in `brazil/README.md` for the format
this section should take: skill vs. trend, weather-only skill with lags held
out, and 5-year holdout MAPE per region-crop, ranked by verdict.)*

## Known departures from the guides

Every guide here names a machine-learning method that the labelled record --
roughly thirty seasons per region, once ICRISAT's span and NASA POWER's 1984
radiation start are both accounted for -- cannot support without fitting
noise. In each case the guide's own derived variables are implemented in
full and fed to the same ridge-on-log-yield regression used throughout this
repo; only the estimator is substituted, and the substitution is recorded on
the affected config in `regions.py` as well as here.

- **Hybrid LASSO-Random Forest** (wheat) -- LASSO variable selection over
  daily weather would select on noise at this sample size. The weekly-
  resolution heat tensor it was meant to search is collapsed to the guide's
  own named windows (THSDD, warm nights) instead. MODIS LST/NDVI from the
  guide's §3 are omitted: MODIS starts in 2000 and would roughly halve the
  usable record.
- **ENSO-coupled LSTM** (soybean) -- a recurrent network cannot be trained on
  ~30 rows without memorising them. The temporal narrative it was meant to
  learn -- onset delay, then flowering dry-spell stress, then harvest
  waterlogging -- is encoded explicitly as those three named features instead.
  This is the largest departure in the set.
- **XGBoost/LightGBM, linear regression explicitly banned** (cotton) -- the
  ban is about the response *shape*: cotton loses to drought on one side and
  to pest pressure on the other, and a linear model cannot turn around at a
  threshold. The non-linearity is moved into the features instead -- a signed
  moisture deficit and a pest-risk counter that only fires inside a
  temperature-humidity box give the regression both arms of the curve -- so
  that a ridge model, which ~20 post-Bt seasons can actually support, still
  carries the guide's inverted-U shape. The guide's irrigation-percentage
  categorical is not implemented; it would need a per-year district
  irrigation series joined in, which is not open data at this resolution.

## Things that may not be weather

Stated per config in `non_weather_drivers` and published in the forecast
JSON, so a low score reads as "weather does not drive this crop" rather than
"the model is broken":

- **punjab_wheat** -- MSP-assured procurement, subsidised tubewell power and
  canal rotation schedules set input intensity and sowing timing directly, and
  none of it is visible in a weather feed. Groundwater depletion is a slower
  constraint acting on the technology trend itself rather than on any single
  season.
- **mp_soybean** -- planted area moves with the relative price of soybean
  against maize and pulses; a change in the area mix shifts average yield with
  no change in weather. Seed replacement rate and yellow mosaic virus pressure
  are real, non-climate drivers too.
- **vidarbha_cotton** -- the crop in this set least explainable by weather.
  The 2002 Bt transition, seed pricing and availability, pink bollworm
  resistance spreading from about 2015, and MSP-relative pricing against
  soybean and pigeonpea all move planted area and input intensity year to
  year. ICRISAT reports cotton in lint terms, so a change in ginning ratio
  moves the series with no change in the field. (Confirmed against the data:
  the region averages 414 kg/ha over 2015-19, which is a lint figure -- seed
  cotton would run 1,000-1,500.)

## Structural note

`india/climate.py` deliberately does not import the region-neutral physics
(FAO-56 ET0, Gamma SPI) from `brazil/climate.py`, even though the equations
are identical. The two country packages need to be able to move
independently -- a change made to the Brazilian package for a Brazilian
reason must never silently alter what the Indian models compute -- so the
published, stable equations are duplicated rather than shared. A `common/`
package promoting them out of both would be a reasonable future refactor, but
should not be done as a side effect of building this package.

## Season conventions

Kharif crops (soybean, cotton) are sown and harvested inside one calendar
year, so their season rolls over with the calendar. Rabi wheat is sown from
November, so from November onward the "current" season is already next
year's harvest -- `collect.current_season()` encodes this per crop via
`calendar_year_crop`.
