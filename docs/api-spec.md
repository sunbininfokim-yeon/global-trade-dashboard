# Phase 2-1 미국 정책 데이터 계약

이 문서는 미국 정책 화면을 구현하는 프론트엔드와 데이터 동기화 코드가 공유하는 계약이다. 실제 수집 범위는 Congress.gov, Federal Register, GovInfo의 Public Law 메타데이터와 U.S. Code 공식 릴리스 지점이다. 검색 입력창은 노출하지 않는다.

## 1. 확정된 화면 흐름

```text
미국 정책
├─ 의회
│  ├─ 하원 / 상원 / 합동 상임위원회
│  │  └─ 상임위 → 단계별 법안 목록 → 법안 상세
│  └─ CRS 정책분야
│     └─ 정책분야 → 단계별 법안 목록 → 법안 상세
└─ 행정부
   ├─ 기관
   │  └─ 기관 → 행정명령 목록 → 행정명령 상세 → 관련 규제
   └─ CFR Title 1–50
      └─ Title → 규제 목록 → 규제 상세
```

상임위와 CRS 정책분야는 같은 법안 목록·상세 컴포넌트를 사용하고 필터만 다르다. 기관 카드의 우측 하단 영역은 현재 비워 둔다.

화면 단위의 정확한 엔드포인트·필드·집계 기준과 아직 비어 있는 영역은 [UI 화면-데이터 매핑](ui-screens.md)을 기준으로 한다. 이 문서는 프론트엔드 구현의 보조 계약이며, 이 파일의 API·보안 원칙을 대체하지 않는다.

## 2. 데이터 설계 원칙

### 중첩 JSON 처리

Congress.gov와 Federal Register 응답을 그대로 한 컬럼에만 저장하지 않는다.

- 화면 필터와 조인에 필요한 값은 정규화한다.
- 원본 추적과 아직 사용하지 않는 필드는 각 주요 테이블의 `raw_source jsonb`에 보존한다.
- 반복 관계인 상임위, 주제, 기관, 표결, 관련 법안, CFR 참조는 연결 테이블로 분리한다.

이 방식은 JSONB-only 설계보다 UI 조회가 안정적이고, 모든 응답 필드를 완전 정규화하는 방식보다 API 변경에 유연하다.

### 전문 저장 금지

법안·행정명령·규제 전문은 다운로드하거나 DB에 저장하지 않는다.

- `bill_text_versions`에는 Congress.gov가 제공한 HTML/PDF/XML/Formatted Text URL만 저장한다.
- EO와 규제도 Federal Register의 공식 HTML/PDF URL만 저장한다.
- 화면에는 공식 summary/digest/abstract와 전문 링크만 제공한다.

### Hot / Warm / Cold 보존 등급

Hot/Warm/Cold는 전문 파일의 저장 계층이 아니라 **동기화 우선순위와 데이터 수명주기**다. 전문은 어느 tier에서도 저장하지 않는다. tier는 최상위 문서인 `bills`, `executive_orders`, `regulations`에만 저장하며, summary·action·표결·공식 링크 같은 하위 데이터는 상위 문서의 tier를 따른다. 이렇게 해야 동일 법안의 하위 행들이 서로 다른 tier가 되는 불일치를 막을 수 있다.

- `hot`: 진행 중 법안 또는 최근 30일 안에 변경된 EO·규제. 매일 상세 동기화한다.
- `warm`: 현재 회기에 속하지만 hot이 아닌 법안, 또는 최근 8년 안의 EO·규제. 공식 변경분이 감지됐을 때만 상세 동기화한다.
- `cold`: 그보다 오래된 종료·역사 데이터. 매일 상세 폴링하지 않고 월간 재조정 또는 공식 변경 감지 때만 다시 동기화한다.

동기화 스크립트는 실행 후 `refresh_policy_lifecycle_tiers(active_congress_number)`를 호출해 tier를 갱신하고 `last_synced_at`을 기록한다. cold 데이터는 기본 목록 화면에서 제외할 수 있지만, 역사 필터나 직접 링크로는 계속 조회 가능하다. HNSW 임베딩 인덱스에서도 제외하지 않는다.

