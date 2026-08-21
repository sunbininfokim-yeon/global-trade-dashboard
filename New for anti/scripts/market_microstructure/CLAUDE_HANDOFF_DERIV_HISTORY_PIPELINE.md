# Claude handoff — derivatives history publish + small UI labels

Codex's data branch writes the three JSONL contracts that the current
`app.js` already loads:

- `derivatives_activity_history_v1.jsonl`
- `leverage_direction_history_v1.jsonl`
- `stock_letf_history_v1.jsonl`

The UI needs no new chart component. Its existing 30/90/전체 modal chart reads
the files and honestly displays “히스토리 축적 중” below two observations.

## Required Actions change

In `.github/workflows/market_microstructure_daily.yml`, after `US→KR L3` and
before the commit step, run the following in the existing working directory.
Keep `KRX_API` in the environment for both KRX-dependent steps.

```yaml
      - name: Market microstructure snapshot
        env:
          KRX_API: ${{ secrets.KRX_API }}
        run: python build_market_microstructure.py --live --source auto --print-stats

      - name: Append external ETF snapshot history
        run: python append_external_history.py --print-stats

      - name: Derivatives board + US OI archive
        env:
          KRX_API: ${{ secrets.KRX_API }}
        run: python build_derivatives_board.py --live --print-stats

      - name: Append derivatives and LETF history
        run: python append_derivatives_history.py --print-stats
```

Add these outputs to the existing `git add` allowlist:

```text
New for anti/public/data/market_microstructure_v1.json
New for anti/public/data/ai_casino_brief_v1.json
New for anti/public/data/derivatives_activity_history_v1.jsonl
New for anti/public/data/leverage_direction_history_v1.jsonl
New for anti/public/data/stock_letf_history_v1.jsonl
New for anti/public/data/external_venues_v1.json
New for anti/public/data/external_leverage_history_v1.jsonl
New for anti/scripts/market_microstructure/TABLES.md
New for anti/scripts/market_microstructure/AI_CASINO_BRIEF.md
```

The Action must not seed or calendar-fill the files. KRX closes/holidays leave
no line; `append_derivatives_history.py` deduplicates only the same
`date` (or `date+ticker`) when a day is re-observed.

`append_external_history.py` uses the external snapshot written by the live
microstructure step. It archives HK/US ETF rows by `date+venue+ticker` only;
Yahoo totalAssets is currently unstamped and volume×close is a proxy, so the
rows are `quality=partial` until Bloomberg or another dated source replaces
those fields. Do not merge this archive into the KR cash turnover denominator.

## Small UI correctness patch

The foreign investor public-dashboard snapshot and KRX EOD market activity can
have different dates. In `msDerivatives`, label each explicitly instead of
calling both “당일”:

```js
const foreignAsOf = (dashboard.futures || {}).as_of
    || (dashboard.options_total || {}).as_of || '—';
const activityAsOf = kr.as_of || options.bas_dd || '—';
```

Use `foreignAsOf` next to `observedAt` in the foreign-flow lead, and
`activityAsOf` in the market-activity lead. This is a provenance label only;
it must not align or interpolate the two data sets.

For the single-stock LETF modal, the new snapshot has
`spot_trading_value_krw`; use it first and retain `adv_spot_krw` as fallback:

```js
const spotTv = st.spot_trading_value_krw ?? st.adv_spot_krw;
```

Label it “현물 당일 거래대금”, not “ADV”, because the source is daily
FDR/`ACC_TRDVAL`, not a rolling average.
