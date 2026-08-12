# Golden metrics

Freeze a known portfolio + cached prices, run the engine, and compare key metrics to a checked-in JSON.

## Workflow

1. **Run with fixed cache** (must already exist under `cache/prices/`):

   ```bash
   cd "New for anti/scripts/금융_재무분석"
   python3 run_pipeline.py \
     --portfolio samples/user_balanced_portfolio.json \
     --cache-only --risk-profile balanced
   ```

2. **Optional — browser SoT:** when the UI is source of truth, paste browser-exported
   `horizon_1y` / `sharpe_short` / `ann_vol_short` (and friends) into
   `user_balanced_metrics.json`. Until then, numbers here are from the Python engine
   after the compounded `ann_return` / Sharpe fix.

3. **Assert:**

   ```bash
   python3 -m unittest discover -s tests -v
   ```

Tolerances live in `tests/test_golden_portfolio.py` (~1e-3 relative or 0.5pp absolute).
