# Brazil Macro Kit (`br_macro_v1`)

농산물·철광석 수출 · **재정/고금리** · **USD/BRL** 변동성.

## 구조 (6탭)

| 탭 | 핵심 |
|----|------|
| 재정·유동성 | **기초재정수지** · 공공부채/GDP · M3 |
| 금리 | **SELIC** · 국채 10Y · **5Y CDS** · 국가신용등급 |
| 환율 | **USD/BRL** · 외환보유 · 경상 · us_fx_watch |
| 주식 | Ibovespa · 외국인 포트폴리오 |
| 성장 | **철광석·대두·원유**(수출 드라이버 · KR 반도체와 동일 슬롯) · GDP · **IBC-Br** · PMI · 실업 |
| 물가 | **IPCA** · IPCA-15 |

### FX vs growth (원자재)

- **환율(`fx`)**: USD/BRL · 경상 · 외환보유 · us_fx_watch. (CDS·등급은 `rates`.)
- **성장(`growth`)**: 철광석 · 대두 · 원유 = 주력 **수출·교역 드라이버**. 환율 탭이 아님 — 한국 반도체 수출과 같은 개념 슬롯.
- **실업**: 해석 앵커 ≈**7–9%**(문헌 포인트 ~8%). 미국 4%·한국 3%와 비교 금지 — [`LABOR_BENCHMARKS.md`](./LABOR_BENCHMARKS.md).

## 헤드라인

기초재정 · SELIC · USD/BRL · 철광석 · Ibovespa · IPCA

## 한계

1. SELIC 인하 ≠ 실물투자·GDP (재정·장기금리 괴리)  
2. 원자재↑ ≠ 내수·1인당소득  
3. M3 통제 ≠ IPCA 안정 (기후·공급 외생)

API: [`DATA_SOURCES.md`](./DATA_SOURCES.md) §브라질
