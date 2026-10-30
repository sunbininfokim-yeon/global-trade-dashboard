# Panama Canal ACP research model

This module is intentionally separate from the deployable shipping snapshot.
It is a local research pipeline, not a published forecast.

## Causal structure

```text
precipitation + reservoir evaporation + trailing 12-month water balance
    -> Gatun Lake level (monthly additive GAM; paper specification)
    -> ACP official booking slots / draft limits / maintenance notices
    -> official ocean-going transits
```

The first arrow follows Muñoz et al. (2025), *Drying of the Panama Canal in a
Warming Climate*, Geophysical Research Letters. Its published R implementation
uses four additive terms—monthly precipitation, reservoir evaporation, and
their trailing 12-month sums—20 spline bases per term, 3x weight on the lowest
and highest decile of lake levels, and a final-year chronological validation.
This module preserves that design in a Python additive-spline approximation;
it labels the result as research-only because it is not byte-for-byte identical
to the authors' `mgcv::gam(..., method = "REML")` implementation.

The second arrow is not estimated: ACP Advisories are the operational ground
truth. The final arrow is estimated only from authorized historical monthly
observations and is withheld unless chronological validation outperforms a
seasonal baseline.

An ENSO challenger adds NOAA ONI with a two-month availability lag. It is
retained only when it improves the exact same holdout. Current-month arrivals,
used booking slots and waiting time are excluded from the transit forecast to
prevent target-time leakage. The response model predicts the monthly change
from the previous official transit average and must beat both seasonal and
persistence baselines.

The model never maps water level directly to DWT, vessel count, or a closure
percentage. In 2023-24 ACP explicitly adjusted daily capacity, booking slots
and maximum draft as water-management decisions, so a direct level-to-traffic
coefficient would be structurally wrong.

## Inputs and rights boundary

| Input | Role | Storage |
|---|---|---|
| ACP Gatun historical CSV | observed daily lake level, aggregated locally to monthly mean | temporary local download only |
| ACP Gatun Water Indicators PDF / projection CSV | current water level, published short-run projection, draft and surcharge | temporary local download only |
| ACP Advisory to Shipping | booking-slot, draft and maintenance labels | temporary local download only |
| STRI-hosted ACP precipitation / ERA5-Land | paper-compatible rainfall / evaporation preparation | user-local path only, with required attribution |
| NASA POWER PRECTOTCORR / EVLAND | reproducible free sensitivity proxy, not paper-identical reservoir evaporation | temporary user-local JSON only |
| NASA GPM IMERG daily Late Run | recent satellite precipitation monitor over a declared rectangular Gatun-area proxy | downloaded to a temporary directory; only local derived daily means retained |
| NOAA CPC ONI | lagged ENSO challenger | temporary user-local text only |
| C3S/NMME ensemble | next-month precipitation/evaporation forecast members | source-specific extraction to local CSV |
| ACP monthly Canal Operations Summary | official transit, booking and congestion labels | fetched in memory; parsed local report only |
| authorized monthly history CSV | model training and time-ordered test labels | user-local path only |
| GPM/ERA5/ONI (optional historical columns) | precipitation, evaporation, ENSO covariates | user-local path only |

No ACP PDF, CSV, or raw history is added to Git or `public/data/` by this
module. ACP's Gatun page currently permits information access but says copying,
distribution, publication and derivative works require prior written consent.
Therefore no scheduled ACP collector or public ACP-derived forecast is enabled
until ACP supplies permission. STRI's ACP-hosted hydrology material also
requires credit to ACP's Meteorology and Hydrology Branch.

## Local input routes

### A. Already-prepared monthly research table

```text
month,gatun_mean_ft,precipitation_mm,evaporation_mm,
oceangoing_transits_daily_average,booking_slots_per_day,
neopanamax_max_draft_ft,panamax_max_draft_ft,oni_lag_6w
2021-01,...
```

The first four fields are required for the hydrology layer. The next four are
required for the traffic layer. `oni_lag_6w` is optional and defaults to zero;
it is retained as a sensitivity variable, not a causal claim.

### B. Official daily Gatun level file + local monthly covariates

Use ACP's `Download_Gatun_Lake_Water_Level_History.csv` only in a local
research directory. The pipeline checks the official `DATE_LOG` and
`GATUN_LAKE_LEVEL(FEET)` columns and refuses any month with fewer than 20
observed daily values. Supply a separate local file with at least:

```text
month,precipitation_mm,evaporation_mm
1965-01,...
```

The covariate file can also include the official transit, slot and draft
columns shown above. `evaporation_mm` must be a documented reservoir
evaporation preparation. Do not substitute an undocumented weather-app value
and call the output paper-equivalent.

## Run locally

