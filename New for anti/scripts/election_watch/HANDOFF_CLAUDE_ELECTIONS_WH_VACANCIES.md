# HANDOFF → Claude — 백악관 공석 vs 미확인, 미기재 보좌

**날짜:** 2026-09-14  
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
| 부통령 비서실장 | **미확인, 공석 아님** | WHO 명부에 부통령실 없음. 공식 명부 미확보. 공석 선언 없음. |
| CEA 의장 | **현직 Christopher Phelan** | `whitehouse.gov/cea/` About: Chairman. 예전 UI는 2차 출처라 숨긴 것. |
| CEQ 의장 | **미확인, 공석 아님** | `whitehouse.gov/ceq/`에 의장명 없음. 공석 선언 없음. 언론 직무대행 승격 안 함. |
| ONDCP 국장 | **현직 Sara Carter** | 2026-01-06 백악관: 상원 인준. 소개 페이지가 이름을 안 적을 뿐. |
| WHMO 국장 | **미확인, 공석 아님** | 군 파견 보직. WHO 민간 급여명부 밖. 공식 국장 페이지 없음. 위키 금지. |
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
