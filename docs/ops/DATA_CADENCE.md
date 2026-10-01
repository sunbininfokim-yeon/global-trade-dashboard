# DATA_CADENCE — 파이프라인 주기 · 저장 · 학습 전략

**목적:** “얼마나 자주 잡을까”를 데이터 성격에 맞게 고정하고, **어디에 두고 / 어떻게 학습에 쓸지**를 한 표로 공유한다.  
**정본 연동:** `PIPELINE.md`(흐름), `DATA_LAYOUT.md`(JSON 계약), 본 문서(주기·전략).

---

## 0. 한 줄 원칙

| 원칙 | 의미 |
|------|------|
| **원천 주기 ≥ 폴링 주기** | 소스가 주간이면 매 30분 호출해도 새 값 없음 → 낭비 + 쿼터 소진 |
| **표시 ≠ 학습** | 대시보드 스냅샷은 얇게·자주 가능. 학습 테이블은 느리고 재현 가능 |
| **캘린더 우선, 맹목 폴링 금지** | Fiscal Data / FOMC / QRA처럼 **발행 일정이 공개된 것**은 일정 D-1·D0 밀집, 평시 듬성 |
| **원본 캐시 ≠ git** | NASA·RSS 전문·대용량 CSV는 `cache/` 또는 KV. git에는 요약·모델·forecast 만 |
| **중요 속보만 빠르게** | 티커 빈도와 항목 수를 함께 캡 (`importance`·`ticker_cap`) |

---

## 1. 저장 계층 (어디에 쌓이는가)

```text
┌─────────────────────────────────────────────────────────────────┐
│ A. 원천 (외부)                                                     │
│    NASA POWER · Open-Meteo · UN Comtrade · FRED · Yahoo · RSS ·  │
│    Treasury FiscalData · USDA · PortWatch · Polymarket …          │
└───────────────────────────────┬─────────────────────────────────┘
                                │ 스크립트 / Worker 프록시
┌───────────────────────────────▼─────────────────────────────────┐
│ B. 원본 캐시 (비커밋 또는 단기 KV)                                   │
│    scripts/yield_model/cache/                                     │
│    scripts/*/cache/  (label_history, translation, 등)            │
│    Cloudflare KV  API_CACHE  (무역·FRED·YFinance 응답)            │
│    CF KV (brazil_agri bot 전용 네임스페이스 — nightly bot)         │
└───────────────────────────────┬─────────────────────────────────┘
                                │ collect / train / build
┌───────────────────────────────▼─────────────────────────────────┐
│ C. 학습·모델 (git)                                                │
│    *_training.csv · *_model.json · series_catalog · country_seed  │
└───────────────────────────────┬─────────────────────────────────┘
                                │ forecast / snapshot build
┌───────────────────────────────▼─────────────────────────────────┐
│ D. 사이트 스냅샷 (git → CF static)  public/data/*.json            │
│    yield_forecast · ticker · liquidity · official_reports ·       │
│    shipping_capacity · elections_board · live_override            │
└───────────────────────────────┬─────────────────────────────────┘
                                │ GET /api/* 또는 static fetch
┌───────────────────────────────▼─────────────────────────────────┐
│ E. 방문자 브라우저 (Cache-Control 수 분)                           │
└─────────────────────────────────────────────────────────────────┘
```

| 계층 | 장기 보관 | git |
|------|-----------|-----|
| B 원본 일별 기상 | Actions artifact 또는 로컬 재생성 | ❌ |
| C training / model | 재현성 | ✅ |
| D 요약 JSON | 대시보드 계약 | ✅ (≤~200KB 권장) |
| API_CACHE KV | TTL 만료 후 소멸 | n/a |

---

## 2. 현재 구현된 주기 (As-Is)

시간대 표기: **UTC cron** · 괄호 **KST (=UTC+9)**.

### 2.1 GitHub Actions → `public/data` (또는 KV)

2026-09-24 에 `.github/workflows/*.yml` 크론을 그대로 옮겨 다시 썼다. 이전 표는
수율 예측을 월요일로 적고 있었지만 실제로는 금요일 밤(UTC)에 돈다.