```bash
cd "New for anti/scripts/shipping_capacity"
python3 -m pip install -r requirements-ml.txt
python3 build_panama_acp_model.py --output /private/tmp/panama_acp_report.json
python3 build_panama_acp_model.py --history /private/tmp/acp_monthly_history.csv \
  --advisory-url 'https://pancanal.com/wp-content/uploads/2023/01/ADV48-2023-Reduction-in-Transits-Due-to-the-Ongoing-Deficit-in-Precipitation-in-the-Canal-Watershed.pdf' \
  --output /private/tmp/panama_acp_report.json
python3 build_panama_acp_model.py \
  --acp-level-history /private/tmp/Download_Gatun_Lake_Water_Level_History.csv \
  --monthly-covariates /private/tmp/panama_monthly_covariates.csv \
  --output /private/tmp/panama_acp_report.json
```

The no-history run is expected to return `history_required` and no traffic
forecast. That is a successful safety result, not a missing-value fallback.
The official ACP projection file is a source for an operational nowcast only;
it is not treated as a model-generated traffic forecast.

### Full local research run

```bash
python3 build_panama_acp_model.py \
  --acp-level-history /private/tmp/acp_gatun_history.csv \
  --acp-nasa-proxy \
  --nasa-power-daily /private/tmp/nasa_power_gatun.json \
  --oni-history /private/tmp/noaa_oni.txt \
  --projection-url 'https://evtms-rpts.pancanal.com/eng/h2o/Gatun_Water_Level_Projection.csv' \
  --projection-month 2026-09 \
  --operations-index-url \
  --output /private/tmp/panama_acp_full_model.json
```

For an external seasonal forecast, add
`--climate-forecast-ensemble /private/tmp/panama_monthly_ensemble.csv`.
The CSV contract is:

```text
source_id,member_id,month,precipitation_mm,evaporation_mm,oni
c3s,m01,2026-09,...
```

The forecast month must be the calendar month immediately after the last
monthly hydrology observation. Source-level ranges are retained; pooled member
ranges carry a warning because forecast systems can have unequal ensemble
sizes.

### Recent satellite observation monitor

Set `NASA_EARTHDATA` (or the legacy `EARTHDATA_TOKEN`) only in the local
process environment, then add `--gpm-imerg-recent-days 7` to a full run.  The
collector reads up to 31 GPM IMERG daily Late Run files through Earthdata,
calculates a latitude-weighted mean in a documented rectangle around Gatun,
and deletes each raw NetCDF4 file at the end of the run.  This produces a
recent-observation monitor; it does **not** replace the long NASA POWER series
in the hydrology backtest or become a water-level/transit forecast without a
separate cross-product bias calibration.

Add `--gpm-imerg-compare-prior-year` to compare the actual returned GPM days
with the identical calendar dates one year earlier.  The result is withheld if
any matching previous-year day is unavailable.  It compares satellite rainfall
only: never interpret it as a year-over-year change in Gatun storage, traffic
or expected transits.

## Report provenance

Every local report carries a `data_sources` catalog with NASA GPM, NASA POWER,
NOAA CPC ONI, the Muñoz et al. research basis, optional Copernicus C3S and the
separate ACP local-only boundary.  This is designed for a portfolio methods
page: it states each source's role, URL and non-overclaiming use boundary.

## Forecast interpretation

- `official_acp_projection_not_model_output`: ACP's own published water-level
  estimate; it takes precedence for the near term.
- `research_only_external_ensemble_forecast`: modelled lake-level distribution
  from declared external climate members.
- `research_scenario_with_carried_forward_operations`: transit response using
  ACP projected water level while unavailable booking/demand variables are
  transparently carried forward. Never publish this as an ACP forecast.
- `withheld`: the model failed its baseline gate or lacks a required label.

## Sources

- Muñoz et al. (2025), [doi:10.1029/2025GL117038](https://doi.org/10.1029/2025GL117038)
- Muñoz (2025), [open CC BY R implementation](https://doi.org/10.5281/zenodo.15044682)
- [ACP Gatun Water Indicators](https://evtms-rpts.pancanal.com/eng/h2o/GatunWaterIndicators.pdf)
- [ACP Advisory to Shipping](https://pancanal.com/en/maritime-services/advisory-to-shipping/)
- [STRI ACP physical-monitoring data and attribution terms](https://striresearch.si.edu/physical-monitoring/panama-canal-authority-with-direct-links/)
- [NASA POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/)
- [NOAA CPC ONI](https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt)
- [NASA GPM IMERG](https://gpm.nasa.gov/data/imerg)
- [Copernicus C3S seasonal forecasts](https://www.ecmwf.int/en/forecasts/datasets/seasonal-forecast-daily-and-subdaily-data-single-levels)
