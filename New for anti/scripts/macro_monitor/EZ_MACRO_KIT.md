# Eurozone Macro Kit (`ez_macro_v1`)

단일통화(EUR) + **회원국 독립 재정**. ECB QT(APP/PEPP)와 **BTP−Bund 분절화**가 핵심.

지도: 독일·프랑스·이탈리아 등 회원국 클릭 → 유로존 팩 (`iso3=EMU`).

## 핵심 칩

| id | 의미 |
|----|------|
| `btp_bund_spread` | IT−DE 10Y · ~250bp = 시스템 리스크 경보 |
| `deposit_facility` | DFR · 실질 기준금리 |
| `app_balance` / `pepp_balance` | QT · PEPP 재투자 유연화 |
| `eurusd` | DXY ~57.6% |
| `hcob_pmi_mfg` | 독일 제조업 = 유럽 산업사이클 |
| `hicp_yoy` / `negotiated_wages` | ECB 2% · 임금 끈적임 |
| `tpi_active` | TPI 가동 여부 (평시 미가동) |

## 한계

평균 지표의 남·북 양극화 은폐 · BTP−Bund의 PEPP/TPI 왜곡 · M3≠신용경로 임계치

API: [`DATA_SOURCES.md`](./DATA_SOURCES.md) §유로존
