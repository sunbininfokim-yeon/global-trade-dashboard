# 미국 정책 UI 화면 ↔ 데이터 파이프라인 매핑

이 문서는 확정된 손그림 화면과 Phase 2-1 데이터 계약을 1:1로 연결한다. 검색 입력창은 **비활성화** 상태이며, 이 문서의 어떤 화면도 검색 API나 LLM을 요구하지 않는다.

> API 경로는 프론트엔드가 사용할 논리 계약이다. 현재 리포지터리에는 HTTP 라우트를 구현하지 않았으며, 서버 계층은 service-role 키로 DB를 읽어 이 응답 모양으로 변환한다. 브라우저는 service-role 키나 원본 테이블을 직접 호출하지 않는다.

## 데이터 흐름

```text
Congress.gov ──→ bills / committees / policy_areas / bill_committees
                         │                    │
                         └──── 의회 목록·상임위·CRS 화면 ───→ 법안 상세

Federal Register ──→ agencies / executive_orders / regulations
                           │             │              │
                           └──── EO 기관·법적 근거·관련 규제 화면

GovInfo ──→ public_laws / public_law_code_impacts / us_code_titles
                    └──── 제정 법률·U.S. Code 참조 화면
```

## 1. 미국 정책 허브

### 10대 정책 Summary 카드

**권장 API**: `GET /api/us/policy/summary?limit=10`

**선정 규칙**

1. `bills`에서 `congress_number = 119`이고 `detail_level in ('tracked', 'enriched')`인 법안을 우선한다.
2. `current_stage`가 `reported` 이후인 법안을 우선하고, `latest_action_date desc`, `status_updated_at desc`, `bill_id desc`로 정렬한다.
3. 아직 10개에 못 미치면 현재 회기의 `detail_level = 'index'` 법안을 같은 정렬로 보충한다.
4. 카드에는 제목, 현재 단계, 최신 활동일, 공식 summary 일부와 상세 링크만 노출한다. 전문은 저장·표시하지 않는다.

**사용 필드**: `bill_id`, `title`, `current_stage`, `current_status`, `latest_action_date`, `summary`, `policy_area_id`, `detail_level`, `congress_url`.

**데이터 파이프라인**: `scripts/sync-congress.js`가 현재 119대 법안, summary, CRS 정책분야와 단계 정보를 채운다. Hot/Warm/Cold는 이 카드 정렬 기준이 아니라 동기화 우선순위다.

## 2. 의회 개요

### 상·하원·합동 상임위 블록

**API**: `GET /api/us/congress/committees?chamber=house|senate|joint`

**사용 필드**: `committees.committee_id`, `name`, `committee_type`, `display_order`, `official_url`, `jurisdiction_summary`.

- 기본 정렬: `display_order asc nulls last`, `name asc`.
- 상임위 클릭은 `GET /api/us/congress/bills?committee_id={id}&stage={stage}`로 이어진다.
- 소위원회는 `parent_committee_id`로 주 상임위원회 아래에 표시한다.

### 부처별 법안 수 그래프

**가능 여부**: 관계가 채워진 기관에 한해 가능하다.

```text
committee_agency_jurisdictions
  → agencies
  ← bill_committees
  ← bills (119대, 화면 필터 적용)
```

**집계 규칙**: `count(distinct bill_committees.bill_id)`를 기관별로 계산한다. 한 법안이 두 상임위에 걸리고 두 상임위가 같은 기관을 맡아도 법안은 기관당 한 번만 센다.

**권장 API**: `GET /api/us/congress/agency-bill-counts?congress_number=119`

**현재 상태 및 결정**: `bill_committees`와 `agencies`는 동기화된다. 그러나 `committee_agency_jurisdictions`는 공식 Congress.gov/Federal Register API가 제공하는 관계가 아니며, 현재 자동 시드가 없다. 그러므로 지금 그래프는 **데이터가 있는 기관만 표시**하고, 값이 없으면 “검증된 담당기관 매핑 준비 중” placeholder를 표시한다. 임의 추론으로 관계를 생성하지 않는다.

### `Agencies (N)` 카운트

**권장 API**: `GET /api/us/executive/agencies?active=true`

