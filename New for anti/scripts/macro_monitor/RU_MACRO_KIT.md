# Russia Macro Kit (`ru_macro_v1`)

제재·**전시경제**. CBR 인플레 통제 · 전쟁자금(NWF/OFZ) · 에너지·CNY 결제 구조 추적.

## 구조 (6탭)

| 탭 | 핵심 |
|----|------|
| 유동성·재정 | **NWF 유동자산**(최우선) · CBR자산 · 외환보유(총/접근가능/동결비중) · M2 |
| 금리 | **CBR Key Rate** · OFZ 10Y · **OFZ 입찰 커버** |
| 환율·원자재 | **CNY/RUB**(주력) · USD/RUB · **Urals−Brent 할인** |
| 주식 | MOEX(루블) · **RTSI(달러)** |
| 성장 | GDP · PMI · 실업(≠호조) · **노동력 부족** |
| 물가 | CPI/Core · **가계 기대인플레(CBR)** |

## 헤드라인 칩

NWF · Key Rate · CNY/RUB · Urals−Brent · RTSI · CPI

## 한계 (필수 고지)

1. 공식통계 조작·발표 중단 → 액면가 신뢰 불가  
2. 군수 GDP(+) ≠ 민간 부/자본 축적  
3. 자본통제로 환율 방어 ≠ 대외 흡수력

## 데이터 상태

`fixture_synth`. 실데이터는 발표 중단·제재로 **공개 API가 가장 빈약한 키트**.  
대안: CBR 공시 잔존분 · NWF 재무부 월보 · Urals 할인(Argus/매체) · MOEX.

API: [`DATA_SOURCES.md`](./DATA_SOURCES.md) §러시아
