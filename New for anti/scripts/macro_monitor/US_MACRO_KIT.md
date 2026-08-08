# US Macro Benchmark Kit

미국은 글로벌 매크로의 **기준점(Benchmark)** 이다.  
Fed 통화정책 수단 + Treasury 자금조달 → 달러 유동성·금리를 정량 추적한다.

구현 위치: `config/series.spec.json` → `country_series.USA` (`kit: us_macro_benchmark_v1`)

## 카테고리 (UI 탭)

| id | 한글 | 내용 |
|----|------|------|
| `liquidity` | 유동성 | Fed BS·만기구조·MBS·ON RRP·FIMA·Discount Window·TGA·QRA·**Net Liquidity**·M2 |
| `rates` | 금리 | EFFR·FedWatch·2Y/10Y·TIPS·10Y−2Y/10Y−3M·HY OAS·SOFR |
| `fx` | 환율 | DXY·EUR/USD·USD/JPY |
| `equity` | 주식 | S&P500·Nasdaq100·Russell2000·VIX |
| `growth` | 성장 | GDP QoQ/YoY·GDPNow·ISM·NFP·실업·Sahm·Initial Claims |
| `inflation` | 물가 | Core PCE·CPI/Core CPI·5Y/10Y BEI |

## 핵심 파생

```
Net Liquidity (T$) = Fed Total Assets (T$) − TGA (B$)/1000 − ON RRP (B$)/1000
10Y−2Y (bp)        = (10Y − 2Y) × 100
```

## 한계 (엔진 JSON `limitations`에도 동일)

1. **유동성 ↔ 자산가격 인과 불확실** — 순유동성↑ ≠ 주식↑. 외생 충격 시 무위험 자산으로 몰릴 수 있음.
2. **QT ↔ QRA 상쇄** — 연준 run-off가 금리 직결이 아님. Bill 비중↑로 수급 충격 완화 가능. 발행전략은 사전예측 불가.
3. **임계치 비선형** — HY OAS·FIMA 등은 후행. RRP 고갈 발작점 등 임계치는 정확히 도출 불가.

## 데이터 상태

현재 빌더는 **fixture_synth** (설정 base에 핀된 데모 경로).  
다음: FRED (`WALCL`, `WTREGEN`, `RRPONTSYD`, …) / Treasury QRA / Atlanta GDPNow 어댑터.
