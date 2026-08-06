# YLWS time-series acquisition log

**Status (2026-08-06): NOT FOUND in any open repository.**  
Raw weekly YLWS/YLS panels remain behind cooperatives / banana boards.

YLWS = Youngest Leaf With Symptoms (leaf rank from the top where Black
Sigatoka first appears). Lower = worse. Recorded **weekly** by plantation
plant-health crews; used to time fungicide cycles.

---

## Target series (what “good” looks like)

| Field | Example |
|---|---|
| `date` or `year_week` | ISO week |
| `site` / farm / cooperative | e.g. COOBANA site 1–3 |
| `country` | PA / CR / EC / GT / HN |
| `YLWS`, `YLWS_7`, `YLWS_10` | leaf ranks by plant age class |
| `YLS`, `YLS_7`, `YLS_10` | youngest leaf spotted |
| optional | `INC`, `LEAF`, `SIN`, bunches harvested |

Literature gold: Olivares et al. 2022 — **n≈623** weekly rows, 3 Changuinola
(Panama) sites, 2015–2018 ([DOI 10.3390/su142114123](https://doi.org/10.3390/su142114123)).

---

## Attempt log

| When | Source | Result |
|---|---|---|
| 2026-08-06 | Olivares et al. 2022 **Data Availability Statement** | **"Not applicable"** — raw weekly panel **not published** |
| 2026-08-06 | Same paper Acknowledgments | Data credited to **COOBANA R.L.** (Cooperativa Bananera del Atlántico, Bocas del Toro / Changuinola) phytosanitary staff — commercial cooperative records |
| 2026-08-06 | MDPI HTML/PDF/S1 from this environment | HTTP **403** (Akamai) — could not re-download; statement recovered from prior full-text cache |
| 2026-08-06 | Zenodo API (`YLWS` / sigatoka epidemiolog) | **403** from this network |
| 2026-08-06 | Figshare search | No YLWS banana epidemiological CSV (noise hits only) |
| 2026-08-06 | GitHub repo search `sigatoka YLWS` | **0** repos |
| 2026-08-06 | arXiv `YLWS AND sigatoka` | **0** |
| 2026-08-06 | Semantic Scholar / DOI | Paper is Gold OA at MDPI, but **no linked dataset DOI**; PDF host 403 here |
| 2026-08-06 | Calvo-Valverde / CORBANA ML papers | Explicitly use **CORBANA** internal weekly disease + meteo (EstadoEvolucion / Preaviso Biológico, ~675 weeks in one study) — **not public** |
| 2026-08-06 | Zenodo “Banana Leaf Disease Dataset” | **Images** for CNN (restricted), **not** YLWS ranks |
| 2026-08-06 | Paper Table 2 / Figure A1 | Site-level **summary stats** and weekly **plots** only — **do not OCR-fabricate** a 623-row CSV |

---

## Who actually holds usable series

1. **COOBANA R.L.** (Panama Atlantic co-op) — confirmed holder of the 2015–2018
   panel used in Olivares et al. 2022.
2. **CORBANA** (Costa Rica) — research-farm weekly Sigatoka scores + stations
   (28 Millas / Matina cited in CIGR proceedings).
3. Aerial spray / plant-health contractors in EC/GT/HN export belts — same
   YLWS field protocol industry-wide; almost never published.

Corresponding author ORCID (Olivares): `0000-0003-2651-570X`  
(for a polite data-reuse request; do not scrape personal email from ORCID).

---

## Allowed next steps (human)

1. Email COOBANA + Olivares requesting **anonymized weekly YLWS/YLS** under
   research / dashboard non-commercial use (CC BY or restricted license).
2. Ask CORBANA research for a **redacted** Preaviso Biológico extract
   (Limón belt).
3. If refused: stay on reference panel forever — **do not** train on weather
   proxies and call it forecast.

### Request template (short)

```text
Subject: Request for anonymized weekly Black Sigatoka scores (YLWS/YLS)

We are building a public trade-risk reference panel (no commercial spray
advisory). Olivares et al. 2022 (Sustainability) used weekly YLWS/YLS from
COOBANA sites (2015–2018) but the Data Availability Statement is
"Not applicable".

Could you share an anonymized CSV (site id, year-week, YLWS*, YLS*, optional
bunches) for research citation? We will not redistribute farm identities.
```

---

## Repo policy until data arrives

- `forecast_available: false` on all LatAm banana JSON
- No `training/farm_sigatoka_weekly.csv` with synthetic rows
- Drop real CSV here only: `latam_banana/reference/ylws_weekly.csv`
  with columns above + `source`, `license` fields