**배포 연결:** 봇이 `main` 에 올린 커밋은 `on: push` 를 깨우지 못한다. 그래서
아래 표에서 `main` 에 커밋하는 워크플로는 전부 `deploy.yml` 의 `workflow_run`
목록에 있어야 사이트에 반영된다. 커밋 없이 끝난 실행은 배포 단계에서 건너뛴다.
목록 누락은 PR 마다 `tools/ops/check_deploy_chain.py` 가 잡는다.

금요일(UTC) 밤 배치는 push 경합을 피하려고 시각을 흩어 놓았다. 옮길 때 서로
겹치지 않게 할 것.

| 워크플로 | cron (UTC) | KST | 산출 | 성격 |
|----------|------------|-----|------|------|
| **수시 (매시~6시간)** | | | | |
| `commodity_news_ticker.yml` | `12 * * * *` | 매시 :12 | `ticker_v1.json` | 속보 RSS |
| `official_reports.yml` | `20 */4 * * *` | 4시간마다 :20 | `official_reports_v1.json` | 기관 피드 |
| `commodity_reports.yml` | `40 */4 * * *` | 4시간마다 :40 | `commodity_reports_v1.json` | 상품×국가 보고서 |
| `macro_liquidity_intel.yml` | `15 */6 * * *` | 6시간마다 :15 | `liquidity_intel_v1.json` | QRA·Fed·기자 유동성 |
| `data_freshness_watchdog.yml` | `9 */4 * * *` | 4시간마다 :09 | (없음, 실패 알림만) | 미시구조·해운 파일 신선도 감시 |
| **매일** | | | | |
| `gas_storage_daily.yml` | `35 0 * * *` | 매일 09:35 | `gas_storage_v1.json` | 천연가스 재고 (EIA·GIE) |
| `sync-congress.yml` | `17 2 * * *` | 매일 11:17 | Supabase | 미국 의회·연방관보·공법 |
| `daily_update.yml` | `6 18 * * *` | 매일 03:06 | **CF KV** (Brazil agri bot) | 브라질 농업 |
| `shipping_capacity_update.yml` | `37 18 * * *` | 매일 03:37 | `shipping_capacity_*_v1.json` 4종 | PortWatch 등 |
| `fomc_collect_refresh.yml` | `2 19 * * *` | 매일 04:02 | `fomc_statement_diff_v1.json`, `us_macro_quality_v1.json` | FOMC·베이지북 (회의일만 실제 변화) |
| `macro_live_overlay_refresh.yml` | `40 19 * * *` | 매일 04:40 | `macro_monitor_v1.json` | TGA·금리·환율·지수 (FRED/Yahoo/BOK) |
| **평일** | | | | |
| `market_microstructure_daily.yml` | `13 21 * * 1-5` | 화–토 06:13 | `market_microstructure_v1.json` 외 20여 종 | 코스피 미시구조·US→KR 전이·파생 보드. `KRX_API` 없으면 US·집중도만 |
| `overseas_letf_daily.yml` | `35 23 * * 1-5` | 화–토 08:35 | `overseas_letf_board_v1.json` | 해외 레버리지 ETF |
| **주간** | | | | |
| `us_superpac_refresh.yml` | `25 8 * 1-9,11-12 1` / `25 8 * 10 1,5` | 월 17:25 (10월은 월·금) | `usa_superpac_index_v1.json` 외 | 미국 선거자금 |
| `peer_gdp_refresh.yml` | `30 18 * * 3` | 목 03:30 | `macro_monitor_v1.json` | 주요국 실질 GDP (World Bank, 연간 원천) |
| `soma_maturity_refresh.yml` | `45 18 * * 3` | 목 03:45 | `soma_maturity_v1.json`, `macro_monitor_v1.json` | 연준 SOMA 만기 버킷 |
| `commodity-digest.yml` | `0 23 * * 0` | 월 08:00 | (메일 발송) | 즐겨찾기 원자재 주간 메일 |
| `fetch_icrisat.yml` | `8 15 * * 5` | 토 00:08 | `icrisat_crop_production.json` (대용량) | 인도 작물 통계 |
| `yield_forecast.yml` | `22 15 * * 5` | 토 00:22 | `yield_forecast.json` | 미국 수율 |
| `brazil_yield_forecast.yml` | `44 15 * * 5` | 토 00:44 | `brazil_yield_forecast.json` | BR 수율 |
| `argentina_yield_forecast.yml` | `6 16 * * 5` | 토 01:06 | `argentina_yield_forecast.json` | AR 수율 |
| `india_yield_forecast.yml` | `28 16 * * 5` | 토 01:28 | `india_yield_forecast.json` | IN 수율 |
| `china_yield_forecast.yml` | `50 16 * * 5` | 토 01:50 | `china_yield_forecast.json` | CN 수율 |
| `russia_yield_forecast.yml` | `12 17 * * 5` | 토 02:12 | `russia_yield_forecast.json` | RU 겨울밀 수율 |
| `climate_global_refresh.yml` | `34 17 * * 5` | 토 02:34 | `climate_global_v1.json` | ENSO·IOD (NOAA) |
| `japan_growth_refresh.yml` | `56 17 * * 5` | 토 02:56 | `macro_monitor_v1.json` | 일본 성장 진단 (ESRI/BOJ) |
| `sst_refresh.yml` | `18 18 * * 5` | 토 03:18 | `sst_anomaly_v1.json` | 해수면 온도 격자 |
| `city_wx_refresh.yml` | `40 18 * * 5` | 토 03:40 | `city_wx_v1.json` | 주요 산지 기상 |
| `update_data.yml` | `24 19 * * 5` | 토 04:24 | `live_override.json` | USDA PSD·Comex |
| **월간·분기** | | | | |
| `elections_eop_monthly.yml` | `0 10 1 * *` | 매월 1일 19:00 | `elections_board_v1.json`, `elections_ui_manifest_v1.json` | 백악관·EOP 명단 |
| `canada_yield_forecast.yml` | `0 11 1 * *` | 매월 1일 20:00 | `canada_yield_forecast.json`, `canada_gov_outlooks.json` | CA 수율 + AAFC/주 작황 |
| `sync-policy-reference-monthly.yml` | `31 3 1 * *` | 매월 1일 12:31 | Supabase | 의원·상임위 기준정보 |
| `sovereign_fiscal_refresh.yml` | `18 18 3 * *` | 매월 4일 03:18 | `macro_monitor_v1.json` | IMF/재무부 국가부채·이자 |
| `elections_committees_quarterly.yml` | `0 10 1 1,2,3,4,7,10 *` | 1·2·3·4·7·10월 1일 19:00 | `elections_board_v1.json` | 미국 상임위 지도부 |
| **이벤트·수동** | | | | |
| `validate_registry.yml` | main push 시 | — | `climate_registry_v1.json` | 수율 모델 레지스트리 재생성 |
| `deploy.yml` | main push + 위 수집기 완료 시 | — | Cloudflare Worker | 배포 |
| `india_icrisat_fetch.yml`, `market_microstructure_backfill.yml`, `fetch_congressional_districts.yml`, `comtrade_probe.yml`, `probe_tigerweb_120th.yml`, `rollover-congress.yml` | 수동 | — | — | 일회성 재수집·진단 |

