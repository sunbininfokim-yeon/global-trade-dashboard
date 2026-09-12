# HANDOFF → Claude — 미국 백악관 주제별 보좌관

**날짜:** 2026-09-12  
**소유:** 데이터·추출 = Cursor (`scripts/election_watch/**`) · UI = Claude  
**요청:** 선빈. 국가안보보좌관처럼 **담당 주제가 직함에 적힌** 보좌관·특보·차르·특사·신앙 라인을 보드에 올린다.

이 PR은 데이터를 `executive_live`에 **미리 조인**한다. UI 카드는 아직 없다. `app.js`에 국가·인명 하드코딩하지 말 것.

## 읽을 경로

보드 JSON:

`countries[USA].executive_live.white_house.topical_advisors`

스키마 `usa_wh_topical_advisors_v1`.

| 필드 | 용도 |
|------|------|
| `payroll_as_of` | WHO 급여명부 기준일 (현재 `2026-07-01`) |
| `inclusion_ko` / `exclusion_ko` | 넣는 것 / 빼는 것 |
| `counts.by_domain` | 주제별 인원 |
| `members[]` | 주제별 보좌관 |
| `unscoped_senior_advisors[]` | 직함에 주제가 없는 Senior Advisor. **members와 섞지 말 것** |

`members[]` 필드: `id`, `domain`, `domain_ko`, `office_en`(급여명부 직함 원문), `name_en`, `rank`, `wh_salary_usd`, `payroll_status`, `source`.

정본 추출물: `scripts/election_watch/config/extracted/usa_wh_topical_advisors.json`  
같은 객체가 `usa_eop.json#topical_advisors` 와 `tier12_executives.json#countries.USA.white_house.topical_advisors` 에도 있다.

기존 UI가 읽는 `executive_live.core` + `cabinet` 은 그대로다. 국실장(OMB·ONDCP·CEA·CEQ·OSTP)은 `white_house.eop_office_heads` / cabinet 쪽이며 **이 목록이 아니다**.

## 넣는 것 (2026-07-01 WHO PDF)

직함에 포트폴리오가 있는 사람만. 이름은 PDF에 있는 그대로다.

- 국가안보: Marco A. Rubio (NSA)
- 국토안보: Stephen Miller (Homeland Security Advisor)
- 국경 차르: Thomas D. Homan
- 사면 차르: Alice M. Johnson
- 평화 특사: Steven C. Witkoff
- 우크라이나 부특사: John P. Coale
- 무역·제조: Peter K. Navarro, Danielle C. Fumagalli, Luke M. Garoufalis
- 국제경제: Raymond E. Cox
- 경제정책(ATP만): Kevin A. Hassett
- 정책(ATP): Walker B. Barrett
- 연대·연합: Lynne M. Patton
- 신앙: Paula M. White, Jennifer S. Korn, Madeline A. Seaman  
  PDF에 직함 **Pastor는 없다**. White는 `Senior Advisor to the White House Faith Office`.
- 유대인 아웃리치: Martin J. Marks
- 디지털자산 자문위 사무: Patrick J. Witt, Harry Y. Jung

## 빼는 것

- OMB / ONDCP / CEA / CEQ / OSTP 국실장
- NEC·DPC·NEDC **실장 전용** 직함 (Agen NEDC, Haley DPC). Hassett은 ATP for Economic Policy 겸임이라 members에 있다.
- 일반 `Policy Advisor` / `Senior Policy Advisor` / `Domestic Policy Advisor` 수십 명
- 대변·기록·기술·의회 연락·Associate Counsel
- `unscoped_senior_advisors`: Tracy L. Johnson, Peter M. Lake, Jason D. Manion, Meghan I. Selip, Jacalynne B. Klopp (`DAP and Advisor`)

클라이언트에서 다른 JSON과 조인하거나 직함을 추정해 채우지 말 것.

## UI 제안 (선택)

주제별 카드 또는 `white_house` 접기 목록에서 `members`를 `domain_ko`로 묶고, 직함은 `office_en` 원문을 보여 주면 된다. `unscoped_senior_advisors`는 따로 “담당 미기재” 각주.

월간 갱신은 기존 `extract_usa_eop` 한 번이면 된다. YAML을 `.github/workflows/`로 이미 복사했다면 추가 복사는 필요 없고, `ci/elections_eop_monthly.yml`의 git add 목록만 다음 복사 때 맞추면 된다.
