# EO 관계 파이프라인

EO 화면의 기관은 두 관계를 구분한다.

- `issuing_document`: Federal Register EO 문서가 발행기관으로 제공한 기관이다. 역사 EO에서는 대체로 EOP다.
- `implementing_regulation`: Federal Register 규제 문서가 EO 번호를 **명시적으로** 인용하고, 같은 규제 문서가 담당 기관을 제공한 경우의 시행 기관이다.
- `directed_agency`: EO 공식 원문에서 장관·청장 등이 `shall`, `must`, `is directed to`의 명시적 명령 주체로 등장한 기관이다.
- `coordinating_agency`: 원문이 `in coordination with` 또는 `coordinate with`로 명시한 협업 기관이다.
- `consulted_agency`: 원문이 `in consultation with`로 명시한 협의 기관이다.

기관명·EO 제목·키워드가 비슷하다는 이유로 관계를 만들지 않는다. EOP는 발령 주체이고, 시행 부처·외청은 후속 규제의 공식 EO 인용을 통해서만 추가된다.
원문 역할 관계는 `evidence_excerpt`, `evidence_section`, `source_url`을 함께 저장한다. 따라서 UI는 “어떤 문장 때문에 이 부처가 표시됐는지”를 보여 줄 수 있다.

## 근거 법령

우선순위는 다음과 같다.

1. Federal Register가 제공한 구조화된 `legal_authorities` (`official_metadata`, `verified`)
2. EO 원문의 `By the authority vested ... it is hereby ordered` 권한 조항에서 인용된 정확한 Constitution / USC / Public Law / Statutes at Large / 과거 EO 표기 (`official_text_citation`, `unverified`)

두 번째는 공식 원문에서 인용 문자열만 보존한다. 본문 전체의 키워드 검색이나 LLM 추정은 하지 않는다. Public Law 표기가 하나의 `public_laws.bill_id`로 확인될 때만 내부 법안 링크를 채운다.

## Federal Register가 차단된 경우

이미 끝난 `EO_BACKFILL`은 EO 번호·제목·날짜 등 **기본 메타데이터** 백필이다. 법령·기관·규제 관계는 별도 원문과 인용 데이터가 있어야 채워진다. Federal Register API 차단은 기존 역사 관계 검색을 멈추게 하지만, 다음 두 작업 전체를 막지는 않는다.

1. 일일 신규 EO/규제 동기화는 차단이 풀린 뒤 이어진다.
2. GovInfo 또는 NARA 등에서 별도로 확보한 공식 EO 원문은 로컬 캐시로 검증·적재할 수 있다. 캐시 파일은 문서번호별 JSON이며, 반드시 공식 URL과 원문을 함께 보존한다.

```json
{
  "official_url": "https://www.govinfo.gov/content/pkg/...",
  "text": "공식 EO 원문 전체"
}
```

캐시 디렉터리에 `94-20873.json`처럼 Federal Register 문서번호와 같은 이름으로 저장한 뒤 아래 명령을 실행한다. 이 명령은 Federal Register에 요청하지 않고 Gemini도 사용하지 않는다.

```bash
export EO_OFFICIAL_TEXT_CACHE_DIR='/absolute/path/to/official-eo-cache'
export MAX_EO_TEXT_CACHE_DOCUMENTS=50
node scripts/backfill-eo-text-relations.js
```

## 역사 관계 백필

```bash
export EO_RELATION_BACKFILL=true
export SKIP_EMBEDDINGS=true
node scripts/sync-federal-register.js
```

이 모드는 EO를 하나씩 체크포인트 처리한다. 각 EO의 공식 원문 권한 조항을 적재하고, Federal Register 검색 결과 중 상세 메타데이터가 그 EO 번호를 명시한 `RULE`/`PRORULE`만 규제·시행기관 관계로 적재한다. 로그의 `history complete`가 나올 때까지 같은 명령을 반복한다.

Federal Register의 자동 차단을 피하기 위해 이 모드의 기본값은 상세 요청 동시 1건,
페이지 5건, 요청 간격 1초다. 속도를 높이는 값은 역사 백필에서 사용하지 않는다.
`HTTP 403 ... IP address has been blocked`가 나오면 프로그램은 **현재 페이지 체크포인트를
넘기지 않고 실패 종료**한다. 즉시 재시작하지 말고 충분히 기다린 뒤 같은 명령으로
재개하면 같은 페이지를 다시 처리한다. 이전 버전에서 이미 `documents skipped`로 넘어간
페이지는 아래처럼 해당 EO부터 한 번 되돌린 뒤 재시도해야 한다. 이 SQL은 실제 EO 번호를
확인한 뒤에만 실행한다.

```sql
-- 예시: EO 12924의 첫 페이지부터 관계 백필을 다시 시작한다.
update public.data_sync_state
set cursor = jsonb_build_object(
  'mode', 'eo_relation_backfill',
  'from_date', '1994-01-01',
  'to_date', '2026-09-01',
  'after_eo_number', 12923,
  'page', 1
),
updated_at = now()
where sync_resource = 'federalregister.gov:eo-relationships:bootstrap';
```

병합 후 먼저 `supabase/migrations/20260905_policy_eo_provenance_and_committee_memberships.sql`을 Supabase SQL Editor에서 한 번 실행해야 한다. 마이그레이션만으로 관계 행이 새로 생기지는 않으며, 위 백필 또는 이후의 일일 동기화가 데이터를 채운다.

UI API는 `executive_order_agencies.relationship_type`과 `relation_origin`을 함께 반환해 발령 주체와 시행 기관을 별도 섹션으로 표시해야 한다. `_worker.js`는 Claude 소유이므로 이 응답 형태 변경은 PR 병합 후 Claude가 연결한다.
