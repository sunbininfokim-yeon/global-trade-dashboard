# Global Spillover (해외-국내 선행 지표)

탭3. JSON: `us_kr_transmission_v1.json` → **`global_spillover`** (+ 상세 필드)

투자 권유 아님. 공개·지연 데이터.

---

## A / B / C 상태 (2026-08-09)

| 탭 | 엔진 | 비고 |
|----|------|------|
| A D&S | **끝** | `distortion_squeeze` 라이브 반영 |
| B Volume | **데이터·스펙 OK** | 탭 간 종목 연동은 **필수 아님** (편의 제안이었음 → 안 해도 됨) |
| C Spillover | **다듬음** | `global_spillover` 블록 + why_short + 분석 |

---

## 지금 스냅이 말하는 것 (as_of 2026-08-08)

**Headline: 높음 · 하방 (`high:downside`)**

의미가 **아닌** 것:
- “미국이 오늘 폭락했다”
- “내일 한국 매도 추천”

의미인 것:
- 공개 옵션에서 **풋 거래·OI가 콜보다 두드러진** 이름(SOXL/SMH/EWY/TSM)이
- 한국 하닉·삼전 **Tier A/B 링크**로 연결돼 heat가 쌓인 상태

### US evidence (P/C)

| 심볼 | P/C 거래량 | P/C OI | 공매 증감% | 레짐 |
|------|----------:|-------:|----------:|------|
| SMH | 4.39 | 2.04 | -5.9 | downside_put_bid |
| EWY | 2.23 | 6.65 | +52.5 | downside_put_bid |
| SOXL | 2.18 | 2.16 | +9.1 | downside_put_bid |
| TSM | 1.30 | 1.11 | +20.3 | downside_put_bid |

### 채널 heat

| 채널 | level | heat |
|------|-------|-----:|
| downside | **high** | 7.13 |
| vol_up | watch | 1.91 |
| upside | quiet | 0 |
| vol_down | quiet | 0 |

### 최강 전이 (edges)

1. SOXL → 000660 heat 1.41 (etf_beta)
2. SOXL → 005930 heat 1.13
3. SMH → 000660 heat 1.03
4. SMH → 005930 …
5. EWY → 000660 …

### 장초 30분 백테스트 (참고)

- 하방 드라이버 버킷 → 익일 KR open R<0 **적중률 평균 ~0.84 (하닉 요약)**
- 알림일 open 평균 수익률은 베이스라인보다 낮음 (복합 지표)
- **옵션 히스토리가 아니라 수익률 버킷 프록시** — 과대해석 금지

### 글로벌 레버 스택 (규모 비교만)

| venue | 비고 |
|-------|------|
| KR 단일종목 LETF | wag-the-dog / IR 본진 |
| HK 7709 ~$1.7bn AUM | swap, 간접 |
| US SOXL notional 큼 / SOXS·SQQQ·TECS 인버스 포함 | 레짐 프록시 |
| crypto OI | 이번 스냅 0 또는 소량 — 합산 금지 |

---

## UI 계약

```text
global_spillover
├── headline / headline_ko / why_short_ko
├── channels_summary.{downside,upside,vol_up,vol_down}
├── top_edges[]
├── evidence_us_top[]
├── open30m_hit
├── read_ko[]
└── data_limits_ko[]
```

상세는 기존 `channels` · `evidence_us` · `edges_active` · `kospi_open30m_prior`.

---

## 분석 가능 범위 / 한계

**가능**
- ETF·지수 옵션 P/C + FINRA short 프록시로 레짐
- Tier A 링크로 KR 타깃 heat
- 과거 open30m 적중률 통계

**불가·금지**
- 미국 개별주 옵션 풀체인 실시간 (유료)
- X로 OI 숫자 대체
- 주체 특정, 목표가, 매수/매도 추천

---

## 재빌드 (US 쪽)

```bash
python build_us_kr_cross_market.py --live --print-stats
# 또는 L3
python build_us_kr_l3.py --live --print-stats
```

코드 변경(`why_short_ko`, `global_spillover`)은 다음 US 라이브부터 자동 생성.  
현재 JSON은 동일 블록을 **패치 반영**해 두었음.