> **워크플로가 없는 공개 파일:** 호주·인도네시아·태국·베트남·가나·코트디부아르·
> 에티오피아·남아공·우간다 수율 예측, `rig_count_v1.json`, `qra_engine_v1.json`,
> `sst_regions_v1.json`, `race_progress_*`, `russia_export_pulse_v1.json`,
> `hedge_fund_ust_v1.json`, `export_controls_v1.json`, `usda_gain_outlook_v1.json` 은
> 손으로 한 번 만든 뒤 갱신 경로가 없다 (2026-09-24 기준). 파일 안의
> `generated_at`/`as_of` 를 보고 판단할 것.
>
> 선거 보드(`elections_board_v1.json`)는 위 월간·분기 잡과 PR 머지로 다시 만들어지고,
> 배팅(Polymarket) 전용 크론은 아직 없다.

### 2.2 Cloudflare Worker (요청 시 캐시 + 야간 warm)

| 경로 / 소스 | KV TTL (대략) | 원천 실제 갱신 | 비고 |
|-------------|---------------|----------------|------|
| **cron `0 * * * *`** (`wrangler.jsonc`) | — | 매시 | Comtrade `API_CACHE` warm-up (신선한 키는 건너뜀) |
| Comtrade 에너지 2709/2711 | 48h | 원천은 연·월 리비전 | 방문 시 프록시 |
| Comtrade 석탄·아연·Al | 7d | 느림 | |
| Comtrade 귀금속·Cu | 24h | 느림 | |
| Comtrade 곡물·당·커피 | 14d | 연간 통계에 가까움 | |
| USDA ESR (주간 수출판매) | 24h | **주 1** | 신선도 가치 높음 |
| USDA NASS / FAS PSD | 24h | 월·시즌 | 쿼터 보호 |
| FRED | **1h** | 시리즈별 (일~월) | 금융 패널 |
| BOK keystats | 1h | 기관 공표 | |
| EIA | 1h | 일·주 | 에너지 |
| Yahoo Finance chart | 1h | 장중 분~일 | 주가·선물 대리 |
| `/api/ticker` 등 스냅샷 | max-age 120–180s | Actions 스냅샷 따름 | git JSON 읽기 |

