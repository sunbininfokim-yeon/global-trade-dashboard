# HANDOFF → Grok — 선거 데이터·파이프라인 전부 (Cursor 사용량 소진)

**as_of:** 2026-08-09  
**보낸이:** Cursor (Auto) — 세션 종료 / 사용량 소진  
**받는이:** **Grok**  
**사용자:** 선빈 (Researcher)

이 문서 한 장으로 **Cursor가 맡아 오던 선거 코드·데이터·수정 권한·상태·다음 큐 전부**를 Grok에 이전한다.

---

## 1. 권한 이전 (소유 매트릭스)

### 1.1 Grok이 **수정 가능** (Cursor 이관 범위)

| 경로 | 내용 |
|------|------|
| `New for anti/scripts/election_watch/**` | 전체: extract, build, config, calendars, profiles, LEARNING, schemas |
| `New for anti/public/data/elections_board_v1.json` | 보드 빌드 산출물 |
| `New for anti/public/data/race_progress_*.json` | 중간 집계 |
| `New for anti/public/data/race_aggregation_compare_v1.json` | 가중 비교 |
| `New for anti/public/data/race_progress_preview.html` | 정적 UX 미리보기 (대시보드 아님) |
| `New for anti/public/data/elections_calendar_master_v1.json` | 마스터 캘린더 |
| `New for anti/public/data/invest_lens_elections.json` | Invest Lens 2차 소스 |
| (같은 이름이 `scripts/election_watch/config/extracted/` 에도 있으면) 둘 다 갱신 | extracted 정본 → public 복사 패턴 유지 |

**운영 루트 (자주 쓰는 cwd):**
```text
…/New for anti/New for anti/scripts/election_watch
```
(로컬 clone 경로에 공백: `Documents/New for anti` — 반드시 따옴표.)

### 1.2 Grok이 **수정 금지** (Claude Code 단독)

| 경로 | 이유 |
|------|------|
| `New for anti/app.js` | UI 소유 Claude — 충돌·롤백 사고 (2026-08-05) |
| `New for anti/style.css` | 동일 |
| `New for anti/index.html` | 동일 |
| `New for anti/data.js` | 동일 |
| `New for anti/shipping.js` | 동일 |
| `_worker.js`, `wrangler.jsonc` | 배포 Claude |
| `.github/workflows/**` | 배포 Claude |
| `docs/ops/OWNERS.md`, `docs/ops/TASKS.md` | Claude/ops — claim 없이 대규모 수정 금지 |
| `CLAUDE.md` | Claude |

**UI가 필요하면:** `HANDOFF_CLAUDE_ELECTIONS_UI.md` 만 넘기고 Grok은 **데이터 계약 유지**만 한다.

### 1.3 yield_model (별 트랙 — 이번 선거 핸드오프와 무관)

국가 스캐폴드/수확 예측은:
`New for anti/scripts/yield_model/**` + `public/data/*_yield_forecast.json`  
규칙은 `DATA_LAYOUT.md` · `MODEL_MANIFEST.md`.  
**Grok이 선거만 받을 거면 yield_model은 건드리지 말 것.**

### 1.4 브랜치 / 커밋

- `main` 직접 push 금지 · force-push 금지  
- 커밋은 **선빈이 요청할 때만**  
- 브랜치 이름 예: `grok/election-<주제>` (기존: `cursor/…`, `claude/ui-…`)  
- Claude `claude/*` 브랜치 checkout **질문 없이 금지** (사용자 규칙)

---

## 2. 제품 규칙 (깨면 안 됨)

1. **거버넌스 지지율만** (국정/총리 직무). 전국 **대선 경마형 평균 배제**.  
2. Null 표기: **`없음`** = 해당 없음 · **`불명`** = 아직 모름. 가짜 날짜 ** invent 금지**.  
3. 전당·당대표: 제품 seed 정책상 경쟁 선거국 **always_include** (미국 예외: 당대표 선거 없음 → 원내).  
4. 지도 색: `config/spectrum_rules.json` — 수장당 spectrum.  
5. 정확성 스티커 (UI·JSON 모두):

