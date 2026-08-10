# 신용·미수 표 (Volume + D&S)

JSON: `public/data/deposit_credit_v1.json` → `deposit_credit.components[]`
(동일 필드가 `market_microstructure_v1.deposit_credit` 에도 반영됨)

## as_of 2026-08-06 (억원, FreeSIS 공개)

| 항목 | 값 |
|------|-----:|
| 투자자예탁금 | 1,040,712 |
| 신용거래융자 | 287,940 |
| ㄴ 유가증권 | 228,685 |
| ㄴ 코스닥 | 59,255 |
| 예탁증권담보융자 | 243,714 |
| **신용공여자금(융자+담보)** | **531,654** |
| 신용거래대주 | 247 |
| 위탁매매미수금 | 10,624 |
| 반대매매금액 | 107 |
| 미수 대비 반대매매% | 1.0 |
| 신용/예탁 % | 27.7 |
| 신용공여자금/예탁 % | 51.1 |

## UI

- D&S / Volume 공통 **표 카드**로 `components[]` 전부 표시
- 배지: **시장 전체 · 종목별 아님**
- Volume Y오른쪽 시리즈: `credit_loan_eok` 또는 `credit_funds_eok` (코스피 뷰)
- 개별종목 Volume에 붙여도 시장 숫자 — 오인 금지 배지

## 소스

FreeSIS (API 키 불필요)
- 증시자금추이 STATSCU0100000060
- 신용공여 잔고 추이 STATSCU0100000070
엔진: `fetch_freesis_credit.fetch_freesis_funding_credit` / `fetch_kr_public_extras`
