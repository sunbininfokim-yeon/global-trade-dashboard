# Russia winter-wheat labels

## What Phase-1 uses now

| Field | Source | Unit | Resolution |
|---|---|---|---|
| `target` | **Rosstat** *Regions of Russia* extract (`tochno-st/regions_collection` indicator **13120000**) | **kg/ha** (c/ha × 100) | **Oblast**, then sown-area-weighted zone |
| Area weights | Same yearbook, indicator **13050000** sown area of cereals+legumes | 1000 ha | Oblast |
| 2024 patch | mojgorod.ru tabR4711 (Rosstat-derived cereals table) | c/ha → kg/ha | Oblast |

Files:

```text
russia/training/oblast_yields.csv      # year, oblast, yield_c_ha, yield_kg_ha, source
russia/training/oblast_sown_area.csv   # year, oblast, sown_1000ha, source
```

Zone builders in `labels.py`:

| Region key | Oblasts |
|---|---|
| `southern_winter_wheat` | Krasnodar, Rostov, Stavropol |
| `cbe_winter_wheat` | Belgorod, Voronezh, Kursk, Tambov |
| `russia_winter_wheat` | all seven (South + CBE) |

## Honest limitations

1. **Crop basket = cereals + legumes**, not winter-wheat-only. In South/CBE the basket is winter-wheat dominated; Volga/Siberia spring wheat is outside this point set.
2. **Annual span:** 2000–2021 continuous; **2024** sparse yearbook patch; **2022–2023** missing until EMISS/fedstat extract.
3. Crimea / “new regions” never joined.
4. USDA PSD national wheat remains a **cross-check** (`psd_yield_kg_ha`), not the training target.

## Conversion

| Rosstat | SI |
|---|---|
| 1 c/ha (центнер/га) | 0.1 t/ha = **100 kg/ha** |

---

## Barley (Track B desired / INTERIM PSD this pass)

| Mode | Source | Resolution |
|---|---|---|
| Track B (when CSV exists) | fedstat **31328** / EMISS ячмень | Oblast → zone |
| **INTERIM (2026-08)** | USDA FAS PSD Russia Barley Yield ≤2024 | **National only** |

Files (Track B drop):

```text
russia/training/oblast_barley_yields.csv[.template]
russia/training/oblast_barley_sown_area.csv[.template]
```

Region keys: `southern_spring_barley`, `cbe_spring_barley`, `volga_spring_barley`.

### Validation honesty

- INTERIM attaches the **same national series** to each zone’s weather → **not** oblast Track B validation.
- Positive skill vs trend under INTERIM can be **spurious** (Siberia etc. move national y).
- `train.py` sets `label_resolution=national_psd_interim` and **refuses** `beats_trend` / usable for forecast even if raw skill > 0.
- True Track B remains blocked until 31328 Excel lands (fedstat 403 from this environment; Zenodo empty; yearbook has no barley code).