이번 단계에서는 cold 데이터를 삭제하거나 외부 저장소로 이동하지 않는다. `archived_at`은 향후 실제 외부 아카이브가 도입될 때만 채운다. `schema.sql`은 새 DB를 위한 단일 기준 파일이며, 기존 DB를 초기화해 다시 만들 때도 이 파일 하나만 실행한다.

### 공식 관계와 AI 관계

- Congress.gov 관련 법안: `bill_relations.relation_origin = "official"`
- pgvector 유사 법안: `relation_origin = "semantic"`
- 검증된 수동 관계: `relation_origin = "verified_manual"`

UI에서도 **공식 관련 법안**과 **유사 법안**을 별도 구역에 표시해야 한다. AI가 만든 관계를 공식 관계처럼 표시하면 안 된다.

EO의 법적 근거는 법안으로 한정되지 않는다. 헌법, U.S.C., Public Law, Statutes at Large, 과거 EO 등이 될 수 있다. EO의 근거는 `legal_authorities`에 공식 citation과 URL만 저장하며, 근거를 찾지 못했을 때 추정하지 않는다.

### Public Law와 U.S. Code

- 대통령이 서명한 일반 법률은 `public_laws`에 Public Law 번호, 제정일, Statutes at Large 인용, GovInfo 공식 링크로 보존한다. PDF·본문은 저장하지 않는다.
- U.S. Code는 현행 일반·영구 법률을 제목별로 편집한 법전이다. 모든 Public Law가 U.S. Code에 편입되는 것은 아니다.
- `public_law_code_impacts`는 GovInfo가 제공한 공식 U.S. Code 참고문헌만 기록한다. 법률이 어느 조문을 바꿨는지 AI가 추론하지 않는다.
- `us_code_titles`는 54개 Title의 가벼운 지도이며, `us_code_sections`도 제목·조문 번호·공식 링크만 담는다. U.S. Code 본문은 저장하지 않는다.

### 분류 개수

- CRS의 Congress.gov 정책분야 목록은 API에서 동기화한다. 화면에 47개를 하드코딩하지 않는다.
- 규제 분류는 CFR Title 1–50 고정 참조 시드로 제공한다. 런타임 eCFR API 동기화는 하지 않으며, 예약된 Title도 `reserved = true`로 유지한다.
- EO는 CFR Title에 직접 분류하지 않는다. EO와 연결된 규제가 가진 CFR 참조를 통해서만 간접 노출한다.

## 3. 주요 테이블

| 영역 | 테이블 | 용도 |
|---|---|---|
| 공통 | `agencies` | Federal Register 기관 기준정보 |
| 공통 | `policy_areas` | Congress.gov CRS 정책분야 |
| 공통 | `legislative_subjects` | 세부 입법주제 |
| 공통 | `cfr_titles` | 고정 참조 CFR Title 1–50 |
| 운영 | `data_sync_state` | 증분 동기화 cursor와 마지막 성공 시각 |
| 운영 | `data_sync_runs` | 동기화 실행 이력·오류·처리량 |
| 운영 | `policy_ingestion_queue` | 발견과 실제 상세 적재를 분리하는 재개 가능 큐 |
| 의회 | `committees` | 하원·상원·합동·소위원회 |
| 의회 | `committee_agency_jurisdictions` | 상임위와 담당/감독 기관의 검증된 다대다 매핑 |
| 의회 | `bills` | 법안 기본정보와 현재 단계 |
| 의회 | `public_laws` | 제정된 법률과 원 법안 연결 |
| 법전 | `us_code_titles` | U.S. Code Title 1–54의 가벼운 공식 참조 지도 |
| 법전 | `us_code_sections` | Public Law 공식 참조에서 확인된 조문 번호·공식 링크 |
| 법전 | `public_law_code_impacts` | Public Law와 공식 U.S. Code 참고문헌의 연결 |
| 의회 | `bill_summaries` | Congress.gov의 공식 summary 이력 |
| 의회 | `bill_text_versions` | 전문 파일이 아닌 공식 링크 |
| 의회 | `bill_actions` | 공식 action 타임라인 |
| 의회 | `bill_status_history` | 상태 변경 이력 |
| 의회 | `bill_committees` | 법안과 상임위의 다대다 관계 |
| 의회 | `bill_subjects` | 법안과 세부 주제의 다대다 관계 |
| 의회 | `bill_votes` | 표결 집계와 공식 출처 |
| 의회 | `bill_vote_members` | 확보 가능한 경우 의원별 표결 |
| 의회 | `bill_relations` | 공식 관련 법안·AI 유사 법안 |
| 행정부 | `executive_orders` | 행정명령 |
| 행정부 | `executive_order_agencies` | EO와 기관 관계 |
| 행정부 | `legal_authorities` | 검증된 법적 근거 |
| 행정부 | `executive_order_authorities` | EO와 법적 근거 관계 |
| 행정부 | `regulations` | Final Rule, Proposed Rule 등 Federal Register 문서 |
| 행정부 | `regulation_agencies` | 규제와 기관 관계 |
| 행정부 | `regulation_cfr_references` | 규제와 CFR Title/Part 관계 |
| 행정부 | `executive_order_regulations` | EO와 관련 규제 |
| 확장 | `reports` | Phase 2-2 정부 보고서 자리 |
| 확장 | `subscriptions` | 키워드/분류 구독 |
| 확장 | `notifications_queued` | 발송 전 큐; 이번 단계에서는 발송하지 않음 |

