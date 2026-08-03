# Evidence map for West African cocoa analysis

This note records what the cited studies and institutions contribute to the **data
design**, rather than copying their algorithms.

## African field evidence

- Ghana's farm-level rainfall study followed 96 farms in Ashanti, Brong-Ahafo,
  Eastern and Western regions from 2012 to 2016. Its value for this project is the
  observed combination of farm yield, rainfall, planting material, management and
  soil properties. A short research panel cannot be substituted with national totals.
  <https://doi.org/10.1016/j.ecolmodel.2019.108790>
- A Ghana Harmattan experiment measured sap flow, radiation above/below canopy,
  soil moisture, temperature, humidity and rain. It supports monitoring atmospheric
  drought and soil drought separately; dust alone is not the plant-response label.
  <https://doi.org/10.1016/j.agrformet.2021.108670>
- A 2026 Côte d'Ivoire survey of 158 farms found yield differences associated with
  fertilisation, planting geometry and planting material, while farmers reported
  insects, black pod, soil fertility, tree mortality and drought as constraints.
  Climate-only predictions therefore need explicit management/disease caveats.
  <https://doi.org/10.1038/s41598-026-42681-y>
- Ghana yield-gap research used field management, tree density, fungicide/black-pod
  control and water-limited yield. The underlying data are not publicly shareable,
  which is a practical limit for reproducing a farm-level model.
  <https://doi.org/10.1016/j.agsy.2022.103466>

## American institutional data

- NASA POWER supplies the reproducible 1981-present climate screen: rain,
  temperature, humidity/dewpoint, wind, radiation and modelled root-zone wetness.
  It is coarse and is tested as a source, not treated as farm truth.
  <https://power.larc.nasa.gov/>
- NASA SMAP L4 supplies 2015-present 0-100 cm root-zone moisture at 9 km and is
  accessible through Earth Engine. It is a short satellite-era comparison layer.
  <https://developers.google.com/earth-engine/datasets/catalog/NASA_SMAP_SPL4SMGP_008>
- USDA FAS GAIN and PSD distinguish marketing-year production, exports and analyst
  forecasts. Forecast values must never be mixed into final observations.
  <https://www.fas.usda.gov/data>
- UCSB/USGS CHIRPS supplies Africa-oriented rainfall from 1981 and is available in
  Earth Engine as `UCSB-CHG/CHIRPS/DAILY`.

## European and international data

- Sentinel-2 optical imagery and Sentinel-1 radar are complementary inputs for cocoa
  area/canopy monitoring. A high-resolution study trained on more than 100,000
  georeferenced farms demonstrates why labelled polygons, canopy height and repeated
  observations are essential. It does not imply that unlabelled S1/S2 imagery is a
  ready cocoa classifier. <https://doi.org/10.1038/s43016-023-00751-8>
- ERA5-Land provides 1950-present weather and four soil-water layers at about 9 km.
  CAMS EAC4, not ERA5-Land, provides explicit dust aerosol variables from 2003.
  <https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land>
  <https://ads.atmosphere.copernicus.eu/datasets/cams-global-reanalysis-eac4>
- FAO WaPOR provides Africa-wide ET, relative soil moisture, biomass, phenology and
  land-cover layers via a token-free v3 API. These layers still require a cocoa mask.
  <https://www.fao.org/in-action/remote-sensing-for-water-productivity/wapor-data/en>
- The public ICCO statistics page exposes the last three cocoa years; the detailed
  history from 1960 is in the subscription Quarterly Bulletin. ICCO therefore cannot
  be described as a fully open long training label.
  <https://www.icco.org/app/statistics/>

## Corrections to the original regional notes

1. The current folder contains only Côte d'Ivoire/Ghana cocoa, not a complete
   West-Africa region-by-crop catalogue.
2. Côte d'Ivoire and Ghana do publish useful official data. The problem is unequal
   history, definitions and machine readability—not total absence.
3. A weather threshold can be called a black-pod **risk proxy**, not a forced yield
   deduction, until disease incidence/loss labels are available.
4. Forest-loss pixels are exposure evidence, not automatic proof of EUDR ineligibility
   or tonnes to subtract from total production.
5. Under the current EU schedule, EUDR application begins 30 December 2026 for large
   and medium operators and 30 June 2027 for other micro and small operators.
   <https://environment.ec.europa.eu/topics/forests/deforestation/regulation-deforestation-free-products_en>
