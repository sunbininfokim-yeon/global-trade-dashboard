# Ukraine winter wheat (Phase-2 kickoff)

Central / Southern / Western winter-wheat scaffolds + sunflower stubs.

Authority: `Regions/흑해_통합/방법론_우크라이나_yield_kickoff.md`  
Contract (later): `scripts/yield_model/DATA_LAYOUT.md` → `public/data/ukraine_yield_forecast.json`

## Status

| Item | Status |
|---|---|
| Zones + POWER climate features | scaffolded |
| Oblасть SSSU labels | **2015–2021 dropped** (data.gov.ua); pre-2015 archive still missing |
| Train / forecast | labels unblock gate, but `min_train=16` needs ≥21 seasons |
| Sunflower | 2015–2021 CSVs present; train only after wheat succeeds |
| Maize / barley | deferred |
| War area / Harvest boundaries | documented, separate layer |
| Shipping black_sea routes | out of scope |

## Setup

```bash
cd "New for anti/scripts/yield_model"
python3 -m pip install pandas numpy scipy scikit-learn
python3 -m ukraine.test_dry_run
```

## Pipeline (after labels)

```bash
# Drop real oblast CSVs into ukraine/training/ (see labels.md)

python3 -m ukraine.collect              # wheat zones by default
python3 -m ukraine.collect --snow       # optional ERA5-Land snow
python3 -m ukraine.train
python3 -m ukraine.run_forecast         # only after models exist
```

## Regions

| key | Points |
|---|---|
| `central_winter_wheat` | Poltava, Vinnytsia, Cherkasy |
| `southern_winter_wheat` | Odesa, Mykolaiv, Kherson |
| `western_winter_wheat` | Ternopil, Khmelnytskyi, Rivne |
| `ukraine_winter_wheat` | all nine (weighted) |
| `*_sunflower` | same points — stub |

Crimea / Donetsk / Luhansk excluded. Train years ≤ 2021.
