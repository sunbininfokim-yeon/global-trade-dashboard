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

## Card click → chart
Each metric prefers `series: [{year, end, value}, ...]` aligned to one fiscal timeline.

## Secrets
- KR OpenDART: Cloudflare env `DART_API_KEY` only. Never in client JS.

## CLI
```
python3 scripts/dart/fetch_live.py --ticker AAPL
DART_API_KEY=… python3 scripts/dart/fetch_live.py --kr --stock 005930
```
