# Market microstructure deployed review — 2026-08-20

Target reviewed: deployed Workers site and latest `origin/main`.  Every visible
card/modal in the four market-microstructure tabs was opened.  This document is
the UI/deploy handoff; Codex did not edit `market-microstructure.js`, `app.js`,
`index.html`, `style.css`, or `.github/workflows/**`.

## What is already sound

- Concentration: Top2/5/10 each has 132 observed sessions (2026-02-03 through
  2026-08-19); chart and 30/90/all switching work.
- Price-level flow: KOSPI 157 sessions and per-stock histories render by chosen
  1/2/3/6-month/all windows.  Price-band and five-session drill-downs work.
- Credit overlay: 188 daily observations align deposit, credit loan, and
  uncollected balances to the price date axis without filling holidays.
- Derivatives EOD snapshot separates foreign public-dashboard `as_of` from KRX
  market-activity `as_of`.  Missing call/put foreign split and OI are left blank.
- All tested buttons opened; no market-microstructure JavaScript exception was
  observed.  The console warning encountered was from an unrelated weather block.

## Data limits found in the deployed output

| Block | Real observations | Current judgement |
|---|---:|---|
| A concentration | 132 | chart-ready |
| B market LETF activity | 4 | accumulation only |
| C direction buckets | 4 | accumulation only |
| D Hynix/Samsung LETF | 4 per ticker | accumulation only |
| price-level flow | 157 index / 180 raw stock | chart-ready |
| credit overlay | 188 | chart-ready |
| K200 market activity | 4 | accumulation only |
| foreign K200 flow | current EOD snapshot | no history in this UI |

Observed four-day logs contain 2026-08-07/13/14/18 for direction and stocks;
derivatives activity contains 2026-08-12/13/14/18.  A four-point line is not a
trend and must not be rendered as one.

## P0 — required UI correctness changes

1. **History readiness:** in `market-microstructure.js` `msHistChart` and
   `msHistBlock`, replace the two-observation threshold with five.  Show N/5 and
   no chart at N<5.  Update B/C/D footnotes that still say two observations.
2. **Hynix routing:** the D-table Hynix `추이` currently routes to `alert_letf`
   while Samsung routes to `stock_letf:<ticker>`.  Route both D rows to the
   generic stock history.  Preserve the separate Hynix alert card route.
3. **AUM provenance:** the UI currently says product AUM is observed.  Read the
   new `letf_aum_quality` and product `aum_quality/aum_source`; label `MKTCAP`
   fallback as a proxy, not observed net assets.
4. **US evidence modal:** add `premarket_gap`, `premarket_gap_quality`, and show
   `rules_ko`/`rule_ko`.  The Python engine now emits only the conditions that
   actually fired.  Do not substitute a generic P/C rule.
5. **Volatility channel availability:** if
   `channels.vol_up.observable === false` or `vol_down.observable === false`,
   render `판정 불가` plus `unavailable_reason_ko`, not `quiet`.  A single IV
   level and call/put volumes do not identify long-vol versus short-vol.

## P1 — requested interaction and naming

1. Navigation, loading text, placeholder, and page H1 still say `호가 및 유동성`
   / `Market Micro-metrics`.  Rename consistently to `시장 미시구조` /
   `Market Microstructure`; the four tab names remain unchanged.
2. Credit summary cards are disabled even though the combined overlay works.
   Make `신용융자`, `미수금`, and optionally `예탁금` cards open the same-date
   individual history modal (or activate the overlay and focus that series).
   Never give the three balances one shared numeric y-scale.
3. Follow every acceptance item in `CLAUDE_HANDOFF_LETF_DELEVERAGING.md`,
   including the two new estimated series and five-observation threshold.

## Backend defects corrected in the accompanying Codex patch

- Cboe previous close + Yahoo premarket price now recompute one internally
  consistent gap; the prior JSON could display one price pair while using a gap
  calculated from another denominator.
- Missing `day_return`, option volume, or FINRA values remain null instead of
  becoming a flat/zero observation.
- Vol-long/vol-short no longer fire without a comparable ATM IV change.
- `evidence_us.rule_ko` is built from the actual fired rule; gap-only evidence
  no longer falsely claims P/C ≥1.1.
- KRX/FDR AUM provenance is explicit; market-cap fallback is `proxy/partial`.
- Hynix/Samsung JSONL gains exact signed estimated-rebalance fields and a KRX
  EOD backfill script that does not attach current Naver flows to past dates.
- B/C direction and K200 futures/options activity gain a separate KRX-only EOD
  backfill script; it stores no investor flow/OI and skips holidays.

## Statements the UI must not make

- Four observations establish a trend, threshold, or warning level.
- LETF/spot turnover proves price distortion or a forced rebalance trade.
- `implied_rebalance_krw` is an observed ETF order, dealer hedge, or price impact.
- Total option buy/sell discloses foreign call-versus-put direction.
- KRX trading volume is open interest or a held position.
- P/C volume identifies the buyer, hedge motive, or next Korean return.
- `quiet` volatility is known when IV-change data is unavailable.
- `MKTCAP` fallback is observed ETF AUM.

## Claude verification order

1. Apply the UI items without changing Python field names or formulas.
2. Run the two backfill tools once for an agreed historical range, then run the
   daily builders so corrected US JSON and new stock history fields are
   published.  Do not seed missing days.
3. Run `python validate_ui_contracts.py` and the normal ownership guard.
4. Open all four tabs, every card, and 30/90/all once on the deployed site.
5. Specifically verify N=4 fallback, both stock routes, a gap-only US evidence
   modal, vol unavailable state, AUM proxy wording, and the three credit cards.