Worker는 **위성·NASA 원시 픽셀을 저장하지 않는다.** 기상 원본은 yield 파이프라인 쪽.

### 2.3 수율(ML) 데이터 원천 주기 (스크립트 기준)

| 데이터 | 원천 예 | 원본 실제 주기 | 파이프 사용 | 저장 |
|--------|---------|----------------|-------------|------|
| 기상 관측·단기예보 | NASA POWER, Open-Meteo | **일(POWER)** / 예보 수일 | 시즌 창 집계 후 Ridge | `cache/*.csv` → `*_training.csv` |
| 위성 지수 (NDVI 등) | MODIS 등 | **16일~월** (제품별) | 대부분 **미사용/생략** (기간 불일치 주석 있음) | 도입 시 cache 전용 |
| 수확 실적 | NASS, CONAB, ICRISAT, 중국 통계 | **연 1 / 시즌 개정** | target | training.csv |
| ENSO/ONI | NOAA | **월** | 시즌 피처 | cache/feature |
| 수출·무역 배경 | Comtrade, ESR, PSD | 주~연 | 대시보드·일부 국가 모델 부가 | KV / live_override / forecast 노트 |

예측 **재실행**은 대체로 **주 1회(월)** — 일별 기상이 바뀌어도 `season_progress` 안에 “관측 vs 예보 vs 기후” 몫만 갱신.

---

## 3. 권장 목표 주기 (To-Be 전략)

원천 속도와 제품 가치로 다섯 층으로 나눈다.

### Layer L0 — 실시간~준실시간 (≤15–30분)

| 항목 | 권장 폴링 | 저장 | 학습? |
|------|-----------|------|--------|
| **속보 티커** (RSS) | **15–30분** (현 30분 유지 가능) | `public/data/ticker_v1.json` | 순위 라벨만 (importance JSONL) — **본문 학습 금지** |
| **예측시장** (Polymarket) | 선거 시즌 **30–60분**, 평시 **4–6h 또는 off** | `elections_board` 필드 | 확률 시계열 로그(옵션) |
| 거래소 틱 수준의 시세 | **사용 안 함** (YFinance 월봉·1h 캐시로 충분) | KV | 직접 타깃에 쓰지 않음 |

**속보 검토 결론**

| 내용 | 권장 |
|------|------|
| 일반 상품·외교 RSS | 30분 충분 (대부분 매시간 갱신) |
| “진짜 속보” 체감 | 15분으로 올려도 됨 — **단** `ticker_cap` 24 + `min_importance` 유지, git commit 폭주 시 **변경 시에만 push** |
| 기자 유동성 추출 | 티커와 분리 — **6h** (`liquidity` 잡에 포함) |
| 개각·대선 당일 | cron 그대로 + **수동 workflow_dispatch** |

Git에 30분마다 빈 커밋이 쌓이면: `git commit` 조건을 **해시 변경 시만** 하도록 workflow에 가드 권장.

### Layer L1 — 장중·일내 (1–6시간)

