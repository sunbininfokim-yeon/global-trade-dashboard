# Calibrated shadow direction engine / research handoff

Depends on #788/#787. This work does not merge/deploy, replace v1 or alter public
input assets. Research public ref f2c834378086725d6951a3cb837d3beae6d05cdb includes #791.

Outcome: independent chronological calibration improves baseline point accuracy
to 53.99% on 1,178 historical outcomes, versus recent class prior 51.95%. The paired
Brier improvement interval crosses zero; many retrospective trials are disclosed.
OI changes, private per-strike IV structure and a causal one-session delay did
not establish incremental information. Full report:
`data/manifests/option_calibration_research_20261102.md` and compact JSON alongside it.

Existing private normalized option hive has 94 monthly parts, so no KRX queries
were needed. Extractor derives 1,889 surface dates in memory, regular/observed
only, preserving 94 file hashes in `option_surface_source_manifest_20261102.json`.
No full raw chain or individual quote-support export is committed.

## Claude: optional shadow integration only

Main code directory: `New for anti/scripts/market_microstructure`.

```sh
python shadow_direction_engine.py predict \
  --board ../../public/data/derivatives_board_v1.json \
  --prices ../../public/data/kospi200_etf_candidates_daily_v1.json \
  --model models/shadow/calibrated_shadow_20261030_research.json \
  --output <dated-shadow-forecast-path>.json
```

Run only after the fresh option board AND same-source-date 069500 daily price
panel are validated. Current ETF rows end 10/30, so the daily price refresh path
is a prerequisite for this shadow engine. The original v1 option-only path
remains available and unchanged. Do not silently switch its model path.

Do not schedule train. New versions use an explicit train command and a new
artifact path. Model, scaler, calibrator and implementation hashes are frozen.
`unavailable` must hide any stale daily direction. `retrospective_research` must
not count as a pre-open forecast. The replay file committed here is retrospective.
Prediction timestamps are local generation evidence, not verified first-publication times.

The current shadow calibrator has zero slope. UI must label
`information_state=recent_base_rate_only` as a base-rate estimate, not as a
validated option signal. It emits UP/DOWN because that is the requested output
contract, but provides no proof of daily predictive edge or trading profitability.

## Cursor

Follow `CURSOR_HANDOFF_SHADOW_DATA_20261102.md` in the code directory:
daily 069500 price refresh, actual expiration metadata, timing provenance, and
existing 10/29–30 gaps. Reuse private normalized chains before new KRX requests.
Do not add multiple expiries to the old chain hive without a new contract.

## Reproduction

Install optional `requirements-direction-research.txt`. This run used
exchange_calendars4.5.6 plus the six-date reviewed closure overlay; use the same
runtime for the committed shadow artifact. Calendar version changes require review.

```sh
python research_option_dynamics.py --ref f2c834378086725d6951a3cb837d3beae6d05cdb --output ../../../data/manifests/option_dynamics_calibration_20261102.json
python research_option_dynamics.py --ref f2c834378086725d6951a3cb837d3beae6d05cdb --lag 1 --output ../../../data/manifests/option_dynamics_lag1_calibration_20261102.json
python extract_private_option_surface.py --public-ref f2c834378086725d6951a3cb837d3beae6d05cdb --private-ref 3a27fa40872926d3e907abd2cb00ec08b4c32072 --output ../../../data/manifests/option_surface_features_20261102.json
python research_option_surface_probe.py --ref f2c834378086725d6951a3cb837d3beae6d05cdb --surface ../../../data/manifests/option_surface_features_20261102.json --output ../../../data/manifests/option_surface_probe_20261102.json
```

The extractor requires authorized private-repo gh access; --gh can select its
binary. Do not print tokens. Raw normalized parts are read in memory only.
14 regression tests plus UI contracts passed. v1 model and original forecast
remain byte-identical. No main push, merge, workflow edit or deployment performed.
