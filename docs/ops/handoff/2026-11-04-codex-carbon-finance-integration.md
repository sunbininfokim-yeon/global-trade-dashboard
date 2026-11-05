# CF04 — EUA market / FuelEU independent audit / equal-energy economics

Branch: `codex/carbon-finance-integration-20261104`. Base: `a899cdf0b803f03a87d5ae34401bc4dad6f95d52`.

Checkout: `/Users/yeoninair/Documents/해운 데이터/carbon-finance-integration-20261104`.
Prior uncommitted work at `shipping-carbon-finance-pr-20261101` remains preserved; do not reset it.

User approved the EUA screen, independent FuelEU verification, and combined cost/funding work on 2026-11-04.
Scope is `tools/shipping_carbon/**`, CF04 TASKS row and this handoff. Claude FuelEU source, production UI,
Worker and workflows are unchanged. No main merge or operational deployment.

## Run and result

`python3 tools/shipping_carbon/server.py --port 8775` then `/climate`.

- EUA daily volume-weighted auction line/supply bars, filters, cover/bidders, observation CSV, EEX gross OI.
- Same-date/venue EUA settlement CSV with missing/zero, expiry, product/type and duplicate validation.
- Corporate shortfall/lot/stress and signed dealer inventory/futures/customer-supply exposure.
- Independent Claude MRV estimator audit: field coverage, actual zero, positive/consistent input, duplicate IMO,
  original/no size proxy and count +/-20% sensitivity. Hypothetical missing-field challenges are explicitly synthetic.
- Equal-energy fossil+pool versus blend+residual pool. Separate ETS factors/scopes, compliance-year-matched
  user pool quotes, no uncontracted surplus revenue, delivered bio price breakeven.
- FuelEU is called unchanged in a separate interpreter to avoid mixing two engine.py modules. Implementation hashes returned.
- Dated fuel/EUA/pool/fee payments and fixed customer receipt, actual/365 interest and end-of-day funding peak.
  Missing financial inputs hold financial results. IM/VM remain in the existing shipping contract tool.
- Input edits invalidate prior results/export; out-of-order responses are discarded.

## Actual source verification

Collected 2026-11-04: EEX auction 189 / ECB 215 observations through 11/03; EEX FEUA OI 11 months observed 11/02.
These references are not executable quotes. Raw prices, original workbooks, audit JSON and captures stay in ignored source_data/.

EMSA listing and complete 2024 v254 / 2025 v80 XLSX obtained. ZIP integrity checked; partial downloads were not audited.
Initial timeout diagnostics remain separate from the later successful audit. CLI supports bounded curl and explicit local-file/listing replay.

2025 Full ER: 17,430 reports. No tested missing/nonfinite fields. Strict usable input 15,359 excludes 2,070 actual-zero
fuel/CO2 reports and one scope inconsistency. Under the same size proxy, the aggregate is unchanged: the missing-to-zero
code path is a demonstrated future-input risk, not evidence of current snapshot distortion. Proxy sensitivity is not
an official ship balance or confidence interval; future target comparisons freeze the fleet/fuel assumptions.

## Checks

Python 53, market JS 5, design arithmetic 16, ownership 15 passed. Chrome real-data chart/volume/OI, filters, roles,
valid/rejected CSV, combined API and stale export defense, actual audit tables, all modules at 320px, light/dark,
no page errors. git diff --check clean. No changed paths under tools/fueleu, New for anti or .github.

## Integration boundary

PR #794 merged the local observed-data work; deployed carbon UI still uses an explicit synthetic fixture.
This follow-up does not replace production prices or copy OPX quotes. Fuel/pool prices, ETS factors, eligibility
and technical scope require scenario inputs. Refer to README.md and MARKET_RESEARCH.md for source links and replay commands.
Production routing, data rights, scheduling and deployment are separate integration work.
