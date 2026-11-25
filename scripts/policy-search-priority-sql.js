'use strict';

function buildPrioritySql({ limit = 25, apply = false } = {}) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error('--limit must be an integer between 1 and 100');
  }

  // 현재 회기와 모델을 운영 색인 기준으로 좁히고, 대기 중인 문서만 선택한다.
  const selection = `with active_congress as (
  select max(congress_number) as number from public.bills
), waiting as (
  select j.document_id, j.source_type, j.source_id, j.priority, j.revision
  from public.policy_search_jobs j
  where j.status = 'queued' and j.claim_token is null
    and j.attempts < 8 and j.retry_at <= now()
    and j.source_type in ('bill', 'public_law')
), eligible as materialized (
  select w.*, b.latest_action_date as source_date, 30 as target_priority
  from waiting w join public.bills b on b.bill_id = w.source_id
  where w.source_type = 'bill' and w.priority < 30
    and b.congress_number = (select number from active_congress)
    and (b.embedding is null or b.embedding_model is distinct from 'gemini-embedding-001')
    and not exists (
      select 1 from public.policy_search_passages p where p.document_id = w.document_id
        and p.embedding is not null and p.embedding_model = 'gemini-embedding-001'
    )
  union all
  select w.*, l.enacted_date, 31 as target_priority
  from waiting w join public.public_laws l on l.public_law_id = w.source_id
  where w.source_type = 'public_law' and w.priority < 31
    and l.congress_number = (select number from active_congress)
    and l.enacted_date between current_date - 90 and current_date
    and not exists (
      select 1 from public.policy_search_passages p where p.document_id = w.document_id
        and p.embedding is not null and p.embedding_model = 'gemini-embedding-001'
    )
), picked as materialized (
  select * from eligible
  order by target_priority desc, source_date desc nulls last, document_id
  limit ${limit}
)`;

  // 실제 반영 시 다시 상태·버전을 확인하고, 다른 실행이 잠근 행은 건너뛴다.
  const promotion = `, locked as materialized (
  select j.document_id, p.target_priority
  from picked p join public.policy_search_jobs j using (document_id)
  where j.status = 'queued' and j.claim_token is null
    and j.attempts < 8 and j.retry_at <= now()
    and j.revision = p.revision and j.priority < p.target_priority
  for update of j skip locked
), promoted as (
  update public.policy_search_jobs j set priority = l.target_priority
  from locked l where j.document_id = l.document_id
  returning j.document_id
)`;

  return `${selection}${apply ? promotion : ''}
select '${apply ? 'apply' : 'preview'}' as mode,
  (select number from active_congress) as congress,
  (select count(*) from eligible where source_type = 'bill') as eligible_bills,
  (select count(*) from eligible where source_type = 'public_law') as eligible_recent_public_laws,
  count(*) as selected,
  ${apply ? '(select count(*) from promoted)' : 'null::bigint'} as promoted,
  coalesce(jsonb_agg(
    jsonb_build_object(
      'document_id', p.document_id,
      'source_date', p.source_date,
      'previous_priority', p.priority,
      'target_priority', p.target_priority,
      'promoted', ${apply ? 'exists(select 1 from promoted m where m.document_id = p.document_id)' : 'null::boolean'}
    ) order by p.target_priority desc, p.source_date desc nulls last, p.document_id
  ), '[]'::jsonb) as documents
from picked p;
`;
}

function main(args) {
  const options = {};
  for (let index = 0; index < args.length; index++) {
    const arg = args[index];
    if (arg === '--apply') options.apply = true;
    else if (arg === '--limit') options.limit = Number(args[++index]);
    else throw new Error(`Unknown option: ${arg}`);
  }
  process.stdout.write(buildPrioritySql(options));
}

module.exports = { buildPrioritySql };
if (require.main === module) {
  try { main(process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
