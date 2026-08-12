# 신용·미수 표 (Volume + D&S)

JSON: `public/data/deposit_credit_v1.json` → `deposit_credit.components[]`  
(동일 필드가 `market_microstructure_v1.deposit_credit` · `investor_price_levels.credit_overlay.table_fields` 에도 반영)

## as_of 2026-08-06 (FreeSIS 공개)

| group | 항목 | 표시 | 값 |
|-------|------|------|-----:|
| 예탁·신용 | 투자자예탁금 | **조원** | 104.1 |
| 예탁·신용 | 신용거래융자 | **조원** | 28.8 |
| 예탁·신용 | ㄴ 유가증권 | 조원 | 22.9 |
| 예탁·신용 | ㄴ 코스닥 | 조원 | 5.9 |
| 예탁·신용 | 신용/예탁 % | % | 27.7 |
| 미수·반대 | 위탁매매미수금 | **억원** | 10,624 |
| 미수·반대 | 반대매매금액 | 억원 | 107 |
| 미수·반대 | 미수 대비 반대매매% | % | 1.0 |

**기본 표에서 제외:** 예탁증권담보융자 · 신용거래대주 · 광의신용공여(융자+담보)  
→ 코스피 가격대 수급 설명력 낮음. 원본 필드는 JSON에 남아 있음 (`ui_display.exclude_keys`).

## 규모가 다른 지표를 같이 그리는 법

- 예탁 ~104조 · 신용 ~29조 · 미수 ~1조 · 반대매매 ~100억
- **한 Y축 절대액 합치면 미수가 안 보임**
- 표: 예탁·신용 = 조원, 미수·반대 = 억원 + 비율 열
- Volume Y오른쪽 기본: `credit_over_deposit_pct` (스케일 중립)
- 대안: `credit_loan_jo` (신용만 조원)
- 미수·반대매매: **별도 소형 스트립 / 보조 카드**
- 가이드 필드: `deposit_credit.ui_display.scale_note_ko`

## UI

- D&S / Volume 공통 **표 카드** → `components[]` (담보 제외 후 9행)
- 배지: **시장 전체 · 종목별 아님**
- Volume Y오른쪽: `credit_overlay.y_right_fields` 순서 참고
- 개별종목 Volume에 붙여도 시장 숫자 — 오인 금지 배지

## 소스

FreeSIS (API 키 불필요)
- 증시자금추이 STATSCU0100000060
- 신용공여 잔고 추이 STATSCU0100000070  
엔진: `fetch_freesis_credit.fetch_freesis_funding_credit`
