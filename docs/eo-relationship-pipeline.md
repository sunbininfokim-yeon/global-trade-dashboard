# EO 관계 파이프라인

EO 화면의 기관은 두 관계를 구분한다.

- `issuing_document`: Federal Register EO 문서가 발행기관으로 제공한 기관이다. 역사 EO에서는 대체로 EOP다.
- `implementing_regulation`: Federal Register 규제 문서가 EO 번호를 **명시적으로** 인용하고, 같은 규제 문서가 담당 기관을 제공한 경우의 시행 기관이다.

기관명·EO 제목·키워드가 비슷하다는 이유로 관계를 만들지 않는다. EOP는 발령 주체이고, 시행 부처·외청은 후속 규제의 공식 EO 인용을 통해서만 추가된다.

## 근거 법령

우선순위는 다음과 같다.

1. Federal Register가 제공한 구조화된 `legal_authorities` (`official_metadata`, `verified`)
2. EO 원문의 `By the authority vested ... it is hereby ordered` 권한 조항에서 인용된 정확한 Constitution / USC / Public Law / Statutes at Large / 과거 EO 표기 (`official_text_citation`, `unverified`)

두 번째는 공식 원문에서 인용 문자열만 보존한다. 본문 전체의 키워드 검색이나 LLM 추정은 하지 않는다. Public Law 표기가 하나의 `public_laws.bill_id`로 확인될 때만 내부 법안 링크를 채운다.

## 역사 관계 백필

```bash
export EO_RELATION_BACKFILL=true
export MAX_EO_RELATION_DOCUMENTS=25
export SKIP_EMBEDDINGS=true
node scripts/sync-federal-register.js
```

이 모드는 EO를 하나씩 체크포인트 처리한다. 각 EO의 공식 원문 권한 조항을 적재하고, Federal Register 검색 결과 중 상세 메타데이터가 그 EO 번호를 명시한 `RULE`/`PRORULE`만 규제·시행기관 관계로 적재한다. 로그의 `history complete`가 나올 때까지 같은 명령을 반복한다.

병합 후 먼저 `supabase/migrations/20260903_policy_eo_relationship_pipeline.sql`을 Supabase SQL Editor에서 한 번 실행해야 한다. 마이그레이션만으로 관계 행이 새로 생기지는 않으며, 위 백필 또는 이후의 일일 동기화가 데이터를 채운다.

UI API는 `executive_order_agencies.relationship_type`과 `relation_origin`을 함께 반환해 발령 주체와 시행 기관을 별도 섹션으로 표시해야 한다. `_worker.js`는 Claude 소유이므로 이 응답 형태 변경은 PR 병합 후 Claude가 연결한다.