**집계**: `count(*) from agencies`가 아니라, Federal Register 동기화로 확인된 기관의 `count(distinct agency_id)`를 반환한다. `54`는 고정 문구가 아니며 현재 DB 값으로 표시한다.

**사용 필드**: `agency_id`, `name`, `short_name`, `agency_type`, `parent_agency_id`, `agency_url`.

**기관 블록 규칙**: `agency_type=eop`은 대통령실, `department`는 15개 내각 부처, `independent`는 독립기관(외청) 블록에 표시한다. `sub`는 최상위 블록에는 중복 노출하지 않고, `parent_agency_id`의 상위 기관 상세 화면에 표시한다. 이 분류는 Federal Register가 제공하는 `parent_id`와 검증된 고정 목록으로만 생성한다.

### 정당·의회 역할 소개

**결정: 정적 콘텐츠.**

정당의 기본 역할, 하원·상원의 제도 설명, 상임위·조정위원회 설명은 법안 동기화 데이터가 아니라 편집된 안내문이다. 프론트엔드 locale/콘텐츠 파일에 정적으로 관리한다. 정치인별 현재 당적·지도부 정보를 수집하는 별도 소스는 이번 단계에 추가하지 않는다.

## 3. 상임위 상세

### 헤더와 위원장

**현재 가능 필드**: `committees.name`, `chamber`, `official_url`, `jurisdiction_summary`, 담당기관 매핑이 있는 경우 `agencies.name`.

**위원장 결정: 이번 단계에는 placeholder. 스키마 추가 없음.**

