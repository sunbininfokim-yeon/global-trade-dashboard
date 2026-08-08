# Claude UI handoff — 선빈 수정사항 전체 + QRA 비교 뷰

**Cursor = 데이터/엔진** (`scripts/macro_monitor/**`, `public/data/macro_monitor_v1.json`, `public/data/qra_engine_v1.json`)  
**Claude = UI/배포** (`New for anti/app.js`, `style.css`, `index.html`, …) — **이 파일만 보고 UI 작업**

관련: [`CLAUDE_UI_HANDOFF.md`](./CLAUDE_UI_HANDOFF.md) · [`CLAUDE_UI_HANDOFF_US_TUNING.md`](./CLAUDE_UI_HANDOFF_US_TUNING.md) · [`QRA_ENGINE.md`](./QRA_ENGINE.md)

데이터 생성:

```bash
cd "New for anti/scripts/macro_monitor"
python3 build_qra_engine.py --download --from-year 2020
python3 build_macro_monitor.py --live   # QRA compare 오버레이 포함
```

---

## 1. (신규) QRA 클릭 → 비교 표/그래프 — **UI 필수**

선빈: *클릭하면 전분기 발행량 또는 전분기 예측 발행량과 해당기 발행량, 또는 셋 다 표·그래프*

### 데이터 계약 (이미 JSON에 있음)

USA 지표/칩 `qra_issuance`:

| 필드 | 용도 |
|------|------|
| `compare.series[]` | 그룹 바 차트 (1~3개) |
| `compare.table[]` | 동일 내용 표 |
| `compare.series[].id` | `prior_actual` \| `prior_forecast` \| `current` |
| `compare.series[].label_ko` | 전분기 실적 / 직전 공시 예측 / 당기 공시 |
| `compare.series[].value` | 순발행 $B (`privately_held_net_marketable`) |
| `compare.series[].period` | 예: `July–September 2026` |
| `components[]` | **보조 뷰**: 만기별 쿠폰 바 (기존) |
| `history_net_borrowing[]` | 선택: 분기 추이 스파크/라인 |
| `ui.click_view` | `"compare_bar_table"` |
| `ui.secondary_view` | `"maturity_components"` |

### UI 동작

1. `qra_issuance` 칩/차트 클릭(또는 드로어 오픈)  
2. **기본**: `compare` 그룹 바 + 표 (있는 시리즈만)  
3. 토글/탭: 만기별 `components`  
4. 칩 숫자: `compare.series` 중 `id==current` 값 우선  

원문 복제·기자 UI 베끼기 금지. 숫자만 공식 Treasury/엔진.

전체 히스토리: `public/data/qra_engine_v1.json` → `events[].compare`, `latest.compare`

---

## 2. 선빈 UX/지표 수정사항 (엔진 반영분 → UI 연결)

아래는 Cursor 엔진/스펙에 **이미 반영**. Claude는 칩·차트·레이아웃만 연결.

| # | 요청 | 엔진/스펙 | UI 할 일 |
|---|------|-----------|----------|
| 1 | 국가 오버레이 확대 | — | 탭·칩·차트 공간 (기존 handoff §A) |
| 2 | 지표 옆 뉴스 레일 | `news_query` / `news_tags` | Worker 검색; 가짜 뉴스 금지 |
| 3 | 차트 공통 | 각 `chart_type` | 라인+크로스헤어, MA5, SOMA stack, FedWatch bar, 메타 뱃지, limitations |
| 4 | 브라질 등 원자재 → **growth** (FX 아님) | CHIP_ORDER / kits | growth 탭에 표시 |
| 5 | 노동 벤치마크 문구 | `LABOR_BENCHMARKS.md`, chip `reference` | 레벨 맹비교 UI 금지; note 표시 |
| 6 | 인도 읽기 순서 | `IN_MACRO_KIT` | CAD→Repo→USDINR→FPI→CPI 우선 |
| 7 | 금리 칩 순서 | `RATES_ORDER.md` | policy→MM→커브→스프레드→신용 |
| 8 | 중국 주식 A→H→Connect, **B주 제외** | CN kit | B-share 칩 없음 |
| 9 | 이스라엘 키트 / 이란 스킵 | `il_macro_v1` | ISR 표시; IRN 없음 |
| 10 | 신용등급 Wikipedia | `sovereign_ratings` live | status 칩 |
| 11 | FedWatch CME 스크래프 **금지** | 자체 스코어링 예정 | 스크래프 UI/폴백 넣지 말 것 |
| 12 | IndexErgo **참고만** | — | UI 복제·스크래프 금지 |
| 13 | **QRA 비교 바/표** | `compare` (본 문서 §1) | **이번 작업 핵심** |
| 14 | QRA Sources&Uses·TBAC | `qra_engine_v1.json` | 고급 드로어 선택(표 링크/접기) |
| 15 | TGA vs QRA · 관세 | `tga_vs_qra`, fiscal | 선택 뱃지/노트 |
| 16 | **중앙은행장 + 재무장관** | `countries[].officials` | 국가 헤더에 2명 표시 |
| 17 | **발전량 + 에너지 믹스** | `electricity_generation` + `energy_mix` | growth 칩; 클릭 시 믹스 바 |

