# Resume here

State as of 2026-08-03. Nothing is mid-edit; the tree is consistent and every
command below is safe to run cold.

---

## 1. FIXED — windowed-trend intercept bug (2026-08-03)

`window_rows()` in `train.py` now narrows the regression to the rows the trend
was fitted to. Verified: all ten models report an intercept of exactly 0.

Effect on results: `mato_grosso_milho` +40.4% -> +24.5%, `parana_trigo`
+11.1% -> +0.7%, `sp_cana` +8.2% -> -13.6%, `matopiba_soja` -17.7% -> -1.3%,
`mato_grosso_soja` -9.4% -> +5.4%. `parana_soja` unchanged at +49.0% as
predicted (deg1, never affected). Tables in README.md are post-fix.

## 2. Orange — built, validated and published

`sp_laranja` is fully built (config, SIDRA code `laranja` → table 1613 / c82 /
2733, training table, model JSON). Two findings are already encoded in it:

- **`regime_start=2001`.** IBGE switched the orange unit from thousands of
  fruits to tonnes between 2000 and 2001: yield drops 84% in one year
  (145,999 → 23,267 kg/ha) and stays. Reporting change, not agronomy.
- **kg/ha is the wrong lens for this crop.** HLB kills trees, not per-hectare
  yield. São Paulo orange area is down 55% from its 1991 peak (789,329 →
  354,562 ha) while yield on surviving area rose 35% since 2005. A kg/ha
  forecast shows a healthy rising crop while the industry contracts.

The guide itself opens by saying the market is collapsing *"기후가 아닌"* —
not from climate — but from citrus greening, and prescribes drone CNN and a
spatial contagion model. `non_weather_drivers` carries that, and the dashboard
prints it in Korean beneath the figure.

Post-fix it scores +43.5% forward-chaining but only +1.1pp on the 5-year
holdout, so it is **forward-chaining only, not confirmed**. Treat the number as
provisional.

**Still open:** publishing planted area alongside kg/ha, so the 55% area
collapse is visible next to a rising yield. Recommended, not built.

---

## 3. Not yet done

- **Coffee `lag3` + frost severity.** `Regions/브라질/미나스제라이스/커피` asks
  for a 3-year biennial memory (we carry lag1, lag2) and a Sentinel-2 NDVI
  drop-magnitude feature for frost damage (we carry a frost day count).
  Region coverage is already correct — `sp_cafe` is MG 0.75 / SP 0.25.
- **Planted-area context for oranges** (see section 2).
- **Sugar/ethanol allocation.** The new guide says the decisive variable is the
  mill's sugar-vs-ethanol mix, driven by crude oil and BRL. That is an
  economic model, not a weather one, and is out of scope for this package.

---

## 4. Uncommitted work

```
.github/workflows/brazil_yield_forecast.yml   weekly run + auto-retrain
New for anti/app.js                            Brazil panel, badges, map regions
New for anti/data.js                           loader + MATOPIBA/SP coordinates
New for anti/scripts/yield_model/brazil/       README.md, NEXT_STEPS.md,
                                               sidra.py, regions.py, models/
```

Also untracked and **not from this work** — check before committing:
`collect_us_wheat.py`, `train_wheat.py`, `us_*_wheat_*.{json,csv}`, and the
newer `yield_model/argentina/`, `yield_model/china/`, `yield_model/india/`
packages with `argentina_yield_forecast.yml`.

Checked, so nobody has to check again: `argentina/train.py` imports `run_cv`,
`fit_trend`, `prepare` and `evaluate` straight from `brazil/train.py`, so its
**validation already inherits the `window_rows()` fix** — no retrain needed.
Its final model fit is its own code (lines ~185-187) and still lacks the window
restriction, so the bug is latent there. It has not bitten: all five Argentine
models selected deg1/deg2 and report an intercept of exactly 0. It will bite
the first time one of them selects recent10/recent20. `china/` and `india/`
have no `train.py` yet.

---

## 5. Settled, do not redo

- Sugarcane is not a weather problem. Our `weather_skill` −3.1%, Dias &
  Sentelhas (2017) getting MAE > 29 t/ha and R² < 0.54 from FAO-AZM,
  DSSAT/CANEGRO and APSIM until a ratoon-decline factor is added, and the new
  guide itself pointing at the sugar/ethanol mix — three independent routes to
  the same conclusion.
- Satellite data should not be added for cotton or cane. Johnson (ORNL) finds
  MODIS NDVI adds little for upland cotton while transforming corn
  (R² 0.93 vs 0.48). If satellite effort is spent, spend it on corn.
- Cotton's pre-2000 era is a different farming system and stays excluded
  (`regime_start=2000`). Brazil cotton is ~92% rainfed — the 2000 break was
  relocation, cultivars and scale, not irrigation.
