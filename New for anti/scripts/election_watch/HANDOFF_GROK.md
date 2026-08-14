# HANDOFF → Grok — election_watch 데이터·파이프 (Cursor 이관)

**as_of:** 2026-08-13
**상태:** Grok 세션 축적분 포함. **최신 이관 정본 → `MIGRATION_HANDOFF_2026-08-13.md`**
**UI·배포:** Claude 전용 (`HANDOFF_CLAUDE_ELECTIONS_UI_V2.md`). **절대 손대지 말 것.**

---

## 0. 소유권 (고정)

| 영역 | 소유 | 경로 |
|------|------|------|
| **데이터·파이프·추출·빌드** | **Grok** | `scripts/election_watch/**` 전체 |
| **선거 관련 public 데이터** | **Grok** | `public/data/elections_*.json`, `race_progress_*.json`, `race_aggregation_compare_v1.json`, `invest_lens_elections.json` 등 |
| **UI / app.js / 배포 / wrangler** | **Claude** | `app.js`, `style.css`, `index.html`, workflows 등 |

README.md 맨 위에도 한 줄: **데이터/파이프 = Grok · UI = Claude**.

**금지:** `app.js` 수정, UI 패널 구현, force-push, LLM으로 숫자 발명.

---

## 1. 제품 목표 (요약)

1. 올해 어디서 선거·당대표·재보궐이 있는지
2. 집권 정당 / 추적 정당
3. 당대표 선거 범위 (대통령제: 여+제1야 / 의원내각: 주요 최대 4)
4. 여론조사: **전국 대선 경마형 배제**, 통치(국정) 지지율만
5. 미국 예측시장(Polymarket) 참고 확률 파이프
6. 주요 개각은 속보·보드 모두 가치 (1급)

철학: **숫자·명단은 공개 문서/공식 소스에서만**. null + reason. LLM 발명 금지. (KFA와 동일 정신)

---

## 2. 핵심 파이프 명령

```bash
cd "New for anti/scripts/election_watch"

# 클로드 인수용 전체 산출물 재생성 및 UI 게이트 검증
python3 run_refresh_cycle.py --build-derived

# 보드 재생성 (Polymarket 생략 가능)
python3 build_board.py --print-stats
python3 build_board.py --no-betting

# race_progress (KOR 스냅 유지, USA 재생성)
python3 -m election_watch.build_race_progress

# 중국 PLA 바이오 (규칙 파싱, LLM 아님)
python3 -m election_watch.build_china_pla_bios

# 추출기들 (필요 시)
python3 -m election_watch.extract_kor
python3 -m election_watch.extract_gbr_isr
python3 -m election_watch.extract_tier2_fill
python3 -m election_watch.extract_rosters
python3 -m election_watch.build_factions
```

산출:
- `public/data/elections_board_v1.json` (메인 보드)
- `public/data/race_progress_{kor,usa,bundle}_v1.json`
- `public/data/race_aggregation_compare_v1.json`
- `public/data/elections_calendar_master_v1.json`
- `public/data/elections_ui_manifest_v1.json` (UI별 ready/partial/disabled + 국가 등급별 최대 깊이)

---

## 3. 19개국 깊이 정책 (현재)

**1급 deep (완료/유지):**
- **USA** — 중간선거 2026 프라이머리 + 하원/상원/주지사, HFC 파벌 스냅
- **JPN** — 중의원 465 + 참의원 + 지사 47, 자민 파벌(공식 아소 + 旧블록)
- **CHN** — CMPR + PLA 바이오 21명 (선거 없음, 리더십/군)
- **RUS** — 두마 2026-09-20, 라이트 구성

**2급 deep:** GBR · ISR · KOR
**2급 composition:** DEU · FRA · BRA (여론 숫자 todo)
**2급 scaffold:** TWN · TUR · IND
**2급 지정학 핵심:** SAU · IRN (leadership/energy/security core). **3급:** ARE (emirates brief)

UI 깊이는 데이터 깊이와 별도 게이트를 둔다. USA만 주 단위 deep, 다른 1급은 국가별 특수 구조, 2급은 국가 단위+선택적 광역 요약, 이란·사우디는 권력기관·안보·에너지 특수축을 추가하고, 3급은 국가 권력 브리프다. 지방의원 개별 명단은 기본 수집 대상이 아니다.

상태 정본: `config/tier1_status.json`
우선순위: `config/priority_tiers.json`

---

## 4. race_progress · 가중 규칙 (중요)

