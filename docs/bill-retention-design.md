# 법안 종료 데이터 보존·표결 확장 설계안

상태: **검토용 설계안. 아직 스키마·동기화 스크립트·Supabase에는 적용하지 않는다.**

이 문서는 두 정책을 안전하게 구현하기 위한 다음 단계의 설계다.

1. 상임위 markup 표결만 의원별 찬성·반대 명단을 노출한다.
2. `failed` 또는 `vetoed` 법안은 최소 색인만 남기고 상세 데이터를 제거한다.
3. 새 Congress 시작 후 직전 Congress에서 제정되지 않은 법안을 완전히 삭제한다.

## A. 표결 단계와 의원별 표결

### 현재 상태

- `bill_votes`는 본회의 roll call 중심의 집계 필드만 있으며, 상임위/본회의 구분이 없다.
- `bill_actions.committee_id`는 스키마에 있으나 현 수집기가 채우지 않는다.
- `bill_vote_members`는 테이블만 있고 현 수집기는 행을 적재하지 않는다.

따라서 현재 `bill_actions.committee_id`만으로는 표결이 상임위 markup인지 판별할 수 없다.

### 향후 스키마 변경안

별도 승인 후 새 마이그레이션에서 다음을 추가한다.

```text
bill_votes.vote_stage             'committee' | 'floor' | 'unknown'
bill_votes.source_action_id       → bill_actions.bill_action_id (nullable)
bill_votes.committee_id           → committees.committee_id (nullable)
bill_votes.member_coverage        'complete' | 'partial' | 'unavailable'

bills.sponsor_party               발의 당시 정당 코드 (nullable)
bills.sponsor_party_source_url    공식 출처
bills.sponsor_party_as_of         확인 시각
```

`vote_stage = 'committee'`는 공식 상임위 출처가 markup/committee vote로 식별할 때만 설정한다. 단순히 표결일의 `bill_committees` 행이 존재한다는 이유만으로는 설정하지 않는다. 다른 표결은 `floor` 또는 `unknown`으로 남긴다.

### 향후 수집 규칙

1. Congress.gov 액션의 원본 URL·action ID를 먼저 `source_action_id`에 연결한다.
2. 상임위 markup 결과와 구성원별 표결은 House/Senate의 공식 위원회 출처가 명시적으로 제공할 때만 수집한다.
3. 명단이 전체인지 검증할 수 없으면 `member_coverage = 'partial'` 또는 `unavailable`로 저장하고 UI에 의원별 명단을 노출하지 않는다.
4. 본회의 표결은 원칙적으로 집계만 표시한다. 구성원 행이 소스에 있더라도 이 UI에서는 숨긴다.
5. 교차정당 지지 기능은 `sponsor_party`와 `bill_vote_members.party`가 모두 공식 출처·시점과 함께 확보된 후에만 활성화한다.

## B. 실패·거부 법안의 즉시 최소화

### 보존 레코드

`bills.current_stage in ('failed', 'vetoed')`가 **새 동기화 결과에서 처음 감지**되면, 아래 업무 필드만 남긴다.

```text
bill_id, congress_number, bill_type, bill_number,
title, sponsor, current_stage, current_status,
latest_action_date, congress_url
```

PostgreSQL의 필수 시스템 필드(`created_at`, `updated_at`, `detail_level`, `storage_tier`, `raw_source`)는 물리적으로 남아야 한다. 이들은 입법 콘텐츠가 아닌 운영 메타데이터로 취급한다. 최소화 후에는 다음처럼 값만 정리한다.

- `detail_level = 'index'`, `storage_tier = 'cold'`
- `summary`, `summary_source`, `summary_updated_at`, `embedding`, `embedding_model`, `embedded_at`, `policy_area_id`, `sponsor_bioguide_id`, `introduced_date`, `latest_action_text`, `law_type`, `law_number`을 `NULL`
- `raw_source`는 원본 상세 JSON을 제거하고 `{ source, retention: 'terminal_minimal', pruned_at }` 같은 최소 운영 메타데이터로 교체

### 삭제 대상

같은 원자적 DB 함수 안에서 다음 행을 삭제한다.

