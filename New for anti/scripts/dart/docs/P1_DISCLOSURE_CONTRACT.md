# P1 disclosure add-on contract

`dart_kfa.p1_disclosures.build_p1_disclosures()` is an offline, JSON-facing
add-on to the P0 `canonical-financial-facts/1` contract.  It deliberately does
not alter `dart-company-v2`, static snapshot shapes, Worker code, or UI code.
An adapter can attach its output later under a new `p1_disclosures` key.

## Input boundary

The primary input is one P0 canonical object.  P1 uses only these canonical
account IDs:

| P1 output | Required P0 accounts | Rule |
| --- | --- | --- |
| `ebitda` | `OPERATING_INCOME`, `PPE_DEPRECIATION`, `INTANGIBLE_AMORTIZATION` | Exact sum of the three facts only. |
| `receivables_to_sales_pct` | `TRADE_RECEIVABLES`, `REVENUE` | Endpoint receivables / same-period revenue × 100. |

`DEPRECIATION`, a combined depreciation-and-amortisation line, CFO, a proxy,
or an estimate are never substituted for the strict EBITDA inputs.  An adapter
that cannot identify reported PPE depreciation and reported intangible
amortisation separately must leave those account facts unavailable.

Every EBITDA input must be an available P0 `flow` fact with identical fiscal
year, fiscal quarter, period start/end, flow basis, CFS/OFS scope, and
normalised currency/unit.  The result is then a `derived_deterministic` value.
Otherwise it is `null` with `missing_or_incompatible:...` reason and all input
references are retained in `provenance.input_facts`.

Receivables is a balance; revenue is a flow.  P1 therefore matches their
fiscal year, quarter, endpoint, scope, and normalised currency/unit, rather
than falsely requiring equal flow starts.  A zero revenue denominator is
unavailable rather than infinite.

## Periods and history

`period_selection` resolves a current endpoint in this order:

1. `Q3` (DART 11014)
2. `Q2` / H1 (DART 11012)
3. `Q1` (DART 11013)
4. `annual` / FY (DART 11011)

It selects only an endpoint for which a P0 fact is actually available; P0's
placeholder cells are not treated as a filing.  `requested_endpoint` accepts
`H1` and `FY` aliases, which resolve to `Q2` and `annual`.  Report code/type,
period start/end, scope, and report ID(s)/type are always included in the
selected output.

Pass separately adapted annual canonical objects through `annual_history`.
They are output in `annual_history`, never merged into the current quarterly
endpoint or interpolated from interim data.

## Structured disclosures

`structured_disclosures` is optional.  P1 accepts `segment_profit` and
`backlog_order_book` rows only if each row has:

```json
{
  "disclosure_type": "segment_profit | backlog_order_book",
  "is_structured_reported": true,
  "segment_id": "optional-stable-id",
  "segment_name": "reported label",
  "value": 0,
  "unit": {"kind": "currency", "currency": "KRW", "scale": 1},
  "fiscal_year": 2025,
  "period_end": "2025-09-30",
  "fs_div": "CFS",
  "report_id": "receipt number or accession",
  "report_type": "quarter_report",
  "source_table": "reported table identifier",
  "source_row_id": "reported row identifier"
}
```

Rows must match the selected fiscal year, endpoint, scope, and canonical
currency.  Note text, heuristic/LLM extraction, or a value without the
structured marker is rejected as `rejected:unstructured_note_evidence`; it is
not parsed or guessed.

## Output shape

```json
{
  "schema_version": "kfa-p1-disclosures/1",
  "classification": "p1_disclosure_addon",
  "period_selection": {"requested": "latest", "selected": "Q3"},
  "current": {
    "period": {"report_code": "11014", "report_type": "quarter_report"},
    "ebitda": {"status": "derived_deterministic", "value": 0, "provenance": {}},
    "receivables_to_sales_pct": {"status": "derived_deterministic", "value": 0},
    "segment_profit": {"status": "reported | unavailable", "value": []},
    "backlog_order_book": {"status": "reported | unavailable", "value": []}
  },
  "annual_history": []
}
```

Values are intentionally classified as `reported`, `derived_deterministic`,
or `unavailable`.  This contract provides no investment recommendation,
price target, or automatic valuation.
