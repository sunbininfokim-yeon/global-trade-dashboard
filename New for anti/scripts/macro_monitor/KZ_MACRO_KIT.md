# Kazakhstan Macro Kit (`kz_macro_v1`)

**원유·우라늄** 의존 · **러시아(RUB/CPC 물류)** 연동 · NBK 고금리 인플레 통제.

## 구조 (6탭)

| 탭 | 핵심 |
|----|------|
| 재정·유동성 | **NFRK 국가기금** · M3 |
| 환율 | **USD/KZT** · **RUB/KZT** · 경상 · us_fx_watch |
| 금리 | **NBK Base Rate** · 국채 10Y |
| 주식·FDI | KASE · FDI(채굴 편중) |
| 성장 | **Brent/CPC · 우라늄**(수출 드라이버 · KR 반도체와 동일 슬롯) · GDP · 산업생산 · **광업/제조 분리** |
| 물가 | CPI (수입물가·RUB 민감) |

### FX vs growth (원자재)

- **환율(`fx`)**: USD/KZT · RUB/KZT · 경상 · us_fx_watch.
- **성장(`growth`)**: Brent/CPC · 우라늄 = 주력 수출·교역 드라이버. 환율 탭이 아님.

## 헤드라인

NFRK · USD/KZT · Brent · Base Rate · 우라늄 · CPI

## 한계

1. 원자재↑ ≠ 내수·비자원 고용  
2. CPC 지정학 차단은 시계열로 예측 불가  
3. 금리인상 ≠ 수입 인플레 통제

API: [`DATA_SOURCES.md`](./DATA_SOURCES.md) §카자흐스탄
