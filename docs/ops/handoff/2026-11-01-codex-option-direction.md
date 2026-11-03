# Frozen option direction model — Claude handoff

Branch `codex/option-direction-model-20261101`; depends on #787's evidence branch.
User requested repeated UP/DOWN forecasts from fresh options until explicit model update.

Implemented `option_direction_model.py` evaluate/train/predict commands; full contract
and integration commands are in `OPTION_DIRECTION_RESEARCH.md` beside it. Production
workflow/UI are not changed. Claude owns adding the predict-only invocation after
15007 board validation and retaining dated forecast outputs in GitHub. Never schedule
train as part of the daily collection. Explicit updates use new artifact paths.

Model artifact: `New for anti/scripts/market_microstructure/models/option_direction_v1_20261030.json`.
Its model_id begins `a97b7256`. Cutoff 2026-10-30, 1,579 labelled common sessions.
Features depend only on observed call/put data in 61 consecutive calendar sessions.
Weights and scaling stay frozen during inference. Latest incomplete day yields
unavailable instead of a stale forecast. Output files preserve original forecasts;
changed sources/model require a new revision path. Model integrity/version is checked.

First forecast in `data/manifests/option_direction_forecast_20261102.json`:
source 2026-10-30, target 2026-11-02; DOWN, P(UP)=0.4290432.
Target is KODEX200 next-session close versus its open, NOT today's close.
DOWN includes flat. Probability is an uncalibrated model estimate. Status research_only.

Expanding quarterly retrospective evaluation has 19 folds / 897 shared outcomes.
Option-only accuracy 51.06%, Brier 0.25213 versus prior 0.25037.
Combined-minus-price Brier +0.00173 (worse); exploratory paired 5-session block
bootstrap 95% interval [-0.00210, +0.00525]. No demonstrated incremental skill.
Illustrative 10bps roundtrip costs leave option-only mean per trade -0.07393%.
These results do not qualify the model as a trade signal.

Calendar caveat: Python3.9 resolves exchange_calendars4.5.6. Six calendar sessions
are absent from both option and ETF data; some correspond to newer announced
holidays. These are unresolved calendar disagreements, not missing-data claims.
Windows crossing them are conservatively excluded; manifest coverage lists every
affected source date. Calendar reconciliation is needed before operational promotion.
Historical availability and OHLC adjustment remain unverified. No imputation or
15001 substitution. Existing UI/public input assets unchanged.

Verification: 10 meaningful regression tests (calendar/gaps, past feature invariance,
label-boundary purge, frozen inference, serialized probability, model tamper,
unavailable latest day), UI contracts passed. Identical forecast replay preserves
file contents/timestamp. Optional research dependencies are in a separate file.
No merge/deploy performed.
