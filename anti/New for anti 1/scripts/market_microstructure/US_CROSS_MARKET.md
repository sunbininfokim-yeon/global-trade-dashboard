# US → KR cross-market (Phase 2 design, revised)

한국 공매도 OpenAPI는 보류.  
원칙: **공식 거래소·규제기관 공개물 우선 → 그다음 공개 API → Yahoo는 폴백**.

투자 권유 아님.

---

## 0. “옵션+공매 동시 스트레스” = 유료인가?

**부분적으로 예.** 나눠서 보면:

| 보고 싶은 것 | 공개로 가능? | 비고 |
|--------------|--------------|------|
| 콜/풋 **거래량·OI**, P/C, 만기·행사가 집중 | ✅ | 지연 체인 / EOD 요약 |
| IV 레벨·스큐(대략) | ✅~△ | 체인에서 추정 또는 공개 VIX/VVIX |
| **누가** 샀는지 (고객 vs MM vs 프로) | △~❌ | Cboe Open-Close(유료)가 정본에 가깝 |
| **실시간 unusual flow** / dark tape 분류 | ❌에 가까움 | 상용 플로우 제품 |
| Dealer **GEX 장부** 정본 | ❌ | 상용 감마 제품; 일부 free tier는 **추정** |
| 공매 + 옵션 동시 급변 패턴 | △ | 공개 프록시로 stress 가능, **의도·주체 특정 불가** |

결론:  
- **조기 경보용 시나리오 엔진** = 공개 데이터로 충분히 시작.  
- **주체·의도 추적** = 유료·비공시에 가깝. 우리는 후자를 목표로 두지 않음.  
- 산출물·UI 표기는 시나리오/채널명만 사용.

---

## 1. 데이터 소스 우선순위 (Yahoo 최후)

### 1.1 공식 / 규제 · 거래소

