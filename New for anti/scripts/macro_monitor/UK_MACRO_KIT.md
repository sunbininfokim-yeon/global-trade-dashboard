# UK Macro Kit (`uk_macro_v1`)

BOE 통화정책 · 브렉시트 구조변화 · **2022 LDI(연금 유동성 위기)** 리스크 모니터.

## 용어 (처음 볼 때)

| 지표 | 한 줄 |
|------|------|
| **M4** | 영국의 **광의통화**. 미국 M2에 가깝다. BOE가 통화량 지표로 M4를 씀. |
| **APF** | Asset Purchase Facility. BOE **QE 포트폴리오**(국채·일부 회사채) 잔고. QT면 줄어듦. |
| **AWE** | Average Weekly Earnings. **주간 평균임금**. BOE 임금·서비스 물가 판단의 핵심. 보통 **보너스 제외**를 더 봄. |
| **비경제활동비율** | Economic inactivity. 일할 수 있는 나이인데 **구직도 안 하는** 비율. 브렉시트·장기병가 이후 영국에서 **노동공급** 이슈로 중요. |
| **RPI** | Retail Price Index. CPI와 다른 영국 전통 물가. **물가연동국채(ILG)·일부 연금** 산정에 쓰여 LDI와 연결. |
| **CDS** | 국채 부도보험 스프레드(bp). 높을수록 신용 불안. |
| **국가신용등급** | S&P · Moody's · Fitch 장기외화 등급. |

## LDI 핵심 칩

| id | 의미 |
|----|------|
| `bond_30y` | Gilt 30Y — LDI 주요 보유 · 급등→마진콜·강제매도 트리거 |
| `gilt_bund_10y` | Gilt−Bund 10Y — 재정·신용 리스크 프리미엄 |
| `sovereign_cds_5y` | 5Y 국채 CDS |
| `sovereign_ratings` | S&P / Moody's / Fitch |
| `rpi_yoy` | RPI — ILG·연금 산정 기준 |

## 나머지 탭

유동성(BOE·**APF**·매입바·비상창구·**M4 vs 2019**) · 금리(Bank Rate·SONIA·Gilt·스프레드·CDS·등급) ·  
FX · 주식 · 성장(GDP·**AWE**·실업·**비경제활동**·PMI) · 물가(CPI·Core·**RPI**·Services)

## 한계

1. OTC 파생 레버리지·증거금은 거시지표에 안 보임 (후행)  
2. FTSE 100 ≠ 내수 (해외매출 ~75%)  
3. M4↑ ≠ CPI 직결

API 목록: [`DATA_SOURCES.md`](./DATA_SOURCES.md)
