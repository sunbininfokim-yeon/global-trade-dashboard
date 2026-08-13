# US Macro Benchmark Kit

미국은 글로벌 매크로의 **기준점(Benchmark)** 이다.  
Fed 통화정책 수단 + Treasury 자금조달 → 달러 유동성·금리를 정량 추적한다.

구현 위치: `config/series.spec.json` → `country_series.USA` (`kit: us_macro_benchmark_v1`)

## 카테고리 (UI 탭)

| id | 한글 | 내용 |
|----|------|------|
| `liquidity` | 유동성 | Fed BS · **SOMA 보유국채(만기 버킷)** · MBS · ON RRP · FIMA · Discount · TGA · **QRA 만기별 발행** · Net Liquidity · M2 |
| `rates` | 금리 | EFFR · **FedWatch(결과 분포)** · **3M/2Y/10Y 시장금리** · TIPS · 스프레드 · High Yield OAS · SOFR |
| `fx` | 환율 | DXY · EUR/USD · USD/JPY |
| `equity` | 주식 | S&P500 · Nasdaq100 · Russell2000 · VIX (가격선 + **MA5**) |
| `growth` | 성장 | **GDP YoY\|QoQ (비연율)** · GDPNow · ISM · NFP · 실업 · Sahm · Claims |
| `inflation` | 물가 | CPI / Core CPI · **Dallas trimmed mean** · 10Y BEI · (Core PCE는 참고·칩 비표시) |

## 보유국채 ≠ 시장금리

`fed_ust_*` / 칩 **「연준 보유국채 ≤1년 (SOMA)」** 등은  
**연준 SOMA(공개시장계정) 재무부 증권 잔고를 잔존만기로 나눈 것**이다. Fed 대차대조표(H.4.1) 항목이지,  
3M·2Y·10Y **시장 수익률이 아니다**.

| 구분 | 지표 | 의미 |
|------|------|------|
| Fed B/S | `fed_ust_holdings` (스택: ≤1y / 1–5y / 5–10y / >10y) | SOMA UST 보유 규모 |
| 시장금리 | `bond_3m`, `bond_2y`, `bond_10y` | FRED `DGS3MO` / `DGS2` / `DGS10` (또는 TB3MS) |

## 핵심 파생

```
Net Liquidity (T$) = Fed Total Assets (T$) − TGA (B$)/1000 − ON RRP (B$)/1000
10Y−2Y (bp)        = (10Y − 2Y) × 100
fed_ust_holdings   = sum(SOMA maturity buckets)
```

GDP 칩: **YoY | QoQ** (QoQ는 **분기 대비 %**, SAAR 연율 아님). `gdp_qoq_saar` 는 USA에서 skip.

## FedWatch

단일 “인하확률” 스칼라가 아니라 차기 FOMC **결과 막대 분포**  
(동결 / ±25 / ±50 bp). 칩 텍스트 = 최고확률 결과만 (예: `25bp 인상 57%`). 라벨 = `FedWatch`.

## 한계 (엔진 JSON `limitations`에도 동일)

1. **유동성 ↔ 자산가격 인과 불확실** — 순유동성↑ ≠ 주식↑. 외생 충격 시 무위험 자산으로 몰릴 수 있음.
2. **QT ↔ QRA 상쇄** — 연준 run-off가 금리 직결이 아님. Bill 비중↑로 수급 충격 완화 가능. 발행전략은 사전예측 불가.
3. **임계치 비선형** — HY OAS·FIMA 등은 후행. RRP 고갈 발작점 등 임계치는 정확히 도출 불가.
4. **NFP** — 월별 증감은 표본·계절조정 개정 폭이 커 **신뢰도가 낮을 수 있음**. Claims·실업과 교차.

## 갱신

[`REFRESH_TIERS.md`](./REFRESH_TIERS.md) — 시장 A/B, 정책 C, BS 주간 D, CPI/NFP 월 E, GDP/QRA 분기 F.  
Alpha Vantage 비1차.

## UI (Claude)

차트·칩·오버레이·뉴스 레일은 Cursor가 `app.js`를 수정하지 않는다.  
정본: [`CLAUDE_UI_HANDOFF.md`](./CLAUDE_UI_HANDOFF.md) → [`CLAUDE_UI_HANDOFF_US_TUNING.md`](./CLAUDE_UI_HANDOFF_US_TUNING.md)  
(오버레이 확대 · 지표 옆 뉴스 · MA5 · YoY|QoQ · SOMA 스택 등)

## 데이터 상태

현재 빌더는 **fixture_synth** (설정 base에 핀된 데모 경로).  
다음: FRED (`WALCL`, `WTREGEN`, `RRPONTSYD`, `DGS3MO`, …) / Treasury QRA / Atlanta GDPNow / CME FedWatch 어댑터.
