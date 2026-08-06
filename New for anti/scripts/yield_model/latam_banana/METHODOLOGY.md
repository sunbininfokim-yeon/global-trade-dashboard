# LatAm banana — methodology (reference panel)

## Decision (2026-08-06)

Ship **statistics + risk reference panels only**. Do not train weather→yield
ridge. Do not invent `point`. Farm interview / micro phenology panels are
not used — they lack belt-scale meaning for export supply.

## What the panel carries

| Block | Content |
|---|---|
| `government_outlooks` | FAOSTAT / FAO Banana Compendium / national board notes (production, exports) with vintage labels |
| `research_notes` | Sigatoka, hurricane blowdown, TR4 — qualitative risk, with links |
| `sources` | URLs + `supports` |
| `forecast_available: false` | mandatory |
| `panel_mode: "reference"` | mandatory |

## What would unlock a real forecast (not this pass)

Weekly **YLWS / YLS** (or equivalent Preaviso Biológico / Stover–Gauhl scores)
from export plantations, aggregated to a belt. Literature that works
(Olivares et al. 2022 RF R²≈0.70) uses exactly that — and the paper’s
**Data Availability Statement is “Not applicable”** (raw panel not released).

See `YLWS_ACQUISITION.md`.

## Hard rules

1. No national FAOSTAT yield glued to a single POWER point as a “model”.
2. No OCR-invented weekly YLWS from paper figures.
3. TR4 = area quarantine narrative, not a continuous yield shock coefficient
   without infection-hectare data.
4. Hurricane blowdown stays a **documented risk switch** (~80 km/h), not a
   soft weather feature claiming skill.
