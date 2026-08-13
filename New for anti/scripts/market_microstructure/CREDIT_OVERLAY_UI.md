# Credit overlay UI (Volume + D&S) — final

Canonical with `CLAUDE_CREDIT_TABLE.md` + `deposit_credit_v1.json` + `fetch_freesis_credit.py`.

## Volume dual axis

```
Y left  = KOSPI price bins
X       = retail / foreign / institution net
Y right = credit_over_deposit_pct  (default)  OR credit_loan_jo
```

## Table fields (default)

| group | key | unit |
|-------|-----|------|
| cash_leverage | investor_deposit | 조원 |
| cash_leverage | credit_loan (+ kospi/kosdaq) | 조원 |
| cash_leverage | credit_over_deposit_pct | % |
| stress | uncollected | 억원 |
| stress | forced_sale | 억원 |
| stress | forced_sale_pct | % |
| stress | uncollected_over_deposit_pct | % |

## Excluded from default UI

`collateral_loan`, `short_loan`, `credit_funds` → `ui_display.exclude_keys`

## Scale

Do not plot 예탁+미수 absolute on one axis. Use ratios or separate stress strip.

## Badge

시장 전체 · 종목별 아님
