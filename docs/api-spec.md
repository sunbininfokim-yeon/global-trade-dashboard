# US Policy Dashboard — API Contract

프론트엔드(`New for anti/policy.js`)가 소비하는 실제 API 스펙이다.
현재는 `New for anti/public/data/ui-policy-mock-data.json`을 그대로 로드해서 렌더링하고 있고,
아래 스펙대로 응답하는 실 엔드포인트가 배포되면 policy.js의 TODO 표시된
fetch 호출부만 URL 교체하면 된다. **응답 스키마는 mock 데이터와 1:1로
맞춰야 UI 쪽 변경 없이 바로 교체 가능하다.**

이 문서는 UI 소유자(Claude Code)가 작성한 계약서이며, 백엔드 구현(수집
스크립트, `/api/us/*` 라우트, Supabase 스키마)은 별도 담당(Codex)이
진행한다. 백엔드 구현 파일(`_worker.js`, 수집 스크립트, Supabase
마이그레이션)에는 관여하지 않는다 — 이 문서와 mock JSON만 기준으로 삼는다.

## 데이터 소스 (제안)

- **법안/의회 데이터**: [Congress.gov API](https://api.congress.gov/) — bills, committees, votes, sponsors. 무료 API 키 필요 (서버사이드 secret으로만 보관, 클라이언트에 노출 금지).
- **행정명령/규제 데이터**: [Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1) — executive orders, rules, 키 불필요.
- **영속 저장/조인**: Supabase. 아래 각 엔드포인트 응답을 만들 때 필요한 테이블 형태를 "Supabase 참고 스키마"로 함께 적어둔다. 정확한 테이블/컬럼명은 백엔드 담당 재량.

Congress.gov API는 분당 요청 제한이 있으므로 KV/DB 캐시를 거쳐 응답할 것.

## 공통 규칙

- 모든 날짜는 `YYYY-MM-DD` (ISO 8601 date).
- 실제 데이터가 없는 필드는 `null`로 보내고, 프론트가 `New for anti/public/data/ui-policy-mock-data.json`의 `ui_states`에 정의된 placeholder 문구로 대체 렌더링한다. **빈 문자열이나 가짜 값으로 채우지 말 것.**
- `bill_id`, `eo_number`, `committee_id` 등 식별자는 mock의 `mock-` 프리픽스를 제거한 실제 값 형식이면 된다 (예: `119-hr-1001`).
- 검색은 아직 비활성 (`meta.search.enabled: false` 유지) — 검색 엔드포인트는 이번 계약에서 제외.

---

## `GET /api/us/policy/summary`
→ `policy_hub` 대체

**Query**: 없음 (또는 향후 페이지네이션용 `?cursor=`)

**Response**:
```json
{
  "country": "US",
  "active_section": "congress",
  "summary_cards": [
    {
      "bill_id": "119-hr-1001",
      "title": "string",
      "current_stage": "introduced|referred|subcommittee|committee_consideration|reported|passed_origin_chamber|second_chamber|resolving_differences|passed_both_chambers|presented_to_president|enacted|vetoed|failed",
      "current_status": "string (사람이 읽는 상태 설명)",
      "latest_action_date": "YYYY-MM-DD",
      "summary": "string",
      "policy_area": { "policy_area_id": "string (CRS policy area slug)", "name": "string" },
      "detail_level": "index|tracked|enriched",
      "congress_url": "https://www.congress.gov/..."
    }
  ]
}
```
`detail_level`: 얼마나 상세히 파고들었는지 표시. `index` = 목록에만 존재, `tracked` = 기본 필드 채움, `enriched` = 표결/관련법안까지 채움. 프론트는 이 값으로 카드 배지를 다르게 그린다.

**Supabase 참고 스키마**: `bills` 테이블(bill_id PK, title, current_stage, current_status, latest_action_date, summary, policy_area_id FK, congress_url, detail_level).

---

## `GET /api/us/congress/committees`
→ `congress_overview` 대체

**Query**: `?chamber=house|senate|joint` (optional, 없으면 전체)

**Response**:
```json
{
  "active_chamber": "house",
  "chambers": [{ "id": "house", "label": "House" }],
  "committees": [
    {
      "committee_id": "string",
      "name": "string",
      "chamber": "house|senate|joint",
      "committee_type": "standing|select|joint",
      "display_order": 1,
      "official_url": "string",
      "jurisdiction_summary": "string",
      "agencies": ["string (agency name)"],
      "chair": { "name": "string", "member_url": "string" } | null,
      "ranking_member": { "name": "string", "member_url": "string" } | null,
      "subcommittees": [
        { "subcommittee_id": "string", "name": "string", "next_meeting_at": "YYYY-MM-DD" | null }
      ]
    }
  ],
  "agency_bill_counts": [
    { "agency_id": "string", "name": "string", "bill_count": 12 }
  ],
  "static_explainer": { "title": "string", "body": "string" }
}
```
`chair`/`ranking_member`가 아직 확보 안 된 데이터면 `null` — 프론트가 `ui_states.empty_chair`/`empty_ranking_member` placeholder로 렌더링한다. `subcommittees[].next_meeting_at`이 없으면 `null` → `empty_subcommittee_meetings` placeholder.

**Supabase 참고 스키마**: `committees`(committee_id PK, name, chamber, committee_type, jurisdiction_summary, chair_name, chair_url, ranking_member_name, ranking_member_url), `subcommittees`(subcommittee_id PK, committee_id FK, name, next_meeting_at), `committee_agencies`(committee_id FK, agency_id FK).

---

## `GET /api/us/congress/committees/{committee_id}/bills`
→ `committee_detail` 대체

**Query**: `?stage=reported` (comma-separated OR 허용, 예: `vetoed,failed`), `?cursor=`

**Response**:
```json
{
  "committee": {
    "committee_id": "string", "name": "string", "chamber": "house|senate|joint",
    "official_url": "string", "jurisdiction_summary": "string",
    "chair": { "name": "string" } | null,
    "ranking_member": { "name": "string" } | null,
    "subcommittees": [{ "subcommittee_id": "string", "name": "string", "next_meeting_at": "YYYY-MM-DD" | null }]
  },
  "stage_tabs": [
    { "label": "string (한글 라벨)", "stage": "reported" | "a,b,c" | null, "count": 9 }
  ],
  "items": [
    {
      "bill_id": "string", "title": "string", "sponsor": "string",
      "introduced_date": "YYYY-MM-DD", "current_stage": "string", "current_status": "string",
      "latest_action_date": "YYYY-MM-DD", "policy_area_id": "string",
      "summary": "string (official summary, 원문 전체 금지 — abstract만)",
      "congress_url": "string"
    }
  ],
  "pagination": { "next_cursor": "string" | null, "has_more": true }
}
```
`stage` 쿼리 파라미터는 콤마로 여러 값 OR 매칭 (프론트 `filterByStage()`가 이미 이 방식으로 구현되어 있음 — `New for anti/policy.js`의 `filterByStage`/`stage_tabs` 참고).

---

## `GET /api/us/congress/policy-areas/{policy_area_id}/bills`
→ `policy_area_detail` 대체. `committee_detail`과 같은 `stage_tabs`/`items`/`pagination` 구조 재사용, `policy_area` 필드만 다음으로 교체:
```json
{ "policy_area": { "policy_area_id": "string", "name": "string", "bill_count": 18 } }
```

---

## `GET /api/us/congress/bills/{bill_id}`
→ `bill_detail` 대체

**Response**:
```json
{
  "bill_id": "string", "title": "string", "sponsor": "string",
  "introduced_date": "YYYY-MM-DD", "current_stage": "string", "current_status": "string",
  "latest_action_date": "YYYY-MM-DD", "summary": "string (abstract only, 전문 금지)",
  "congress_url": "string",
  "committees": [{ "committee_id": "string", "name": "string", "chamber": "string", "official_url": "string" }],
  "votes": [
    {
      "vote_id": "string", "chamber": "house|senate", "vote_date": "YYYY-MM-DD",
      "question": "string", "result": "string",
      "yea_count": 230, "nay_count": 195, "present_count": 0, "not_voting_count": 5,
      "source_url": "string",
      "member_votes_visible": false
    }
  ],
  "official_related_bills": [
    { "bill_id": "string", "title": "string", "relation_type": "string", "relation_origin": "official" }
  ],
  "similar_bills": [
    { "bill_id": "string", "title": "string", "relation_origin": "semantic", "similarity_score": 0.82 }
  ],
  "ui_rules": {
    "show_full_text": false,
    "show_official_related_before_similar": true,
    "show_member_vote_lists": false
  }
}
```
- `similar_bills`는 Gemini 임베딩 기반 semantic similarity (별도 파이프라인, `scripts/yield_model` 담당 영역과 무관 — 정책 임베딩 파이프라인은 아직 미정 사항이니 이 문서 범위 밖).
- `member_votes_visible: false`인 동안은 `votes[].yea_count` 등 집계만 제공, 의원별 투표 리스트는 별도 엔드포인트로 Phase 2에 추가 (지금 계약에 없음).

---

## `GET /api/us/executive/overview`
→ `executive_overview` 대체

**Response**:
```json
{
  "agencies": [
    {
      "agency_id": "string", "name": "string", "short_name": "string",
      "agency_type": "eop|department|independent|sub",
      "parent_agency_id": "string | null",
      "executive_order_count": 2,
      "secretary_placeholder": "string" | null,
      "eo_ids": [99999]
    }
  ],
  "executive_orders": [
    {
      "eo_number": 99999, "title": "string", "signed_date": "YYYY-MM-DD",
      "publication_date": "YYYY-MM-DD", "summary": "string",
      "federal_register_url": "string", "storage_tier": "hot|cold",
      "agency_id": "string"
    }
  ]
}
```
`agency_type`은 화면에서 대통령실 / 부처(내청) / 독립기관(외청) 블록을 나누는 기준이다.
`sub`(하위 기관, 예: IRS·FDA)는 상위 디렉터리 블록에 넣지 않는다 — `parent_agency_id`로
상위 기관 화면에서 보여줄 값이다.

Federal Register API는 이 분류를 주지 않는다(`parent_id`로 상하위만 알 수 있고,
부처와 독립기관은 둘 다 최상위라 구분되지 않는다). 백엔드가 기준 목록으로 채워야 하는
필드이며, 오지 않으면 프론트가 이름 규칙으로 추론한다 —
`New for anti/policy.js`의 `agencyType()`. 추론은 `sub`를 판별하지 못하므로
(`parent_id`를 프론트가 못 봄) 정확한 값은 백엔드에서 와야 한다.
`short_name`은 이름이 30자를 넘을 때 블록 라벨로 쓰인다 (Department of Defense → DOD).

`agencies[].eo_ids`는 `executive_orders[].agency_id`로 그룹핑한 결과와 반드시 일치해야 한다 (프론트가 이 배열로 부처별 EO 허브를 그린다 — `New for anti/policy.js`의 `renderExecutiveHubByAgency()` 참고). `secretary_placeholder`가 `null`이 아니면 실제 장관 정보 대신 이 문구를 보여준다; 실제 장관 데이터가 준비되면 이 필드 자체를 없애고 `secretary: { name, title }` 필드를 추가하는 방식으로 확장할 것 (필드 추가는 breaking change 아님).

---

## `GET /api/us/executive/orders/{eo_number}`
→ `executive_order_detail` 대체

**Response**:
```json
{
  "eo_number": 99999, "title": "string", "signed_date": "YYYY-MM-DD",
  "publication_date": "YYYY-MM-DD", "summary": "string",
  "official_links": { "federal_register_url": "string", "executive_order_url": "string" },
  "agencies": [{ "agency_id": "string", "name": "string" }],
  "legal_authorities": [
    {
      "citation": "string (예: '50 U.S.C. 1701')",
      "official_url": "string",
      "verification_status": "official_metadata|unverified",
      "bill_id": "string" | null
    }
  ],
  "related_regulations": [
    {
      "regulation_id": "string", "title": "string", "document_type": "Rule|Proposed Rule|Notice",
      "abstract": "string",
      "publication_date": "YYYY-MM-DD", "effective_on": "YYYY-MM-DD" | null,
      "federal_register_url": "string", "relation_origin": "official"
    }
  ]
}
```

**중요 — `legal_authorities[].bill_id` 매칭 규칙:**
EO는 보통 법안번호가 아니라 **법전 조항**(U.S. Code citation)을 인용한다. 이 조항이 어떤 법안(Public Law)에서 나왔는지 확인 가능할 때만 `bill_id`를 채우고, 확인 불가하면 반드시 `null`로 둔다. **추측으로 매칭하지 말 것** — 프론트는 `bill_id`가 있고 해당 bill이 실제로 존재할 때만 내부 링크로 렌더링하고, 그 외엔 `official_url` 외부 링크로 폴백한다 (`New for anti/policy.js`의 `renderLegalAuthorities()`/`resolveBillId()` 참고). Congress.gov API의 Public Law 크로스레퍼런스 필드를 활용해 매칭하는 것을 권장.

`related_regulations`는 UI에서 **제목 + document_type + effective_on만** 표시하고 `abstract`는 렌더링하지 않는다 (요약 없이 외부 링크만) — 그래도 `abstract` 필드 자체는 다른 소비자를 위해 계속 채워서 보낼 것.

---

## `GET /api/us/congress/policy-areas`
→ `policy_areas` 대체 (의회 화면의 CRS 정책분야 블록)

```json
[
  { "policy_area_id": "string (slug)", "name": "string", "bill_count": 18 | null }
]
```
Congress.gov의 Policy Area 어휘 전체를 보낼 것. `bill_count`가 아직 집계 안 됐으면 `null` (프론트는 개수를 표시하지 않는다).

---

## `GET /api/us/regulations/cfr-titles/{title_number}`
→ CFR 분류 상세. 해당 Title에 속한 규제와, 그 규제를 낳은 행정명령을 함께 반환한다.

```json
{
  "title_number": 19,
  "name": "Customs Duties",
  "reserved": false,
  "regulations": [
    {
      "regulation_id": "string", "title": "string", "document_type": "Rule|Proposed Rule|Notice",
      "abstract": "string", "publication_date": "YYYY-MM-DD", "effective_on": "YYYY-MM-DD" | null,
      "federal_register_url": "string"
    }
  ],
  "executive_orders": [
    { "eo_number": 99999, "title": "string", "signed_date": "YYYY-MM-DD", "agency_id": "string" }
  ]
}
```
규제는 여기서도 외부 링크 전용이며 목록에 abstract를 렌더링하지 않는다.

---

## `GET /api/us/regulations/cfr-titles`
→ `cfr_titles` 대체

**Response**:
```json
[
  { "title_number": 19, "name": "Customs Duties", "reserved": false, "regulation_count": 4 }
]
```

---

## 변경 이력

- 2026-08-31: 정책분야/CFR 분류 엔드포인트와 `agency_type` 추가. 화면 구조는
  `정책 › 미국 › (의회|행정부) › 상임위·부처·분류 › 법률·행정명령`.
- 2026-08-31: 최초 작성. `New for anti/public/data/ui-policy-mock-data.json`과 1:1 대응 (committee `ranking_member`/`subcommittees`, executive `eo_ids`/`secretary_placeholder`, legal_authorities `bill_id` 포함 — 2026-08-31 UI 반영분 기준).
