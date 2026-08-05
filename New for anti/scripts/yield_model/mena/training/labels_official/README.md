# Official yield labels (`labels_official/`)

Collect writes FAOSTAT national wheat yield here for T1 region-crops:

| file | FAOSTAT area | note |
|------|--------------|------|
| `egypt_nile_wheat.csv` | Egypt | national wheat; not Delta vs Upper Egypt |
| `morocco_atlantic_wheat.csv` | Morocco | national wheat; not Chaouia vs Oriental |
| `algeria_hauts_wheat.csv` | Algeria | national wheat/barley mix at country scale |

Schema:

```csv
year,yield_kg_ha,label_source,label_note
```

`label_source` defaults to `faostat_national_wheat` when fetched by collect.

## Overrides

Drop a CSV with the same name to replace FAOSTAT for that region-crop.
Use `label_source` and `label_note` to document provenance.

If no file exists, `labels.py` falls back to
`provisional_synthetic_climate_response` — skill then measures scaffold
consistency only, not production forecast skill.

## Honesty

FAOSTAT national labels imply `labels_season_imperfect` on trained models:
they do not resolve subnational season structure or irrigated vs rainfed
splits within a country.
