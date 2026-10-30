# 2026-09-21 02시 예약: 운영 위원회 계층 보정 결과

## 적용 완료

운영 Supabase에서 119대 committees 613행을 백업·대조했다.
공식 `/committee/119` 목록은 pagination.count=238이나 실제 고유 배열은 236개였다.
offset=236 후속 조회 2개는 이미 받은 코드(hsif00, hsru00)였으며, 236개 상세를 각각 확인했다.
공식 고유 목록에 없는 DB 377행은 모두 부모가 있는 행으로, 이번에 삭제하거나 현역이라고 재인증하지 않았다.
과거 상세 응답의 자식 목록을 119대에 일괄 저장하던 수집 경로가 있어 별도 회기 소속 감사가 필요하다.

- 53행 변경: 부모가 없던 상원 소위원회 36개 + 기구 유형 17개.
- ssfr09 → ssfr00 포함. ID와 이름은 변경하지 않았다.
- 최상위 상임위: 하원 20, 상원 16. 상원 select 3 + special 1, 하원 select 2.
- 최상위에 남은 이름상 Subcommittee: 0개. 이는 613행 모두의 회기 소속 검증 완료를 뜻하지 않는다.
- 대상 bill_committees 195행, committee_members 168행: 전체 행 직렬화 SHA256이 전후 동일.
  대상 bill_actions 및 committee_agency_jurisdictions 연결은 각 0행으로 동일.
- 전체 committees ID 집합 및 행 수 613 유지. 즐겨찾기·구독·bills는 수정하지 않았다.
- 운영 트리거 사전 조회: committees에는 updated_at 갱신만 있었고 법안 메일 트리거는 없었다.
  법안 단계 변경이나 실제 메일 발송은 수행하지 않았다.

실행 SQL: `supabase/migrations/20260921020000_committee_hierarchy_repair.sql`.
Supabase SQL Editor 실행 결과 verified_rows=53 및 별도 REST 재조회로 적용을 확인했다.
원본 백업: `/Users/yeoninair/Documents/policy-downloads/committee-audit-20260921/` (비공개).
계획·미해결 ID 목록: `data/policy/committee-hierarchy-119-20260921.json`.

## 재발 방지

두 수집기가 공식 type / committeeTypeCode / parent를 공통 파서로 처리한다.
부분 법안 응답에 유형이 없으면 standing을 만들어 쓰지 않는다.
위원회 디렉터리는 해당 회기 목록에서 얻은 행만 상세 조회하고 부모부터 저장한다.
전체 역사에 걸친 detail.subcommittees를 현재 회기에 무조건 가져오던 경로를 제거했다.

운영 보정 53행은 raw_source._verified_hierarchy에 근거를 남겼다.
BEFORE UPDATE 트리거는 기존 수집기가 raw_source와 유형을 덮어써도 검증된 type/parent를 유지한다.
향후 공식 개편을 재검증해 수정할 때는 명시적 트랜잭션에서
`SET LOCAL app.committee_hierarchy_repair = 'on'`을 사용하고 metadata도 함께 갱신해야 한다.
이 보호는 이번 53행에 한정되며 모든 새 위원회의 정확성을 자동 보증하지 않는다.

활성 recovery checkout의 sync-congress.js는 관련 두 줄과 공통 helper만 교체했다.
sync-committees.js는 기존 버전 일치를 확인한 뒤 수정본을 반영했다.
두 파일 원본을 백업했고 프로세스는 중복 실행하거나 재시작하지 않았다.
GitHub 수집기 반영은 이 변경의 병합이 필요하다. 이전 GitHub 코드가 돌아도 보정 53행은 DB가 보호한다.

## 보존한 예외

- Joint Economic의 jjec00/jhje00/jsec00는 공식 API에도 각각 존재하며 isCurrent=true다.
  모두 joint로 교정했지만 canonical 병합은 하지 않았다. UI에서 한 기구로 보이려면 별칭·참조 감사가 먼저다.
- hzgo34(Task Force), hlqj00(Select)는 parent가 있으나 일반 Subcommittee와 다른 공식 유형이다.
  이번 보정에서는 그대로 보존했다. 특별 소위원회/태스크포스의 유형과 계층을 별도 표현할 후속 검토가 필요하다.
- hsgo16, ssap08, ssap18은 공식 type=Standing과 parent가 함께 오는 충돌이 있다.
  기존 부모/소위원회 관계를 보존했다. 일반 수집 파서는 이 경우 parent를 우선한다.
- slia00는 Congress API Other이지만 상원 공식 16+4 체계에 따라 select로 정규화했다.
  scnc00는 상원 공식 안내의 caucus로 구분했다.
- CRS와 UI, 사이트 배포는 이번 작업에서 제외했다.

## PR #340 검토 — Claude 후속

검토 시 PR은 OPEN, policy.js만 변경. DB 작업과 충돌하는 migration은 없었다.
다음 이름은 현재 정규식에 매칭되지 않는다:

| DB 이름 | PR의 검색 패턴 | 결과 |
|---|---|---|
| Aging (Special) Committee | special committee on aging | standing으로 잘못 분류 |
| Ethics (Select) Committee | select committee on ethics | standing으로 잘못 분류 |
| Intelligence (Select) Committee | select committee on intelligence | standing으로 잘못 분류 |
| Indian Affairs Committee | committee on indian affairs | standing으로 잘못 분류 |
| Intelligence (Permanent Select) Committee | permanent select committee on intelligence | standing으로 잘못 분류 |

이제 DB committee_type을 우선 사용하고 select/special을 특별 그룹, commission_or_caucus/caucus를 기타 그룹으로 연결할 것.
parent가 있는 행은 최상위 목록에서 제외하고 부모 상세에서 조회할 것.
현재 overview의 parent null 필터로 이번 orphan은 빠지지만 캐시 갱신 후 확인이 필요하다.
unknown 또는 새 유형을 무조건 standing으로 취급하지 말 것.
이름 예외 목록은 정규화된 DB 이름 fixture로 검증할 것. JEC 3코드는 삭제 없이 별칭 설계 후 표시 통합할 것.

## 검증

- 공통 파서 5개 단위 테스트(부분 응답, 부모, 유형, 원/회기 불일치, Senate 예외).
- PGlite에서 hierarchy guard 재실행/기존 수집기 덮어쓰기/명시적 보정 검증.
- 실제 613행 스냅샷으로 migration 2회, ID·법안 연결 보존, guard 검증.
- 두 수집기 node --check, git diff --check.
- 운영 SQL 결과 + 별도 REST 53행 확인 + 대상 참조 전체 행 hash 비교.

공식 출처:
https://api.congress.gov/v3/committee/119 (자격증명 없는 경로)
https://www.senate.gov/committees/
https://www.senate.gov/about/origins-foundations/committee-system.htm
https://clerk.house.gov/Help/ViewCommitteeFAQs
