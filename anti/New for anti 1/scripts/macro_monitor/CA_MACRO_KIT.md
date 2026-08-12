# Canada Macro Kit (`ca_macro_v1`)

미국 연동 · **자원(에너지) 수출** · **가계부채/주택**이 BOC 통화정책 뇌관.

## 구조 (6탭)

| 탭 | 핵심 |
|----|------|
| 유동성·부채 | **가계부채/가처분소득** · M3 · BOC 자산 |
| 금리 | Overnight · GoC 2Y/10Y · **미−캐 2Y 스프레드** |
| 환율 | **USD/CAD** · **WCS−WTI**(가격 스프레드) · 무역수지 · 경상 · us_fx_watch |
| 주식 | S&P/TSX · 외국인 유가증권 |
| 성장·부동산 | **WCS**(수출 드라이버 · KR 반도체와 동일 슬롯) · **Teranet HPI** · GDP · **1인당 GDP** · Ivey PMI · 고용 |
| 물가 | CPI · **CPI-trim / median**(BOC) |

### FX vs growth (원자재)

- **환율(`fx`)**: USD/CAD · WCS−WTI 스프레드 · 무역수지/경상 · us_fx_watch.
- **성장(`growth`)**: WCS 중질유 가격 = 주력 수출·교역 드라이버. 환율 탭이 아님.

## 헤드라인

가계부채/소득 · Overnight · USD/CAD · WCS · Teranet · CPI-trim

## 한계

1. 총량 GDP↑ ≠ 1인당·생산성·구매력  
2. 금리인하 ≠ 즉시 주택·소비 (모기지 갱신 비선형)  
3. M3↑ ≠ 산업고도화·CAD/인플레 예측

API: [`DATA_SOURCES.md`](./DATA_SOURCES.md) §캐나다
