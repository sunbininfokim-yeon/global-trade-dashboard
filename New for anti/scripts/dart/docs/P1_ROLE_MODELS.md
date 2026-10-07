# P1 role-model contract

`dart_kfa.p1_models.build_p1_models()` emits a separate JSON model contract.
It does not alter reported facts, legacy cards, or the Worker/UI.  All model
amounts remain in the canonical filing currency.

| View | Models | Calculation rule |
| --- | --- | --- |
| Fundamental investor | `oe_hurdle`, `reverse_dcf`, `oe_yield` | Owner earnings needs an explicit maintenance-Capex input. Reverse DCF needs explicit discount and operating assumptions. Market cap needs source, as-of date and matching currency. |
| PE | `delever_path`, `coverage_capacity`, `fcf_yield_entry` | Any EBITDA-dependent model uses P1 strict EBITDA only: operating income + separately reported PPE depreciation + separately reported intangible amortisation. Combined D&A or EBITDA proxies are prohibited. |
| IB | `fcff_dcf`, `trading_comps`, `sotp_or_ev_bridge` | FCFF needs explicit assumptions. Comps and SOTP accept only supplied observations with source, as-of date and matching currency. |

## Status policy

- `computed`: every reported and explicit input passed validation.
- `needs_input`: a user or adapter must provide a named non-accounting input.
- `omitted`: a filing input is missing, incompatible, estimated, or violates a
  model rule.
- `not_applicable`: financial entity policy blocks industrial models.

The result is not a recommendation or price target.  A presentation adapter
may show a scenario/value output only alongside its exact assumptions and
source metadata; it must not convert model currencies implicitly.
