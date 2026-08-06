# Vietnam — Mekong **risk monitor** (ops) + yield scaffold (deferred)

Methodology source (Obsidian): `기후 모델링/Regions/베트남/`  
Master: `베트남_쌀_커피_상세수식.md` · data stack: `베트남_데이터스택_레시피.md`

Code path: `New for anti/scripts/yield_model/vietnam/`

---

## Ops product (2026-08 pivot)

**Mekong climate → yield prediction is abandoned / deferred for ops.**

Provincial panel and regional CV did not beat province/region trend with
honest labels (negative skill; short T). Continuing to ship yield point
estimates would overclaim. Ops path is now a **hydrology / salinity early-warning
risk monitor** for the same Mekong Delta WS dry season.

| | Yield path (deferred) | Risk monitor (active) |
|--|--|--|
| Output | `vietnam_yield_forecast.json` skill/point | `vietnam_mekong_risk_v1.json` scores/flags/TS |
| Claim | skill vs trend | **none** — heuristic early-warning only |
| Drivers | ridge on climate → kg/ha | Q-proxy, salt_proxy, SPI/SPEI-like, ONI context |
| MRC Q | wanted for labels | still wanted; **POWER proxy** until portal works |

### Run risk monitor

```bash
cd "New for anti/scripts/yield_model"
python3 -m vietnam.risk
# optional:
python3 -m vietnam.risk --year 2026
python3 -m vietnam.risk --out ../../public/data/vietnam_mekong_risk_v1.json
```

Writes `public/data/vietnam_mekong_risk_v1.json`.

### Risk field cheat-sheet

| Field | Meaning |
|-------|---------|
| `overall.risk_score_0_100` | Heuristic blend (basin Q-proxy + coastal salt + ENSO). **Not** a probability. |
| `overall.risk_level` | `low` / `watch` / `elevated` / `high` |
| `overall.flags` | e.g. `low_q_upstream_proxy`, `el_nino_context`, `coastal_salt_proxy_alert` |
| `basin.q_upstream_proxy` | POWER Pakse wet + Tan Chau dry SM/precip composite. **Not MRC Q.** Higher ⇒ more freshwater push. |
| `enso.oni_lag2` / `oni_djf` | NOAA CPC ONI — risk **context**, not a yield coefficient claim |
| `provinces.*.salt_proxy` | coast × dry hydro × wet memory × ONI × Q-proxy |
| `provinces.*.ec_proxy` | scaled hydro stand-in — **not** field ECe (dS/m) |
| `provinces.*.spi_ws` / `spei4_ws_min` | POWER-based z approx for WS dry stress |
| `time_series[]` | Annual basin risk + components for charts |
| `area_risk.soft_flag` | Planted-area **caveat** when coastal salt alerts fire — no ha model / no skill |
| `field_guide` / `how_to_read` | Machine-readable descriptions + KO/EN reading notes |
| `claim_boundary` | Explicit ships / does-not-ship (no yield, no skill-vs-trend) |
| `yield_model_status` | always `abandoned_for_ops` on this product |
| `forecast_available` | `false` |

Full methodology: [`risk/README.md`](risk/README.md)  
Vault note: `Regions/베트남/메콩_리스크모니터_피벗.md`

---

## Yield scaffold (kept for research; not ops)

```bash
cd "New for anti/scripts/yield_model"
python3 -m vietnam.collect                 # NASA POWER + ONI → training/*.csv
python3 -m vietnam.train                   # ridge CV → models/*.json
python3 -m vietnam.predict --year 2026
python3 -m vietnam.run_forecast            # public/data/vietnam_yield_forecast.json
```

Do **not** treat Mekong WS skill metrics as production-ready. Coffee / RRD
remain provisional-label scaffolds.

### Region-crops (legacy table)

| key | tier | crop | guide focus |
|-----|------|------|-------------|
| `mekong_rice_ws` | T1 (deferred ops) | rice | WS salt / ENSO / dry stress |
| `central_highlands_coffee` | T1 scaffold | coffee | Feb–Apr WD, irrigation_buffer, Kath |
| `red_river_rice` | T1 scaffold | rice | typhoon / flood / coast salt proxy |
| `central_coast_rice` | T2 stub | rice | schema only |
| `central_highlands_pepper` | T2 stub | pepper | schema only |

### Honest proxies (unchanged)

```
salt_proxy ≈ f(coast_km, dry-season precip, prior wet precip, ONI lag-2, Q_upstream_proxy)
ec_proxy                  → Maas–Hoffman *shape* on scaled proxy — not dS/m
q_upstream_proxy          → POWER Pakse/TanChau stand-in for MRC QTCmin
```

MRC discharge / SIWRP field EC / GEE S1 area: still gaps. Risk monitor documents
them under `data_gaps` and does not block on MRC login.
