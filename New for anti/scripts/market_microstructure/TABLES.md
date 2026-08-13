# Market microstructure tables — 2026-08-07

공개 상품 AUM·거래대금 기반 추정. 증권사 고객 레버리지 공시가 아님. 투자 권유 아님.

## 0. 증권사 레버리지 공시?

| 항목 | 값 |
|------|-----|
| available | False |
| note | 증권사는 종목별 고객 레버리지 비율을 공시하지 않음. 대체: LETF AUM, FreeSIS 신용·미수 집계, KRX 투자자별 매매. |
| public_proxies | krx_letf_aum, krx_letf_turnover, kofia_freesis_margin, krx_investor_flows, krx_short_interest, yahoo_hk_letf, yahoo_us_levered_inverse, binance_stock_perps, us_options_regime |

## 1–6, 8–10

( unchanged in this credit-focused pass — see branch history for full LETF/concentration tables )

## 7. Deposit & credit (FreeSIS)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님.  
**UI 기본:** 예탁금·신용거래융자·미수·반대매매 (+비율).  
**제외:** 예탁증권담보융자·대주·광의신용공여(융자+담보) — 원본 필드만 유지.

| metric | 값 | unit | as_of | quality |
|--------|---:|------|-------|---------|
| 투자자예탁금 | ~104.1 | 조원 | 2026-08-06 | observed |
| 신용거래융자 | ~28.8 | 조원 | 2026-08-06 | observed |
| 신용/예탁금 % | ~27.7 | % |  |  |
| 위탁매매미수금 | ~1.06 | 조원 (표는 억원) | 2026-08-06 | observed |
| 반대매매금액 | ~107 | 억원 | 2026-08-06 | observed |
| 미수 대비 반대매매% | ~1.0 | % |  |  |

규모 차이 → 표는 조/억+비율 병행, 차트 Y오른쪽은 신용/예탁% 권장. `ui_display.scale_note_ko` 참고.

Canonical: `deposit_credit_v1.json`, `CLAUDE_CREDIT_TABLE.md`, `CODEX_REVIEW_CREDIT.md`.
