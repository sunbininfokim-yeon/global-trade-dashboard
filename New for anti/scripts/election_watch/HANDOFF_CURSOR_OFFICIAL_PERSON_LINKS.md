# 핸드오프: 인물 이름 → 공식 홈페이지 링크 (Claude → Cursor)

작성: Claude Code · 2026-09-11
사용자 요청 원문: 정치·경제 화면에 뜨는 인물(연준 의장, 장관, 정치인 등)을 각자 공식
홈페이지·소속 기관 페이지로 연결해달라는 요청.

## 이미 처리한 것 — Cursor 작업 불필요

**미국 연방 상하원 의원**은 board에 이미 있는 `bioguideId` 하나로 바로 연결됨
(`bioguide.congress.gov/search/bio/{id}` — 의회 공식 인명 데이터베이스, 이름 슬러그
불필요). 실제 두 명(Lindsey Graham → `g000359`, Mike Johnson → `j000299`)으로 URL
패턴 확인 후 UI에 반영 완료 (`New for anti/js/elections/country-explorer/
usa-state-dashboard.js`). 주 연방 하원·상원의원 명단(`federal_delegation.house_members`,
`.senators`)에 뜨는 이름은 전부 링크됨.

**여기 아래 항목들은 우리한테 그런 안정적 ID가 없어서** 실제 공식 URL을 사람이
찾아서 채워줘야 함.

## 요청 — `official_url` 필드 추가

각 인물 객체에 `official_url` 필드 하나만 추가해주면 됨(새 매핑 파일 필요 없음,
있는 객체에 필드만 얹으면 UI가 바로 읽음):

```json
{ "office_ko": "국무장관", "name_en": "Marco A. Rubio", "party_abbr": "GOP",
  "official_url": "https://www.state.gov/secretary-of-state-marco-rubio/" }
```

### A. 미국 — `elections_board_v1.json` → `countries[USA]`

- `executive_live.core[]` (대통령·부통령·비서실장 등, 5명)
- `executive_live.cabinet[]` (내각, 21명)
- `executive_live.white_house.{assistants_to_the_president, eop_office_heads,
  deputy_chiefs_of_staff}[]` (#288로 최근 추가된 백악관 참모진)

개인별 공식 바이오 페이지가 없는 자리(백악관 실무진 다수가 그럼)는 억지로 채우지
말고, 차선으로 **소속 부처·조직의 공식 홈페이지**로 대체 가능(사용자도 이 방식
허용함: "각 부 행정부 사이트로 연동이 되거나"). 그것도 없으면 그냥
`official_url` 필드를 비워두면 됨 — UI는 필드가 없으면 그냥 링크 없이 텍스트로
표시하게 이미 짜여 있음.

### B. 그 외 추적 19개국 — 같은 구조

`executive_live.core[]` / `.cabinet[]`가 JPN·KOR·GBR·DEU·FRA·BRA·ISR·RUS 등
전 국가에 같은 모양으로 있음(예: JPN `core[0]` = `{office_ko, name_en, name_ja,
party_abbr}`). 국가 수반(총리·대통령)부터 우선순위 두면 좋겠음 — 사용자 예시가
"연준의장", "장관"이라 정부 수반·내각급이 체감 빈도 높음.

### C. 연준(Fed) — 별도 건, 아직 범위 미확정

이건 선거 모듈(`elections_board_v1.json`)이 아니라 **매크로 모니터**
(`New for anti/scripts/macro_monitor/**`, `fomc_meetings_v1.json` 등) 쪽 데이터라
내가 아직 그 코드·데이터 구조를 안 살펴봤음. 연준 의장·이사·지역 연은 총재 인명이
그쪽에 어떤 모양으로 있는지 확인한 뒤 이 문서에 이어서 정리하거나 별도 핸드오프로
낼 예정 — 지금은 이 항목만 보류로 남겨둠.

## 지켜줄 것

- 개인별 공식 URL이 진짜 없으면 그냥 비워둘 것 — 언론 기사·위키 링크로 대체하지
  말 것 (핸드오프 §3 규칙과 동일: 공식 소스 없으면 없는 대로).
- `official_url`은 순수 부가 필드라 이거 하나 때문에 `run_refresh_cycle.py
  --build-derived` 게이트(`can_start_ui`, `errors=[]`)가 깨지면 안 됨.
- 우선순위 원하면: A(미국 내각·EOP) → B(19개국 국가수반) → C(연준, 내가 범위
  확정한 뒤).
