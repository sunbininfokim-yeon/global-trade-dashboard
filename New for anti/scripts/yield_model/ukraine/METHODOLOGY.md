# Ukraine yield modeling — kickoff methodology

Authority (Obsidian): `Regions/흑해_통합/방법론_우크라이나_yield_kickoff.md`  
Prior: `파이프라인_딥다이브_RU_UA_Phase1.md` §E-4·F · Russia package patterns (not shared labels).

## Scope this pass

| Crop | Zones | Status |
|------|-------|--------|
| Winter wheat | Central, Southern, Western, belt | **labels 2000+2010+2015–2021** (9 seasons); annual pre-2015 still missing → train blocked (`min_train=16` needs ≥21) |
| Sunflower | same points, flowering features | **labels 2015–2021** CSVs; train deferred |
| Maize / barley | — | deferred |

**No train / no forecast / no fake oblast CSV / no git commit this pass.**

## Hard rules

1. **RU ≠ UA** — do not join Rosstat tables or reuse Russia training CSVs.
2. **Biophysical yield first** — war effects live in a separate area/abandonment layer.
3. **Train years ≤ 2021** by default; 2022+ holdout / satellite area.
4. **PSD national = cross-check only** — never attach national y to zone weather (barley INTERIM lesson).
5. **Crimea, Donetsk, Luhansk** excluded from points and Phase-1 label joins.
6. **Shipping** `black_sea_*` routes stay outside yield train.

## Pipeline (when labels land)

```
SSSU / data.gov.ua oblast yields + sown area (≤2021)
        │
        ▼
area-weighted zone target (kg/ha = c/ha × 100)
        │
NASA POWER daily (+ optional ERA5-Land snow)
        │
        ▼
features (wheat winterkill / sunflower flowering)  ← reuse russia.climate helpers
        │
        ▼
ridge residual on log yield trend
        │
        ▼
models/*.json  → later public/data/ukraine_yield_forecast.json
```

## Next gate

Drop real files (not templates):

```text
ukraine/training/oblast_wheat_yields.csv
ukraine/training/oblast_wheat_sown_area.csv
```

Columns: `year, oblast, yield_c_ha` (or `yield_kg_ha`) and `year, oblast, sown_1000ha`.  
Then: `python3 -m ukraine.collect` → `python3 -m ukraine.train`.

Until then `labels.*` raises `FileNotFoundError` and `train` skips.

## War / validation honesty

- Official 2022+ oblast stats often cover government-controlled territory only.
- Do not claim weather skill on war years until area masks are applied.
- NASA Harvest field boundaries = Phase-2 **area** alignment, not y/ha labels.
