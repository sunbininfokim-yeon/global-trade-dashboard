# LatAm banana — Phase-1 scaffold

Ecuador coastal belt + Central American “banana republic” exporters
(Guatemala, Costa Rica, Honduras). Cavendish export bananas.

Authority: `Regions/중남미/바나나공화국_에콰도르/바나나/`  
Method: `METHODOLOGY.md` · Labels: `labels.md` · Contract: `DATA_LAYOUT.md`

## Status

| Item | Status |
|---|---|
| Zones + POWER climate features (Sigatoka / wind / ENSO) | scaffolded |
| Province yields + area | **blocked** — templates only |
| Farm YLWS/YLS / UAV NDVI (literature RF) | Phase-2 |
| TR4 area quarantine layer | documented, separate |
| Train / forecast JSON | gated on labels + skill |
| UI `CLIMATE_COUNTRIES` | out of Cursor ML scope |

## Setup

```bash
cd "New for anti/scripts/yield_model"
python3 -m pip install pandas numpy scipy scikit-learn
python3 -m latam_banana.test_dry_run
```

## Pipeline (after province CSVs)

```bash
python3 -m latam_banana.collect                 # all zones
python3 -m latam_banana.collect ecuador_coast_banana
python3 -m latam_banana.train
python3 -m latam_banana.run_forecast            # only if models operational
```

## Regions

| key | Points (production priors) |
|---|---|
| `ecuador_coast_banana` | Quevedo (Los Ríos), Guayaquil belt, Machala (El Oro) |
| `guatemala_banana` | Puerto Barrios (Izabal), Escuintla Pacific |
| `costa_rica_banana` | Limón / Sixaola Caribbean |
| `honduras_banana` | La Lima / El Progreso (Cortés–Yoro north) |

## Unit note

Commercial ops often speak **boxes/ha** (≈18.14 kg export box). Phase-1
target is **kg/ha** so it matches FAOSTAT / national yearbooks; convert
with a documented box weight if a CORBANA panel arrives in boxes.
