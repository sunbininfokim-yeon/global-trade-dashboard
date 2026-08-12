# Portfolio UI baseline — Claude handoff

This is the **public user flow** for the portfolio calculator.  It deliberately
does not add a “diagnostic report” tab backed by a pre-generated JSON file.
That file is an engine artifact, not a visitor's portfolio.

`New for anti/app.js` is Claude-owned.  This document specifies the product
and engine contract that the UI must implement; it is intentionally separate
from the UI source to avoid parallel edits to `app.js`.

## One public flow

```text
First visit / saved input
        ↓
Portfolio input (default screen)
        ↓ [Calculate]
Local browser calculation + price lookup
        ↓
My result — Basic | Expert (same calculation, different explanation depth)
        ↓
Adjust input / recalculate
```

There is no public **“진단 리포트”** tab and no instruction to run Python,
create a JSON file, or understand `.gitignore`.  `portfolio_analysis_v1.json`
may remain an offline-engine artifact for developers and regression tests, but
must not become the default result for a visitor.

## Screen 1 — default: `내 포트폴리오`

The page title may remain `포트폴리오 진단`, but the first actionable block is
always `내 포트폴리오`.  A first-time user sees an empty list, not a report
placeholder.

```text
포트폴리오 진단
보유 자산의 위험이 어디에 몰려 있는지 확인합니다. 수익 예측이 아닙니다.

[ 내 포트폴리오 ]                         (not a tab; current page heading)

기준통화  [ KRW ▾ ]   투자 성향 [ 보수적 | 일반 | 공격적 ]

계좌 정보
순자산(NAV) [________________] KRW   ⓘ 실제 보유자산에서 부채를 뺀 금액
[ ] 신용·미수 사용      신용 사용액 [________________] KRW

보유 자산                                        [ 종목 추가 ]
┌────────────────────────────────────────────────────────────────────┐
│ 종목/티커 검색 │ 금액·수량 │ 매수·공매도 │ 입력값 │ 삭제           │
└────────────────────────────────────────────────────────────────────┘

  현금은 보유자산으로 직접 추가할 수 있습니다.
  외화 현금은 현금 완충이 아니라 환율 노출로 별도 표시됩니다.

[ 계산하기 ]              [ 이 브라우저의 입력 모두 지우기 ]
```

### Input rules

1. **KRW is the initial base currency**; the selector also offers USD.  All
   account summary labels and input units must change to the selected base
   currency.  Do not show a KRW-only field label after USD is selected.
2. NAV is optional only for a simple long-only account.  If empty, the UI says
   `입력한 보유금액 합계로 계산` before calculation.
3. Once either credit/margin or a short position is selected, NAV is required.
   The UI must explain the accounting identity before calling the calculator:

   ```text
   부호 있는 보유금액 합계 − 신용·미수 = 순자산(NAV)
   ```

   A mismatch is a validation error, not an automatically added cash balance.
4. Do not label a short position as `매도`.  Use `공매도` and preserve the
   distinction from selling an existing long holding.
5. `7709`, `7709.HK`, and `CSOP 하이닉스 2배` resolve to the actual HKD listed
   CSOP SK Hynix Daily (2x) Leveraged Product.  The old synthetic
   `하이닉스2배` proxy must be visually labelled `프록시` and must not silently
   replace 7709.HK.
6. The user clicks **Calculate**.  Reopening the page or restoring local input
   never triggers a price request or automatic calculation.

### Local-storage wording

When saved positions exist, place this directly above the holdings table:

> 이전에 이 브라우저에 저장한 입력입니다. 서버에는 보유금액이 저장되지 않습니다.

Do not call saved entries “my holdings” without the qualifier.  Provide the
clear button in the same visible area.  A fresh browser must show `보유 목록
0건` and no calculation result.

## Screen 2 — one result, two explanation modes

Basic and Expert are **not separate calculations** and are not tabs for a
sample report.  They toggle explanatory density for the result of the just
submitted browser input.

```text
내 포트폴리오 결과                         [ 기본 | 전문가 ]
기준통화 KRW · 관측기간 2025-08-12 ~ 2026-08-12 · 가격 출처 Yahoo

Account summary: NAV | 총노출 | 신용·미수 | 기준통화 현금 | 외화 현금
Risk status:     성향 경고 (if any)

Basic:  계좌 흔들림 | 단기 손실 가능 규모 | 현금 완충 | 위험 집중도 | 조절 방향
Expert: 변동성 | Historical/parametric VaR | CVaR | Sharpe | 상관·공분산 |
         위험기여 | HRP 제안 | 과거 스트레스 구간
```

### Basic requirements

- Default mode after a calculation.
- No `VaR`, `CVaR`, `Sharpe`, `EWMA`, or `HRP` in the primary card titles.
- Keep technical terms available through `전문가 보기` rather than hiding the
  underlying basis.
- Show `단기 손실 가능 규모` as a historical/model estimate, **not** a future
  loss prediction or a guaranteed maximum loss.
- State that `과거 1년 성과` is historical, not an expected return.

### Expert requirements

- Show metric name, method, lookback, confidence level, and denominator.
- VaR cards must say `NAV 기준`; total exposure is separately shown.
- Show base-currency cash and foreign cash separately.
- Show whether an instrument is leveraged, a proxy, a short, or a foreign
  listing.
- Show correlation/covariance, risk contribution, stress-window method, and
  HRP constraints.  HRP output is a **rebalancing reference**, never an order.

## Result data contract for the browser calculator

The browser result must expose the same minimum shape as the Python report,
even if it is not serialized to disk:

```js
{
  base_currency: 'KRW' | 'USD',
  input: {
    net_asset_value, credit_used, positions
  },
  accounting: {
    net_asset_value,
    gross_exposure,
    gross_exposure_of_nav,
    credit_used
  },
  cash_breakdown: {
    base_cash_value,
    foreign_cash_value,
    base_cash_weight_of_nav,
    foreign_cash_weight_of_nav
  },
  profile_check: { ok, breaches_ko, gross_exposure_of_nav },
  data_quality: { price_sources, n_obs, start, end, unresolved_queries },
  result_copy: {
    basic: /* equivalent to ui_copy_basic_ko */,
    expert: /* equivalent to ui_copy_ko */
  }
}
```

For USD base currency, `net_asset_value`, `credit_used`, and money results are
all USD.  The existing engine field name `credit_used_krw` is therefore an
engine migration item, not a UI label to expose; UI must not claim that a USD
account's debt is KRW.

## Completion checklist for Claude

- [ ] Default page is direct input, never a static/offline JSON report.
- [ ] No public `run_pipeline.py`, `.gitignore`, or local developer-file copy.
- [ ] First visit: no positions, no price request, no result.
- [ ] Saved input: clear local-storage explanation and explicit `계산하기` only.
- [ ] KRW/USD base currency alters account units consistently.
- [ ] Credit and short validation use NAV; no silent residual cash in those cases.
- [ ] `7709.HK` resolves to actual HKD product and is distinct from a proxy.
- [ ] One calculated result supports Basic and Expert, with identical numerical
      values and only different wording/detail.
- [ ] Basic never markets a past return or VaR as an expected future outcome.
- [ ] Browser test cases cover blank, long-only, 130%-gross credit, short with
      collateral, USD/HKD cash, and 7709.HK.

