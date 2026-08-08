# Japan Macro Kit (`jp_macro_v1`)

DXY 내 비중 2위(~13.6%). 초저금리·YCC·ETF/J-REIT 매입 등 **비전통 정책** 때문에
미국 키트와 다른 고유 지표가 필요하다.

## 카테고리

| id | 내용 |
|----|------|
| `liquidity` | BOJ 총자산·GDP비·YoY · ETF/J-REIT · **JGB 보유비율** · 당좌예금 · M2 vs 2019 |
| `rates` | 무담보콜 · JGB 2Y/10Y/30Y · 10Y−2Y · **30Y−10Y** · 월간 JGB 매입 목표/실적 |
| `fx` | USD/JPY · EUR/JPY · 엔 REER · 외환보유액 · 개입 |
| `equity` | Nikkei · TOPIX · 외국인 순매수 · Nikkei VI |
| `growth` | GDP QoQ/YoY · Jibun PMI · **춘투** · 실질임금 · 유효구인배율 |
| `inflation` | 근원 CPI · 근원-근원 · 도쿄 CPI · CGPI |

## 한계

1. **BOJ ETF 출구** — 잔고는 보이지만 Exit 룰/선례 없음 → 충격 시점·강도 예측 불가  
2. **JGB 가격발견 훼손** — YCC·대규모 매입으로 금리 ≠ 순수 펀더멘털  
3. **개입 단기성** — 미·일 금리차 지속 시 개입 효과는 수일~수주

## 데이터

현재 `fixture_synth`. 다음: BOJ 통계 · MOF 개입 · TSE 수급 · 춘투 연간 시리즈.
