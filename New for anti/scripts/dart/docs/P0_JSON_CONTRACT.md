# P0 static KFA JSON contract

This document defines the handoff from the Codex financial engine to a later
Worker/UI adapter.  The static asset is a source-qualified snapshot, not a
forecast, quote feed, or investment recommendation.

## Compatibility

Existing UI consumers keep reading:

```json
{
  "basic_cards": {
    "revenue": {"value": 0, "series": [{"year": 2025, "end": "2025-12-31", "value": 0}], "reason": null}
  }
}
```

P0 adds (rather than replaces) `snapshot_contract`, `currency_contract`,
`entity_policy`, `period_lineage`, `data_quality`, and `unified_views`.

## Currency and scope

`currency_contract.calculation_currency` is the filing currency.  It is also
the default `display_currency`.  A USD-to-KRW display requires an explicit FX
rate, source, and as-of date; no static snapshot silently converts a model
input.  `meta.fs_div` and each lineage record preserve `CFS`/`OFS` scope.

## Period lineage

Annual static samples only contain annual records.  The future live adapter
may materialise a `kfa-quarter-lineage/1` block with the following invariant:

- direct discrete quarter observation first;
- YTD subtraction only for P&L and cash-flow flows;
- balance-sheet data are point-in-time and never subtracted;
- conflicts, missing predecessor periods, scope mismatch, or unit mismatch
  result in `null + reason`, never interpolation.

## Entity and model policy

Financial entities are gated from industrial FCF, EBITDA, net-debt and DCF
chains.  Static exports do not create valuation assumptions.  A model without
verified inputs remains `needs_input`/`omitted`; there is no automatic target
price or recommendation.

## EBITDA

EBITDA is available only when the source contains all three reported facts:

`operating income + PPE depreciation + intangible amortization`.

Operating income is not an EBITDA proxy in P0 static output.  Legacy samples
without the two depreciation components intentionally expose `null` with a
reason.