## 4. 법안 단계 표준값

`bills.current_stage`와 `bill_actions.normalized_stage`는 다음 값을 사용한다.

| 값 | 화면 의미 |
|---|---|
| `introduced` | 발의 |
| `referred` | 상임위 회부 |
| `subcommittee` | 소위원회 |
| `committee_consideration` | 상임위 심사 |
| `reported` | 상임위 보고/통과 |
| `passed_origin_chamber` | 발의원 본회의 통과 |
| `second_chamber` | 상대원 심사 |
| `resolving_differences` | 양원 차이 조정 |
| `passed_both_chambers` | 양원 통과 |
| `presented_to_president` | 대통령 송부 |
| `enacted` | 법률 제정 |
| `vetoed` | 거부권 |
| `failed` | 부결 |
| `other` | 자동 분류 불가 |

Congress.gov action code와 문구를 근거로 정규화하되, 원문은 항상 `bill_actions.action_text`에 보존한다.

## 5. 프론트엔드 조회 계약

아래 경로는 프론트가 기대할 논리 API 계약이다. 현재 작업은 DB와 동기화 파이프라인 범위이므로 HTTP 라우트 자체는 별도 서버 계층에서 구현한다. 브라우저에서 `SUPABASE_SERVICE_ROLE_KEY`를 직접 사용하면 안 된다.

### 의회 탐색

- `GET /api/us/congress/committees?chamber=house|senate|joint`
- `GET /api/us/congress/policy-areas`
- `GET /api/us/congress/bills?committee_id=...&stage=...&cursor=...`
- `GET /api/us/congress/bills?policy_area_id=...&stage=...&cursor=...`
- `GET /api/us/congress/bills/:bill_id`
- `GET /api/us/law/public-laws?congress_number=119&cursor=...`
- `GET /api/us/law/public-laws/:public_law_id`
- `GET /api/us/law/us-code/titles`
- `GET /api/us/law/us-code/sections?title_number=19&cursor=...`

상임위 카드의 담당 부처명은 `committee_agency_jurisdictions → agencies` 조인 결과다. 공식 또는 검증된 수동 매핑만 표시한다.

### 행정부 탐색

- `GET /api/us/executive/agencies`
- `GET /api/us/executive/orders?agency_id=...&cursor=...`
- `GET /api/us/executive/orders/:eo_number`
- `GET /api/us/executive/cfr-titles`
- `GET /api/us/executive/regulations?title_number=...&cursor=...`
- `GET /api/us/executive/regulations/:regulation_id`

### 페이지네이션

목록은 날짜와 PK를 결합한 cursor 방식이 권장된다.

```json
{
  "items": [],
  "next_cursor": "2026-08-28T00:00:00Z|119-hr-1234",
  "has_more": false
}
```

## 6. 샘플 응답

### 상임위별 법안 목록

