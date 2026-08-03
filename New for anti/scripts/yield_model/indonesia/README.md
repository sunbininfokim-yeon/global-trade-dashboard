# Indonesia climate-to-production models

This package implements the immediate forecasting objective: measure whether
historical climate deviations explain Indonesian crop yield/production after a
technology trend is removed, and use only relationships that beat a trend-only
forecast in forward chaining.

It covers four national FAOSTAT commodities:

| key | target commodity | climate geography |
|---|---|---|
| `indonesia_rice` | Rice | Java + South Sulawesi + South Sumatra |
| `indonesia_oil_palm` | Oil palm fruit (FFB) | Sumatra + Kalimantan |
| `indonesia_coffee` | Coffee, green | six main coffee belts |
| `indonesia_rubber` | Natural rubber in primary forms | Sumatra + Kalimantan |

The label remains national because a consistent 40-year open province series
is not yet wired in. The weather is not a national centroid: crop features are
derived at multiple production points first and then weighted. This is the
first defensible baseline; BPS province panels can later replace the label
without changing the model/output contract.

## Run

From `scripts/yield_model`:

```bash
PYTHONPATH=. python3 -B -m indonesia.collect
PYTHONPATH=. python3 -B -m indonesia.train
PYTHONPATH=. python3 -B -m indonesia.backtest --years 5
PYTHONPATH=. python3 -B -m indonesia.predict --year 2026
PYTHONPATH=. python3 -B -m indonesia.run_forecast 2026
```

Artifacts:

- `training/*.csv`: annual raw climate features, prior-20-year anomalies, and
  FAOSTAT yield/area/production.
- `models/*.json`: coefficients and measured forward-chaining skill.
- `public/data/indonesia_yield_forecast.json`: current yield, area and total
  production forecast with 68%/95% ranges.

## Method

For each target (yield, harvested area and production):

1. Fit a log-linear technology/structural trend inside every historical fold.
2. Convert each crop-specific climate feature to a z score against only the
   preceding 20 seasons.
3. Fit ridge regression to the log deviation from trend. Ridge strength is
   selected by leave-one-out inside the training fold.
4. Forward-chain one year at a time and compare with the trend-only baseline.
5. Stop the climate adjustment unless there are at least 25 complete seasons
   and at least five seasons per fitted weather parameter, and recent forward
   skill is at least 10% better than trend alone.
6. Stop the operational forecast itself when the recent five-fold MAPE exceeds
   15%. A rejected value may remain as a diagnostic trend, but its public point
   estimate and interval are null.

## Variables by crop and geography

All weather variables are calculated at each point first, combined with the
listed production weights, and converted to a z score using only the preceding
20 seasons. NOAA ONI for the preceding Indonesian dry season is an additional
candidate control. These are hypotheses tested by validation, not assumed
causal relationships.

### Rice — Java, South Sulawesi and South Sumatra

Points: Indramayu (24%), Grobogan (23%), Ngawi (25%), Sidrap (16%) and
Banyuasin (12%). Candidate variables are wet-season onset delay; October–March
rainfall; January–March root-zone soil moisture; extreme degree-days above
33°C; January–March solar radiation; and the longest January–March dry spell.
The predeclared core set is onset delay, soil moisture, heat and main-season
rainfall. Area additionally tests onset, soil moisture and rainfall.

### Oil palm fruit — Sumatra and Kalimantan

Points: Riau (25%), North Sumatra (18%), South Sumatra (17%), Jambi (13%),
West Kalimantan (12%) and Central Kalimantan (15%). Candidate variables are
June–October root-zone soil moisture one and two years before harvest,
one-year-lag rainfall, maximum vapour-pressure deficit, longest dry spell, and
August–October solar radiation as a limited haze proxy. The core set is lag-1
and lag-2 soil moisture plus lag-1 VPD. Area is trend-only because no defensible
annual weather-to-planted-area mechanism was specified.

### Green coffee — Sumatra, Java and South Sulawesi

Points: Lampung (27%), South Sumatra (23%), Aceh/Gayo (14%), North Sumatra
(14%), East Java (12%) and South Sulawesi (10%). Candidate variables are
July–September soil moisture and VPD before flowering; October–December
rainfall; November–March fungal-risk days and wet days; and wet-season solar
radiation. The core set is pre-flowering soil moisture/VPD, flowering rainfall
and fungal-risk days. Area is trend-only. The national label mixes Arabica and
Robusta, so these variables cannot identify cultivar-specific responses.

### Natural rubber — Sumatra and Kalimantan

Points: South Sumatra (31%), North Sumatra (18%), Riau (14%), Jambi (14%),
West Kalimantan (13%) and South Kalimantan (10%). Candidate variables are
January–April wet tapping days, weather-based fungal-risk days and tapping
rainfall; plus July–October lagged root-zone soil moisture and VPD. The core set
excludes tapping rainfall. Area is trend-only. Disease incidence, rubber price,
labour and tapping intensity are not observed by this weather model.

## Current validation result

The collected table has 39 labelled production seasons through 2024, but the
strict prior-20-year anomaly rule leaves only 19 complete climate-training
seasons. That is below every weather-model sample gate (25–40 seasons depending
on feature count). No Indonesian crop currently receives a climate adjustment.
Rice and coffee may emit a clearly labelled trend-only production baseline
where recent backtests pass. Oil-palm production is stopped because its latest
backtest error exceeds 15%, and rubber production is stopped because both
recent average and latest errors fail the gate. More features or a more complex
AI model would make this small-sample problem worse, not solve it.

The live season is assembled as NASA POWER observation, then 16-day Open-Meteo
temperature/precipitation/radiation forecast, then the prior-20-year daily
climatology. Open-Meteo soil moisture is never used.

## Important limitations

- FAOSTAT's recent oil-palm production/yield is estimated and harvested area is
  imputed; the flags are retained in the training table and forecast JSON.
- National coffee combines Arabica and Robusta, masking different calendars and
  biennial cycles.
- Rubber price and tapping intensity, palm age/replanting, and rice irrigation
  releases are omitted. They are explicitly reported as non-weather drivers.
- The direct production forecast is the headline. `yield × area` is also emitted
  as a cross-check; disagreement diagnoses target/area problems rather than
  being silently averaged away.
- Feature-set selection sees the same forward folds reported in the artifact.
  The season-by-season last-five-year report is therefore a configuration
  backtest, not a fully nested model-selection test.
