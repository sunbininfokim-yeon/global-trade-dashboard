# HANDOFF → Claude Code — 선거 창 UI (사용량 통제)

> 이 문서는 2026-08-08 P0 범위 기록이다. 현재 UI 데이터 계약과 국가별 화면 매핑은 `HANDOFF_CLAUDE_ELECTIONS_UI_V2.md`를 따른다.

**as_of:** 2026-08-08  
**상태:** 데이터·계약 **동결** / Cursor측 신규 국가 조사·extract **중단**  
**목표:** UI만 올리고, Claude 토큰·왕복을 **한 티켓·한 PR**로 제한

---

## 0. 사용량 통제 (사람·Claude 공통)

| 규칙 | 이유 |
|------|------|
| **이 문서 + 아래 JSON 경로만 읽기** | `scripts/election_watch/**` 전량 탐색 금지 |
| **국가 추가·캘린더 보강 안 함** | Cursor 재개 전까지 freeze |
| **앱 UI만** (`app.js` / `style.css` / `index.html` / 필요 시 `data.js`) | 배포·wrangler 이번 티켓 밖 |
| **미리보기 HTML을 레퍼런스로 복제 가능** | 로직 재설계·재파싱 금지 |
| **1 PR = P0만** 통과 후 P1 | 범위 팽창 방지 |
| Cursor: UI 탭 **닫기** / 같은 레포 Agent **중지** | 08-05 `app.js` 롤백 재발 방지 |

**금지 (Claude·Cursor 모두):**  
`config/calendars/**` 추측 날짜 · 신규 국가 조사 · IRN 데이터 임의 수정 · `main` 직접 push · force-push

---

## 1. 이미 준비된 산출물 (읽기 전용 계약)

경로 기준: 레포 `New for anti/` (앱 루트).

| 파일 | 역할 |
|------|------|
| `public/data/elections_board_v1.json` | 국가 보드. `countries[]` · `summary` · 뉴스/배팅 |
| `public/data/race_progress_bundle_v1.json` | 진행 중 레이스 합본 + `aggregation_compare` |
| `public/data/race_progress_kor_v1.json` | 한국 민주당 전당 **중간** 집계 |
| `public/data/race_progress_usa_v1.json` | 미국 2026 **주별 프라이머리** 진척 + 주 클릭 승자 |
| `public/data/race_aggregation_compare_v1.json` | 가중/비중이 다른지 비교 표 |
| `public/data/race_progress_preview.html` | **UX 스케치** (정적 fetch). 패널 동작 레퍼런스 |
| `public/data/elections_calendar_master_v1.json` | 전체 캘린더 (P1 이후) |
| `scripts/election_watch/README.md` | 파이프·계약 요약 |

보드에 이미 부착:

- 한국·미국 행: `countries[i].race_progress` (= 위 Kor/Usa 문서와 동일 스키마)
- `summary.countries_with_race_progress` = 2

스키마 검증 도구가 있으면 그걸로만 확인. 빌드 재실행은 불필요(데이터 freeze).

---

## 2. 제품 의도 (UI에 넣을 말)

1. **올해 어디** 선거·당대표 있는지 (보드 일정)
2. **진행 중**이면 중간 데이터  
   - **한국:** 권역 순회 누적 + 클릭 시 권역·%  
   - **미국:** 주 롤링 타임라인 + 클릭 시 그 주 공천 승자  
3. **가중 규칙 배지** (필수 — 숫자만 보면 오해)  
   - 한국 전당: **최종 70% 당원·대의원 + 30% 여론**, 지역 +5% 등 · **지금 누적 ≠ 최종**  
   - 미국 중간 프라이머리: **관할 독립**, 40/51은 **진척 카운트**이지 전국 가중 점수 아님  

거버넌스(국정) 지지율만. 전국 대선 경마 평균 금지(기존 제품 규칙).

---

## 3. 구현 범위 (단계 — 한 번에 하나만)

### P0 (이번 티켓 · 이것만)

**「선거」패널 1개** — 홈/기존 네비에 진입점 1곳.

1. `elections_board_v1.json` fetch (실패 시 빈 상태 문구)
2. 국가 리스트 또는 필터: **진행 중 / 다가옴 / 완료** (있으면 `events`·`calendar` 필드 사용, 없으면 `race_progress.status`)
3. **진행 중 race_progress** 카드  
   - 한국: 선두·격차·권역 리스트 → 클릭 상세  
   - 미국: 완료 주 수 → 주 리스트 → 클릭 시 상원/주지사/승자  
4. `aggregation` 배지 (모델 라벨 + 주의 문장)  
5. 미리보기 HTML과 **동등한 정보 위계**면 충분 (지도 불필요)