[Congress.gov 공개 API](https://api.congress.gov/)에는 상임위 목록·상세·법안·보고서 등의 endpoint는 있지만, 상임위별 현재 위원/위원장(Chair)을 안정적으로 반환하는 endpoint가 공개 계약에 포함되어 있지 않다. 따라서 `committee_chair_bioguide_id`를 지금 추가해도 자동 수집값이 없어 신뢰할 수 없다.

- UI: `chair: null`이면 “위원장 정보 준비 중”을 표시한다.
- 다음 승인 범위: House Clerk와 Senate 공식 위원회 페이지를 검증 소스로 정해 `committee_leadership` 테이블(위원회, 역할, bioguide ID, 재임 시작/종료, 공식 출처)을 별도 파이프라인으로 추가한다.
- 이 데이터가 생기기 전에는 원본 JSON이나 LLM 추론으로 chair를 표시하지 않는다.

### 단계별 법안 리스트

**API**: `GET /api/us/congress/bills?committee_id={committee_id}&stage={stage}&cursor={cursor}`

**조인**: `bill_committees → bills`, 필요 시 `policy_areas`.

**기본 탭: 전체 보기**

첫 진입은 `stage`를 보내지 않는 **전체 보기**다. 이 탭은 종료된 법안과 아직 자동 분류되지 않은 법안을 포함한 모든 결과를 최신 활동일 순으로 보여 준다. 따라서 어떤 법안도 상임위·정책분야 화면에서 조용히 사라지지 않는다.

**화면 탭 → 필터 값**

| 화면 라벨 | `stage` 값 |
|---|---|
| 전체 보기 (기본) | 생략 — 모든 단계 포함 |
| 발의·회부 | `introduced,referred,subcommittee,committee_consideration` |
| 상임위 통과/보고 | `reported` |
| 발의원 본회의 통과 | `passed_origin_chamber` |
| 상대원 심사 | `second_chamber` |
| 양원 조정 | `resolving_differences` |
| 양원 통과 | `passed_both_chambers,presented_to_president` |
| 대통령 서명·법률 제정 | `enacted` |
| 종료·거부/부결 | `vetoed,failed` |

`other`는 원본 Congress.gov action은 보존됐지만 자동 단계 분류가 확정되지 않은 예외 상태다. 별도 “종료”로 오인하지 않고 전체 보기에서 `분류 확인 필요` 배지로 표시한다. 필요해질 경우에만 `other` 전용 운영 필터를 추가한다.

탭 수는 `policy_bill_stage_counts` 읽기 전용 RPC가 반환한 실제 행 수를 사용한다. 집계 RPC를 호출할 수 없는 경우에는 `0`을 표시하지 않고 수치를 숨긴다. `0`은 해당 필터에 법안이 없다는 검증된 값일 때만 표시한다.

**목록 필드**: `bill_id`, `title`, `sponsor`, `introduced_date`, `current_stage`, `current_status`, `latest_action_date`, `policy_area_id`, `summary`, `congress_url`.

### 법안 상세: 회부 상임위·표결·관련 법안

**현재 회부 상임위 칩**: `bill_committees → committees`를 조인해 `name`, `chamber`, `official_url`을 칩으로 보인다. 상임위 칩을 누르면 해당 상임위의 단계별 목록으로 이동한다.

**표결 노출 계약**

| 표결 구분 | UI에 노출할 것 | 데이터 조건 |
|---|---|---|
| 상임위 markup 표결 | 찬성·반대 집계와 의원별 `bill_vote_members` 명단 | `vote_stage = 'committee'` 이고 구성원 데이터가 공식 출처에서 완전하게 확보된 경우 |
| 본회의·그 이후 표결 | `yea_count`, `nay_count`, `present_count`, `not_voting_count`, `result`, 공식 링크만 | `vote_stage = 'floor'` 또는 `unknown` |
| 기록 표결 없음 | “기록 표결 없음” | 집계가 없거나 음성표결/만장일치 동의인 경우 |

**현재 구현 한계**: 현재 `bill_votes`는 `chamber`와 집계만 보관하며 `vote_stage`, `source_action_id`, `committee_id`가 없다. `bill_actions.committee_id` 컬럼은 존재하지만 현재 수집기는 그 값을 채우지 않는다. 또한 현재 수집기는 `bill_vote_members`를 채우지 않는다. 그러므로 현 단계 UI는 모든 표결을 **집계만** 표시해야 하며, 상임위 의원별 명단을 추정해 표시하면 안 된다.

다음 승인 범위의 스키마·수집 설계는 [법안 종료 데이터 보존 및 표결 확장 설계](bill-retention-design.md)를 따른다. 그 변경이 실제 적용된 뒤에만 상임위 markup 표결의 의원 명단을 노출한다.

**관련 법안 구역**

- `official_related_bills`: `bill_relations.relation_origin in ('official', 'verified_manual')`만 표시한다.
- `similar_bills`: `relation_origin = 'semantic'`만 표시하고 “AI 유사성” 라벨·점수를 함께 보인다.
- 두 구역은 시각적으로 분리한다. 유사 법안을 공식 관계처럼 표시하지 않는다.

**향후 교차정당 지지**: 법안 발의 당시의 정당을 나타내는 `bills.sponsor_party`가 아직 없다. 이 필드는 현재 단계에서 추가하지 않으며, 향후 표결 구성원 파이프라인과 함께 추가한다. 발의 시점 정당과 확인 출처·시각을 보존해야 하므로 현재 의원의 당적만 역참조해서 계산하지 않는다.

### 산업 프로필 자료

**결정: Phase 2-1 범위 밖, UI placeholder.**

Congress.gov/Federal Register에는 산업 프로필·시장 설명·산업 영향 분석 데이터가 없다. 해당 블록은 `자료 준비 중`으로 두고, Phase 2-2의 기관 보고서/CRS 보고서 또는 검증된 외부 산업 데이터 소스를 승인한 뒤 `reports` 중심으로 설계한다.

## 4. CRS 정책분야 상세

상임위 상세와 **동일한 단계별 법안 목록 컴포넌트**를 사용한다.

- API: `GET /api/us/congress/bills?policy_area_id={policy_area_id}&stage={stage}&cursor={cursor}`
- 목록 출처: `bills.policy_area_id → policy_areas`.
- 정책분야 칩/블록 개수는 하드코딩하지 않고 `GET /api/us/congress/policy-areas`의 실제 행 수를 사용한다.
- 클릭 후에는 기본 전체 보기와 발의·상임위 보고·본회의 통과·양원 통과·제정·종료/거부/부결을 같은 `stage` 체계로 필터한다.

## 5. 행정부 개요와 EO 상세

### EO 목록 카드

**API**: `GET /api/us/executive/orders?agency_id={agency_id}&cursor={cursor}`

**사용 필드**: `eo_number`, `title`, `signed_date`, `publication_date`, `summary`, `federal_register_url`, `storage_tier`.

EO 번호(`EO 01`, `EO 02` 같은 UI 라벨)는 `eo_number`를 표시용으로 포맷한 값이며, 실제 정렬은 `signed_date desc`, `eo_number desc`를 사용한다.

### EO 상세 한 화면

**API**: `GET /api/us/executive/orders/:eo_number`

기존 `api-spec.md`의 EO 상세 응답 구조와 일치한다.

| UI 구역 | 응답 필드 / 조인 |
|---|---|
| 상단 EO 카드 | `eo_number`, `title`, `signed_date`, `publication_date`, `summary`, `official_links` |
| 담당 기관 | `executive_order_agencies → agencies` |
| 법적 근거 | `executive_order_authorities → legal_authorities` (`citation`, `official_url`, `verification_status`) |
| 관련 규제 별도 섹션 | `executive_order_regulations → regulations` |

**레이아웃 결정**: 상단 EO 카드는 `summary`만 개괄 노출한다. 관련 규제는 아래의 독립 섹션에 목록으로 표시한다. 이것은 API 응답의 `related_regulations[]`와 정확히 대응한다. `relation_origin = semantic`은 AI 유사 관계이므로 공식 인용 관계와 시각적으로 구분한다.

## 6. 행정부 CFR Title → 규제 화면

- Title 칩: `GET /api/us/executive/cfr-titles` → `cfr_titles.title_number`, `name`, `reserved`.
- 규제 목록: `GET /api/us/executive/regulations?title_number={n}&cursor={cursor}`.
- 조인: `regulation_cfr_references → regulations`; 기관 표시는 `regulation_agencies → agencies`.
- 규제 카드: `title`, `document_type`, `abstract`, `publication_date`, `effective_on`, `federal_register_url`.
- `reserved = true` Title은 목록은 보여 주되 “예약됨”으로 표시하고 문서 수 0을 정상값으로 취급한다.

## 7. 파이프라인-UI 준비 상태

| 화면 데이터 | 수집 파이프라인 | 현 상태 | UI 처리 |
|---|---|---|---|
| 119대 법안·단계·summary | Congress.gov | 동기화 진행 중, cursor 재개 | 목록/상세 표시 |
| 상임위-법안 관계 | Congress.gov 법안 상세 | tracked/enriched 중심 | 단계별 목록 표시 |
| CRS 정책분야 | Congress.gov | 법안과 함께 저장 | 하드코딩 없이 칩 표시 |
| 상임위-기관 담당관계 | 검증된 수동 시드 필요 | 미수집 | 비어 있으면 그래프/부처명 placeholder |
| 위원장 | 공식 House/Senate 별도 소스 필요 | 미수집 | placeholder |
| EO·기관·법적 근거·규제 | Federal Register | 동기화 진행 중 | EO 상세/관련 규제 표시 |
| Public Law·U.S. Code 참조 | GovInfo | cursor 재개 백필 | 제정 법률/공식 링크 표시 |
| 산업 프로필 | Phase 2-2 이후 | 미수집 | placeholder |
| 키워드·의미 검색 | FTS/embedding 후속 | 검색 UI 비활성화 | 노출하지 않음 |

## 구현 순서

1. 서버 계층에서 이 문서의 논리 API를 구현하고, 목록 페이지는 cursor pagination을 적용한다.
2. 의회·CRS·EO·CFR 화면은 현재 수집된 데이터부터 렌더링한다. 빈 관계는 오류가 아니라 명시적 placeholder로 처리한다.
3. 상임위-기관 매핑을 검증해 시드한 뒤 부처별 그래프와 담당 부처 문구를 활성화한다.
4. 별도 공식 소스와 갱신 주기가 승인되면 위원장/위원 명부 파이프라인을 추가한다.
5. Phase 2-2에서 산업 프로필·보고서를 추가한 뒤 해당 UI 블록을 채운다.
