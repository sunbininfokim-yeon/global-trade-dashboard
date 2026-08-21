# Claude handoff — Hynix/Samsung LETF deleveraging UI

Scope: `New for anti/market-microstructure.js` only.  Do not recalculate the
model in JavaScript and do not rename the fields below.

## Data contract supplied by Codex

`public/data/stock_letf_history_v1.jsonl` remains the one shared log.  Filter by
`ticker` (`000660` Hynix, `005930` Samsung).  New observations contain:

```json
{
  "date": "YYYY-MM-DD",
  "as_of": "YYYY-MM-DD",
  "source": "...",
  "quality": "observed|partial|estimated",
  "ticker": "000660",
  "underlying_day_return": -0.0123,
  "implied_rebalance_krw": -123000000000.0,
  "implied_ir_pct": 4.25,
  "implied_rebalance_quality": "estimated",
  "implied_rebalance_formula": "signed Σ[AUM × (L² − L) × underlying_day_return]; implied_ir_pct=abs(net sum)/spot daily trading value ×100; model estimate, not observed ETF trades or price impact"
}
```

Rules enforced in Python:

- `implied_rebalance_krw` is the **signed net sum** `total_rebalance(...).tr_total`.
- `implied_ir_pct` uses `abs(tr_total)`, not `tr_abs_sum`.
- Missing daily return, spot trading value, product AUM, leverage, or products
  makes both metrics `null`, never zero.
- `implied_rebalance_quality` is always `estimated`; it is not an observed ETF
  order or trade.
- No moving average is stored.  Holidays have no row.
- Each product also carries `aum_source` and `aum_quality`.  `MKTCAP` fallback
  means `aum_quality=proxy`, and the parent history row is `quality=partial`.

The one-time KRX EOD backfill is implemented in
`backfill_single_stock_letf_history.py`.  It explicitly disables current Naver
investor flows for historical dates.

## Required UI changes

1. In `msStockLetfSeries`, retain the existing four observed series and append:
   - signed `implied_rebalance_krw`, unit 조원;
   - `implied_ir_pct`, unit %.
2. If a 7-observation moving average is useful, calculate it in JS from the
   available trading observations only.  Do not fill holidays and do not treat
   null as zero.  Do not draw the MA before seven finite observations.
3. `msHistChart` and `msHistBlock` must require **five finite observations**,
   not two.  With 0–4, show `히스토리 축적 중 · N/5 거래일` and no line.
4. In the D table, route both Hynix and Samsung `추이` buttons to
   `stock_letf:<ticker>`.  Keep `alert_letf` only for the separate Hynix alert
   card, because its historical bucket table answers a different question.
5. In each stock modal, label the new charts exactly:
   - `추정 리밸런싱 압력 (부호 포함)`;
   - `추정 압력 / 현물 당일 거래대금`.
   Add: `일일 리셋 공식 추정치이며 실제 ETF 주문·체결·가격영향이 아님`.
6. Replace unconditional `순자산(AUM) 실측` wording:
   - `letf_aum_quality === observed` → `순자산총액 관측`;
   - `proxy` or parent `quality === partial` → `시가총액 기반 순자산 프록시`;
   - missing → blank.

## Acceptance checks

- Hynix and Samsung open the same generic six-series history component.
- Four rows never appear as a smooth trend; 30/90/all controls appear at N≥5.
- A negative estimate remains negative in the tooltip and table.
- A null estimate creates a gap, not a zero point.
- The Hynix alert card still opens its bucket statistics, separately.
- No text calls the estimate an observed rebalance, forced buy/sell, or price impact.

