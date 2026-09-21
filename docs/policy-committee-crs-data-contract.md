# 위원회·CRS 분류 DB 계약 및 Claude UI 인수인계

작성: 2026-09-20 / 기준 checkout: PR #339, c11ecd78.
범위: DB 구조·감사 결과·수정 설계 문서. 이 커밋은 운영 DB, 수집기, API, UI를 변경하지 않는다.
운영 관측은 2026-09-20 읽기 전용 조회 시점의 스냅샷이다. 적용 전 재조회한다.

## 1. 핵심 결론

- 하원 상임위 20개, 상원 상임위 16개를 기준으로 한다. 특별/선정위원회, 소위원회, 기타 기구를 같은 상임위 목록에 섞지 않는다.
- 상원 특별/선정위원회 4개는 Aging, Ethics, Intelligence, Indian Affairs이다.
- 합동위원회는 Economic, Library, Printing, Taxation 4개다. Helsinki Commission, Congressional-Executive Commission on China, US-China Economic and Security Review Commission은 기타 기구로 구분한다.
- 하원 Permanent Select Intelligence 및 중국 관련 Select Committee는 별도 유형이다. Tom Lantos Human Rights Commission 역시 상임위원회가 아니다.
- CRS Policy Areas는 공식 32개다. 현 DB의 31개에는 `Social Sciences and History`가 빠져 있다.
- 위원회는 공식 심사 관계, CRS 분야는 주된 정책 주제, 임베딩은 의미 유사성이다. AI 검색 결과로 공식 회부 관계나 CRS 분류를 덮어쓰지 않는다.

공식 근거:
- https://clerk.house.gov/Help/ViewCommitteeFAQs
- https://www.house.gov/committees
- https://www.senate.gov/about/origins-foundations/committee-system.htm
- https://www.senate.gov/committees/
- https://www.foreign.senate.gov/about/subcommittees
- https://www.congress.gov/help/field-values/policy-area

CRS는 공식 원문 공개 후 법안/결의안의 주된 내용을 나타내는 분야 하나를 배정한다.
내용이 크게 바뀌면 분야도 변경될 수 있다. 아직 미배정인 법안은 미분류로 보존한다.
32개는 법안용 Policy Areas의 수이며 CRS 보고서 자체의 주제 분류와 혼동하지 않는다.

## 2. 현재 저장 구조

아래는 이 checkout의 schema.sql 및 수집 코드 기준이다. 운영 제약·함수의 전체 일치를 보증하지 않는다.
실제 반영 전 누적 migrations와 운영 pg_catalog를 비교해야 한다.

| 테이블 | 핵심 컬럼 / 키 | 역할 |
|---|---|---|
| committees | committee_id PK; congress_number, committee_code, chamber, committee_type, parent_committee_id FK, name, official_url, raw_source | 의회 회기별 위원회 정체성과 계층 |
| bill_committees | (bill_id, committee_id) 복합 PK/FK; activity_names, first_referred_at, last_activity_at, raw_source | 법안↔위원회 다대다 공식 활동 연결 |
| bills | bill_id PK; policy_area_id FK | 법안과 단일 주 정책분야 연결 |
| policy_areas | policy_area_id PK; name UNIQUE; source, source_url, active | 공식 정책분야 사전 |
| legislative_subjects / bill_subjects | subject_id / (bill_id, subject_id) | 주 정책분야보다 세부적인 다중 주제 태그 |
| bill_actions | committee_id FK(nullable), action_text, action_date, normalized_stage | 실제 단계 판단의 근거 이력 |
| committee_members / committee_agency_jurisdictions | committee_id 참조 | 위원회 인적 구성·기관 관할 연결 |

위원회 ID 생성 규칙은 `{congress}-{chamber}-{committeeCode}`이다.
`committees_source_identity_uidx`는 `(coalesce(congress_number,0), chamber, committee_code)`를 unique로 제한한다.
이 제약은 **서로 다른 코드가 같은 기구를 가리키는 경우**까지 제거하지 않는다.
`committee_type`은 현재 schema.sql에서 자유 text이고, parent FK는 ON DELETE SET NULL이다.
따라서 parent가 null이라는 이유만으로 상임위원회 또는 정상적인 최상위 기구라 판단하면 안 된다.