| 키 | 값 |
|----|-----|
| 영국 총리 | **Andy Burnham** (2026-07-20~). Starmer 현직 금지 |
| 한국 대통령 | **이재명** (2025-06-04~) |
| 한국 총리 | **한성숙** (2026-07-01~) |
| 미국 2026 | **중간선거 프라이머리** (대선 경선은 **2028**). 선거인단 식으로 주 점수 합산 **금지** |
| 한국 민주 전당 누적 | 권리당원 **1순위 중간** · 최종은 **70% 당원/대의원 + 30% 여론** · TK·경남 당원 **+5%** → **중간 ≠ 최종** |

---

## 3. 파이프라인 (명령)

```bash
cd "/path/to/New for anti/New for anti/scripts/election_watch"

# 보드 재생성 (배팅 API 생략 권장)
python3 build_board.py --no-betting --print-stats
# → public/data/elections_board_v1.json

# 국가별 extract (네트워크 필요할 수 있음)
python3 -m election_watch.extract_rosters      # 미·일 등
python3 -m election_watch.extract_gbr_isr      # 영국·이스라엘
python3 -m election_watch.extract_kor          # 한국
python3 -m election_watch.extract_tier2_fill   # 독일·프랑스·브라질 composition
python3 -m election_watch.build_factions
python3 -m election_watch.build_china_pla_bios
python3 -m election_watch.build_race_progress  # 미국 프라이머리 진척 재생성 (한국 스냅 유지)
```

**흐름:**
```
profiles + calendars/*.json + extracted/*.json
        ↓
   build_board.py
        ↓
public/data/elections_board_v1.json
  (한국·미국 행에 race_progress 부착)
```

중간 진척 전용:
```
race_progress_kor_v1 / usa_v1 → bundle → (보드 재빌드 시 부착)
aggregation: 가중 규칙 메타
```

문서:
- `README.md` — 개요  
- `LEARNING.md` — 문서 추출형 학습  
- `HANDOFF_CLAUDE_ELECTIONS_UI.md` — UI P0 (데이터 freeze 가정; Grok이 데이터 재개하면 Claude에 “계약 버전 올림”만 통지)  
- `config/tier1_status.json` · `config/extracted/learning_analysis_v1.json` — 깊이·다음 큐  

---

## 4. 현재 데이터 상태 (동결 스냅 · 2026-08-08~09)

### 4.1 보드 커버리지 (~15국)

| 깊이 | 국가 (풀네임) |
|------|----------------|
| deep | 미국, 일본, 영국, 이스라엘, **한국** |
| composition | 독일, 프랑스, 브라질 |
| thin | 러시아 (두마 light, 9월 선거 후 승급 대기) |
| scaffold | 대만, 튀르키예, 인도 |
| leadership_doc (비선거) | 중국(PLA), 사우디, 아랍에미리트 |
| 의도적 미작성 | 이란 |

### 4.2 race_progress (진행 중 중간 집계)

| 국가 | 모드 | 요지 |
|------|------|------|
| 한국 | 전당 순회 중간 | 김민석 누적 선두(중간) · 최종 8/17 · **가중 혼합** |
| 미국 | 주별 중간 프라이머리 | 주 일정 누적 + 클릭 시 승자 · **관할 독립**, UI만 1주=1 진척 |

파일:
- `public/data/race_progress_kor_v1.json`
- `public/data/race_progress_usa_v1.json`
- `public/data/race_progress_bundle_v1.json` (+ aggregation_compare)
- `public/data/race_aggregation_compare_v1.json`
- `public/data/race_progress_preview.html`

미국 승자 파서: The Midterm Project 텍스트 → **다음 House `XX-##` 코드로 주 태깅**.  
원본 스크랩 보관: `scripts/election_watch/raw/usa/themidtermproject_results_2026-08-08.txt`

### 4.3 기타 public 산출

- `elections_calendar_master_v1.json`
- `invest_lens_elections.json` (invest-lens.io; 일본 총선 날짜 IL과 내부 불일치 있음 — 덮어쓰지 말 것)

### 4.4 보드에 이미 붙은 필드

- `countries[].race_progress` — 한국·미국  
- `summary.countries_with_race_progress`  
- 의회 `legislature_live`, 한국 `party_leadership_live` 등  

