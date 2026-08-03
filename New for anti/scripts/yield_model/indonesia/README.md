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
5. If recent forward skill is non-positive, publish the trend and expose the
   rejected climate adjustment as `candidate_weather_effect`; do not apply it.

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