관계: `policy_areas ← bills → bill_committees → committees → parent committees`.
법안은 복수 위원회에 회부될 수 있으므로 위원회별 법안 수 합계는 전체 고유 법안 수와 다를 수 있다.

## 3. 확인된 오류와 코드상의 원인

### 소위원회 계층 누락

DB `119-senate-ssfr09`는 `committee_type=standing`, `parent_committee_id=null`이었다.
Congress.gov `/committee/senate/ssfr09`는 `type=Subcommittee`, parent `ssfr00`을 제공한다.
올바른 관계는 `119-senate-ssfr00` (Foreign Relations) → `119-senate-ssfr09` (Africa and Global Health Policy)다.

- `scripts/sync-committees.js`의 rowFrom: `isSubcommittee`, 전달받은 parent ID, `committeeType`을 사용한다. 응답의 `type`과 `parent`를 일관되게 반영하지 못한다.
- `scripts/sync-congress.js`의 위원회 upsert: `isSubcommittee`가 없으면 `standing`으로 쓴다. 별도 위원회 동기화에서 교정한 유형을 다시 오염시킬 수 있다.
- `_worker.js`의 usOverview: `parent_committee_id=is.null`로 최상위 목록을 조회한다. 이 checkout의 조회에는 의회 회기 필터도 없다. 잘못 저장된 parent/type 및 회기 혼합을 UI만으로 해결할 수 없다.

### Africa 소위원회 법안 0건

119대 전용 공식 `/committee/119/senate/ssfr09/bills` 응답 count는 0,
DB bill_committees 연결도 0이었다. 부모 Foreign Relations는 DB 연결 502건이었다.
이는 해당 소위원회에 공식 연결된 119대 법안이 없다는 관측이며, 아프리카/보건 관련 법안 자체가 없다는 뜻이 아니다.
API 배열은 `body['committee-bills'].bills`이며 빈 최상위 `body.bills`를 보고 0으로 판정하면 안 된다.
다른 위원회도 수집 상태를 확인하기 전에는 DB 0건을 공식 0건으로 일반화하지 않는다.

### Joint Economic Committee 중복

동일 119대·joint·같은 이름의 행이 아래 세 코드로 존재했다:
`jjec00`, `jhje00`, `jsec00` (모두 parent null, type standing).
이름만 기준으로 삭제하면 법안·인물·즐겨찾기 등 연결이 끊길 수 있다.
공식 코드별 현재성·역사·별칭을 확인해 canonical 기구와 source alias를 결정해야 한다.
정확한 canonical 코드 선정과 운영 병합은 아직 수행하지 않았다.

### CRS 31개

`sync-congress.js`는 수집한 법안에 policyArea가 있을 때 해당 분야를 upsert한다.
이 경로만으로는 전체 공식 사전이 갖춰졌다고 보장할 수 없다.
32개 공식 사전을 독립적으로 seed하고 안정적인 기존 policy_area_id를 보존한다.
`Social Sciences and History`를 추가하되 어떤 법안을 그 분야로 재배정할지는 공식 값으로 판단한다.

## 4. 데이터 수정 설계 — 구현 예정

1. 위원회 메타데이터 정규화 함수를 두 수집기가 공유한다. 공식 type/parent 및 회기를 우선 사용한다.
2. 부분 응답의 필드 부재는 기존 검증 값을 지우거나 standing으로 바꾸는 근거가 아니다.
   명시적인 parent 없음과 parent 정보 미수집을 구분한다. raw_source 전체 교체로 상세 출처를 잃지 않게 한다.
3. 내부 유형 계약 제안: standing / select / special / subcommittee / joint / commission / caucus / unknown.
   이는 **제안 값**이며 기존 운영 값의 전수 조사·호환성 확인 후 migration에서 확정한다.
4. 부모를 먼저 저장하고 자식을 연결한다. 부모·자식의 회기/원 일치, 자기참조·순환 여부를 검사한다.
5. JEC는 공식 별칭 매핑을 먼저 확정한다. FK뿐 아니라 text 기반 구독·즐겨찾기·JSON 참조도 조사한다.
   병합 시 bill_committees의 복합 PK 충돌을 처리하고 활동/출처를 합친 뒤 고유 법안 집합을 비교한다.
   오래된 ID의 상세 링크는 alias 조회를 통해 유지하는 방식을 권장한다.