---

## 5. 코드 진입점 (파일)

| 파일 | 역할 |
|------|------|
| `build_board.py` | 보드 조립 · 한국/미국 `race_progress` 로드 |
| `election_watch/extract_kor.py` | 한국 의회·지방·전당·갤럽 등 |
| `election_watch/extract_gbr_isr.py` | 영국·이스라엘 |
| `election_watch/extract_tier2_fill.py` | 독일·프랑스·브라질·러시아 light |
| `election_watch/extract_rosters.py` | 미국·일본 roster |
| `election_watch/build_race_progress.py` | 미국 unit 재생성 |
| `election_watch/betting.py` | Polymarket (보드 `--no-betting` 권장 시 스킵) |
| `config/country_seed.json` | 시드 이벤트 |
| `config/calendars/{iso}_2026.json` | 연도 일정 **정본** |
| `config/profiles/{iso}.json` | 체제·수장·모드 |
| `config/extracted/*` | extract 출력 정본 |
| `schemas/elections_board_v1.schema.json` | 보드 스키마 |

---

## 6. 나중에 조사 큐 (실행은 Grok·사람 판단)

**사용량 위해 일괄 딥 금지. 우선순위:**

1. **브라질** — 2026-10-04 대선·총선 · 국정 지지율 + TSE 좌석 승급  
2. **독일** — 9월 주의회 3 · 총리 지지율  
3. **프랑스** — 총리 신원 + 대통령 직무 지지  
4. **대만** — 입법위 deep (한국 템플릿)  
5. **인도** — 주 선거 일정 팩트만  
6. **튀르키예** — YSK 발표 시에만  
7. **사우디·아랍에미리트** — 브리프 유지, 신규 조사 불필요  

UI 패널은 Claude P0 (`HANDOFF_CLAUDE_ELECTIONS_UI.md`). Grok은 데이터 계약 깨지 말 것.

---

## 7. 작업 중 사용량 통제 (Grok 권장)

1. 세션당 **한 국가 또는 한 스크립트**.  
2. `build_board.py` 전후 diff만 확인 — 전체 JSON 컨텍스트 덤프 지양.  
3. UI·deploy 경로 열지 않기.  
4. 날짜·의석 **출처 URL + grade** 남기기 (`official` > `media_cross_check` > `aggregator` > `approximate`).  
5. 한국/미국 race_progress 갱신 시 **aggregation 블록 유지**.  

---

## 8. Grok 첫 프롬프트 (복붙)

```
너는 Grok이다. 레포 global-trade-dashboard의 선거 데이터·파이프라인 소유를 Cursor에서 이관받았다.

필수 읽기 (순서):
1) New for anti/scripts/election_watch/HANDOFF_GROK.md  (이 문서)
2) New for anti/scripts/election_watch/README.md
3) New for anti/scripts/election_watch/HANDOFF_CLAUDE_ELECTIONS_UI.md  (UI 경계만)

수정 가능: scripts/election_watch/** 과 위 public/data 선거 JSON/HTML
수정 금지: app.js, style.css, index.html, data.js, shipping.js, _worker.js, wrangler, workflows

규칙: 없음/불명, 경마형 여론 금지, 영국=Andy Burnham, 한국 총리=한성숙,
미국 2026=중간 프라이머리(전국 가중 점수 아님), 한국 전당=70/30 가중.

첫 작업은 사람 지시 전까지: status 확인만
  cd "…/scripts/election_watch" && python3 build_board.py --no-betting --print-stats
커밋/푸시는 사람 요청 시에만.
```

---

## 9. Cursor 측 종료 메모

- Cursor는 이 선거 세션 **권한·작업 중단**.  
- 미커밋 변경이 로컬에 남아 있을 수 있음 → 선빈이 `git status`로 확인 후 Grok/사람 PR.  
- Claude UI 티켓은 별도; 데이터 freeze 문구는 Grok이 보드를 다시 쓰는 순간 **버전 올려 통지**하면 됨.

---

## 10. 한 줄

**Grok = `election_watch` 코드 + 선거 public 데이터 전권. Claude = UI/배포. Cursor = 사용 종료.**
