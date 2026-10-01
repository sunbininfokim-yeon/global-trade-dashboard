# HANDOFF → Claude — 백악관 공석 vs 미확인, 미기재 보좌

**날짜:** 2026-09-14 (2026-10-01 보도 기준 등급 추가)  
**요청:** 선빈. UI의 「명단 수집 예정」을 공석과 확인 못 한 현직으로 나누고, 직함에 주제가 없는 5명을 분석한다.

`app.js`에 인명 하드코딩하지 말 것. `office_status.vacant`가 true일 때만 「공석」.

## 읽을 경로

`countries[USA].executive_live.white_house.office_status`

각 `offices[]`: `vacant`, `display`, `ui_ko`, `name_en`, `note_ko`.

| display | UI |
|---------|----|
| `show_name` | 이름 |
| `show_name_with_as_of` | 이름 + as_of |
| `unconfirmed_not_vacant` | **미확인 (공석 아님)** — 「명단 수집 예정」 금지 |
| `show_vacant` | **공석** |

## 선빈이 붙여 넣은 화면 기준

| 칸 | 판정 | 이유 |
|----|------|------|
| 부통령 비서실장 | **Nick Luna · 보도 기준** (2026-10-01 갱신) | 공식 부통령실 명부 없음. Federal News Network 2026-08-28(Leadership Connect 인사 기록)·Punchbowl 2026-06-16. 전임 Jacob B. Reses 2026-08 퇴임. |
| CEA 의장 | **현직 Christopher Phelan** | `whitehouse.gov/cea/` About: Chairman. 예전 UI는 2차 출처라 숨긴 것. |
| CEQ 의장 | **Rachael McNitt · 직무대행 · 보도 기준** (2026-10-01 갱신) | Katherine Scarlett(2025-09-18 인준, 백악관 발표) 2026-07-07 퇴임. The Hill·E&E News가 정부 관계자 인용으로 McNitt 직무대행 보도. CEQ 공식 직원명단은 2026-04판이 마지막. |
| ONDCP 국장 | **현직 Sara Carter** | 2026-01-06 백악관: 상원 인준. 소개 페이지가 이름을 안 적을 뿐. |
| WHMO 국장 | **미확인, 공석 아님** | WHO 급여명부 밖. 공식 국장 페이지 없음. 2025 이후 임명 보도를 신뢰 매체에서 못 찾음. 위키백과 표의 무출처 이름 금지. |

### 보도 기준 (`source_grade: "reported_reliable"`)

공식 원문에 이름이 없는 자리를 서로 다른 신뢰 매체 2곳 이상(하나는 정부 관계자 확인 인용)이
같은 이름으로 전할 때만 채운다. 2026-10-01 선빈 요청으로 도입.

- `office_status.offices[].name_en` 은 **공식 이름 전용**이라 계속 `null`. 이름은 `reported.name_en`.
- `display` 는 `unconfirmed_not_vacant` 그대로, `ui_ko` 가 "Nick Luna · 보도 기준" 식이라 지금 UI 코드 그대로 표시된다.
- `core.vp_chief_of_staff` 와 `eop_office_heads[ceq]` 는 `name_en` 에 이름, `status` 에 "보도 기준", `source_grade: reported_reliable`, `reported.sources[]`(org·date·url·claim).
- UI에서 출처 링크를 보이려면 `reported.sources[].url` 을 쓰면 된다. 공식 링크(`official_url`)로 섞지 말 것.
- 공식 원문이 이름을 적으면 파이프라인이 보도 기준을 지운다(CEQ는 `ceq_names_chair`).
| PIAB 의장 | **Devin Gerald Nunes (2025-02-11 임명)** | 백악관 임명 발표. 2026 명부 갱신 없음. 공석 선언 없음. |
| PCLOB **의장** | **공석** | pclob.gov: 전 의장 임기 2025-01 종료. 2026 보고서 Chair is Vacant. 위원 Beth A. Williams는 있음. |

## 미기재 5명 — 담당 없는 빈자리가 아님

전원 WHO 2026-07-01 급여명부에 **현직으로 올라 있다.** 직함에 FOR/TO THE 포트폴리오가 없을 뿐.

| 이름 | 급여명부 | 분류 |
|------|----------|------|
| Jacalynne B. Klopp | DAP and Advisor, $175k, EMPLOYEE | **정무특보(부보좌관급)**. 담당만 직함에 없음. |
| Tracy L. Johnson | Senior Advisor, $0, EMPLOYEE | 무급/겸임 Senior Advisor. 2025에도 동일. 담당 미기재. |
| Peter M. Lake | Senior Advisor, DETAILEE $197,200 | 타 기관 파견. 정무특보로 단정하지 않음. |
| Jason D. Manion | Senior Advisor, DETAILEE $134,839 | 파견. 7/14 양형위 지명이 있으나 그때도 WH 담당은 직함에 없음. |
| Meghan I. Selip | Senior Advisor, EMPLOYEE $110,500 | 실무 Senior Advisor. ATP/정무특보 급 아님. |

경로: `white_house.topical_advisors.unscoped_senior_advisors[]` 의 `kind`, `kind_ko`, `vacant: false`.  
바이오·링크드인으로 담당을 추정해 채우지 말 것.

Sacks(AI·암호화폐)는 이 5명이 아니라 `members` 의 `ai_crypto`다.