6. CRS 공식 32개 사전을 재실행 가능한 seed로 반영한다. 기존 이름/ID·FK를 유지하고 누락 항목만 보강한다.
7. 수정 전후 보고서, 검증 쿼리, migration, schema.sql을 함께 남긴다. 이 문서에는 실행용 UPDATE/DELETE가 없다.
8. 재발 방지 수집기 배포와 DB 보정을 함께 계획한다. 메타데이터 정리가 법안 상태 알림을 발생시키지 않는지 확인한다.

## 5. Claude UI/API 인수인계

현재 `usOverview`는 committee_id/name/chamber/committee_type 등을 전달하지만
parent_committee_id와 congress_number는 overview 응답에서 빠져 있다.
데이터 보정과 함께 아래 API 계약을 구현·검증한 뒤 UI를 연결한다.

| 항목 | 제안 계약 |
|---|---|
| 회기 | 선택한 congress_number로 위원회·법안 수를 동일하게 제한 |
| 위원회 | committee_id, canonical ID(별칭 도입 시), name, chamber, committee_type, parent_committee_id, congress_number, official_url |
| 계층 | 목록에 부모/자식을 제공하거나 부모 상세에서 소위원회를 별도 조회; 현재 상세의 parent 필터 경로 재사용 가능 |
| 건수 | 직접 연결된 고유 bill_id 수. 하위 포함 집계는 별도 필드/라벨로 제공하고 중복 제거 |
| 데이터 상태 | 확인 시각·수집 성공/실패·미확인 상태. 실패를 0건으로 반환하지 않음 |
| CRS | 전체 32개 사전 + 현재 조건에 해당하는 건수; 0건 분야도 전체 사전에서 유지 |

UI 수정 방향:
- 하원/상원 안에서 상임위원회와 특별·선정위원회를 구분하고 소위원회는 부모 아래 둔다.
- 합동위원회와 기타 기구를 별도 그룹으로 둔다. 숫자 20/16을 맞추기 위해 미확인 데이터를 숨기지 않는다.
- 미확인 유형은 별도 표시한다. `Subcommittee Subcommittee` 중복 접미사도 정리하되 원본 명칭은 보존한다.
- 빈 목록: `현재 수집된 119대 공식 회부 법안 0건`처럼 범위를 밝힌다.
  공식 출처까지 확인한 경우에만 공식 0건이라고 표시한다. 부모의 법안을 자식의 회부 법안으로 표시하지 않는다.
- 부모 위원회 보기 및 주제 검색은 제공 가능하나 공식 회부 목록과 구분한다.
- CRS 필터와 위원회 필터는 별개다. 의미 검색 관련도는 공식 심사 관계를 대체하지 않는다.

## 6. 수용 기준 및 반영 순서

- [ ] 현재 회기의 공식 기구 목록과 유형별 ID 집합 대조(개수만 비교하지 않음).
- [ ] ssfr09가 ssfr00 아래 소위원회로 보이고 최상위 상임위 목록에 나타나지 않음.
- [ ] JEC가 화면에서 한 번 표시되며 기존 ID/연결/활동 기록이 보존됨.
- [ ] CRS 공식 32개 이름 일치, Social Sciences and History 포함; 기존 법안 분야 임의 변경 없음.
- [ ] 두 수집기를 재실행해도 교정한 type/parent가 되돌아가지 않음.
- [ ] 위원회 직접 건수와 하위 포함 고유 건수, 회기 필터가 API/화면에서 일치.
- [ ] 조회 실패와 0건, 공식 관계와 AI 관련도 구분; 모바일에서도 부모·자식 구분.
- [ ] DB 보정으로 즐겨찾기/메일 구독 유실 또는 허위 단계 변경 메일이 발생하지 않음.

권장 순서: 공식 식별자 재검증 → 수집기 회귀검증 → 운영 스키마/FK 조사 →
가역적인 DB 보정 계획·migration → API 계약 → Claude UI → 배포 후 실데이터 확인.
현재 단계는 문서 커밋까지이며 나머지 체크박스는 구현 완료 표시가 아니다.

관련 계약: [CLARITY 검색·입법 단계·메일](policy-clarity-search-lifecycle.md).
