# Indonesia BPS province data audit

This directory builds a provenance-rich province panel before any regional
model is trained. Raw BPS PDFs and the SQLite database are ignored by Git;
transparent CSV extracts and code can be reviewed independently.

The current snapshot covers oil palm, coffee and rubber. BPS reports oil-palm
plantation area and **CPO production**, not FAOSTAT's oil-palm-fruit/FFB target.
The two products must never be joined as if they were the same label.

## Current snapshot

| Target | BPS seasons | Stable provinces | Complete climate province-years | Status |
|---|---:|---:|---:|---|
| Oil palm (CPO) | 23 (2001-2023) | 30 | 690/690 | stopped: 23 < 25 independent seasons |
| Coffee beans | 8 (2016-2023) | 33 | 264/264 | stopped: 8 < 25 independent seasons |
| Dry rubber | 17 (2007-2023) | 33 | 561/561 | stopped: 17 < 25 independent seasons |

There is no published regional forecast in this directory. The row count of a
province panel is not treated as the effective sample size: provinces in the
same harvest year share national and climate shocks, so the model gate counts
distinct harvest seasons. `data/MODEL_READINESS.md` records the audit result and
the reason every operational model is stopped.

The reviewable snapshot is stored in Git. Raw BPS PDFs and the derived SQLite
database stay local and are reproducible from the publication manifest. The two
largest tracked extracts are:

- `data/province_observations.csv`: 6,412 BPS province/category observations.
- `data/province_climate.csv`: 24,024 GEE province/window/metric observations.

`data/SNAPSHOT.json` records row counts and SHA-256 hashes for integrity checks.

Run with the bundled PDF runtime available in the Codex desktop workspace:

```bash
PYTHONPATH=scripts/yield_model python3 -B -m indonesia.region_db.collect_bps
PYTHONPATH=scripts/yield_model \
  ~/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m indonesia.region_db.build_db
PYTHONPATH=scripts/yield_model \
  ~/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m indonesia.region_db.export_audit
PYTHONPATH=scripts/yield_model python3 -B -m indonesia.region_db.collect_gee
PYTHONPATH=scripts/yield_model \
  ~/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m indonesia.region_db.analyze_readiness
```

Earth Engine always uses the existing machine authentication and initializes as
`ee.Initialize(project="climate-project-504313")`. The collector does not create
credentials or start an authentication flow.

The parser uses Poppler's raw text order so diagonal BPS watermarks do not split
province rows. Every observation retains publication id, PDF page, table id,
data status and the source PDF SHA-256. Audits compare producer-category sums
with province totals and province sums with the printed Indonesia total.

Climate rows use GAUL 2015 province means from ERA5-Land and CHIRPS at an
11,132-metre reduction scale. They do not yet use crop masks. North Kalimantan
production is merged into East Kalimantan to match the stable GAUL boundary.
