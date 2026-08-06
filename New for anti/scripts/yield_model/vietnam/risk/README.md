# Mekong climate risk monitor (`mekong_risk_v1`)

**Ops product:** hydrology / salinity **early-warning** for Mekong Delta Đông Xuân (WS dry season).  
**Not a yield forecast.** No skill-vs-trend claim. No kg/ha point.

Output: `public/data/vietnam_mekong_risk_v1.json`  
Run: `python3 -m vietnam.risk` (from `scripts/yield_model`)

Vault: `기후 모델링/Regions/베트남/메콩_리스크모니터_피벗.md`  
Why yield was dropped: `../PANEL_SIGNIFICANCE_KO.md`

---

## 1. What this product claims (and does not)

| Claims | Does **not** claim |
|--------|-------------------|
| Relative dry-season stress vs recent climatology | Yield (kg/ha) point or range |
| Heuristic 0–100 risk scores + discrete levels | Calibrated probability of loss |
| Open-data **proxies** for Q, salt, drought, ENSO | MRC gauge Q, field EC, station SPEI |
| Soft **planted-area** caveat when coastal salt flags fire | S1/GEE planted-area anomaly skill |

`forecast_available` is always `false`. `yield_model_status` is `abandoned_for_ops`.

---

## 2. Why yield / trend path was abandoned (ops)

Provincial Đông Xuân panel (T≈8, n≈100) forward CV did **not** beat province trend
(skill ≈ −25%). Regional aggregate likewise failed. Short T cannot separate ENSO /
basin common shocks from climate→yield. Shipping a yield point would overclaim.

Research scaffolds (`collect` / `train` / `predict`) remain in-repo for later
label extensions; **ops + interview / review story = this risk monitor**.

---

## 3. Score methodology (heuristic)

### Levels

| `risk_level` | score |
|--------------|-------|
| `low` | &lt; 35 |
| `watch` | 35–54 |
| `elevated` | 55–74 |
| `high` | ≥ 75 |

### Basin score (annual)

1. `q_upstream_z` — climatological z of POWER Pakse/Tan Chau **Q-proxy** (low Q → high risk)
2. `salt_proxy_z` — z of mean coastal `salt_proxy` (high → high risk)
3. ENSO term — ONI lag-2 (or DJF); El Niño side raises risk; La Niña does not “buy” yield skill

```
basin ≈ 0.40·q_risk + 0.40·salt_risk + 0.20·enso_risk
```

### Province coastal stress

Coastal belt (`coast_km ≤` threshold): blend of salt_proxy, dry SPI, SPEI-like, coastal exposure.  
Inland: drought terms dominate; salinity channel muted.

### Overall

```
overall ≈ 0.55·basin + 0.45·mean(coastal province scores)
```

These weights are **transparent heuristics**, not estimated loss functions.

---

## 4. Proxies vs real sensors

| Field | What it is | What it is **not** |
|-------|------------|--------------------|
| `q_upstream_proxy` | POWER precip/SM composite (Pakse wet + Tan Chau dry) | MRC Tan Chau discharge |
| `salt_proxy` / `ec_proxy` | coast_km × hydro × wet memory × ONI × Q-proxy | Canal / field ECe (dS/m) |
| `spi_ws` / `spei4_ws_min` | POWER window z / CWB-like z | Station SPI/SPEI (log-logistic) |
| `sm_peak_gwetroot` | NASA POWER root-zone wetness | In-situ soil moisture |
| `enso.oni_*` | NOAA CPC ONI | Causal yield coefficient |

Honest labels live in JSON under `honesty` and `data_gaps`. MRC portal 403 must
**not** block the monitor — proxy is explicit.

---

## 5. How to read alerts (`overall.flags`)

| Flag | Meaning | Action framing |
|------|---------|----------------|
| `low_q_upstream_proxy` | Freshwater-push proxy weak vs own history | Watch salt intrusion risk inland of coast |
| `el_nino_context` | ONI in El Niño range | Historical WS stress context — not a yield call |
| `coastal_salt_proxy_alert` | ≥1 coastal province high `salt_proxy` | Prioritize Ben Tre / Tra Vinh / Soc Trang belt |
| `regional_dry_spi` | ≥1 province SPI_WS ≤ −1 | Dry stress watch (POWER-based) |

Province `flags`: `high_salt_proxy`, `dry_spi_ws`, `dry_spei4`, `low_rootzone_sm_proxy`.

**Interview line:** “We monitor relative hydro-salinity stress with labeled proxies;
we do not ship climate→yield skill because the panel failed an honest trend benchmark.”

---

## 6. Planted-area risk (caveat, not a model)

Mekong literature treats **area** (planting abandonment under salt) separately from
**yield**. Official area cells in the provincial scrape were often contaminated
(2017–2020), and S1/GEE planted-area anomaly is **not wired** (no GEE auth).

JSON `area_risk` therefore:

- status = `proxy_flag_only`
- soft flag mirrors coastal salt alerts
- **no** ha forecast, **no** skill metric

When auth exists: Sentinel-1 anomaly vs 2016-style baselines can upgrade this block.

---

## 7. JSON field guide (consumers)

| Path | Use |
|------|-----|
| `product` / `product_ko` | Product id |
| `overall.risk_score_0_100` / `risk_level` / `flags` | Headline panel |
| `overall.interpretation` | Always show near the score |
| `basin.*` | Freshwater-push story |
| `enso.*` | Context chip |
| `provinces.*` | Map / table by province |
| `time_series[]` | Multi-year chart of basin risk |
| `area_risk.*` | Area caveat banner |
| `field_guide` | Machine-readable descriptions |
| `how_to_read` | Short Korean/English reading notes |
| `yield_model_status` | Must stay `abandoned_for_ops` |
| `forecast_available` | Must stay `false` |

---

## 8. Gaps (honest backlog)

1. MRC Tan Chau / Chau Doc real Q (replace proxy when portal opens)
2. SIWRP / field EC alerts
3. GEE: CHIRPS + SMAP + S1 planted-area / inundation
4. Longer GSO province×WS labels — *research only*; does not revive ops yield until skill clears trend
