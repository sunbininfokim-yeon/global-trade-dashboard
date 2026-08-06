# LatAm banana (“banana republics” + Ecuador) — methodology

Authority (local notes):  
`Regions/중남미/바나나공화국_에콰도르/바나나/바나나_상세분석_및_수식.md`

Contract (later): `DATA_LAYOUT.md` →  
`public/data/{ecuador,guatemala,costa_rica,honduras}_yield_forecast.json`  
(or one bundled `latam_banana_yield_forecast.json` once UI countries are claimed).

## Why banana ≠ grain

Cavendish is a **perennial, continuously harvested clone**. Literature and
operational practice agree that **disease and storm damage dominate**
year-to-year exportable boxes — not a single flowering-window heat stress
like Prairie canola.

| Driver | Role | Phase |
|---|---|---|
| Black Sigatoka (`P. fijiensis`) | Chronic leaf necrosis → bunch weight / box count | 1 weather proxy → 2 field YLWS/YLS |
| Hurricane / blowdown | Central America: shallow roots, wind cut-off | 1 POWER wind + IBTrACS overlay |
| TR4 (Fusarium wilt) | Plot quarantine / area loss, not continuous yield shock | **Separate area layer** — never regress into kg/ha |
| Climate / ENSO | Cycle length, drought (esp. Ecuador Pacific), Sigatoka humidity | Phase-1 features |
| Spray / agronomy | Corbana / farm management — large residual | Caveat only until farm panels |

## Literature mapped to this package

| Source | What it shows | What we reuse |
|---|---|---|
| **Jiménez et al. 2022** (*Sustainability*) — RF on Panama farm bunches | R²≈0.70 using **YLWS / YLS / INC / LEAF**, site, week — *not* open climate alone | Target variable = bunches/boxes; disease score is lead feature; farm panel required for Phase-2 |
| **Garcés-Fiallos et al. 2025** (*Sustainability*) — Ecuador Buena Fe RF | R²≈0.96 with **NDVI + height/diameter + soil N/porosity/slope** | UAV/NDVI as canopy vigor; farm-scale only |
| **Rojas-Briones et al. 2011** (*Acta Hort.*) — Ecuador Bayesian net | Weather → fumigation → Sigatoka → yield; CPTs often expert-elicited | Causal DAG for narrative; not LOO ridge yet |
| **Calvo-Valverde et al.** — CORBANA Sigatoka ML | Station meteo + weekly severity → disease forecast | Costa Rica disease early-warning path |
| **FAO Banana Statistical Compendium / FAOSTAT item 486** | National production / area / yield; export volumes | Phase-1 **national cross-check only**; province labels preferred |
| **FAO / World Banana Forum TR4 guides**; Scheerer et al. 2020 | TR4 → up to 100% plot loss; LAC arrival post-2019 | Area abandonment layer, not y/ha train |
| Local guide (중남미) | Sigatoka RH≥90% proxy; wind >80 km/h → ×0.1 yield; CNN/TR4 vision | Encoded in `climate.py` + hard rules below |

**Honest gap:** peer-reviewed high skill is almost always **farm weekly**
panels with disease scores or UAV NDVI. Public province×year panels will
likely show **low skill vs trend** until YLWS/YLS or NDVI time series land.
Do **not** publish `point` forecasts that fail the operational skill gate
(same spirit as Canada ≥0.10 / cocoa `forecast_available: false`).

## Scope this pass

| Country | Zone key | Status |
|---|---|---|
| Ecuador | `ecuador_coast_banana` | scaffold + label gate |
| Guatemala | `guatemala_banana` | scaffold + label gate |
| Costa Rica | `costa_rica_banana` | scaffold + label gate |
| Honduras | `honduras_banana` | scaffold + label gate |
| Colombia / Panama | — | deferred |

**No fake province CSV · no train on national y glued to zone weather · no
forecast JSON with invented `point` this pass.**

## Hard rules

1. **PSD / FAOSTAT national = cross-check only** — never attach national
   yield to a single province weather average as if it were a zone label
   (same lesson as Ukraine barley INTERIM).
2. **TR4 ≠ weather residual** — infected hectares go to an area /
   quarantine mask; surviving hectares keep biophysical yield.
3. **Blowdown is a switch, not a soft coefficient** — if IBTrACS (or
   documented storm) max sustained wind over the belt exceeds ~80 km/h
   (≈22 m/s), apply hard damage factor before residual model
   (`yield *= blowdown_factor`, default 0.1 for full blowdown year).
4. **Phase-1 climate features are Sigatoka / storm *proxies*** — they do
   **not** replace YLWS/YLS. Document `low_confidence` until farm scores
   or verified province skill exist.
5. **Export boxes ≠ biological yield** — reject / pack-out / shipping
   strikes live outside the yield train (shipping routes stay in
   `shipping.js` ownership).
6. Stay on current ML branch; do not edit UI / `CLIMATE_COUNTRIES`.

## Pipeline (when province labels land)

```
INEC/ESPAC · MAGA · INEC-CR/CORBANA · SAG province yields + harvested area
        │
        ▼
area-weighted zone target (kg/ha or boxes/ha — pick one, document)
        │
NASA POWER daily (T, rain, RH2M, WS2M, GWETROOT) + ONI
        │
        ▼
features: sigatoka_wet_days, humid_spells, rain, heat, wind_storm_days,
          oni (Ecuador), optional IBTrACS blowdown flag
        │
        ▼
log-linear trend + Ridge on causal z-anomalies  (Canada protocol)
        │
        ▼
models/*.json → public/data/*_yield_forecast.json  only if skill gate passes
```

### Phase-2 (farm / disease)

```
Weekly YLWS / YLS / INC (CORBANA, cooperatives) + optional UAV NDVI
        │
        ▼
RF / Bayesian net (Jiménez 2022 · Rojas-Briones 2011)
        │
        ▼
belt aggregation → same JSON contract
```

## Next gate

Drop real files (not templates):

```text
latam_banana/training/province_banana_yields.csv
latam_banana/training/province_banana_area.csv
```

Columns: `year, country, province, yield_kg_ha` (or `boxes_ha`) and
`year, country, province, harvested_ha`.  
Province names must match `labels.py` keys.

Then:

```bash
python3 -m latam_banana.collect
python3 -m latam_banana.train
python3 -m latam_banana.run_forecast   # only after operational models
```

Until then `labels.*` raises / train skips; dry-run stays green.