| 레이스 | model_id | 가중 |
|--------|----------|------|
| KOR 민주 전당 | `weighted_convention_hybrid` | **최종 70%** 대의원·권리당원 + **30%** 국민여론. TK·경남 당원 **+5%**. 중간 누적 = 권리당원 1순위 단순합 (≠최종) |
| KOR 국민의힘 (2025) | 동일 계열 | 80/20 (완료) |
| USA 2026 중간 프라이머리 | `independent_jurisdiction_first_past_post` | 관할 **독립**. UI 진척만 1주=1. **전국 가중합 없음** |
| USA 대선 경선 (2028) | delegate_allocation… | 2026 보드 밖 |

비교 정본: `public/data/race_aggregation_compare_v1.json`
UI는 반드시 aggregation 배지(주의 문장) 표시. Grok은 데이터 쪽에서 `aggregation.*` 필드를 정확히 유지.

- KOR units: 권역 순회, 클릭 → %/득표·시도 서브
- USA units: 주, 클릭 → 상원·주지사·하원 샘플 승자 (The Midterm Project 파싱)

---

## 5. 정확성 스티커 (절대 틀리지 말 것)

| 키 | 올바른 값 |
|----|-----------|
| 영국 총리 | **Andy Burnham** (2026-07-20~). **Starmer 현직 금지** |
| 한국 대통령 | 이재명 (2025-06-04~) |
| 한국 총리 | **한성숙** (2026-07-01~) |
| 미국 2026 | **중간선거 프라이머리** (대선 경선은 2028). 선거인단 점수 표현 금지 |
| 한국 전당 누적 | “권리당원 1순위 중간 · 최종 70/30 전” |
| 일본 파벌 | 공식 존속 = 아소파만. 旧아베·모테기 등은 `ex_*` 회동 블록 |

출처 교차 필수. 추측 날짜·명단 금지.

---

## 6. 다음에 팔 나라 큐 (재개 시 순서)

1. **브라질** (10월 대선) — composition → deep, TSE 좌석 업그레이드
2. **독일** (9월 주의회 + 총리 지지)
3. **프랑스** (총리 신원 + 지지율)
4. 대만 입법위 (KOR 템플릿 재사용)
5. 인도 주 캘린더
6. 튀르키예 (일정 발표 시)

3급 ARE: 조사 불필요. SAU/IRN은 2급 지정학 핵심으로 월간 원문 검토.

재개 시 `config/tier1_status.json`의 `remaining`과 `tier2_activation.remaining` 갱신.

---

## 7. 주요 설정·스키마 파일

| 파일 | 역할 |
|------|------|
| `config/country_seed.json` | 국가 골격 |
| `config/calendars/{iso}_2026.json` | 연도 일정 (우선) |
| `config/profiles/{iso}.json` | 프로필 |
| `config/spectrum_rules.json` | 지도색 (conservative→빨강 등) |
| `config/official_sources.json` | 선관위·공식 포털 |
| `config/betting.json` | Polymarket 검색 |
| `config/usa_house_factions.json` | HFC 등 |
| `config/jpn_ldp_factions.json` | 자민 파벌 |
| `config/china_pla_bios.json` | PLA 한국어 바이오 |
| `schemas/` | 검증용 |
| `LEARNING.md` | 학습·추출 철학 정본 |

속보 연동: commodity_news (election / cabinet_reshuffle / governance_poll 통과, 경마형 배제).

---

## 8. Grok 첫 프롬프트 (복붙용)

```
이관 받음. HANDOFF_GROK.md 기준.

소유: scripts/election_watch/** + 선거 public/data/*
금지: app.js 및 UI/배포 (Claude)

현재 상태 확인:
1. python3 build_board.py --print-stats  (또는 --no-betting)
2. race_progress_kor/usa/bundle 존재·스키마 점검
3. 스티커 검증 (Burnham / 한성숙 / 미국 midterms)
4. tier1_status.json remaining 확인

다음 작업 후보 (사람 지시 후):
- 브라질 composition→deep + TSE
- DEU/FRA governance poll 숫자
- FRA PM 신원
또는 race_progress 갱신 / 캘린더 보강

숫자·명단은 공식 소스만. LLM 발명 금지. null+reason.
```

---

## 9. 한 줄 요약

**데이터·파이프 = Grok. UI = Claude.**
19개국 골격 + KOR/USA race_progress + 가중 규칙 + 스티커는 이미 있다.
Cursor는 접었다. 신규 국가는 큐 순서대로, 사람 지시 후에만 진행.

관련: `README.md` · `LEARNING.md` · `HANDOFF_CLAUDE_ELECTIONS_UI.md` (UI만) · `HANDOFF_ANTIGRAVITY_CHINA_LIT.md` (중국 문헌 전용)
