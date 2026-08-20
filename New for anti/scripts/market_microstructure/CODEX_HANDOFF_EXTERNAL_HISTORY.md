# Codex handoff — external LETF snapshot archive

## What is implemented

`build_market_microstructure.py --live` now writes the external venue snapshot
to `public/data/external_venues_v1.json` after the Yahoo/Binance fetch.  The
daily runner then calls `append_external_history.py`, which appends dated HK
and US ETF rows to:

```text
public/data/external_leverage_history_v1.jsonl
```

Rows are keyed by `date + venue + ticker`.  Re-running a date replaces only the
same key, and weekends/holidays/API failures produce no row.  Crypto perps are
not mixed into this ETF file because OI is a different contract.

## Quality boundary

The current Yahoo payload has an EOD bar but `totalAssets` has no independent
as-of date.  Therefore the archive marks these rows:

- `quality: "partial"`
- `aum_quality: "observed_snapshot_unstamped"` when totalAssets exists
- `trading_value_quality: "proxy"` for volume × close
- `aum_as_of: null`

Do not present this file as historical AUM or exchange trading value until
Bloomberg/KRX records with their own observation dates replace those fields.
The exact schema and validator live in
`market_microstructure/external_history.py`.

## Claude/UI follow-up

UI ownership remains with Claude (`app.js`, `market-microstructure.js`).  A
future chart may read the file for 7709.HK, 7747.HK and 7347.HK, showing the
partial badge and the actual bar dates.  Do not merge HK/US turnover into the
KR cash wag-the-dog denominator.  Render it as a separate spillover/scale
comparison.

When Bloomberg data arrives, keep the same keys and set `source`, `aum_as_of`,
`quality`, and `trading_value_quality` from the actual feed.  Do not overwrite
old Yahoo rows; append a new source/date row or use a documented correction for
the same observation key.