```json
{
  "filter": {
    "type": "committee",
    "id": "119-house-hsba",
    "name": "House Committee on Financial Services",
    "chamber": "house",
    "agencies": [
      {
        "agency_id": "treasury",
        "name": "Department of the Treasury",
        "mapping_source": "verified_manual"
      }
    ]
  },
  "stage_counts": {
    "introduced": 12,
    "referred": 38,
    "committee_consideration": 7,
    "reported": 4,
    "passed_origin_chamber": 2
  },
  "items": [
    {
      "bill_id": "119-hr-1234",
      "congress_number": 119,
      "bill_type": "hr",
      "bill_number": 1234,
      "title": "Example Trade Act",
      "sponsor": "Jane Doe",
      "introduced_date": "2026-03-04",
      "current_stage": "reported",
      "current_status": "Reported by committee",
      "latest_action_date": "2026-08-25",
      "policy_area": {
        "policy_area_id": "foreign-trade-and-international-finance",
        "name": "Foreign Trade and International Finance"
      }
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

### 법안 상세

```json
{
  "bill_id": "119-hr-1234",
  "title": "Example Trade Act",
  "sponsor": {
    "name": "Jane Doe",
    "bioguide_id": "D000000"
  },
  "introduced_date": "2026-03-04",
  "current_stage": "passed_origin_chamber",
  "current_status": "Passed House",
  "detail_level": "enriched",
  "summary": {
    "text": "Official Congress.gov summary text.",
    "source": "Congress.gov",
    "updated_at": "2026-08-25T14:00:00Z"
  },
  "votes": [
    {
      "chamber": "house",
      "vote_date": "2026-08-25T18:20:00Z",
      "question": "On Passage",
      "result": "Passed",
      "yea": 231,
      "nay": 198,
      "present": 1,
      "not_voting": 3,
      "source_url": "https://clerk.house.gov/..."
    }
  ],
  "text_versions": [
    {
      "version_code": "EH",
      "version_name": "Engrossed in House",
      "html_url": "https://www.congress.gov/...",
      "pdf_url": "https://www.congress.gov/..."
    }
  ],
  "official_related_bills": [
    {
      "bill_id": "119-s-567",
      "title": "Example Companion Act",
      "relation_type": "Identical bill",
      "identified_by": "CRS"
    }
  ],
  "similar_bills": [
    {
      "bill_id": "118-hr-999",
      "title": "Prior Trade Act",
      "similarity_score": 0.87,
      "label": "AI similarity"
    }
  ],
  "congress_url": "https://www.congress.gov/bill/119th-congress/house-bill/1234"
}
```

표결이 음성표결 또는 만장일치 동의인 경우 찬성·반대 집계는 `null`일 수 있다. UI는 숫자를 임의로 0으로 바꾸지 말고 “기록 표결 없음”으로 표시한다.

### 행정명령 상세

```json
{
  "eo_number": 14319,
  "document_number": "2026-00001",
  "title": "Example Executive Order",
  "signed_date": "2026-08-20",
  "publication_date": "2026-08-22",
  "summary": "Official Federal Register abstract when available.",
  "agencies": [
    {
        "agency_id": "fr-executive-office-of-the-president",
      "name": "Executive Office of the President"
    }
  ],
  "legal_authorities": [
    {
      "authority_type": "usc",
      "citation": "19 U.S.C. 2411",
      "official_url": "https://uscode.house.gov/...",
      "verification_status": "verified"
    }
  ],
  "related_regulations": [
    {
      "regulation_id": "FR-2026-12345",
      "title": "Implementation of Example Executive Order",
      "document_type": "RULE",
      "relation_origin": "official_citation",
      "federal_register_url": "https://www.federalregister.gov/..."
    }
  ],
  "official_links": {
    "html": "https://www.federalregister.gov/...",
    "pdf": "https://www.govinfo.gov/..."
  }
}
```

법적 근거를 검증하지 못한 경우 `legal_authorities`는 빈 배열이고 공식 문서 링크만 제공한다.

## 7. 검색과 임베딩

검색 UI는 현재 invisible 상태다. 스키마의 임베딩 컬럼과 HNSW 인덱스는 이후 기능을 위해 유지한다.

- 키워드 검색: PostgreSQL Full Text Search로 구현 가능하며 LLM이 필요 없다.
- 의미 검색/유사 법안: `text-embedding-3-small`로 만든 1536차원 벡터와 cosine distance를 사용한다.
- 자연어 질의·RAG 답변: 별도 LLM이 필요하며 이번 범위가 아니다.
- 임베딩 입력: 제목 + 공식 summary/abstract만 사용한다.

HNSW를 초기 전략으로 사용한다. 연간 신규 법안 약 1만 건과 EO·규제를 합친 규모에서는 별도 학습이 필요한 IVFFLAT보다 운영이 단순하다. 수백만 벡터 규모에서 메모리와 인덱스 생성 시간이 문제가 될 때 IVFFLAT 또는 별도 벡터 저장소 전환을 벤치마크한다.

## 8. 동기화 정책

### Congress.gov

- 수집 범위는 **현재 119대 Congress**다. 과거 4개 회기의 실패·계류 법안 전체를 적재하지 않는다. 필요하면 `CONGRESS_NUMBERS`를 명시한 일회성 실행으로만 확장한다.
- 현재 회기의 모든 발의안은 `detail_level = index`의 가벼운 색인(제목·발의일·최신 상태·요약·공식 링크)으로 수집한다.
- 상임위 보고/통과(`reported`)부터 `tracked`, 본회의 통과 이후는 `enriched`다. 이 두 단계에서만 actions, 표결, 관련 법안, 법안 전문 링크 메타데이터를 상세 수집하고 임베딩 후보가 된다.
- 발견 결과는 먼저 `policy_ingestion_queue`에 쌓는다. 한 실행의 `MAX_BILLS`를 넘는 법안은 실패하거나 버려지지 않고 다음 실행에서 이어서 처리한다.
- bootstrap cursor는 `data_sync_state.cursor`에 Congress 번호·페이지 offset을 저장한다. 한 번 `SYNC_MODE=bootstrap`으로 시작하면, 이후 일일 실행도 cursor가 완료될 때까지 자동으로 다음 페이지를 이어받는다. 실패해도 큐에서 성공 처리한 행은 다시 처리하지 않는다.
- incremental은 `fromDateTime` 변경분을 발견해 큐에 추가한다. 큐가 실제 저장 완료를 보장하므로, 실행 중 실패해도 처음부터 다시 시작하지 않는다.
- 현재 상태가 바뀌었을 때만 `bill_status_history`에 추가한다.
- API 최대 페이지 크기는 250을 사용한다.
- 429/5xx는 지수 백오프 + jitter로 재시도하고 `Retry-After`가 있으면 우선한다.
- 시간당 5,000 요청의 약 80%를 자체 상한으로 잡아 다음 실행으로 이월한다.

### Federal Register

- Federal Register API는 키 없이 호출한다.
- EO는 Presidential Documents 중 Executive Order만 적재한다.
- 규제는 최소 `RULE`과 `PRORULE`을 적재한다. Notice 확대는 별도 결정한다.
- 실행 중 처리한 Federal Register `document_number`도 `data_sync_state.cursor`에 체크포인트로 저장한다. 각 실행은 `data_sync_runs`에 성공·실패·건수·오류를 남긴다.
- 각 소스 동기화가 성공하면 `refresh_policy_lifecycle_tiers(active_congress_number)` RPC를 호출한다.
- `cfr_titles`는 초기 SQL의 고정 참조 시드다. eCFR API를 호출하는 동기화 작업은 이번 범위에 없다.

### Public Law와 U.S. Code 참조

- GovInfo Public Law 수집은 `DATA_GOV_API_KEY`를 사용한다. 이용 가능한 전체 Public Law 기록을 메타데이터·공식 링크·Statutes at Large 인용만으로 백필할 수 있다.
- Public Law 백필도 `policy_ingestion_queue`를 사용하며, 기본 실행당 `MAX_PUBLIC_LAWS=50`개까지만 상세 처리한다. 한 번 bootstrap을 시작하면 이후 일일 실행이 다음 검색 페이지와 남은 큐를 이어서 처리한다.
- U.S. Code 동기화는 본문 수집이 아니라 U.S. House Office of the Law Revision Counsel의 공식 다운로드 페이지에서 현재 release point만 갱신한다. 54개 Title의 정적 이름 시드는 DB에 이미 있다.
- U.S. Code 조문 연결은 GovInfo Public Law summary의 공식 references가 있는 경우에만 만들어진다. `classification_status = pending`은 아직 공식 분류가 나타나지 않았거나 반영 시차가 있다는 뜻이다.

### 로컬 첫 적재 순서

환경변수는 로컬 셸 또는 GitHub Actions Secrets로만 제공한다. 키를 소스 파일이나 `.env` 커밋에 넣지 않는다.

```bash
# 1) 작게 연결·적재 확인: 최근 변경 법안/FR 문서만 10개까지
MAX_BILLS=10 MAX_FR_DOCUMENTS=10 node scripts/sync-congress.js
MAX_BILLS=10 MAX_FR_DOCUMENTS=10 node scripts/sync-federal-register.js

