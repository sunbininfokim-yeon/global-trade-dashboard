# JEC 대표 식별자와 CRS 사전 — 운영 DB 적용 완료

2026-09-21 사용자 후속 승인으로 `20260921110000_jec_identity_crs_dictionary.sql`을 적용했다.
SQL 결과 CRS active=32, canonical JEC=1. 별도 REST로 동일 결과를 확인했다.

## JEC 조회 계약 (Claude Worker/UI 연결 필요)

원본 3행은 삭제하지 않았다. 공식 API가 세 코드를 각각 유지하므로 앱의 대표 식별자로
`119-joint-jjec00`을 선택하고 jhje00/jsec00를 별도 alias 테이블로 연결했다.
이는 Congress.gov가 다른 코드를 폐기했거나 공식 redirect로 지정했다는 주장이 아니다.
공식 동일 명칭, JEC 공식 사이트 및 역사 정보를 근거로 한 사이트 내부 통합이다.
기존 FK·즐겨찾기·구독·보고서 URL·수집 키를 유지한다. 수집기는 원본 코드를 계속 쓴다.

- `committee_identity`: source_committee_id → canonical_committee_id. 이전 상세 URL 진입 시 먼저 resolve.
- `committee_directory`: 대표 행만 반환. source_committee_ids에 자기 자신과 모든 alias가 포함된다.
  canonical_parent_committee_id는 표시할 부모, canonical_bill_count는 고유 법안 수다.
- `committee_canonical_bill_links`: (committee_id, bill_id) 단위 중복 제거. source_committee_ids로 출처 보존.
- `committee_identity_aliases`: 2개 매핑, 같은 회기/원 제약과 self/chain/cycle 거부. 서비스 역할 전용.
- 모든 뷰는 security_invoker=true, service_role만 조회 허용. 브라우저에 서비스 키를 넘기지 않는다.

**아직 기존 `_worker.js`는 committees를 읽으므로 사이트의 JEC 카드가 자동으로 1개가 되지는 않는다.**
Claude가 다음을 함께 연결해야 한다:
1. overview 위원회 조회를 committee_directory로 바꾸고 회기·canonical_parent 필터 적용.
2. 위원회 건수는 canonical_bill_count 사용. 원본 코드별 count를 단순 더하지 않기.
3. 옛 ID 상세도 committee_identity로 대표 ID 해석 후 source_committee_ids 전체의 활동·구성원·관할 조회.
4. 법안 필터에는 committee_canonical_bill_links 또는 원본 ID IN 필터 후 bill_id 중복 제거 사용.
5. source_committee_ids 전체의 부모 연결 자식을 읽거나 canonical_parent_committee_id로 조회.
   회기 소속 미검증 377개 기존 자식은 이번에도 현역으로 재인증하지 않았다.
6. 즐겨찾기 원본 ID가 남으므로 구성원·법안·구독을 대표 ID 하나로만 조회해 누락시키지 않기.
7. overview/detail KV 캐시 버전 갱신 및 3가지 옛 URL 회귀검증 후 배포.

JEC 3코드에 연결된 원본 구성원 20행은 전후 내용이 동일하다.
현재 bill_committees/bill_actions/기관 연결은 각각 0개로 유지된다. 테스트에는 동일 법안이
여러 코드에 걸리는 경우와 신규 alias 코드 법안이 이후 추가되는 경우를 포함했다.

## CRS

공식 32개 명칭은 `data/policy/crs-policy-areas.json`, 재실행 가능한 seed는
`scripts/lib/crs-policy-areas-seed.sql`에 있다. 이번 실제 추가는 Social Sciences and History 1행이다.
기존 31행의 ID/필드와 법안 분류를 바꾸지 않았다. 예전 캐시가 만료되거나 갱신되면 기존
policy_areas 조회에서도 32개를 읽을 수 있다. 0건 분야를 숨기지 말 것.

## 검증 / 복구

PGlite: 2회 migration, 원본 보존, 고유 법안 집계, 미래 연결 반영, alias 순환 거부,
기존 비표준 policy_area_id 보존, 익명 접근 거부 통과. 운영 REST에서도 CRS32/JEC1 확인.
운영 원본·전후 백업: `/Users/yeoninair/Documents/policy-downloads/jec-crs-20260921/` (비공개).
UI 배포 전 되돌림은 새 뷰 사용을 중단하면 된다. 원본 행을 이동하지 않아 데이터 역이관이 없다.
CRS 항목은 새 법안이 참조할 수 있으므로 롤백 목적으로 함부로 삭제하지 않는다.

공식 근거:
https://www.jec.senate.gov/public/index.cfm/about
https://api.congress.gov/v3/committee/joint/jjec00
https://api.congress.gov/v3/committee/joint/jhje00
https://api.congress.gov/v3/committee/joint/jsec00
https://www.congress.gov/help/field-values/policy-area