**완료 정의:** 로컬 정적 서버에서 한국·미국 드릴다운 클릭 가능 + 가중 배지 표시.  
앱 전체 리디자인·deck.gl 연동 **안 함**.

### P1 (다음 PR · 사용자가 열어줄 때까지 대기)

- 15개국 보드 카드: 수장 · 스펙트럼 · 다가오는 일정 D-day  
- 캘린더 마스터 얇은 링크  
- 통치 지지율 숫자(이미 `governance_polls` 있는 국가만)

### P2 (나중)

- 예측시장 스트립  
- 지도 색연동  
- CI/`elections_board` cron (workflow = 별 claim)

---

## 4. 데이터 필드 치트시트 (더 읽지 말 것)

### `race_progress` (공통)

```
iso3, status, mode, as_of
race.label_ko, race.final_date | race.general_date
aggregation.model_id
aggregation.model_label_ko
aggregation.summary_ko
aggregation.interim_display.user_caution_ko
aggregation.like_usa_equal_units   // true=진척 동등 카운트, false=비중 합산
cumulative.{…}
units[]  // 클릭 대상
```

### 한국 units

`label_ko, date, status, winner, results[{name_ko,pct,votes}], subunits?`

### 미국 units

`id, name_ko, date, status, headline, contests_statewide[], contests[]`  
`contests: { office_kind, party, winner }`

### 보드 행 (최소)

`iso3, name_ko, head, map_spectrum, events_this_year, race_progress?`

`null`/`없음`/`불명` 표기 정책: 빈 칸 만들지 말고 문자열 유지.

---

## 5. 정확성 스티커 (UI 카피)

| 키 | 표시 |
|----|------|
| 영국 총리 | **Andy Burnham** (2026-07-20~). Starmer 현직 금지 |
| 한국 대통령 | 이재명 · 총리 **한성숙** |
| 미국 2026 | **중간선거 프라이머리** (대선 경선 2028). 선거인단 점수 표현 금지 |
| 한국 전당 누적 | “권리당원 1순위 중간 · 최종 70/30 전” |

---

## 6. Claude에게 붙일 프롬프트 (복붙)

```
작업: 선거 패널 UI P0만. 데이터 조사·재추출 금지.

읽을 것 (이것만):
- New for anti/scripts/election_watch/HANDOFF_CLAUDE_ELECTIONS_UI.md
- New for anti/public/data/elections_board_v1.json (countries[].race_progress)
- New for anti/public/data/race_progress_preview.html
- New for anti/public/data/race_progress_bundle_v1.json (aggregation만 참고)

수정 허용: app.js, style.css, index.html (필요 시 data.js만)
수정 금지: scripts/election_watch/**, public/data/*.json (데이터 freeze), wrangler, workflows

P0:
1) 네비/진입 → 선거 패널
2) board fetch
3) 한국·미국 race_progress 누적 + 클릭 드릴다운
4) aggregation 배지 (가중 vs 진척-only)
완료 후: 로컬 스모크 3줄 + diff 요약. P1 제안만 적고 구현하지 말 것.

브랜치: claude/ui-elections-panel-p0
```

---

## 7. 스모크 (Claude 완료 시)

```bash
# public/data 서빙 또는 앱 정적 서버 기준
# 1) Network: elections_board_v1.json 200
# 2) 패널에 “김민석” 또는 누적 % 보임
# 3) 미국 주 클릭 시 party + winner 문자열
# 4) 배지에 70/30 또는 “중간≠최종” / “전국 점수 아님” 중 하나
```

---

## 8. Cursor 동결 (이 핸드오프 이후)

- election_watch **신규 국가 조사 안 함** (브라질·독일 등 큐는 문서에만 존재)
- 데이터 갱신이 필요할 때만 사람 지시 후 `build_board.py` / race_progress 재생성
- UI PR 중에는 Cursor Agent 레포 부착 금지

### 나중에 재개할 조사 큐 (실행 금지 · 메모만)

1. 브라질 (10월 대선) 2. 독일 (9월 주의회 + 총리 지지) 3. 프랑스 (총리·지지)  
4. 대만 입법위 5. 인도 주 캘린더 6. 튀르키예(일정 발표 시)  
3급 UAE: 조사 불필요. 사우디·이란은 2급 지정학 특수형으로 권력·안보·에너지 카드만 확장.

---

## 9. 한 줄 요약

데이터는 됐다. Claude는 **보드 + race_progress 미리보기 동작만 패널에 이식**하고, **JSON·조사·다른 국가는 만지지 않는다.**
