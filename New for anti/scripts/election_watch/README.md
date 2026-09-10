# Election watch — 세계 선거 창 (scaffold)

**소유: 데이터/파이프 = Grok · UI = Claude**
Grok 이관 문서: `HANDOFF_GROK.md` · UI 이관: `HANDOFF_CLAUDE_ELECTIONS_UI_V2.md`

이후 UI에 **「선거」패널**을 붙일 때 읽는 계약입니다.

## 제품 목표 (사용자 요구)

1. **올해 어디서** 선거가 있는지 (대선·총선·지선·재보궐·당대표)
2. **집권 정당** / 추적 정당
3. 당대표 선거 범위  
   - **대통령제**: 여당 + 제1야당  
   - **의원내각제**: 주요 정당 **최대 4개**
4. 재보궐 포함
5. **여론조사**: 전국 대선 경마형 배제 · **통치(국정) 지지율** 유지
6. **미국 예측시장**(Polymarket 등)을 선거 사이클 중 참고 확률 파이프라인으로
7. **주요 개각**은 속보·보드 모두 가치 있음 (1급)

깊이는 국가별 차등 적용한다. 미국만 연방+주 deep, 다른 1급은 국가별 특수 구조, 2급은 국가 단위와 선택적 광역 요약이다. 이란·사우디는 2급 지정학 특수형으로 권력기관·안보·에너지 축을 추가하고, 3급은 국가수반·집권축·핵심 일정이 기본이다. 한국을 포함한 각국 지방의원 개별 명단은 기본 범위가 아니다.

## 지금 하는 일 / 안 하는 일

| 함 | 안 함 |
|----|--------|
| `country_seed.json` 골격 + 시스템·정당 캡 정책 | 전 세계 자동 캘린더 완성 |
| 속보 RSS 선거·개각·통치지지율 (commodity_news) | app.js 선거 창 UI (T01 이후) |
| Polymarket Gamma API → `betting_markets` | 도박 UX / PredictIt(지역 제한 시 보류) |
| `elections_board_v1.json` 스냅샷 | LLM 전량 요약 |

## 실행

```bash
cd "New for anti/scripts/election_watch"
python3 run_refresh_cycle.py --build-derived
# ticker_v1.json 이 있으면 election / cabinet / governance 헤드라인 live 부착
# --no-betting 으로 Polymarket 호출 생략
```

산출: `public/data/elections_board_v1.json`, `elections_calendar_master_v1.json`, `elections_ui_manifest_v1.json`. UI는 매니페스트를 먼저 읽고 `ready / partial / disabled` 계약을 따른다.

미국 백악관 수석급은 공식 페이지만 자동 승격한다.

```bash
python3 -m election_watch.extract_usa_eop --fetch --merge-tier12 --write-report
# 또는
python3 run_refresh_cycle.py --refresh-usa-eop --build-derived
```

정본 `config/extracted/usa_eop.json` → `tier12_executives.json#countries.USA` → 보드 `executive_live.white_house`.  
월간 GitHub Actions YAML은 `ci/elections_eop_monthly.yml` (Claude가 `.github/workflows/`로 복사). 핸드오프: `HANDOFF_CLAUDE_ELECTIONS_EOP_ACTIONS.md`.

## 속보 연동 (commodity_news)

통과:

- 대통령/총선/지선/재보궐/당대표
- **개각·외교/재무/국방 장관 교체** (`cabinet_reshuffle`)
- **국정·통치 지지율** (`governance_poll`)

배제:

- 전국 대선 경마형 여론조사·RCP 평균 등

중요도 과다 속보는 `importance.json` (주요국 3급 > 비주요 2급 가능).

## 배팅 시장

`config/betting.json` → `election_watch.betting.fetch_us_election_markets`  
공개 Polymarket 검색/목록만 사용. `betting_markets.markets[]` 에 question·outcome 가격·volume.

## 데이터 채우기

`config/calendars/{usa,jpn,rus}_2026.json` 에 연도 일정을 넣고 `build_board.py`가 병합.  
시드·프로필의 `events_2026` 는 캘린더 파일이 우선. 교차 로그: `config/extracted/calendars_2026.json`.

## 학습 (문서/텍스트)

숫자 API 페인팅이 아님. → **`LEARNING.md`**

- 스펙트럼 규칙: `config/spectrum_rules.json` (공화·자민 = conservative → 지도 빨강)
- 중국 보고서: `config/china_report_sources.json` + `raw/china/CMPR_2025.{pdf,txt}`
- PLA 한국어 바이오: `python3 -m election_watch.build_china_pla_bios` → `config/china_pla_bios.json` (LLM 아님)
- Anti 문헌만: `HANDOFF_ANTIGRAVITY_CHINA_LIT.md` — JSON/파이프는 Cursor

## 1급 상태 · 파벌 (언론 교차)

| 파일 | 내용 |
|------|------|
| `config/tier1_status.json` | 뭐가 됐고 뭐가 남았는지 |
| `config/official_sources.json` | 선관위·공식 포털 |
| `config/usa_house_factions.json` | 하원 파벌 + HFC 119대 스냅샷(언론 교차) |
| `config/jpn_ldp_factions.json` | 자민 파벌/旧파벌 (読売·日経·연합 등) |