| 항목 | 권장 | 저장 | 학습 |
|------|------|------|------|
| FRED (TGA, RRP, WALCL 등) | Worker **1h** 캐시 유지 / 패널은 방문 시 | `API_CACHE` | 유동성 피처 테이블(향후 일단위 다운샘플) |
| EIA 스팟·주간 | 1–6h | KV | 에너지 부가 신호 |
| **공식 보고서 피드** | **4h** (현행) + **캘린더 D0에 추가 1회** | `official_reports_v1.json` | series promote/drop JSONL |
| QRA·권위 매크로 문장 | **6h** + **Treasury release-calendar 당일** | `liquidity_intel_v1.json` | 이벤트 태그 → 티커 1급 주입 |

### Layer L2 — 일 1회 (야간 KST)

| 항목 | 권장 UTC | 저장 | 학습 |
|------|----------|------|------|
| Comtrade warm | `0 18 * * *` 유지 | KV | 무역 구조 피처(연도 롤) |
| Brazil agri bot | 동일대 | KV | 시즌 진행률 보조 |
| Shipping / PortWatch | 일 1 | `shipping_capacity_v1.json` | 병목 더미/이벤트 |
| 선거 보드(+배팅 평시) | 일 1 또는 주 수회 | `elections_board_v1.json` | seed 일정 갱신 |

### Layer L3 — 주 1회

| 항목 | 권장 | 저장 | 학습 |
|------|------|------|------|
| **수율 re-forecast** (기상 관측 누적 반영) | 월 09–11 UTC 현행 유지 | `*_yield_forecast.json` | point/range 갱신; train은 연 개정 때만 |
| USDA ESR 소비 | Worker 24h + 원천 주간 | KV | 미국 수출 스케줄 피처 |
| `live_override` | 주 1 (현 일요) 또는 월 1로 축소 가능 | `live_override.json` | 대시보드 오버레이 |

### Layer L4 — 월·시즌·연

| 항목 | 권장 | 저장 | 학습 |
|------|------|------|------|
| NASS / CONAB / PSD 개정 | 공표 후 **이벤트 트리거 + 주 점검** | training 갱신 후 retrain | **핵심 target / 보정** |
| ICRISAT 대용량 | **수동 또는 월 1**, 결과는 scripts 쪽 요약만 public | blob ≠ 무분별 public | 인도 패널 타깃 |
| full retrain | 시즌 종료·방법 변경 시 | `*_model.json` | skill 재측정 |
| 위성 NDVI 도입 시 | 16일 제품 주기 | cache only | 피처 창 정합 후만 train 컬럼 |

---

## 4. 정부·공식 “릴리스 캘린더” 전략

