# HANDOFF → Claude — 미국 의회 임원 카드 (원목·사무총장·경위총감 등)

**날짜:** 2026-10-01  
**요청:** 선빈. 원내 목사(원목) 등 의회 주요 인사를 카드로 올린다.

`app.js`에 인명 하드코딩 금지. 카드는 보드에서 읽는다.

## 읽을 경로

`countries[USA].ui_ready.congress.officer_cards`

- `house[]` 5장: 사무총장(Clerk), 경위총감(Sergeant at Arms), 행정최고책임자(CAO), 원목(Chaplain), 의사규칙관(Parliamentarian)
- `senate[]` 7장: 임시의장(President pro tempore), 사무총장(Secretary), 경위총감, 원목, 의사규칙관, 다수당·소수당 원내사무관(party secretaries)

카드 필드:

| 필드 | 뜻 |
|---|---|
| `office_ko` / `office_en` | 직책 |
| `name_en` | 공식 페이지 이름. 없으면 `null` + `ui_ko: "미확인 (공석 아님)"` |
| `role_ko` | 직책 한 줄 설명 |
| `kind` | `elected_officer` / `nonpartisan_official` / `party_officer` / `constitutional_officer` |
| `since`, `since_year` | 취임일(있을 때만) |
| `appointment_ko` | "본회의 선출" / "임명 (직무 수행)" — 원문에 적힌 경우만 |
| `denomination` | 원목 교단 |
| `predecessor_en` | 같은 회기 중 교체된 경우 전임 |
| `source.url` | 공식 출처 링크(이름 링크로 쓰면 된다) |
| `confirmations[]` | 교차 확인 (원목: 의회의사록 개회 기도 날짜·링크) |
| `stale` | true면 이번 회차에 원문을 못 받아 직전 값을 유지한 것 |

## 2026-10-01 값

| 원 | 직책 | 이름 | 비고 |
|---|---|---|---|
| 하원 | 사무총장 | Kevin F. McCumber | 2025-01-03 |
| 하원 | 경위총감 | William McFarland | 2025-01-03 |
| 하원 | 행정최고책임자 | **Anne Dressendorfer Binsted** | **2025-12-31 임명. 전임 Catherine Szpindor** |
| 하원 | 원목 | Margaret Grun Kibben (장로교) | 의사록 2026-09-24 개회 기도 |
| 하원 | 의사규칙관 | Jason Smith | |
| 상원 | 임시의장 | Chuck Grassley (R-IA) | |
| 상원 | 사무총장 | Jackie Barber | |
| 상원 | 경위총감 | Jennifer A. Hemingway | |
| 상원 | 원목 | Barry C. Black (재림교) | 2003-07-07~, 의사록 2026-09-28 개회 기도 |
| 상원 | 의사규칙관 | Elizabeth MacDonough | |
| 상원 | 다수당 원내사무관 | Robert Duncan | 2020~ |
| 상원 | 소수당 원내사무관 | Gary Myrick | 2011~ |

## 출처와 주의

- 하원: history.house.gov 역대 임원표 마지막 행, chaplain.house.gov 하단 연락처, Clerk MemberData.xml.
  chaplain.house.gov 본문 인사말은 전임 Patrick J. Conroy 명의로 남아 있다 — 하단 연락처가 현직.
- 상원: senate.gov 4개 페이지. 이번 값은 로컬망 403 때문에 Cursor WebFetch로 받았다(`source.fetched_via: cursor_webfetch`).
  GitHub Actions(미국 IP)에서는 `--fetch`가 직접 받는다.
- 의회의사록: govinfo API. `DATA_GOV_API_KEY` 시크릿이 없으면 `DEMO_KEY`(시간당 제한)로 내려간다.

## 자동화

`ci/run_usa_eop_monthly.sh` 에 `extract_usa_congress_officers --fetch` 를 붙였다. 매월 EOP 갱신과 같이 돈다.
`ci/elections_eop_monthly.yml` 은 `usa_congress_officers.json` 을 커밋하고 `DATA_GOV_API_KEY` 시크릿을 넘긴다 —
`.github/workflows/` 복사는 Claude 몫.
