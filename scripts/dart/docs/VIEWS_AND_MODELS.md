# KFA views and model contracts

Basic is the common financial-statement layer.  Investor, PE and Deal may
repeat Basic cards and add their own cards; a repeated number is preferable to
silently applying a different definition in each view.

## Card rules

- Money is stored in the issuer's statement currency and in native statement
  units.  The engine does not convert USD to KRW without a supplied FX rate,
  source and as-of date.
- A ratio uses only facts with the same fiscal end.  Annual and quarterly facts
  are never joined merely because their calendar year matches.
- `CFS` and `OFS` do not mix.  The entity / consolidation scope is part of a
  source adapter's identity key.
- `null` is a valid result only with a reason.  `0` is a calculated zero, not a
  stand-in for a missing fact.

## Investor

| Card / model | Definition | Gate |
| --- | --- | --- |
| Owner earnings | Net income + D&A − min(abs(D&A), abs(Capex)) | D&A and Capex are both reported; proxy is labelled |
| Earnings quality | CFO / Net income | same fiscal end, non-zero NI |
| Margin trend | operating income / revenue by year | same fiscal end |
| OE hurdle | Owner earnings capitalised at 8/10/12% hurdle | growth < hurdle; no per-share target |
| Reverse DCF | CAGR that makes the FCFF equity value equal supplied market cap | all FCFF inputs + market cap |
| OE yield | Owner earnings / market cap | OE + market cap |

## PE

| Card / model | Definition | Gate |
| --- | --- | --- |
| EBITDA or EBIT proxy | Reported EBITDA; EBIT only if D&A unavailable | proxy is labelled |
| Net debt / EBITDA | net debt / reported EBITDA or labelled EBIT proxy | positive denominator |
| FCF / EBITDA | FCF / reported EBITDA or labelled EBIT proxy | positive denominator |
| Maintenance Capex burden | min(abs(D&A), abs(Capex)) / revenue | proxy is labelled |
| NWC change / sales | annual change in operating NWC / annual revenue | two aligned annual NWC facts |
| Delever path | current net debt reduced by FCF over 5 years | constant-FCF assumption is shown |
| Coverage capacity | current interest coverage and/or net debt / EBITDA | no target leverage is imposed |
| FCF entry yield | FCF / equity value and FCF / EV | market cap required |

## Deal

| Card / model | Definition | Gate |
| --- | --- | --- |
| Trading multiples | issuer P/E, P/S, EV/EBITDA; peers only if supplied | no invented peer group |
| EV bridge | market cap + net debt | market cap + net debt |
| QoE flags | cash-conversion facts only | not a substitute for note-level QoE work |
| Segment | reported/provided segments | no segment inference |
| FCFF DCF | 5-year bear/base/bull, FCFF and WACC sensitivity | reported historical seed inputs |
| SOTP / EV bridge | provided segment values less discount / net debt | segment inputs, otherwise bridge only |