```text
bill_summaries
bill_text_versions
bill_actions
bill_status_history
bill_committees
bill_subjects
bill_votes
bill_vote_members
bill_relations (source_bill_id 또는 target_bill_id가 해당 bill_id인 모든 행)
```

`notifications_queued`는 아직 발송 기능이 없고 향후 구독 이력을 위해 즉시 삭제하지 않는다. 다만 최종 법안 행 삭제 때 FK cascade로 삭제된다. `policy_ingestion_queue`의 해당 법안은 `skipped`로 표시해 다음 일일 실행에서 상세 데이터가 재적재되지 않게 한다. 이후 공식 상태가 달라져 `enacted` 등으로 변경되면 수집기가 queue를 다시 `pending`으로 전환하고 상세를 재수집할 수 있어야 한다.

### 제안 함수와 호출 지점

```text
prune_terminal_bill_details(p_bill_id text) returns void
```

이 함수는 `bills`를 잠근 뒤 현재 단계가 `failed` 또는 `vetoed`일 때만 실행한다. 하위 행 삭제와 부모 행 최소화는 **하나의 트랜잭션**으로 끝나야 한다. 동기화 스크립트는 법안 upsert와 상태 이력 기록 후, 직전 단계가 비종료이고 새 단계가 종료일 때 이 RPC를 한 번 호출한다.

DB trigger 대신 명시적 RPC를 우선 제안한다. 이렇게 하면 수동 상태 정정, 초기 데이터 적재, 테스트에서 의도치 않은 대량 삭제를 피할 수 있다. 함수는 idempotent해야 하며, 삭제 행 수·시각은 `data_sync_runs.metadata`에 기록한다.

## C. 새 Congress 시작 시 정리

### 삭제 규칙

활성 Congress 번호가 바뀐 것이 검증된 뒤, 직전 Congress의 다음 법안을 삭제한다.

```text
bills.congress_number = 이전 Congress
and bills.current_stage <> 'enacted'
```

`public_laws`는 `bill_id on delete set null`이므로 제정 법률 메타데이터는 보호된다. 삭제 대상 법안의 notification·하위 행은 FK cascade 또는 위 최소화 규칙에 따라 제거된다.

### 새 회기 감지

1. 일정 후보는 홀수해 1월 3일(예: 2027-01-03)이다.
2. **날짜만으로 삭제하지 않는다.** 일일 실행은 Congress.gov의 current Congress 응답을 읽어 DB에 저장된 활성 번호보다 큰지 확인한다.
3. 번호 변경이 확인되면 `rollover_candidate` 실행 이력에 이전/신규 Congress, 삭제 예정 건수, 샘플 bill ID를 기록한다.
4. 첫 도입 시에는 `dry_run = true`만 실행하고 사람이 건수·Public Law 연결을 확인한다.
5. 별도 환경변수 `ALLOW_CONGRESS_ROLLOVER_PURGE=true`와 승인된 실행에서만 실제 삭제한다. 삭제 후에도 원본 전문은 저장하지 않으므로 복구는 공식 Congress.gov 재동기화에 의존한다.

### 운영 안전장치

- 한 실행에 삭제 가능한 최대 행 수를 둔다. 초과하면 실패시키고 수동 검토한다.
- 이전 Congress 이외의 행은 절대 삭제하지 않는다.
- `enacted` 행, `public_laws`, `us_code_*`는 rollover purge 대상이 아니다.
- 삭제 전 `data_sync_runs`에 계획, 삭제 후 실제 행 수와 오류를 기록한다.
- GitHub Actions에는 동시 실행 방지(concurrency)를 유지한다.

## 구현 전 결정이 필요한 항목

1. `notifications_queued`를 종료 법안 최소화 때 보존할지 즉시 삭제할지.
2. `other` 상태도 회기 종료 purge에 포함할지 (현재 제안은 `current_stage <> 'enacted'`이므로 포함).
3. 상임위 markup 표결의 공식 원천을 House, Senate 어느 페이지/API로 고정할지.
4. rollover 실제 삭제를 자동 실행할지, 매 회기 사람 승인으로 실행할지. 초기 권고안은 사람 승인이다.
