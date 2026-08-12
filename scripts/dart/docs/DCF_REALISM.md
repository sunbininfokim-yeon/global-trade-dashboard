# FCFF DCF realism rules

This engine produces a transparent valuation reference, not a price target,
recommendation or implied action.

## Inputs

- Seed revenue CAGR from the issuer's reported annual revenue series; it must
  contain two positive, aligned fiscal-year observations.
- Seed EBIT margin from the latest reported annual operating income / revenue.
- Use reported tax rate, Capex / sales, D&A / sales and operating NWC / sales.
- If an input is absent, FCFF DCF is omitted.  The engine never fills missing
  accounting inputs with an industry average.
- WACC may be supplied with its source and as-of date.  Otherwise the engine's
  9% default is expressly labelled non-company-specific.

## Scenarios

| Scenario | Revenue CAGR | EBIT margin |
| --- | --- | --- |
| Bear | reported seed − 2 percentage points | reported seed − 1 percentage point |
| Base | reported seed | reported seed |
| Bull | reported seed + 2 percentage points | reported seed + 1 percentage point |

All scenarios forecast five years.  Terminal growth is 2% by default and may
not exceed 3%.  The result always contains the 7%, 8%, 9%, 10% and 11% WACC
sensitivity values for the base case.

## Formula

`FCFF = EBIT × (1 − tax) + D&A − Capex − Δoperating NWC`

`Terminal value = FCFF₅ × (1 + terminal growth) / (WACC − terminal growth)`

Enterprise value equals present value of the forecast FCFF plus present value
of terminal value; equity value equals enterprise value less reported net debt.
No per-share value is emitted by this KFA contract.

## Non-comparable sectors

Banks, insurers and other financial institutions do not use this industrial
FCFF/NWC/debt framework by default.  If classified as such, the source adapter
must mark the relevant models `omitted` and provide a sector-specific model
later.  Lease-heavy, shipping and project-finance issuers must keep lease debt
separate from drawn debt unless the chosen debt policy explicitly includes it.
