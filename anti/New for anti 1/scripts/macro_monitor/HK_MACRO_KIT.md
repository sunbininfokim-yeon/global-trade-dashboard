# Hong Kong Macro Kit (`hk_macro_v1`)

**이중 구조:** 통화정책은 USD 페그(LERS)로 미국에 종속 · 실물·증시는 중국 본토에 연동.

## 구조 (6탭)

| 탭 | 핵심 |
|----|------|
| 유동성 | **총결제잔액(Aggregate Balance)** 최중요 · 외환보유 · M2 |
| 금리 | HKMA Base Rate · HIBOR 1M/3M · **HIBOR−SOFR** |
| 환율 | **USD/HKD 7.75–7.85** · USD/CNH(역외 위안 허브) |
| 주식·부동산 | HSI · HSCEI · HSTECH · **CCL** |
| 성장 | GDP · **소매판매** · **수출입**(중계무역) |
| 물가 | Composite CPI(주거비 비중↑) |

## 헤드라인

Aggregate Balance · USD/HKD · HIBOR−SOFR · HSI · CCL · 소매판매

## 한계

1. 침체여도 미국 따라 긴축 — 금리↔경기 인과 불성립  
2. HSI ≠ 홍콩 내수 (시총 80%+ 본토)  
3. AB↓ ≠ 즉각 신용경색 (은행 예금 버퍼)

API: [`DATA_SOURCES.md`](./DATA_SOURCES.md) §홍콩
