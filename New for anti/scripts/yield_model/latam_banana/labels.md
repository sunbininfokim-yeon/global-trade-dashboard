# LatAm banana labels

## Status: **blocked** — train gated

No verified province×year Cavendish yield panel is in-repo yet.
Templates under `training/*.template` show the required schema.

## Primary (required before train)

| Field | Preferred source | Unit | Resolution |
|---|---|---|---|
| `yield_kg_ha` | National statistical offices / banana boards | kg/ha | **Province / canton**, then area-weighted zone |
| `harvested_ha` | Same | ha | Same |

Drop files:

```text
latam_banana/training/province_banana_yields.csv
latam_banana/training/province_banana_area.csv
```

Columns:

```text
# yields
year,country,province,yield_kg_ha

# area
year,country,province,harvested_ha
```

`country` ∈ `ecuador` | `guatemala` | `costa_rica` | `honduras`.  
`province` must match keys in `labels.py` `PROVINCES`.

## Country sources (to pull manually)

| Country | Agency / board | Notes |
|---|---|---|
| Ecuador | INEC ESPAC / MAG | Los Ríos, Guayas, El Oro dominate export belt |
| Guatemala | MAGA / BANGUAT trade | Izabal Caribbean + Pacific south |
| Costa Rica | INEC + **CORBANA** | Limón primary; CORBANA also has disease weekly — Phase-2 |
| Honduras | SAG / BCH | Cortés–Atlántida north coast; hurricane years marked |

## Cross-checks only (do not train as zone y)

| Source | Use |
|---|---|
| FAOSTAT item **486** Bananas | National production / area / yield QA |
| FAO Banana Statistical Compendium | Export volumes (trade, not yield) |
| USDA PSD | National production cross-check |

Attaching national FAOSTAT yield to one POWER point is **forbidden**
(see `METHODOLOGY.md` hard rule 1).

## Optional Phase-2 panels

| File | Content |
|---|---|
| `training/farm_sigatoka_weekly.csv` | site, week, YLWS, YLS, INC, LEAF, bunches |
| `training/ibtracs_blowdown_years.csv` | year, zone_key, max_wind_ms, blowdown_factor |

## Acquired

_(none yet)_