---

## 2b. (신규) 중앙은행장 · 재무장관 — **UI 표시**

선빈: *말한 국가의 중앙은행장 + 재무(국제금융·재정) 장관만*

데이터: 각 `countries[]` / `countries_index[]` 의 `officials`:

```json
{
  "asof": "2026-08-08",
  "central_bank": {
    "institution_ko": "한국은행",
    "title_ko": "총재",
    "name_ko": "신현송",
    "name_en": "Hyun Song Shin",
    "appointed": "2026-04-21"
  },
  "finance": {
    "institution_ko": "재정경제부",
    "title_ko": "부총리 겸 장관",
    "name_ko": "구윤철",
    "name_en": "Koo Yoon-cheol",
    "appointed": "2026-01-02"
  }
}
```

**중국만** `set[]` (당서기 + 장관/행장, 동일인이어도 임명일 각각):

```json
"finance": {
  "institution_ko": "재정부",
  "set": [
    {"title_ko": "당조서기", "name_ko": "란포안", "appointed": "2023-09-28"},
    {"title_ko": "부장", "name_ko": "란포안", "appointed": "2023-10-24"}
  ]
}
```

인민은행도 동일: `당위서기`(2023-07-01) + `행장`(2023-07-25).

UI: 국가 헤더에 이름 + `appointed`(임명일). 중국은 세트 2줄.  
금융감독 수장 제외. 한국=재정경제부(구윤철).

설정: `config/officials.json` (인사 교체 시 여기만).

---

## 2c. (신규) 성장 탭 — 발전량 + 에너지 믹스 클릭

선빈: *성장에 전력량, 그래프 클릭 시 에너지 믹스*

지표 `electricity_generation` (growth, 전 국가):

| 필드 | 용도 |
|------|------|
| `value` / `display` | 연간 총발전량 TWh (칩) |
| `history` | 연간 시계열을 월말로 step-fill |
| `energy_mix.series[]` | 클릭 뷰: 연료별 비중 `%` (+ `twh`) |
| `components[]` | 동일 내용 (기존 바 렌더러 호환) |
| `ui.click_view` | `"energy_mix"` |
| `source` | Ember Yearly Electricity Data (CC-BY-4.0) |

UI: 기본 라인(발전량) → 클릭/토글 시 `energy_mix` 바(비중%).  
EMU는 Ember **EU** 지역 합산 프록시.

원본: `config/electricity_ember_v1.json` · 재추출 `tools/extract_ember_electricity.py`

---

## 3. QRA 엔진이 이미 하는 것 (Claude 재구현 금지)

- Treasury 아카이브 2020+ HTML + Sources&Uses PDF + TBAC PDF  
- 순발행/현금/스탠스/인과 플래그  
- Fiscal Data TGA · Customs Duties  
- CLI: `build_qra_engine.py`  
- 산출: `public/data/qra_engine_v1.json` (`engine_version` ≥ 0.3.0)

---

## 4. Smoke (Claude)

1. USA → liquidity → **QRA 발행** 클릭  
2. 비교 바 1~3개 + 표 (전분실적/직전예측/당기)  
3. 토글 시 만기 components  
4. 칩에 당기 순발행($B)  
5. `source`/`asof`/`quality` 뱃지  
6. CME FedWatch 스크래프 경로 없음  

---

## 5. Out of scope

- `app.js` / Worker / wrangler — Claude만  
- 네이버·이코노미21 기사 크롤·문장 복제  
- CME FedWatch 사이트 스크래핑  
