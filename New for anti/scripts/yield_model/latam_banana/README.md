# LatAm banana — runs **without** YLWS

No yield `point`. Same honesty mode as West Africa cocoa.

| Input | Used for |
|---|---|
| FAO Banana Statistical Compendium (static export refs) | `government_outlooks` |
| NASA POWER (RH / rain / wind) | **risk proxies only** — not yield |
| YLWS / farm disease | optional later; not required to run |

```bash
cd "New for anti/scripts/yield_model"
python3 -m latam_banana.test_dry_run
python3 -m latam_banana.collect_risk          # needs network (POWER)
python3 -m latam_banana.build_reference       # offline OK if profiles exist
# or one shot:
python3 -m latam_banana.run_panel
python3 -m latam_banana.run_panel --offline    # skip POWER
```

Output: `public/data/{ecuador,guatemala,costa_rica,honduras}_yield_forecast.json`  
all with `forecast_available: false`, `panel_mode: reference`.

YLWS: prefer **multi-year weekly** (literature used ~2015–2018). Until then
this panel is the product.
