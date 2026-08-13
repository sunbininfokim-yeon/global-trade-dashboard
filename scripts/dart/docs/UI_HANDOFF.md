# KFA → UI handoff (Claude)

## 범위
- Engine only under `scripts/dart/`.
- Sample live numbers: `public/data/kfa_aapl_v1.json`, `public/data/kfa_005930_v1.json`

## JSON shape (`kfa_*_v1.json`)
```
schema: kfa_engine_v1
view_presets.default_view = "basic"
view_presets.views.{basic|investor|pe|deal}.cards[]
view_presets.views.*.models[]
accounting_pack
  pnl.{revenue,operating_income,net_income,ebitda}.{value,series,margin}
  cash_flow.{cfo,capex,fcf}.{value,series}
  liquidity.{cash_and_equivalents,debt_due_within_1y,liquidity_coverage_1y,interest_coverage,current_ratio}
  debt_structure.net_debt
  working_capital.ccc_days
  alignment / reasons[]
investor.owner_earnings / market / models.{oe_hurdle,reverse_dcf,oe_yield}
pe.models.{delever_path,coverage_capacity,fcf_yield_entry}
deal.models.{fcff_dcf,trading_comps,sotp_or_ev_bridge}
```

`basic_cards` remains the UI card bag for every view.  A non-Basic card must
always have `value`, `series`, and `reason`; use `null + reason` when the
normalised source fact is unavailable.  Do not present a zero as a substitute
for unavailable D&A, interest expense, tax, market cap, peer observations or
segment disclosures.

## Provenance / period gate

- A calculation input must be `CFS` or `OFS` consistently for its issuer; do
  not mix consolidated and separate facts inside a ratio or a model.
- A ratio series may only divide values with the same fiscal end date.  Annual
  figures cannot be joined to a quarter simply because the calendar year
  matches.
- `as_of` is the latest fiscal period end, not an API request date.
- `data_quality.raw_filing_facts_embedded=false` means a sample was derived
  from a UI snapshot, not recomputed from raw SEC/OpenDART facts.
- `market_cap`, peer multiples and segment values are optional source inputs.
  If absent, the relevant card/model must be partial or omitted with a reason.

## Model guardrails

- No target price, recommendation, or buy/sell/overpay wording in outputs.
- `fcff_dcf` emits bear/base/bull enterprise/equity values and the 7–11% WACC
  sensitivity table.  Terminal growth is capped at 3%; base is 2%.
- D&A/maintenance Capex uses the clearly labelled `min(abs(D&A), abs(capex))`
  proxy only when both reported values are available.
- SOTP is calculated only from provided source/user segment values; otherwise
  it is an EV bridge or `omitted`, never an invented business mix.

## Card click → chart
Each metric prefers `series: [{year, end, value}, ...]` aligned to one fiscal timeline.

## Secrets
- KR OpenDART: Cloudflare env `DART_API_KEY` only. Never in client JS.

## CLI
```
# enrich an existing snapshot's basic_cards into the 16 expert cards + models
python3 scripts/dart/enrich_snapshot.py \
  "New for anti/public/data/kfa_005930_v1.json" \
  --output /tmp/kfa_005930_enriched.json

# fetch a new company live from OpenDART and write the full UI snapshot
# (requires DART_API_KEY; produces single-fiscal-year data -- see START_HERE.md)
export DART_API_KEY=...
python3 scripts/dart/fetch_kfa_snapshot.py 00164779 000660 "SK하이닉스" "SK Hynix Inc." --year 2025
```
