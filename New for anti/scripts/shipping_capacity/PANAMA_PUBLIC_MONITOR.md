# Public Panama rainfall monitor

This portfolio module is intentionally independent from the local ACP research
pipeline.  It uses only NASA GPM IMERG daily Late Run observations to describe
recent rainfall in a transparent rectangular monitor around the Panama Canal.

It does **not** collect, contain, infer, or display canal-operator data,
water levels, draft limits, booking slots, vessel transits, shipping capacity,
or a transit forecast.

## Public output

The generated JSON contains:

- recent observed satellite precipitation;
- the matching-calendar-day previous-year comparison;
- GPM product, URL and attribution; and
- explicit exclusions so a UI cannot present it as a canal-traffic forecast.

Raw NetCDF4 files are processed in a temporary directory and deleted after the
run.  The Earthdata token is read only from `NASA_EARTHDATA` (or legacy
`EARTHDATA_TOKEN`) in the runtime environment.  It is never written to JSON,
source code or Git.

## Run locally

```bash
cd "New for anti/scripts/shipping_capacity"
python3 -m pip install -r requirements-ml.txt
python3 build_panama_public_monitor.py --as-of-date 2026-09-01 \
  --output /private/tmp/panama_climate_monitor_v1.json
```

GPM Late Run availability can lag the requested date.  The script bases its
previous-year comparison on the days actually returned, so it never compares a
short current series against a longer previous-year series.

## Attribution

> Rainfall observations: NASA GPM IMERG daily Late Run.  This dashboard
> reprocesses satellite observations and is not a NASA forecast, endorsement,
> or operational canal-traffic assessment.

NASA GPM IMERG: <https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDL_07/summary>