| 데이터 | 소스 | 비용 | 용도 |
|--------|------|------|------|
| 옵션 시리즈 레퍼런스 | [Cboe Reference Data CSV](https://www.cboe.com/us/options/market_statistics/reference_data) | 무료 | 상장 시리즈 유니버스 |
| 시장 통계·일부 체인 | Cboe delayed chains / market stats | 무료(지연) | 일별 스냅 |
| OCC 청산·OI 집계 | OCC 공개 통계 | 무료(집계) | 시장 전체 OI 추세 |
| Short interest | **FINRA** consolidated short interest | 무료 API(개발자 등록) | 반월 공매 잔고 |
| Reg SHO / threshold | FINRA / exchange notices | 무료 | 공매 제약 플래그 |
| 현물 공식 시세 | Nasdaq / NYSE 지연 또는 거래소 파일 | 무료 지연 ~ 유료 실시간 | 갭·프리마켓 |
| VIX / VVIX / SKEW | Cboe 지수 페이지 | 무료 | 변동성 레짐 |

### 1.2 공개 2차 (공식 재배포·연구용)

| 데이터 | 소스 | 용도 |
|--------|------|------|
| 옵션 체인 OI/vol (지연) | Nasdaq.com options, MarketChameleon 일부 | 종목별 P/C |
| GEX **추정** (선택) | FlashAlpha 등 free tier (한도 있음) | 딜러 감마 프록시 — `quality=estimated` |
| SOXL/SMH/EWY | ETF 발행사 + 거래소 | 레버·국가 베타 |

### 1.3 폴백

| 데이터 | 소스 | 때 |
|--------|------|-----|
| 체인·숏 필드·프리마켓 | **Yahoo / yfinance** | 공식·FINRA 실패 시만 |
| KR 시초 30분 | FDR / KRX (이미 국내 파이프) | transmission 검증 |

빌드 로그에 반드시 `source_priority_used: cboe|finra|nasdaq|yahoo_fallback` 기록.

---

## 2. 시나리오 엔진 (방향 + 변동성)

단순 “오른다/내린다”가 아니라 **옵션 구조 레짐**을 먼저 분류한다.

### 2.1 US 종목 단위 레짐 (매일)

| regime_id | 관측 (공개 프록시) | 해석 |
|-----------|-------------------|------|
| `downside_put_bid` | put vol↑, P/C_vol↑, put OI↑, spot≤0 | 하방 헤지/공격 |
| `upside_call_bid` | call vol↑, P/C↓, call OI↑, spot≥0 | 상방 추종/감마 |
| `vol_long_straddle` | call+put vol 동시↑, IV↑, |ΔS| 아직 작음 | 변동성 매수 |
| `vol_short_strangle` | call+put vol↑ but IV↓ 또는 OI 소진·핀 | 변동성 매도/안정 |
| `short_cover_squeeze` | shortRatio 고 + call 급증 + 갭업 | 숏커버+콜 |
| `gap_down_stress` | 프리마켓/전일 종가 대비 큰 −갭 + put | 익일 KR 경계 |
| `quiet` | z-score 모두 작음 | 무시 |

하방을 **가중치↑** 로 두되 (`downside_weight > upside_weight`), 상방·vol 레짐도 별도 채널로 저장.

### 2.2 KR 전파 가설 (시나리오 × 링크타입)

미리 분석해 둘 **조건부 관계** (나중에 데이터로 θ 재추정):

| US regime | peer_memory (MU→하닉) | demand_* (NVDA/AMZN→하닉) | etf_beta (SOXL) | korea_country (KORU/EWY) |
|-----------|----------------------|---------------------------|-----------------|--------------------------|
| downside_put_bid | KR 시초 − 동행 강 | KR − (수요 쇼크) | KR − 강 | KOSPI − |
| upside_call_bid | KR + 동행 | KR + | KR + | KOSPI + |
| vol_long_straddle | KR 시초 변동성↑ (방향 모호) | 동 | SOXL 경로 증폭 | VKOSPI↑ 가능 |
| vol_short_strangle | KR 변동성↓·횡보 | 동 | 핀/약세 변동 | 안정 |
| gap_down_stress | **09:00–09:30 과민** (문헌: overnight spillover) | 동 | 레버 ETF 리밸런 추가 | 지수 갭 |

문헌 앵커:
- US→KR **overnight / open spillover**, 변동성 전이, cojump (Emerging Markets Finance & Trade 등).
- 한국 투자자 US 뉴스 **과잉반응 후 주중 되돌림** 가능성 (KOSPI200 선물 연구) → 경보는 “시초 30분”과 “장중 되돌림”을 **분리**.
- 신용·공포 게이지(CVI 등) 충격 → KOSPI·선물·VKOSPI (전염) — 보조 피처로 VIX/SKEW.

### 2.3 프리마켓·시간대

```
US regular close → KR next open ≈ 16–18h
US after-hours / next premarket → KR same morning (겹침 구간 주의)
```

피처:
- `r_us_ah` (애프터아워)
- `r_us_pre` (다음날 프리마켓, KR 개장 직전)
- `regime_at_us_close` vs `regime_pre_kr_open` (갱신되면 경보 재계산)

---

## 3. 링크 그래프 = 고정 + 발견

### 3.1 Tier A — 구조적 (수동, 지금 JSON)

피어·수요·ETF·국가 베타 (`config/us_kr_link_graph.json`).

### 3.2 Tier B — 통계적 발견 (분기 재학습)

KOSPI / 삼전 / 하닉 / Top10 과 US 유니버스(SOX 구성 + 하이퍼스케일러 + 반도체 장비)의:

- 일별 `corr(r_us_close, r_kr_open)`  
- `corr(r_us_close, r_kr_0930)`  
- 하락일만 / 상승일만 **조건부 corr**  
- 변동성 전이: `|r_kr_open| ~ |r_us| + IV_us`

임계 넘는 edge만 `discovered_edges`로 승격 (`quality=estimated`, 리뷰 후 Tier A 편입).

→ **언급한 회사만이 아니라** 데이터가 가리키는 조기경보 후보를 확장.

### 3.3 Tier C — 집중도 채널

국내 Conc_top2 높을수록 US semis 쇼크 → **KOSPI 전체** 민감도 ↑  
`kospi_beta_to_us_semis = f(conc_top2, soxl_stress)`.

---

## 4. 경보 출력 (시나리오 멀티채널)

```
alert_v1:
  as_of_kr_session
  channels:
    downside:  { level, kr_tickers[], us_drivers[], regime_ids[] }
    upside:    { ... }
    vol_up:    { ... }
    vol_down:  { ... }
  kospi_open30m_prior: { mean, p10, p90 | conditioned_on }
  sources_used: [...]
  model_version: "uskr-scenario-YYYYMM"
```

하방 채널을 UI/브리프에서 기본 강조.

---

## 5. 성능 업데이트 — 예, 필수

매 틱 딥러닝이 아니라 **캘린더 재캘리브**:

| 주기 | 할 일 |
|------|--------|
| **매일** | US 스냅 + 레짐 분류 + 경보 (모델 가중치 고정) |
| **매주** | θ(임계)·시나리오별 hit-rate 리포트 (경보→익일 open30m) |
| **매월** | Tier B corr 재추정, weight 소폭 조정 |
| **분기** | 논문/레짐 구조 변경 반영 (0DTE 비중, SOXL AUM 등), `model_version` bump |
| **이벤트** | 거래소 API 변경·새 유료/무료 소스 등장 시 어댑터만 교체 |

성공 지표 (백테스트):
- 하방 경보 후 KR open30m `R < 0` 비율 vs 베이스라인  
- 상방·vol 채널은 **분리 채점** (섞지 않음)  
- Conc 높은 날 vs 낮은 날 층화

---

## 6. 구현 로드맵

1. ~~소스 어댑터: FINRA short · Cboe delayed options/VIX · Yahoo fallback~~ (`fetch_us_public.py`, `fetch_cboe_public.py`)
2. ~~시나리오 분류기 + fixture unittest~~
3. ~~Tier A 그래프 join → multi-channel alert JSON~~
4. ~~Tier B rolling corr discovery~~ (`build_us_kr_discovery.py` → `us_kr_discovered_edges_v1.json`)
5. ~~KR open30m 조건부 분포~~ (Yahoo 30m ~60일 + overnight open 장기; `us_kr_open30m_backtest_v1.json`)
6. (선택) GEX free-tier 보조 피처 · OCC 집계 · 옵션 히스토리로 레짐 백테스트 정밀화

UI는 Claude 소유 — 데이터 JSON만 제공.

### 실행

```bash
cd "New for anti/scripts/market_microstructure"
../../.venv/bin/python build_us_kr_cross_market.py --live --print-stats
../../.venv/bin/python build_us_kr_discovery.py --live --print-stats
```
)
