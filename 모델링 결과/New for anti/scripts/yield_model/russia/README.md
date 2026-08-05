# Russia winter wheat (Phase-1)

Southern export belt + Central Black Earth winter-wheat yield models.

Authority: `Regions/흑해_통합/파이프라인_딥다이브_RU_UA_Phase1.md`  
Contract: `scripts/yield_model/DATA_LAYOUT.md` → `public/data/russia_yield_forecast.json`

## What is in scope

| Item | Status |
|---|---|
| Zones: South (Krasnodar, Rostov, Stavropol) + CBE (Belgorod, Voronezh, Kursk, Tambov) | yes |
| NASA POWER daily (+ GWETROOT, RH, wind, radiation) | yes |
| Winterkill bare-frost from POWER Tmin; optional ERA5-Land snow | yes (`--snow`) |
| Open-Meteo short forecast T/P only | yes (predict) |
| Labels: USDA PSD national Russia **Wheat** | yes (see `labels.md`) |
| Rosstat oblast yields | deferred path |
| Ukraine / export-duty Logit / AIS | out of scope |

Crimea and wartime “new regions” are not in the point set.

## Setup

From repo root (or any cwd):

```bash
cd "New for anti/scripts/yield_model"
python3 -m pip install pandas numpy scipy scikit-learn
```

## Pipeline

```bash
cd "New for anti/scripts/yield_model"

# 1) Build training tables (network: POWER + PSD + ONI)
python3 -m russia.collect
# optional winter snow insulation join (Open-Meteo ERA5-Land):
python3 -m russia.collect --snow

# single region:
python3 -m russia.collect southern_winter_wheat

# 2) Train ridge models (forward-chaining skill)
python3 -m russia.train

# 3) Live season → dashboard JSON
python3 -m russia.run_forecast
# or a fixed harvest year:
python3 -m russia.run_forecast 2026
```

Outputs:

| Artifact | Path |
|---|---|
| Training CSVs | `russia/training/<region_key>.csv` |
| Model JSON | `russia/models/<region_key>.json` |
| Forecast | `public/data/russia_yield_forecast.json` |
| API cache | `russia/cache/` (gitignored via `yield_model/.gitignore`) |

## Regions

| key | Points | Critical window |
|---|---|---|
| `southern_winter_wheat` | Krasnodar, Rostov, Stavropol | May–Jun grain fill |
| `cbe_winter_wheat` | Belgorod, Voronezh, Kursk, Tambov | May–Jul |
| `russia_winter_wheat` | South + CBE production-weighted | May–Jun |

## Dry run / tests

```bash
# Unit test on synthetic daily (no network)
python3 -m russia.test_dry_run

# Import smoke (needs training tables + models if forecasting)
python3 -c "from russia.regions import ALL; print([r.key for r in ALL])"
```

## Skill honesty

National PSD yield moves slowly and mixes spring wheat / Volga weather this package does not sample. **Low or negative skill vs trend is a valid Phase-1 outcome** and is written into the JSON (`beats_trend`, `low_confidence`). Do not manually “fix” the score.

## Design rules carried from the repo

- Soil moisture from **POWER GWETROOT only** — never Open-Meteo soil.
- Forecast tail: Open-Meteo **temperature + precip** (+ dewpoint for VPD); soil filled from POWER DOY climatology.
- Technology trend in log space; weather = residual ridge; trend refit **inside** each CV fold.