사용자 제안([Fiscal Data release calendar](https://fiscaldata.treasury.gov/release-calendar/))과 일치:

### 4.1 왜 주기 폴링만으로 부족한가

| 문제 | 설명 |
|------|------|
| 대부분 날짜 공지 | D0 이전에 페이지가 비어 있음 → 4h 폴링해도 신호 0 |
| 일부 “tentative” | 당일 시각 이동 |
| 시리즈 단위 불균일 | MTS, DTS, MSPD, refund rates 등 날짜 다름 |

### 4.2 권장 아키텍처

```text
release_calendar_v1.json   ← 일 1회 스크랩 또는 고정 seed + 수동 보정
        │
        ├─ today ∈ calendar  ?  →  high-cadence probe (15–60min, 해당 URL만)
        │                         success → official_reports / liquidity 스냅샷 주입
        │                         + event_log (series_id, released_at)
        └─ else               →  기존 4–6h 피드 유지
```

| 시리즈군 (예시) | 접근 | 폴링 |
|-----------------|------|------|
| FiscalData 일일/월 표 | 캘린더 파서 (HTML/API 가능하면 API 우선) | D-1 저녁 1회 + D0 밀집 |
| FOMC statement / minutes | Fed 캘린더 | 회의일만 |
| Beige Book | 연 8회 | 발행일 probe |
| QRA | Treasury 보도자료 패턴 | 분기 D0 |
| USDA WASDE | 월간 일정 고정에 가깝 | 캘린더 seed |
| EIA STEO / inventory | 주간 | 수/목 등 고정 규칙 |
| BOK 통계 | 보도자료 RSS | 4h 피드에 편입 |

**개별 체크리스트(초기):** 캘린더 항목마다 `series_id`, `url`, `expected_local_time`, `grace_hours`, `handler`(liquidity | official_reports | ticker), `last_seen_hash`.

### 4.3 학습 연결

- 공표 성공 → `event_log.jsonl` (비커밋 가능) 또는 `label_history` 에 `promoted:release`
- 수치 추출 가능한 것만 **feature 테이블**(일자×시리즈)로 down-sample → 금융/수출 모델에 조인
- PDF 전문 LLM 학습 **비목표** (catalog promote/keep/drop 만)

---

## 5. 도메인별: 파악 주기 · 저장 · 학습 활용

### 5.1 위성

| | |
|--|--|
| **현재** | 수율 코드 일부에서 MODIS NDVI **의도적 제외**(시계열 시작 2000, 갭) |
| **권장 주기** | 제품 cadence(예 16-day) + **지연 1–2 제품트** 후 수집 |
| **저장** | `scripts/yield_model/cache/sat/` 만. public 금지 |
| **학습** | 연도×지역 피크/면적 요약 1행 → training 컬럼. 픽셀 스택 금지 |
| **대시보드** | 있으면 forecast `note` 또는 skill 보조, 메인 point는 기상+추세 유지 |

### 5.2 기상

| | |
|--|--|
| **원천** | NASA POWER daily + Open-Meteo short forecast (기존) |
| **폴링** | collect 시 증분(이미 캐시 있으면 스킵) · **주 1 forecast 전에 강제 sync** |
| **저장** | `cache/power_*.csv` 등 비커밋 |
| **학습** | 시즌 창 합(precip, heat days, frost…) → Ridge residual. LSTM 기본 금지 (GOAL) |
| **실시간 UI** | 일별 raw 미배포; `season_progress.observed_share` 로만 |

### 5.3 주식·원자재 가격

| | |
|--|--|
| **현재** | Yahoo chart 월 interval, Worker 1h |
| **권장** | 패널 표시 **1h 캐시** 충분. 분봉 파이프 불필요 |
| **저장** | `API_CACHE` only |
| **학습** | 수율 모델 타깃으로 쓰지 않음. (선택) 주간 평균을 무역 스트레스 더미로만 |

### 5.4 무역·해운

| | |
|--|--|
| Comtrade | 연·월 성격 · KV warm 일 1 · TTL 2–14d |
| ESR | 주간 신호 · 24h KV |
| Shipping capacity | 일 1 스냅샷 · 병목 이벤트 플래그로 티커 주입 가능 |

### 5.5 뉴스·속보·보고서

| 스트림 | 폴링 | public | 학습 |
|--------|------|--------|------|
| RSS 속보 | 15–30m | ticker_v1 | importance promote/demote |
| 공식 보고서 RSS/목록 | 4h + 캘린더 | official_reports_v1 | series catalog label |
| 개각·통치지지율 | 티커 필터 | ticker / elections | 이벤트 타입 태그 |
| 경마 여론 | **수집 안 함** | — | — |
| 배팅 확률 | 시즌 밀집 | elections_board | 시계열 log 옵션 |

### 5.6 수율 예측 산출물

| | |
|--|--|
| **재예측** | 주 1 (기상 누적) |
| **재학습** | 새 수확 year target 확보 시 또는 skill 붕괴 시 |
| **저장** | training ✅ · model ✅ · forecast ✅ · raw ❌ |

---

## 6. 학습 전략 (데이터 → 모델) 요약

```text
[구조 모델]
  weather deviations + technology trend  →  *_model.json
  입력: 느린 통계 target + 일별기상의 시즌 집계
  재학습 트리거: 연 타깃 갱신 / 방법론 변경 (NOT 매 티커)

[이벤트·텍스트 계층 — “속보 과다” 대응]
  importance = f(country_tier, info_grade) + human JSONL
  용도: 표시 순위·캡. 수율 계수에 직접 안 넣음

[시리즈 카탈로그]
  official_reports promote/keep/drop → 다음 빌드 가중
  용도: 어떤 정부 소스가 대시보드 가치 있는지

[유동성]
  수치(FRED)는 시계열 feature 후보
  기자 본문 추출 수치(TGA/RRP 언급) = 검증·교차
  용도: 금융 패널 · (향후) 스트레스 더미

[캘린더 이벤트]
  release 성공 로그 → “발표 충격” 타임스탬프
  용도: 사후 평가, 속보 1급 강제, 과소 폴링 보정
```

**금지·비목표**

- 뉴스 전문으로 yield를 매일 재훈련  
- Dropbox 대량 PDF 학습  
- 위성 원시 큐브를 public/data에 커밋  

---

## 7. 권장 일일·주간 운영 리듬 (에이전트/사람)

| 시각(KST) | 자동화 | 사람/에이전트 |
|-----------|--------|----------------|
| 상시 30분 | 티커 | importance drop 폭주 시 demote |
| ~03:00 | Comtrade warm, shipping, brazil bot | KV 실패 로그 |
| 주간 월 저녁 | 국가 yield forecast | skill/low_confidence 확인 |
| 일 1–2회 | 캘린더 scraper (도입 후) | FiscalData “tentative” 수정 |
| 발표 예정일 | probe 밀집 | 실패 시 수동 URL |
| 시즌 | retrain | DATA_LAYOUT 계약 준수 커밋 |

---

## 8. 갭과 다음 구현 우선순위

| 우선 | 작업 | 효과 |
|------|------|------|
| P0 | **Release calendar** 수집기 + D0 밀집 probe | 정부 보고서 낭비 폴링 감소·놓침 감소 |
| P0 | 티커 commit **content-hash 가드** | git 노이즈·Actions 분 절약 |
| P1 | `elections_board` workflow (일 1 + 시즌 30–60m 배팅) | 배팅 파이프 자동 연결 |
| P1 | `DATA_CADENCE` 표를 README/TASKS에 링크 | 멀티에이전트 동기화 |
| P2 | FRED/TGA 일별 피처 적재 (git 소형 parquet 또는 csv) | 유동성 학습 기반 |
| P2 | 위성 요약 피처 파일럿 1개 작물 | 문헌 T05와 조율 |
| P3 | live_override 범위 정리 (중복 Comtrade 제거) | 유지비 감소 |

---

## 9. 빠른 참조 — “지금 어디에 있나”

| 알고 싶은 것 | 위치 |
|--------------|------|
| 방문자 예측치 | `public/data/*_yield_forecast.json` |
| 방문자 속보 | `public/data/ticker_v1.json` → `/api/ticker` |
| 유동성 이벤트 | `public/data/liquidity_intel_v1.json` → `/api/liquidity` |
| 공식 보고서 목록 | `public/data/official_reports_v1.json` |
| 상품×국가 보고서 | `public/data/commodity_reports_v1.json` → `/api/commodity-reports` |
| 해운 | `public/data/shipping_capacity_v1.json` |
| 선거+배팅 | `public/data/elections_board_v1.json` |
| 무역 프록시 신선도 | Worker `API_CACHE` + COMTRADE_TTL |
| 기상 원본 | `scripts/yield_model/cache/` |
| 학습 재현 | `*_training.csv` + `*_model.json` |
| cron 목록 | `.github/workflows/*.yml` · `wrangler.jsonc` triggers |

---

## 10. 의사결정 치트시트

```
Q. 새로 API를 붙일 때 몇 분마다?
  1) 원천 공표 주기 확인
  2) UI 민감도 (속보 vs 연간 무역)
  3) 쿼터/비용
  → min(원천×½, UI 요구) 로 상한, 캘린더 있으면 평시↓ D0↑

Q. git에 넣을까?
  방문자가 직접 쓰는 요약 JSON / 모델 계수 → YES
  일별 원시 시계열·RSS 본문 → NO (cache/KV)

Q. 학습에 넣을까?
  재현 가능한 숫자 피처·시즌 집계 → YES
  제목 텍스트·경마 여론·틱 시세 → 기본 NO
```

문서 갱신 시 cron 변경은 **본 표 As-Is 섹션과 workflow 파일을 같이** 수정한다.
