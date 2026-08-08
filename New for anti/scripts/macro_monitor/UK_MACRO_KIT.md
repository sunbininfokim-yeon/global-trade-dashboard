# UK Macro Kit (`uk_macro_v1`)

BOE 통화정책 · 브렉시트 구조변화 · **2022 LDI(연금 유동성 위기)** 리스크 모니터.

## LDI 핵심 칩

| id | 의미 |
|----|------|
| `bond_30y` | Gilt 30Y — LDI 주요 보유 · 급등→마진콜·강제매도 트리거 |
| `gilt_bund_10y` | Gilt−Bund 10Y — 재정·신용 리스크 프리미엄 |
| `sovereign_cds_5y` | 5Y 국채 CDS |
| `rpi_yoy` | RPI — ILG·연금 산정 기준 |

## 나머지 탭

유동성(BOE·APF·비상창구·M4) · 금리(Bank Rate·SONIA·Gilt 2/10/30·10Y−2Y) ·  
FX(GBP/USD·EUR/GBP·REER) · 주식(FTSE100/250) · 성장(GDP·PMI·AWE·실업·비경제활동) ·  
물가(CPI·Core·Services)

## 한계

1. OTC 파생 레버리지·증거금은 거시지표에 안 보임 (후행)  
2. FTSE 100 ≠ 내수 (해외매출 ~75%)  
3. M4↑ ≠ CPI 직결

API 목록: [`DATA_SOURCES.md`](./DATA_SOURCES.md)