# 2) 현재 119대 발의안 색인 백필. 발견과 적재가 큐로 분리되어
#    한 번 실행에 처리하지 못한 나머지는 다음 실행에 이어진다.
SYNC_MODE=bootstrap MAX_BILLS=25 node scripts/sync-congress.js

# 3) Public Law 메타데이터 백필과 U.S. Code release point 갱신
PUBLIC_LAW_MODE=bootstrap MAX_PUBLIC_LAWS=50 node scripts/sync-public-laws.js
node scripts/sync-us-code.js
```

기본 임베딩 모델은 `text-embedding-3-small`이며, 제목과 공식 summary/abstract만 임베딩한다. `SKIP_EMBEDDINGS=true`는 연결 테스트에만 사용한다.

### Supabase Free Plan 안전 기본값

Free Plan의 데이터베이스 한도는 프로젝트당 500MB이며, 이 한도를 넘으면 읽기 전용이 될 수 있다. 따라서 기본 GitHub Actions 설정은 `MAX_BILLS=100`, `MAX_PUBLIC_LAWS=50`, `MAX_FR_DOCUMENTS=50`, `MAX_EMBEDDINGS=25`이다. 이 값은 한 실행의 처리량일 뿐 일일 전체 보관 한도가 아니다. 남은 Federal Register 문서와 법안·Public Law 큐는 다음 실행으로 넘긴다.

- 법안·action의 `raw_source`에는 원본 응답 전문이 아니라 추적 가능한 API URL·갱신시각 등 최소 메타데이터만 저장한다.
- bootstrap은 `MAX_BILLS=25`부터 시작하고, 각 배치 뒤 Supabase Dashboard의 **Settings → Usage**에서 DB 크기를 확인한다.
- 119대의 `index` 법안은 임베딩하지 않는다. `tracked`/`enriched` 법안과 EO·규제 중 최근 변경된 최대 25개에만 1,536차원 벡터를 생성한다.
- `OPENAI_API_KEY`의 API 잔액이 없거나 키가 없을 때도 공식 데이터 적재는 성공해야 한다. 이 경우 임베딩만 건너뛰며, 잔액을 충전한 뒤 별도 임베딩 재처리 실행을 할 수 있다.
- 데이터베이스가 400MB에 근접하면 bootstrap을 멈추고, 오래된 warm/cold 데이터·전수 임베딩 확대 여부를 재검토한다. 전문 파일과 PDF는 저장하지 않는다.

Supabase는 Free 프로젝트를 저활동 상태에서 일시 중지할 수 있다. 매일 동기화가 성공하면 데이터베이스 활동도 생기지만, 실패가 지속될 때는 대시보드 이메일을 확인한다. [Supabase Free 요금/한도](https://supabase.com/pricing), [DB 크기 동작](https://supabase.com/docs/guides/platform/database-size), [무료 프로젝트 일시 중지](https://supabase.com/docs/guides/platform/free-project-pausing)를 기준으로 운영한다.

## 9. 보안과 환경변수

동기화 서버 또는 GitHub Actions에서만 다음 값을 사용한다.

- `CONGRESS_API_KEY`
- `DATA_GOV_API_KEY` — Congress 키 장애 시 예비키
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`

`SUPABASE_SERVICE_ROLE_KEY`와 `OPENAI_API_KEY`는 Cloudflare 프론트 번들, 브라우저 코드, 로그, API 응답에 절대 포함하지 않는다. 모든 테이블은 RLS가 활성화되어 있으며 현재 스키마에는 공개 브라우저 정책을 만들지 않는다.

## 10. 이번 구조에서 제외

- UI 구현
- 검색 입력창 노출
- 법안/EO/규제 전문 다운로드와 저장
- PDF 파싱
- 이메일 발송
- 보고서 수집·요약
- 뉴스 스크래핑과 법안-뉴스 연결
- 검증되지 않은 EO 법적 근거 자동 추론
