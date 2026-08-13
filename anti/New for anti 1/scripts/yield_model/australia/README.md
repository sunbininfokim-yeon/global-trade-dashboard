# Australia state crop-yield models

This package is the phase-1, honestly validated benchmark for the guides in
`기후 모델링/Regions/호주`.  It separates Western Australia, South Australia
and Victoria wheat, and separates New South Wales and Queensland cotton.

```bash
cd scripts/yield_model
python3 -m australia.collect wa_wheat
python3 -m australia.train wa_wheat
python3 -m australia.run_forecast
```

`ABARES_STATE_XLSX=/path/to/state-data.xlsx` can pin a manually downloaded
Australian Crop Report workbook.  Without it, `abares.py` resolves the newest
quarterly state workbook and caches it for 30 days.

## What is carried over from HANDOFF_PROMPT.md

The statistical target remains:

    log(yield) = technology trend + weather anomaly

The trend and the feature scaler are refitted inside every forward fold.  Every
weather feature is a z-score against up to the preceding 20 seasons; the season
being predicted is never part of its own normal.  A log-linear trend-only model
is the baseline, and a weather model is operationally accepted only if it beats
that baseline by at least 10% both over all forward folds and over the most
recent folds.  Below 20% recent skill is marked low confidence.

Only three feature sets are tested, declared before looking at scores:

1. weather;
2. weather + root-zone soil wetness;
3. weather + soil wetness + large-scale climate drivers.

The JSON artifact records all three results and the search note.  Prediction
interval widths come from forward errors, not training residuals.

## Australia-specific corrections to the handoff

The handoff is a good global benchmark protocol, not an immutable scientific
model.  These points are treated as Australia-specific exceptions:

* NASA POWER is the reproducible phase-1 feed, not the intended final primary
  Australian feed.  SILO/BoM AGCD weather and AWRA-L root-zone soil water are
  the next registered source ablation.  POWER's coarse MERRA-2 wetness remains
  useful for a like-for-like global benchmark.
* A failed MODIS experiment on a different crop/region does not justify a
  universal NDVI ban.  Australian wheat literature supports testing NDVI as a
  later residual-correction layer, without shortening the long climate model.
* Fertiliser and variety need not enter this small statistical baseline because
  trend absorbs much of their long-run movement.  They cannot be declared
  irrelevant to APSIM/OZCOT or farm-level models.
* IOD, ENSO and SAM receive no forced sign or importance.  BoM explicitly notes
  that SAM impacts vary by season and region.  They survive only if their
  pre-registered ablation improves forward skill.
* The deprecated GEE collection
  `NASA_USDA/HSL/SMAP10KM_soil_moisture` is not used.  The later satellite step
  must use the current SMAP L4 collection and must compare percentile/anomaly,
  not splice raw SMAP values into POWER `GWETROOT`.

## Data and target definitions

| role | phase-1 source | important detail |
|---|---|---|
| state area and production | ABARES Australian Crop Report workbook | Forecast rows (`f`) are excluded; estimate rows (`s`) are identified in artifacts |
| daily weather and root wetness | NASA POWER | `PRECTOTCORR`, temperature, dew point, radiation, `GWETROOT` |
| ENSO | NOAA CPC ONI | realised-season diagnostic in this full-season benchmark |
| IOD | NOAA PSL HadISST DMI | realised-season diagnostic; forecast vintages are required for early warning |
| SAM | NOAA CPC AAO | tested for SA/Victoria only; no universal sign assumption |

ABARES financial-year labels require crop-specific conversion.  Winter wheat
`2025-26` is the 2025 harvest; summer cotton `2025-26` is the 2026 harvest.
Cotton yield is based on harvested area, while wheat yield is based on planted
area.  Those are not interchangeable target definitions.

## Known limits before the results are operational

* State labels cannot support the finer AAGIS/agroecological boundaries that
  should eventually replace state-wide point sampling.
* Point weights are equal sampling weights until annual crop-area masks provide
  defensible spatial weights.
* Cotton labels mix irrigated and dryland fields.  A production forecast needs
  a separate planted-area model driven by water allocations/storage, followed
  by separate irrigated and dryland yield models.
* The phase-1 French-Schultz variable is rainfall-only and is named
  `french_schultz_rain_limit`; it is not presented as potential yield until
  gridded PAWC and initial stored water are available.
* Full-season climate indices are diagnostic only.  A live July/August wheat
  forecast must use observed weather to the issue date and vintage-matched
  ACCESS-S/climatology after it; realised spring IOD, SAM or rainfall would be
  leakage.

`run_forecast` currently uses observations followed by 20 intact historical-
year weather paths.  Keeping each year's sequence preserves heat, frost and dry
spell extremes that a daily-average climatology would erase.  The interval
combines the scenario spread with forward-chaining error.  The JSON explicitly
reports `access_s_integrated: false`; it is a leakage-safe interim forecast,
not yet the registered ACCESS-S upgrade.

## Registered next experiments

1. Run the five state-crop screens and reject any model that loses to trend.
2. Replace POWER rainfall/temperature/root wetness with SILO or AGCD + AWRA-L,
   holding labels, folds and features fixed.
3. Add CSIRO Soil and Landscape Grid PAWC and a daily water balance.
4. For wheat only, fit a MODIS NDVI residual model on the 2000+ subset and test
   incremental forward skill rather than discarding the long climate history.
5. Add APSIM water-limited yield as a feature/teacher, not as ground truth.
6. Build cotton area and yield as separate systems using basin water data.
