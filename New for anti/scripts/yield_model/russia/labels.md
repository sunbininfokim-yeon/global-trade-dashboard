# Russia winter-wheat labels

## What Phase-1 uses

| Field | Source | Unit | Resolution |
|---|---|---|---|
| `target` | USDA FAS PSD `Wheat` / `Yield` for `Country_Name=Russia` | **kg/ha** (PSD MT/HA × 1000) | **National** |
| Market year | PSD `Market_Year` | harvest-year aligned for winter wheat (summer harvest) | annual |

Downloader: `labels.py` → `https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip`  
Cache slice: `cache/psd_grains_russia.csv` (not committed).

## Limitations (honest)

1. **No oblast resolution.** South vs CBE weather both score against the same national tonnage yield. Spring-wheat Siberia and dry Volga still sit inside the target and dilute regional skill.
2. **PSD is an estimate series**, revised through WASDE; not a farm survey like NASS.
3. **Crimea / “new regions”.** Not added as POWER points. PSD national totals may still embed disputed accounting in some years; we do **not** attempt a silent correction.
4. **Rosstat / EMISS** (preferred next step): indicator `урожайность` in **c/ha** (×100 → kg/ha). Access path: fedstat.ru indicator export or static yearbook CSVs. Place curated files at:

```text
russia/training/oblast_yields.csv
# columns: year, oblast, yield_kg_ha
#   or yield_c_ha  (auto-converted ×100)
```

`labels.load_curated_oblast_csv()` will read this when present; wiring into regional targets is deferred until a multi-year extract is available.

## Conversion

| Rosstat | SI |
|---|---|
| 1 c/ha (центнер/га) | 0.1 t/ha = **100 kg/ha** |

## Not used as yield labels

- Shipping / AIS / black-sea capacity JSON  
- Export duty / policy Logit  
- Production alone without area (unless both sides check `prod ≈ yield × area`)
