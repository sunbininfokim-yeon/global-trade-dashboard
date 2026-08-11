# Russia sunflower + wheat methodology (forecast 직전)

## Scope this pass

| Crop | Zones | Status |
|------|-------|--------|
| Winter wheat (grain-proxy labels) | South, CBE, belt, **Volga** | train |
| Sunflower | South, CBE, Volga, belt | train |
| Barley / maize | — | **deferred** (no oblast crop-specific yield in yearbook extract) |

**Forecast JSON is not run in this pass** (user request: stop before forecast).

## Data pipeline

```
Rosstat oblast yields (tochno-st Regions of Russia)
  wheat/grain: 13120000 + sown 13050000
  sunflower:   13160000 + sown 13070000
        │
        ▼
area-weighted zone target (kg/ha = c/ha × 100)
        │
NASA POWER daily (T, precip, GWETROOT, RH, wind, radiation)
  + optional ERA5-Land snow for wheat winterkill
        │
        ▼
features (wheat winterkill / sunflower flowering)
        │
        ▼
ridge residual on log yield trend  (china/australia pattern)
        │
        ▼
models/*.json   ← stop here (no run_forecast this pass)
```

## Authoritative literature → feature choices

### Wheat (existing + Volga)

| Source | Takeaway for code |
|--------|-------------------|
| Schierhorn et al. 2014 *ERL* — Russia wheat yield gaps | Oblast-scale drought / winterkill matter; zone split South vs continental Volga |
| Aase & Siddoway snow insulation; Fowler winter cereal survival | Bare-frost / snow proxies in `winterkill_*` |
| Package prior: South+CBE Rosstat grain labels | Keep cereals+legumes basket caveat (winter-wheat dominated in these oblasts) |

### Sunflower

| Source | Takeaway for code |
|--------|-------------------|
| SPbU Biology 2023 — Peredovik, North Caucasus ([doi](https://doi.org/10.21638/spbu03.2023.204)) | April precip (+); May–Aug heat / HTK stress; detrend before weather regression |
| Hydrometcenter Trudy 373 — CFO sunflower agromet forecast ([PDF](https://method.meteorf.ru/publ/tr/tr373/07.pdf)) | Physical–statistical yield models 1–3 months before harvest; CBE oblast relevance |
| MSU Soil Sci. WOFOST RU hybrids (sunflower, barley, maize) | Process benchmark only — we stay ridge+trend like other yield_model packages |
| Regional production studies (Volga / Saratov share) | Include Volga as first-class sunflower zone |

### Feature map (sunflower)

| Feature | Window | Role |
|---------|--------|------|
| `precip_april`, `sm_april` | Apr | Establishment / early moisture |
| `edd_flower`, `heat_days_flower`, `vpd_flower` | Jun–Aug | Flowering heat |
| `sm_flower`, `sm_stress_flower`, `precip_flower` | Jun–Aug | Flowering drought |
| `precip_may_aug`, `sm_season` | May–Aug | Season moisture |
| `radiation_season`, `gdd_season` | Apr–Aug | Biomass / oil-related thermal & light |

## Honesty

- Yearbook **does not** split winter vs spring wheat; Volga “winter wheat” key still uses grain-basket labels.
- Sunflower 2000–2021 only (no 2024 patch yet). Sentinels (−8.8e7 style) dropped in `load_curated_oblast_csv`.
- Barley / maize: Rosstat yearbook extract has **no** crop-specific yield series → next pass needs EMISS crop IDs or PSD national fallback.

## Train results (this pass — no forecast)

| Model | skill vs trend | Verdict |
|-------|----------------|---------|
| cbe_winter_wheat | +36.6% | usable |
| volga_winter_wheat | +20.5% | usable |
| russia_sunflower | +31.5% | usable |
| southern_winter_wheat | +9.4% | usable |
| southern_sunflower | +5.1% | usable |
| russia_winter_wheat | −1.6% | trend only |
| volga_sunflower | −5.9% | trend only |
| cbe_sunflower | −41.5% | trend only (overfit / short folds) |
