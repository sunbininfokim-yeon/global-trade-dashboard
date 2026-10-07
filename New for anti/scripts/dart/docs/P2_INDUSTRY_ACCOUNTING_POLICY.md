# P2 industry accounting policy

P2 turns an industry-kit label into a constrained accounting policy.  A kit
does not itself create a number, infer a note disclosure, or justify a
valuation assumption.

## Scope

| Area | P2 behaviour | Not permitted |
| --- | --- | --- |
| Shipping / airline leases | Shows a lease-excluded liabilities-to-equity view only where the kit requests it and total lease liabilities, total liabilities and equity share one reported balance-sheet period, scope, currency and unit. | Treating a current lease maturity, high debt ratio, or a generic liability as total lease debt. |
| Shipbuilding advances | Shows a contract-liability-excluded liabilities-to-equity view only where all three reported balances match. | Calling a current-only contract liability the total advance balance. |
| Segment profit / order backlog | Passes through P1 structured, reported table rows with source table/row provenance. | Parsing a note sentence, using LLM extraction, or estimating order backlog. |
| Other kits | Prioritise existing reported metrics and checklist items; no adjustment is emitted unless declared in the kit. | Applying shipping's lease adjustment to every company that has a lease balance. |

`debt_ratio_ex_lease` and `debt_ratio_ex_contract_liab` are analytical
presentation adjustments, not replacements for the statutory ratio.  The
output retains the formula and input-basis metadata.  Missing or incompatible
inputs never get a zero or an inferred amount; the computed adjustment key is
absent and `industry.adjustment_status` explains why.

## P1 boundary

P1 remains the only route for `segment_profit` and `backlog_order_book`.
Its acceptance contract requires structured reported rows, a report ID, table
and row identifier, compatible period/scope/currency, and source provenance.
P2 only exposes that status to a relevant industry kit.  It does not fetch,
scrape, or interpret DART note prose.

## Financial entities

The P0 financial-entity policy remains higher priority than every industrial
kit.  Banks, insurers and suspected financial issuers receive no industrial
lease, contract-liability, FCF, EBITDA, net-debt or DCF interpretation.

## Delivery boundary

This engine contract is ready for a later Worker/UI adapter.  The adapter
should display `industry.adjusted_metrics` only when present, and otherwise
hide the card or use the explicit `industry.adjustment_status.reason`.  It
must not reconstruct an adjusted ratio in JavaScript.
