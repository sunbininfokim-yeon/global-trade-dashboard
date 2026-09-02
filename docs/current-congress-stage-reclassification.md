# 현재 Congress 법안 단계 재판정

이 절차는 `scripts/sync-congress.js`가 action 이력 기반 단계 판정을 지원하는 버전으로 배포된 뒤에만 사용한다. 과거 회기나 실패 큐를 되살리지 않고, 현재 Congress에서 이미 성공 처리된 법안만 다시 처리한다.

## 1. 적용 전 확인

Supabase SQL Editor에서 먼저 단계 분포를 기록한다.

```sql
select current_stage, count(*) as bill_count
from public.bills
where congress_number = 119
group by current_stage
order by current_stage;
```

## 2. 현재 Congress의 성공 큐만 재등록

`119`는 실행 시점의 active Congress 번호로 바꾼다. 이 SQL은 `succeeded`인 Congress.gov 법안만 `pending`으로 되돌린다. `failed`, `processing`, 다른 데이터 소스, 다른 Congress는 건드리지 않는다.

```sql
begin;

update public.policy_ingestion_queue as queue
set
  status = 'pending',
  attempts = 0,
  available_at = now(),
  claimed_at = null,
  completed_at = null,
  last_error = null
from public.bills as bill
where queue.sync_resource = 'congress.gov:bills'
  and queue.status = 'succeeded'
  and queue.source_key = bill.bill_id
  and bill.congress_number = 119;

commit;
```

## 3. 로컬에서 큐를 비울 때까지 동기화

이후 기존의 로컬 환경변수를 사용해 `node scripts/sync-congress.js`를 반복 실행한다. 각 index 법안은 공식 action 이력을 **읽어** 단계만 다시 계산하며, `reported` 이상이 아니면 action·표결·본문 상세를 저장하지 않는다.

완료 여부는 다음 SQL로 확인한다.

```sql
select status, count(*) as queue_count
from public.policy_ingestion_queue
where sync_resource = 'congress.gov:bills'
group by status
order by status;
```

`pending`과 `processing`이 0이면 재판정은 끝난다. `failed`는 자동으로 되살리지 말고 `last_error`를 검토한다.
