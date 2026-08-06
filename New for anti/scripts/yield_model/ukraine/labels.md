# Ukraine winter-wheat / sunflower labels

## Status: **partial (2000, 2010 + 2015–2021)** — train still blocked

Real oblast CSVs from SSSU open data + Ukrstat yearbook sparse years.
**Annual pre-2015 series still missing** — `train` needs ≥ `min_train+5` (=21)
seasons; we have **9** seasons after append.

## Primary (required before train)

| Field | Source | Unit | Resolution |
|---|---|---|---|
| `target` | SSSU / Ukrstat / [data.gov.ua crop yield-area set](https://data.gov.ua/dataset/188450fa-3a63-43b5-a783-503b52b3f847) | **kg/ha** (c/ha × 100) | **Oblast (region)**, then sown-area-weighted zone |
| Area weights | Same — sown/planted area by crop | 1000 ha | Oblast |

Drop files:

```text
ukraine/training/oblast_wheat_yields.csv
ukraine/training/oblast_wheat_sown_area.csv
ukraine/training/oblast_sunflower_yields.csv      # sunflower pass
ukraine/training/oblast_sunflower_sown_area.csv
```

Oblast names in CSV must match `labels.py` EN keys:
`Poltava`, `Vinnytsia`, `Cherkasy`, `Odesa`, `Mykolaiv`, `Kherson`,
`Ternopil`, `Khmelnytskyi`, `Rivne`.

## Acquired (2026-08-05)

| File | Source detail | Years | Oblasts |
|---|---|---|---|
| `oblast_wheat_*.csv` | SDMX-JSON `DF_AREA_HARVESTS_CROP_YIELD_A` via data.gov.ua resource `20364020-…`; crop code **`C_0040`** matched to USDA PSD Ukraine Wheat Yield (c/ha ≈ MT/HA×10 within ~0.5); area = `AREA_PLANTED` (тис. га, scale=3) | **2015–2021** | 9 zone oblasts |
| `oblast_wheat_*.csv` (append) | Ukrstat [zb_rosl_2022.pdf](https://ukrstat.gov.ua/druk/publicat/kat_u/2023/zb/09/zb_rosl_2022.pdf) tables **2.4** (harvested area, thsd.ha) + **2.6** (wheat yield, c/ha). 2015 cells exact-match SDMX. Area column = **harvested** used as sown-area weight (2015 harvested ≈ planted within ~1 thsd.ha). | **2000, 2010** | same 9 |
| `oblast_sunflower_*.csv` | Same SDMX feed; crop **`C_0520`** exact-match to resource 124 “Урожайність соняшнику” | **2015–2021** | same 9 |

Excluded from joins: Crimea, Donetsk, Luhansk (and Kyiv city). Years >2021 stripped.

### Crop-code evidence (national c/ha)

| Year | SSSU `C_0040` | PSD Wheat×10 |
|---|---:|---:|
| 2015 | 38.8 | 38.3 |
| 2016 | 42.1 | 41.5 |
| 2017 | 41.1 | 40.6 |
| 2018 | 37.3 | 37.3 |
| 2019 | 41.6 | 41.6 |
| 2020 | 38.0 | 37.1 |
| 2021 | 45.3 | 44.6 |

`C_0050` ≈ winter wheat (nearly identical to `C_0040`); `C_0080` ≈ spring wheat.

### Still blocked for full train

SSSU Data Bank / SDMX history starts **2015**. Published yearbooks
(*Рослинництво України*, *Сільське господарство України*) only print
**sparse** historical columns (typically 1990 / 2000 / 2010 / 2015 + last 2–3
years) — not annual 2001–2014 by oblast.

Pre-2015 **annual** oblast wheat/area lives in the **Archive** ZIPs on
[stat.gov.ua dataset page](https://stat.gov.ua/en/datasets/areas-gross-harvests-and-crop-yield-annual)
(“Площі, валові збори… за їх видами” / “Посівні площі…”). Those pages return
Cloudflare **403 / blocked** from this environment (curl + browser MCP) —
**manual download** required, then extend CSVs annually back to ~2000.

#### Attempt log (2026-08-05, agent)

| Source | Result |
|---|---|
| `stat.gov.ua` en/uk dataset pages (browser-like headers) | HTTP **403** Azure/CF |
| Browser MCP → same URL | “The request is blocked” |
| Wayback CDX / Save for dataset page | 429 / empty useful crop ZIPs |
| `data.gov.ua` 188450fa datapackage + SDMX annual JSON | Works; years **≥2015** only |
| Resource 124 JSON/XLSX/CSV (урожайність за регіонами) | Works; **grain aggregate**, not wheat; ≥2015 |
| Ukrstat `zb_rosl_2022.pdf`, `zb_rosl_2019.pdf`, `zb_rosl_2020/21.pdf` | Works; wheat by oblast but **sparse** years |
| `Arch_rosl_zb.htm` / `Arch_sg_zb.htm` | Lists 2013–2021 editions; direct PDF hrefs not extractable here; older path guesses 404 |
| Obsidian `Regions/흑해_통합/` | Method notes only — **no** downloaded oblast tables |
| FAOSTAT / PSD | National only — **not** used as zone labels |
| Zenodo / regional ukrstat | No ready annual 9-oblast wheat panel found |

## Exclusions

- Crimea
- Donetsk, Luhansk (occupation / dual-count risk)
- Train years **> 2021** stripped by default (`LABEL_MAX_YEAR`)

## Cross-check only

| Source | Role |
|---|---|
| USDA FAS PSD `Ukraine` Wheat / Sunflowerseed Yield | National dual-source check |
| FAOSTAT | Auxiliary |

**Do not** use PSD as zone training target.

## Conversion

| SSSU / Ukrstat | SI |
|---|---|
| 1 c/ha (ц/га) | 0.1 t/ha = **100 kg/ha** |

## Manual drop (annual pre-2015) — user action

1. Open (personal browser, pass Cloudflare):
   - https://stat.gov.ua/en/datasets/areas-gross-harvests-and-crop-yield-annual
   - or https://stat.gov.ua/uk/datasets/… (same dataset, uk locale)
2. Download Archive ZIPs for **areas / gross harvests / crop yields** (and sown areas if separate).
3. Extract oblast × year **wheat** yield (ц/га) and sown/planted area (тис. га) for the 9 oblasts, years ideally **2000–2014** (or at least enough to reach ≥21 seasons with 2015–2021).
4. Append rows to the existing CSVs with the same columns; `source` = archive filename + sheet.
5. Re-run `python3 -m ukraine.collect` then `python3 -m ukraine.train`.

Mirror yearbook PDFs (sparse only — already partially ingested):

- https://ukrstat.gov.ua/druk/publicat/kat_u/2023/zb/09/zb_rosl_2022.pdf
- https://ukrstat.gov.ua/druk/publicat/Arhiv_u/07/Arch_rosl_zb.htm
- https://ukrstat.gov.ua/druk/publicat/Arhiv_u/07/Arch_sg_zb.htm

## Optional interim (NOT done): lower `min_train`

If annual archive cannot be obtained soon, a **documented** temporary
`regions.py` change `min_train: 16 → 5` (need ≥10 seasons) would let Ridge
fit on the current 9 seasons — but forward folds would be **tiny**, skill
unstable, and `usable` thresholds should stay strict (or force
`forecast_available: false`). Prefer archive append over this.
