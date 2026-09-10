# Portfolio Lab browser numerical engine — T25

Pure, dependency-free ESM. No network, storage, telemetry, DOM, clock or Python
runtime is used by the engine. Both Claude-owned screens import **this same
module**. No build step; deploy the directory with the site's other static assets.

```js
const {analyzePortfolio, pricesToLogReturns} = await import('/portfolio-engine/index.mjs');

// Tiny illustrative inputs, not a market dataset. Real analysis needs history.
const history = pricesToLogReturns({
  dates: ['2025-01-06', '2025-01-07', '2025-01-08'],
  prices: [[100, 1], [101, 1], [99, 1]], // date × asset, already in KRW
});
const result = analyzePortfolio({
  ...history,
  positions: [
    {id: 'resolved-stock-id', currency: 'KRW', asset_class: 'equity', value: 800000},
    {id: 'cash:krw', currency: 'KRW', asset_class: 'cash', value: 200000},
  ],
  baseCurrency: 'KRW', netAssetValue: 1000000, creditUsed: 0,
  riskFreeRateAnn: 0.03, // supplied annual decimal, 0 is honored
});
// Basic and Expert render the SAME result. Do not calculate twice or persist it.
```

## Boundary / ownership

```text
Claude: manual rows OR local spreadsheet/CSV parser
  → resolve instrument identity + currency, value positions using quote/FX
  → retrieve public price histories (symbols only through existing proxies)
  → local dated FX conversion + explicit calendar/missing-price policy
Codex: pricesToLogReturns → analyzePortfolio → numeric result
Claude: Basic | Expert presentation of that one result
```

The engine does not call `/api/quote` or `/api/futures`: reuse those **in the
caller**, passing only public symbols/range, never quantities, NAV, average
purchase cost, uploaded files or the serialized portfolio. A spot quote alone is
not a historical return series. Never fabricate futures history from a spot.
No Supabase change, spreadsheet library, ticker search UI, `portfolio.js`,
`mypage.js`, `app.js`, Worker edit, or deployment is included here.

The original CLI normalize/resolve/price-fetch/forward-fill/report-copy functions
are not browser dependencies. This is the numerical module and a valued-account
adapter, **not a drop-in clone of the offline report renderer**.

## Inputs

- `positions[]`: unique resolved `id`, `currency` (trading currency, e.g. HKD),
  `asset_class`, and signed **current market value in selected base currency**.
  Positive = long, negative = short. Merge duplicate rows in the caller before
  calculating. No silent ticker substitution or 20-name truncation is performed.
- `logReturns`: dense date × position matrix; column order must match positions.
  All values must already incorporate historical FX into the selected base
  currency. Decimals, not percentages. `dates`: unique increasing weekday ISO
  dates; at least 2 return observations (= at least 3 price rows).
- `netAssetValue`: positive current NAV in KRW or USD, **not a future budget**.
  Simple long-only accounts can omit it (sum of values inferred). A positive
  residual becomes flat base cash; already-entered base cash is augmented.
- With shorts or credit: explicit NAV and full collateral/cash ledger required;
  `sum(signed current values) - creditUsed = NAV`. Mismatch raises an error, no
  guessed collateral or residual cash. Tolerance is max(1e-8, NAV × 1e-10).
- Weights are `signed value / NAV`. Gross exposure can exceed 100%; **do not
  renormalize by sum(abs(weights))**. Base cash is identified by selected
  currency, regardless of the Python registry's legacy `fx_as_asset` flag.
- Current quantity × current price × current FX gives `value`; average purchase
  cost/date are for a separate personal P&L/account-history feature, not this
  constant-weight historical risk simulation.
- `caps` optional array, each entry null or [0,∞) fraction of NAV. No risk-profile
  defaults are invented. Supply only user-confirmed constraints, or omit to show
  an unconstrained long-sleeve HRP reference. Risk-profile warning cards remain
  the caller's responsibility; there are no execution/trade controls here.

