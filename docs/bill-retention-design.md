# 법안 종료 데이터 보존·표결 확장 설계안

상태: **구현 준비 완료.** PR 병합 뒤 `supabase/migrations/20260903_policy_bill_retention.sql`을 Supabase SQL Editor에서 한 번 실행해야 활성화된다. 실제 회기 전환 삭제는 기본적으로 dry-run이며, 별도 승인 환경변수가 없으면 실행되지 않는다.

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

**순서 규칙**: 종료 상태를 감지한 동기화는 반드시 `알림 매칭·notifications_queued 삽입 → terminal queue를 skipped 표시 → pruning RPC 호출` 순서로 실행한다. pruning이 먼저 실행되면 `title`·`summary`가 비워져 실패/거부 알림의 키워드 매칭이 조용히 누락될 수 있다.

### 구현 함수와 호출 지점

```text
prune_terminal_bill_details(p_bill_id text) returns (outcome, detail_rows_removed)
```

이 함수는 `bills`를 잠근 뒤 현재 단계가 `failed` 또는 `vetoed`일 때만 실행한다. 하위 행 삭제와 부모 행 최소화는 **하나의 트랜잭션**으로 끝난다. 동기화 스크립트는 법안 upsert와 알림 매칭·큐 삽입을 마친 뒤, 종료 법안을 `skipped`로 표시하고 이 RPC를 호출한다. 공식 소스의 이후 업데이트로 다시 처리된 종료 법안도 안전하게 다시 최소화할 수 있도록 함수는 idempotent다.

`public_laws.bill_id`가 존재하는 법안은 `protected_public_law` 결과로 종료하고 어떤 상세도 삭제하지 않는다. 이는 잘못 분류된 `current_stage` 하나로 제정 법률 연결을 끊는 일을 막는 이중 안전장치다.

DB trigger 대신 명시적 RPC를 우선 제안한다. 이렇게 하면 수동 상태 정정, 초기 데이터 적재, 테스트에서 의도치 않은 대량 삭제를 피할 수 있다. 함수는 idempotent해야 하며, 삭제 행 수·시각은 `data_sync_runs.metadata`에 기록한다.

## C. 새 Congress 시작 시 정리

### 삭제 규칙

활성 Congress 번호가 바뀐 것이 검증된 뒤, 직전 Congress의 다음 법안을 삭제한다.

```text
bills.congress_number = 이전 Congress
and bills.current_stage <> 'enacted'
and not exists (
  select 1
  from public.public_laws pl
  where pl.bill_id = bills.bill_id
)
```

`public_laws`는 `bill_id on delete set null`이므로 제정 법률 메타데이터는 보호된다. 또한 `public_laws` 연결이 있는 법안은 `current_stage` 값이 비정상이어도 rollover purge에서 제외한다. 삭제 대상 법안의 notification·하위 행은 FK cascade 또는 위 최소화 규칙에 따라 제거된다.

`policy_ingestion_queue`는 FK가 없으므로 rollover purge의 같은 트랜잭션에서 대상 법안의 `sync_resource = 'congress.gov:bills' and source_key = bill_id` 행을 **명시적으로 삭제**한다. 그래야 삭제된 법안이 고아 큐로 남거나 이후 재처리되지 않는다.

### 새 회기 감지

1. 일정 후보는 홀수해 1월 3일(예: 2027-01-03)이다.
2. **날짜만으로 삭제하지 않는다.** 일일 실행은 Congress.gov의 current Congress 응답을 읽어 DB에 저장된 활성 번호보다 큰지 확인한다.
3. 번호 변경이 확인되면 `rollover_candidate` 실행 이력에 이전/신규 Congress, 삭제 예정 건수, 샘플 bill ID를 기록한다.
4. 첫 도입 시에는 `dry_run = true`만 실행하고 사람이 건수·Public Law 연결을 확인한다.
5. 별도 환경변수 `ALLOW_CONGRESS_ROLLOVER_PURGE=true`와 승인된 실행에서만 실제 삭제한다. 삭제 후에도 원본 전문은 저장하지 않으므로 복구는 공식 Congress.gov 재동기화에 의존한다.

### 구현된 수동 실행 절차

`scripts/rollover-congress.js`가 먼저 Congress.gov의 현재 Congress 번호를 조회하고, **직전 회기만** 대상으로 삼는다. 날짜만으로는 절대 삭제하지 않는다.

```bash
# 기본값: 삭제하지 않고 후보 최대 25건을 실행 기록에 남긴다.
node scripts/rollover-congress.js

# dry-run 결과를 검토한 뒤에만 실제 삭제를 허용한다.
export ALLOW_CONGRESS_ROLLOVER_PURGE=true
export ROLLOVER_PURGE_MAX_BILLS=1000
node scripts/rollover-congress.js
unset ALLOW_CONGRESS_ROLLOVER_PURGE
```

실제 삭제 RPC도 `p_confirm = true`가 없으면 거부한다. 따라서 (1) 기본 dry-run, (2) 로컬 환경변수 승인, (3) RPC 확인 인자라는 세 겹의 방어가 적용된다. 삭제 건수와 함께 명시적으로 정리된 `policy_ingestion_queue` 행 수를 `data_sync_runs`에 남긴다.

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
