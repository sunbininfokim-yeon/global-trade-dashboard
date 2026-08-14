# Claude handoff — Samsung + SK Hynix LETF AUM / implied-rebalance charts

## What Codex added

The existing shared data log, `public/data/stock_letf_history_v1.jsonl`, now
gets the following fields for **both** `000660` (SK Hynix) and `005930`
(Samsung Electronics):

| Field | Status | Meaning |
|---|---|---|
| `letf_aum_sum_krw` | observed | Sum of listed, matching single-stock LETF AUM on that KRX session |
| `letf_trading_value_krw` / `spot_trading_value_krw` / `letf_turnover_ratio` | observed | LETF trading activity relative to same-day underlying cash turnover |
| `underlying_day_return` | observed | KRX underlying daily return |
| `implied_rebalance_krw` / `_abs_krw` / `_ir_pct` | **estimated** | Daily-reset model proxy; not confirmed ETF trading or dealer hedging |
| `implied_rebalance_formula` | metadata | `Σ AUM × (L² − L) × underlying daily return` |

Each row keeps `date`, `as_of`, `source`, and the input data `quality`. The
separate `implied_rebalance_quality: "estimated"` prevents a model output from
being styled as an observed trade.

## One-time observed backfill (Claude-owned workflow/run environment)

Codex cannot run this locally because `KRX_API` is intentionally absent from
the local shell.  Run once in the existing Actions environment, where the
already-configured `KRX_API` secret is present:

```bash
cd "New for anti/scripts/market_microstructure"
python backfill_single_stock_letf_history.py \
  --start 2026-05-27 \
  --end "$(date -u -d 'yesterday' +%F)"
```

The script reads only KRX `sto/stk_bydd_trd` and `etp/etf_bydd_trd`; it
deliberately does **not** use current Naver investor data for a historical
date. Weekends and KRX holidays write no row. It replaces only duplicate
`date+ticker` rows with the newly observed KRX row. Do not seed demo history.

The normal daily `append_derivatives_history.py` now writes the same extra
fields from the fresh snapshot. Keep it in the scheduled workflow.

## Required UI changes (Claude-owned `app.js`)

1. Route D's `000660` **추이** to `stock_letf:000660`, not `alert_letf`.
   The alert card may independently open `alert_letf`. Do not mix their
   potentially different `as_of` dates.
2. In the D modal for both tickers, render exactly three separately named
   chart blocks:
   - **단일종목 LETF AUM 추이** — `letf_aum_sum_krw`; describe as an AUM
     observation, not a cause of price moves.
   - **LETF 거래대금 / 현물 거래대금** — `letf_turnover_ratio`.
   - **추정 리밸런싱 압력 (7거래일 평균)** — rolling mean of the last seven
     observed `implied_rebalance_ir_pct` values. Include the formula and
     persistent disclaimer: *"모델 추정치이며 실제 ETF 체결·딜러 헤지·가격
     영향이 아닙니다."*
3. Never calendar-fill a missing day. If fewer than five actual observations
   exist, do not draw a line: show `히스토리 축적 중 N/5` and a compact
   observed-value table. A 7-day line needs seven observations.
4. Keep alert thresholds only in the alert card. The D charts are monitoring
   evidence, not a prediction panel.

## Paper mapping

This supports the three relevant AI Casino chart families without conflating
them:

| Paper family | Dashboard field / status |
|---|---|
| `Deleveraging` | `letf_aum_sum_krw` time series |
| `Leverage ETFs turnover / cash equity turnover` | `letf_turnover_ratio` |
| `Rebalancing flows / cash turnover (7dma)` | rolling `implied_rebalance_ir_pct`, labelled model estimate |

The dashboard must not say it has observed forced sales, actual end-of-day
rebalance executions, dealer gamma hedging, or a causal price impact.
