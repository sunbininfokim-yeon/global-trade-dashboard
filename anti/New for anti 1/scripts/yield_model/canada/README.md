# Canada crop-yield models (Phase 2 — SAD/CAR)

Honest StatsCan + NASA POWER for guides in
`기후 모델링/Regions/북미_캐나다`.

```bash
cd "New for anti/scripts/yield_model"
python3 -m canada.collect
python3 -m canada.train
python3 -m canada.run_forecast
```

## Hierarchy

1. **SAD/CAR** labels (`32-10-0002`) + region-specific feature packs  
2. Else **province** weather (`32-10-0359`) if that track beats trend  
3. Else **trend_only** — operational point = trend, but **climate diagnostic stays**:
   - `weather_effect_pct` / `climate_risk.diagnostic_gap_pct` = climate model vs trend
   - `stance` / `stance_ko` = 유리 / 불리 / 중립
   - `risks` / `favors` / `reason_ko` for the UI

## Literature skill baseline

Chipanshi et al. (2015) ICCYF on CAR: canola/wheat R² ~0.66–0.67; Morrison HSU@29.5 °C;
Mkhabela SMOS excess moisture; MASC Excess Moisture (MB); Schlenker-style EDD for ON corn.

## Protocol

`log(yield) = technology trend + weather anomaly` — causal 20-yr z-scores, Ridge,
forward skill gate ≥10% (all + recent). Same skeleton as Australia.

## Monthly refresh

GitHub Actions: `.github/workflows/canada_yield_forecast.yml`  
cron `0 11 1 * *` (1st of month 11:00 UTC). Runs `collect` → `run_forecast`
(including `gov_outlooks` scrape of AAFC monthly Outlook + prairie weekly crop reports).

```bash
python3 -m canada.gov_outlooks   # federal/provincial outlook snapshot only
python3 -m canada.run_forecast   # yield JSON + gov embed
```

## Official Canadian cadence (what they publish)

| source | level | cadence |
|---|---|---|
| AAFC Outlook for Principal Field Crops | federal | **monthly** |
| CCYF / Crop Metrics | federal | **monthly Jul–Oct** (corn/soy + Oct) |
| StatsCan field crop surveys | federal | seasonal (Mar / Jun / Jul–Aug / Nov) |
| SK / AB / MB Crop Report | provincial | **weekly** in growing season |