## Prices, currency, missingness and leverage

`pricesToLogReturns({dates, prices, syntheticLeverage?})` takes **base-currency**
positive adjusted-price rows and returns `{dates, logReturns}`. It does not fetch,
sort, drop missing assets, forward-fill, guess FX, or fill missing prices with 0.
Validate unresolved symbols and stale/missing histories before calling it. The
caller must expose any holiday carry-forward policy and stale-price diagnostics.
Weekends must be removed at the price-row level **before** taking returns.

FX conversion must be date-matched: local price × (base units per local unit).
Examples: USD→KRW multiply by USDKRW; KRW→USD divide; HKD→KRW multiply by
USDKRW/USDHKD. If these histories are missing, show unavailable instead of using
today's FX for the entire past. Base cash has zero returns; foreign cash has FX
returns. Do not treat `cash:usd` as risky in a USD account.

Use adjusted prices consistently (splits/dividends); unadjusted fallback must be
disclosed by the caller. Actual **7709.HK** is its own HKD traded series and gets
factor **1**, not another ×2. Only an explicitly labeled synthetic underlying
proxy receives `syntheticLeverage[j] = 2`. The Python transformation order is
preserved: base-currency simple return × factor, then `log1p`.

## Exports / outputs

| Export | Purpose |
|---|---|
| `analyzePortfolio` | Valued account → accounting, cash breakdown, risk, covariance and cash/short-fixed HRP advice |
| `analyzeRisk` | Lower-level aligned log returns + signed NAV weights → numerical bundle, unconstrained all-asset `hrp_weights` |
| `pricesToLogReturns` | Supplied base prices → log returns, optional explicit synthetic leverage |
| `sampleCov`, `ewmaCov`, `ledoitWolfCov`, `corrFromCov` | Covariance/correlation primitives; LW returns `{covariance, shrinkage, mean_corr}` |
| `hierarchicalClusters`, `hierarchicalRiskParity`, `allocateLongSleeve` | Average-linkage HRP and optional bounded long-sleeve allocation |
| `portfolioReturns`, `riskContribution`, `annReturn`, `annVol`, `sharpe`, `histVarCvar`, `parametricVar` | Standalone math primitives |

All arrays in `analyzePortfolio` align with returned `asset_ids` (including any
appended residual cash). Use `advice.target_weights`, **not** a second all-asset
HRP calculation. Fixed base cash and shorts stay fixed, long positive positions
retain their aggregate NAV budget. If caps cannot absorb the budget, target and
delta are null and `allocation_status = 'infeasible_caps'`; show an explanation,
not a suggested trade. Fixed-sleeve cap violations are separately reported.

`schema_version = portfolio_engine_v1` deliberately differs from offline
`portfolio_analysis_v1`. The numeric keys `performance`, `accounting`,
`cash_breakdown`, `risk`, and `advice` are available; UI-copy blocks,
`profile_check`, stress-window narratives, registry names, and quote-source
metadata are **not synthesized**. Claude supplies rendering/copy and source
metadata. No claim is made that the old static renderer can consume this whole
object without an adapter.

Money keys use `_amount`, denominators are NAV, units are `base_currency`.
`risk.long.var_1w_95`/`cvar_1w_95` are WEEKLY, not monthly. Missing 1M/3M/1Y
history returns null (unavailable), never a made-up zero. Invalid inputs throw
TypeError/RangeError; the UI must catch and show validation, not a stale result.

## Exact parity and deliberate safety differences

Ported Python at branch source `b3c71d32`:

- EWMA: demean full short window; initialize sample covariance ddof=1; λ=.94.
- LW: **the repository's simplified constant-correlation shrinkage formula**,
  not sklearn's identity-target estimator or a claim of full textbook LW.
  Sample denominator T for multiple assets, eigenvalues floored at 1e-12;
  single-asset branch retains Python ddof=1. Jacobi symmetric eigensolver.
