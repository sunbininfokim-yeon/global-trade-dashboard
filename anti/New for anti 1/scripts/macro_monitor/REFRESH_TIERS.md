# Macro Monitor — Refresh Tiers (API quota)

실데이터 어댑터·Worker 스케줄러용. 엔진 JSON의 `refresh_tier` / 시리즈 스펙 메타와 맞춘다.  
**Alpha Vantage는 1차 소스가 아니다** — FRED / ECOS / KOSIS / yfinance 실패 시에만 최후 수단.

## Tier 요약

| Tier | id | 주기 (권장) | 예시 | 비고 |
|------|-----|-------------|------|------|
| A | `market_intraday` | 15–60분 (장중) | FX, equity index, VIX | yfinance·시세 API; 장외는 일 1회 |
| B | `market_daily` | 1일 (장 마감 후) | 국채 3M/2Y/10Y, TIPS, HY OAS, SOFR, DXY | FRED 일별 시리즈 우선 |
| C | `policy_event` | FOMC·의사결정일 +1 | EFFR 목표 구간, FedWatch, 정책금리 | 이벤트 캘린더 트리거; 평시는 일 1회 폴링 |
| D | `weekly` | 주 1회 (목/금) | Initial claims, Fed H.4.1 BS, SOMA 만기, RRP/TGA | FRED 주간 |
| E | `monthly` | 월 1–2회 (발표일) | CPI, Core CPI, trimmed mean, NFP, 실업, ISM, M2 | 발표 캘린더 우선 |
| F | `quarterly` | 분기 (잠정/확정) | GDP YoY/QoQ, QRA issuance | BEA / Treasury QRA |
| G | `static_rare` | 분기 이하·수동 | 한계 문구, kit purpose | 빌드 시 고정 |

## 미국 매핑 (벤치마크)

| 지표군 | Tier |
|--------|------|
| DXY · EURUSD · USDJPY · SPX/NDX/RUT · VIX | A |
| 3M/2Y/10Y · TIPS · spreads · HY OAS · SOFR · BEI | B |
| EFFR · FedWatch | C |
| Fed total assets · SOMA UST buckets · MBS · ON RRP · TGA · FIMA · Discount · Claims | D |
| CPI / Core CPI / trimmed mean · NFP · U-rate · Sahm · ISM · M2 · Core PCE(참고) | E |
| GDP · GDPNow(수시) · QRA | F (GDPNow는 주 수회 예외) |

## 타국 전이

- **시장 금리·FX·주가** → A/B (로컬 거래소 마감 기준)
- **정책금리** → C (한은·BOJ·ECB 등 결정일)
- **고용·CPI** → E
- **GDP** → F
- ECOS/KOSIS는 월·분기 쿼터를 아끼려면 E/F만 자동, A/B는 yfinance·FRED 대리

## JSON 필드

시리즈 스펙 또는 인디케이터:

```json
"refresh_tier": "market_daily"
```

유니버스 루트(선택):

```json
"refresh_policy": {
  "doc": "scripts/macro_monitor/REFRESH_TIERS.md",
  "alpha_vantage": "last_resort_only",
  "preferred": ["fred", "ecos", "kosis", "yfinance"]
}
```