**2급 deep:** `GBR`·`ISR` (`extract_gbr_isr`) · `KOR` (`extract_kor`).  
**2급 composition:** `DEU`·`FRA`·`BRA` (`extract_tier2_fill`) — 여론 숫자 todo.  
**2급 scaffold:** `TWN`·`TUR`·`IND`.  
**2급 지정학 핵심:** `SAU`·`IRN` — 선거 경쟁성보다 왕실·최고지도자·안보·에너지·권력기관 중심. → `tier3_leadership_briefs.json` 특수 팩 + 각 프로필.
**3급 간략:** `ARE` — 연방 왕정·7개 토후국 지도자 카드 중심.
**학습 분석 정본:** `LEARNING.md` + `config/extracted/learning_analysis_v1.json` + `human_labels.jsonl`.

미국: 당대표 선거 없음 → 원내대표만. HFC는 공식 명단 없음 → NADA(2025-04) + Ballotpedia/Pew/CDC 교차로 32명 스냅샷 남김.

일본: 공식 파벌은 아소파만 존속(読売·47NEWS). 旧아베·모테기·기시다·니카이 등은 해산 후에도 회동 블록으로 언론 추적 → `ex_*`로 남김. 전체 명단은 변동 심해 count+출처만.

## 진행 중 중간 집계 (`race_progress`)

진행 중 레이스만 권역/주 단위 누적 + 클릭 드릴다운 계약.

| 파일 | 내용 |
|------|------|
| `public/data/race_progress_kor_v1.json` | 민주당 전당 순회 **중간** 득표 |
| `public/data/race_progress_usa_v1.json` | 2026 중간선거 **주별 프라이머리** 누적 + 주 클릭 시 당 승자 |
| `public/data/race_progress_bundle_v1.json` | 합본 + UI 계약 |
| `public/data/race_progress_preview.html` | 로컬 미리보기 (대시보드 app.js 미연동) |

```bash
python3 -m election_watch.build_race_progress   # USA 재생성 (KOR 스냅 유지)
python3 build_board.py --no-betting             # row.race_progress 부착 (KOR·USA)
```

미리보기: `public/data` 에서 정적 서버 후 `race_progress_preview.html` 열기.

- **KOR**: 단위 = 순회 권역; 클릭 → %/득표·시도 서브.
- **USA**: 2026은 대선 경선 아님(대선 프라이머리 2028). 단위 = 주; 클릭 → 상원·주지사·하원 샘플 승자. 승자 출처 The Midterm Project 파싱.

### 가중·합산 모델 (`aggregation`)

| 레이스 | model_id | 동일 가중? |
|--------|----------|------------|
| KOR 민주 전당 | `weighted_convention_hybrid` | **아니오** — 최종 **70%** 대의원·권리당원 + **30%** 국민여론; TK·경남 당원 **+5%**; 순회 중간은 권리당원 1순위 단순 누적 |
| KOR 국민의힘 (2025) | 동일 계열 | **80/20** (완료) |
| USA 2026 중간 프라이머리 | `independent_jurisdiction_first_past_post` | 관할 **독립**; UI 진척만 1주=1. 전국 가중합 **없음** |
| USA 대선 경선 (2028) | `delegate_allocation_…` | 대표 수·주 규칙 가중 — 2026 보드 밖 |

비교 정본: `public/data/race_aggregation_compare_v1.json` · 번들 `aggregation_compare`.

## UI 스케치 (나중)

```
[2026 선거 맵/리스트]
  국가 · 체제 · 집권당
  다가오는 일정 (D-day)
  진행 중 race_progress (KOR 순회 / USA 주 롤링)
  예측시장 스트립 (US cycle)
  통치지지율 헤드라인
  개각 / 관련 속보
```

## 미국 슈퍼팩 공시 분석

`python3 build_superpac.py --cycle 2026` · `FEC_API_KEY` 또는 `DATA_GOV_API_KEY` 사용.
연방 후보 명부와 정정된 정기 독립지출을 별도 주별 JSON으로 발행한다. 지도용 후보·정당·경선·단체·선거구 조회 계약과 워싱턴 주지사 부분 수집을 제공한다. UI 연결과 배포는 Claude 인수 단계다. 주지사 전국 자동 수집은 미지원이다. 범위·원본 근거·주지사 검토 입력·실행 방법: [SUPERPAC_PIPELINE.md](SUPERPAC_PIPELINE.md).

### 미국 지도 선거자금 백엔드 인수

- [Claude UI/배포 인수인계](HANDOFF_CLAUDE_SUPERPAC_BACKEND.md)
- 실행: `python3 refresh_superpac.py --plan` / `python3 refresh_superpac.py --cadence daily`
- 지도 계약 생성·대조: `python3 build_superpac_map.py` / `python3 validate_superpac_map.py`
- 워싱턴 주지사 단독 수집: `python3 build_governor_finance.py --cycle 2024`
- 비활성 Actions 설치 템플릿: `ops/us_superpac_refresh.yml` (Claude가 설치·배포)