- HRP: average linkage, sorted-ID strict-`<` tie selection, recursive bisection
  and inverse-variance cluster weights. No expected-return forecast.
- Returns: simple-return mix of signed NAV weights, then log1p. CAGR and Sharpe
  match Python: `(historical CAGR - annual rf) / annualized log-return volatility`.
  This is not an arithmetic excess-return Sharpe. Short window 252d; weekly
  W-FRI sums (including empty intervening weeks) up to 260w.
- Historical VaR: linear quantile at 5%, inclusive tail CVaR, positive losses.
  Parametric 10d uses fixed 95% normal z and square-root-of-time scaling, not a
  worst-case loss or forecast. Sample vol ddof=1, annual factors 252/52.

Deliberate deviations: reject insolvency/simple return ≤−100% instead of Python
clipping; reject missing/nonfinite inputs instead of silent dropping; unsupported
VaR confidences raise (95%/99% supported); all-flat HRP gets a neutral split;
cash/short-only accounts stay fixed instead of fallback all-long HRP; infeasible
caps are explicit instead of the Python 20-pass cap/renormalization bug. Base
cash is currency-relative (USD works); `_krw` and monthly-mislabeled weekly keys
are not copied. Costs, financing interest and tax modeling remain out of scope.

## Golden provenance — do not “fix” NAV to fit the old golden

`scripts/금융_재무분석/tests/golden/user_balanced_metrics.json` is unchanged.
Its four numbers reproduce **exactly on legacy gross-normalized weights**.
Current Python returns.py preserves NAV weights, so its current output differs:

| Metric | Original gross golden | Current NAV Python = JS |
|---|---:|---:|
| 1Y / annual short return | 0.4212933686353064 | 0.4727482469970974 |
| Short volatility | 0.15636879600128953 | 0.17282428775021505 |
| Short Sharpe | 2.5023750175327786 | 2.561840426254246 |

Same existing cache, 1,291 aligned observations, 2021-08-11–2026-08-07. The
sample includes a short: NAV=9.5m KRW vs gross=10.5m KRW. The bundled regression
input freezes its final 252 aligned rows, both weight bases and cache SHA256s.
This is the repository's existing example, not visitor data. Original four
golden metrics are asserted on their original basis; a separate NAV fixture
prevents reintroducing gross normalization. Do not overwrite the old golden
or mark it as NAV-compatible. No prices were recollected.

## Tests (repository root)

```bash
node --test tests/portfolio-engine/*.test.mjs
# Also rerun the current Python oracle and the full existing cache:
PORTFOLIO_PYTHON=/absolute/path/to/python-with-numpy-pandas \
PORTFOLIO_CACHE=/absolute/path/to/existing/cache/prices \
node --test tests/portfolio-engine/engine.test.mjs
# Optional real Chromium (installed Playwright, no downloads required):
PORTFOLIO_PLAYWRIGHT=/absolute/path/to/playwright/index.mjs \
node --test tests/portfolio-engine/browser.test.mjs
```

Ordinary tests require only Node and the checked-in deterministic fixtures.
Optional Python/cache/browser tests are visibly skipped unless their environment
variables are supplied. With them set, failures/missing dependencies are errors,
not silently skipped. Python oracle disables socket connections and uses
cache-only reads. Numerical tolerance: max(1e-11 absolute, 1e-9 relative), also
used across Node/Chromium floating-point implementations. No dependency on dates
“today”, remote prices or personal portfolios.

Fixtures cover covariance/shrinkage/HRP/RC/VaR/CAGR/Sharpe, singleton, near singular,
short/credit, 2-observation edge; account tests cover cash, USD/HKD, residuals,
caps, insolvency, bad inputs, leverage, 20×1260 scalability, immutability.
Chromium test imports native modules through intercepted in-memory responses,
then disables network/storage APIs and checks no requests during calculation.
This proves module behavior, not privacy of Claude's eventual whole-site wiring.
