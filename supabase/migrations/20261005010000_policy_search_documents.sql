-- Independent search snapshots: never mutate bill lifecycle or send mail.
begin;
set local lock_timeout='2s';
create table if not exists public.policy_search_documents (
  document_id text primary key,
  source_type text not null check (source_type in ('bill','public_law','executive_order','regulation')),
  source_id text not null,
  title text not null,
  document_date date,
  source_url text not null,
  search_text text not null,
  search_vector tsvector generated always as (to_tsvector('simple'::regconfig,search_text)) stored,
  evidence_parts jsonb not null default '[]',
  references_json jsonb not null default '[]',
  coverage jsonb not null default '{}',
  input_hash text not null,
  refreshed_at timestamptz not null default now(),
  unique(source_type,source_id)
);
create index if not exists policy_search_documents_text_idx on public.policy_search_documents using gin(search_vector);
create table if not exists public.policy_search_passages (
  document_id text not null references public.policy_search_documents on delete cascade,
  passage_index integer not null check (passage_index between 0 and 23),
  field text not null,
  text_content text not null,
  source_url text not null,
  target_type text, target_id text,
  input_hash text not null,
  embedding extensions.vector(1536),
  embedding_model text,
  embedded_at timestamptz,
  primary key(document_id,passage_index)
);
create index if not exists policy_search_passages_embedding_idx on public.policy_search_passages
  using hnsw (embedding extensions.vector_cosine_ops) where embedding is not null;
create table if not exists public.policy_search_jobs (
  document_id text primary key,
  source_type text not null, source_id text not null,
  revision bigint not null default 1, claimed_revision bigint,
  status text not null default 'queued' check (status in ('queued','processing','done','failed')),
  claim_token uuid, lease_until timestamptz,
  attempts integer not null default 0,
  retry_at timestamptz not null default now(), last_error text,
  priority integer not null default 0,
  updated_at timestamptz not null default now()
);
alter table public.policy_search_jobs add column if not exists priority integer not null default 0;
create index if not exists policy_search_jobs_pending_idx on public.policy_search_jobs(status,retry_at,updated_at);

create or replace function public.enqueue_policy_search_document(p_type text,p_id text) returns void
language sql security definer set search_path=public,extensions as $$
  insert into policy_search_jobs(document_id,source_type,source_id,priority) values(p_type||':'||p_id,p_type,p_id,20)
  on conflict(document_id) do update set revision=policy_search_jobs.revision+1,
    status=case when policy_search_jobs.status='processing' then 'processing' else 'queued' end,
    attempts=case when policy_search_jobs.status='processing' then policy_search_jobs.attempts else 0 end,
    priority=20,retry_at=now(), updated_at=now(),last_error=null;
$$;
-- Idempotent historical backfill: live changes outrank newest-session bootstrap.
create or replace function public.seed_policy_search_jobs(p_limit int default 1000) returns integer
language plpgsql security definer set search_path=public,extensions as $$
declare inserted integer;
begin
  with active as (select max(congress_number) n from bills), sources as (
    select 'bill' kind,bill_id id,latest_action_date dated,case when congress_number=(select n from active) then 10 else 0 end priority from bills
    union all select 'public_law',public_law_id,enacted_date,case when congress_number=(select n from active) then 10 else 0 end from public_laws
    union all select 'executive_order',eo_number::text,coalesce(signed_date,publication_date),case when coalesce(signed_date,publication_date)>=current_date-interval '2 years' then 10 else 0 end from executive_orders
    union all select 'regulation',regulation_id,publication_date,10 from regulations
  ) insert into policy_search_jobs(document_id,source_type,source_id,priority)
    select kind||':'||id,kind,id,priority from sources s
    where not exists(select 1 from policy_search_jobs j where j.document_id=s.kind||':'||s.id)
    order by priority desc,dated desc nulls last,kind,id limit least(greatest(p_limit,1),1000)
    on conflict(document_id) do nothing;
  get diagnostics inserted=row_count;
  return inserted;
end; $$;
create or replace function public.policy_search_source_changed() returns trigger
language plpgsql security definer set search_path=public,extensions as $$
declare src text:=tg_argv[0]; ident text; r record;
begin
  if tg_op='UPDATE' and
    (to_jsonb(new)->'title',to_jsonb(new)->'law_title',to_jsonb(new)->'summary',to_jsonb(new)->'abstract',to_jsonb(new)->'official_text_url',to_jsonb(new)->'source_updated_at',to_jsonb(new)->'bill_id',to_jsonb(new)->'latest_action_date',to_jsonb(new)->'enacted_date',to_jsonb(new)->'signed_date',to_jsonb(new)->'publication_date')
    is not distinct from
    (to_jsonb(old)->'title',to_jsonb(old)->'law_title',to_jsonb(old)->'summary',to_jsonb(old)->'abstract',to_jsonb(old)->'official_text_url',to_jsonb(old)->'source_updated_at',to_jsonb(old)->'bill_id',to_jsonb(old)->'latest_action_date',to_jsonb(old)->'enacted_date',to_jsonb(old)->'signed_date',to_jsonb(old)->'publication_date') then return new; end if;
  ident:=coalesce(to_jsonb(new),to_jsonb(old))->>tg_argv[1];
  if tg_op='DELETE' then
    delete from policy_search_documents where document_id=src||':'||ident;
    delete from policy_search_jobs where document_id=src||':'||ident;
  else
    perform enqueue_policy_search_document(src,ident);
  end if;
  -- A public law may carry the official summary of its originating bill.
  if src='bill' then
    for r in select public_law_id from public_laws where bill_id=ident
    loop perform enqueue_policy_search_document('public_law',r.public_law_id); end loop;
  end if;
  -- One-hop dependencies only; a cited document changing refreshes its citers.
  for r in select distinct d.source_type,d.source_id from policy_search_documents d,
    jsonb_array_elements(d.references_json) ref
    where ref->>'target_type'=src and ref->>'target_id'=ident
  loop perform enqueue_policy_search_document(r.source_type,r.source_id); end loop;
  return coalesce(new,old);
end; $$;
drop trigger if exists policy_search_bill_changed on public.bills;
create trigger policy_search_bill_changed after insert or delete or update of title,summary,source_updated_at,latest_action_date
  on public.bills for each row execute function public.policy_search_source_changed('bill','bill_id');
drop trigger if exists policy_search_eo_changed on public.executive_orders;
create trigger policy_search_eo_changed after insert or delete or update of title,summary,source_updated_at,signed_date,publication_date
  on public.executive_orders for each row execute function public.policy_search_source_changed('executive_order','eo_number');
drop trigger if exists policy_search_law_changed on public.public_laws;
create trigger policy_search_law_changed after insert or delete or update of law_title,official_text_url,source_updated_at,bill_id,enacted_date
  on public.public_laws for each row execute function public.policy_search_source_changed('public_law','public_law_id');
drop trigger if exists policy_search_reg_changed on public.regulations;
create trigger policy_search_reg_changed after insert or delete or update of title,abstract,source_updated_at,publication_date
  on public.regulations for each row execute function public.policy_search_source_changed('regulation','regulation_id');
create or replace function public.policy_search_bill_detail_changed() returns trigger
language plpgsql security definer set search_path=public,extensions as $$
begin
  perform enqueue_policy_search_document('bill',coalesce(to_jsonb(new),to_jsonb(old))->>'bill_id');
  if tg_op='UPDATE' and old.bill_id is distinct from new.bill_id then
    perform enqueue_policy_search_document('bill',old.bill_id);
  end if;
  return coalesce(new,old);
end; $$;
drop trigger if exists policy_search_bill_text_changed on public.bill_text_versions;
create trigger policy_search_bill_text_changed after insert or delete or update
  on public.bill_text_versions for each row execute function public.policy_search_bill_detail_changed();
drop trigger if exists policy_search_bill_subject_changed on public.bill_subjects;
create trigger policy_search_bill_subject_changed after insert or delete or update
  on public.bill_subjects for each row execute function public.policy_search_bill_detail_changed();

create or replace function public.claim_policy_search_job() returns setof public.policy_search_jobs
language sql security definer set search_path=public,extensions as $$
  update policy_search_jobs j set status='processing',claim_token=gen_random_uuid(),
    lease_until=now()+interval '15 minutes',claimed_revision=revision,attempts=attempts+1
  where j.document_id=(select document_id from policy_search_jobs
    where (status in ('queued','failed') and retry_at<=now() and attempts<8)
       or (status='processing' and lease_until<now())
    order by priority desc,updated_at,document_id for update skip locked limit 1)
  returning j.*;
$$;
create or replace function public.finish_policy_search_job(p_id text,p_token uuid,p_error text default null) returns boolean
language plpgsql security definer set search_path=public,extensions as $$
begin
  update policy_search_jobs set status=case when revision<>claimed_revision then 'queued'
    when p_error is null then 'done' else 'failed' end,
    last_error=left(p_error,240),retry_at=now()+case when revision<>claimed_revision or p_error is null then interval '0'
      else interval '5 minutes'*least(attempts,12) end,claim_token=null,lease_until=null,
    attempts=case when revision<>claimed_revision or p_error is null then 0 else attempts end
    where document_id=p_id and claim_token=p_token;
  return found;
end; $$;

create or replace function public.save_policy_search_document(p_document jsonb,p_passages jsonb,p_token uuid)
returns boolean language plpgsql security definer set search_path=public,extensions as $$
declare ident text:=p_document->>'document_id'; item jsonb; job policy_search_jobs;
begin
  select * into job from policy_search_jobs where document_id=ident for update;
  if not found or p_token is null or job.claim_token is distinct from p_token or job.status<>'processing' or job.lease_until<now() then
    raise exception 'search job lease is no longer owned';
  end if;
  if job.revision<>job.claimed_revision then return false; end if;
  if ident<>job.source_type||':'||job.source_id or p_document->>'source_type'<>job.source_type
    or p_document->>'source_id'<>job.source_id then raise exception 'search document identity mismatch'; end if;
  if jsonb_array_length(p_passages)>24 then raise exception 'passage cap exceeded'; end if;
  insert into policy_search_documents(document_id,source_type,source_id,title,document_date,source_url,
    search_text,evidence_parts,references_json,coverage,input_hash)
  values(ident,job.source_type,job.source_id,p_document->>'title',(p_document->>'document_date')::date,
    p_document->>'source_url',p_document->>'search_text',p_document->'evidence_parts',p_document->'references',
    jsonb_build_object('text_status',p_document->>'text_status','embedding_coverage',p_document->>'embedding_coverage',
      'available_passages',p_document->'available_passages','body_characters',p_document->'body_characters',
      'retained_body_characters',p_document->'retained_body_characters','resolved_references',p_document->'resolved_references',
      'reference_count',p_document->'reference_count','version',p_document->>'version'),p_document->>'input_hash')
  on conflict(document_id) do update set title=excluded.title,document_date=excluded.document_date,
    source_url=excluded.source_url,search_text=excluded.search_text,evidence_parts=excluded.evidence_parts,
    references_json=excluded.references_json,coverage=excluded.coverage,input_hash=excluded.input_hash,refreshed_at=now();
  for item in select value from jsonb_array_elements(p_passages) loop
    insert into policy_search_passages(document_id,passage_index,field,text_content,source_url,target_type,target_id,
      input_hash,embedding,embedding_model,embedded_at)
    values(ident,(item->>'passage_index')::int,item->>'field',item->>'text',item->>'source_url',
      item->>'target_type',item->>'target_id',item->>'input_hash',
      case when item->'embedding' is not null and item->'embedding'<>'null'::jsonb then (item->'embedding')::text::extensions.vector(1536) else null end,
      item->>'embedding_model',case when item->'embedding' is not null and item->'embedding'<>'null'::jsonb then now() end)
    on conflict(document_id,passage_index) do update set field=excluded.field,text_content=excluded.text_content,
      source_url=excluded.source_url,target_type=excluded.target_type,target_id=excluded.target_id,input_hash=excluded.input_hash,
      embedding=case when excluded.embedding is not null then excluded.embedding
        when policy_search_passages.input_hash=excluded.input_hash then policy_search_passages.embedding end,
      embedding_model=case when excluded.embedding is not null then excluded.embedding_model
        when policy_search_passages.input_hash=excluded.input_hash then policy_search_passages.embedding_model end,
      embedded_at=case when excluded.embedding is not null then now()
        when policy_search_passages.input_hash=excluded.input_hash then policy_search_passages.embedded_at end;
  end loop;
  delete from policy_search_passages where document_id=ident and passage_index>=jsonb_array_length(p_passages);
  return true;
end; $$;

create or replace function public.search_policy_document_vectors(p_query_embedding extensions.vector(1536),
  p_embedding_model text,p_result_limit int default 50)
returns table(source_type text,source_id text,title text,similarity_score double precision)
language sql stable set search_path=public,extensions as $$
  with nearest as (
    select p.document_id,p.embedding<=>p_query_embedding distance
    from policy_search_passages p where p.embedding is not null and p.embedding_model=p_embedding_model
    order by p.embedding<=>p_query_embedding limit least(greatest(p_result_limit,1),100)*24
  )
  select d.source_type,d.source_id,d.title,(1-n.distance)::double precision
  from (select document_id,min(distance) distance from nearest group by document_id) n
  join policy_search_documents d using(document_id)
  order by 4 desc,d.document_id limit least(greatest(p_result_limit,1),100);
$$;
-- No full text crosses the public request boundary. Return only bounded proof
-- windows; JS applies word-boundary verification before claiming N/N matches.
create or replace function public.search_policy_document_terms(p_terms jsonb,p_limit int default 60)
returns table(source_type text,source_id text,title text,source_url text,document_date date,
  evidence_parts jsonb,coverage jsonb,refresh_pending boolean)
language sql stable set search_path=public,extensions as $$
  with matches as (
    select d.document_id,term->>'key' term_key,
      (part-'text')||jsonb_build_object('text',substring(part->>'text'
        from greatest(1,pos.value-100) for 360)) evidence,
      row_number() over(partition by d.document_id,term->>'key' order by
        case part->>'field' when 'title' then 0 when 'summary' then 1 when 'subjects' then 2 when 'body' then 3 else 4 end,
        length(alias) desc,part->>'source_url',pos.value) ordinal
    from policy_search_documents d,jsonb_array_elements(d.evidence_parts) part,
      jsonb_array_elements(p_terms) term,jsonb_array_elements_text(term->'aliases') alias,
      lateral (select regexp_instr(lower(part->>'text'),
        case when alias~'^[a-z0-9]' then '(^|[^a-z0-9])' else '' end
        ||replace(alias,' ','[[:space:]-]+')||case when alias~'[a-z0-9]$' then '([^a-z0-9]|$)' else '' end) value) pos
    where d.search_vector @@ (select string_agg('('||plainto_tsquery('simple',a)::text||')',' | ')::tsquery
      from jsonb_array_elements(p_terms) t,jsonb_array_elements_text(t->'aliases') a)
      and pos.value>0
  ), proof as (
    select document_id,count(distinct term_key) hits,jsonb_agg(evidence order by term_key,ordinal) parts
    from matches where ordinal<=3 group by document_id
  ) select d.source_type,d.source_id,d.title,d.source_url,d.document_date,
    (select jsonb_agg(value) from (select value from jsonb_array_elements(proof.parts) limit 30) t),
    d.coverage,coalesce(j.status<>'done',false)
  from proof join policy_search_documents d using(document_id) left join policy_search_jobs j using(document_id)
  order by proof.hits desc,d.document_date desc nulls last,d.document_id
  limit least(greatest(p_limit,1),100);
$$;
create or replace function public.policy_search_status() returns jsonb
language sql stable set search_path=public,extensions as $$
  select jsonb_build_object('database_bytes',pg_database_size(current_database()),
    'documents',(select count(*) from policy_search_documents),
    'passages',(select count(*) from policy_search_passages),'embedded_passages',(select count(*) from policy_search_passages where embedding is not null),
    'partial_vector_documents',(select count(*) from policy_search_documents where coverage->>'embedding_coverage'='partial'),
    'without_body',(select count(*) from policy_search_documents where coverage->>'text_status'='unavailable'),
    'pending',(select count(*) from policy_search_jobs where status in ('queued','processing')),
    'failed',(select count(*) from policy_search_jobs where status='failed'),
    'last_refreshed_at',(select max(refreshed_at) from policy_search_documents));
$$;

alter table policy_search_documents enable row level security;
alter table policy_search_passages enable row level security;
alter table policy_search_jobs enable row level security;
revoke all on policy_search_documents,policy_search_passages,policy_search_jobs from public,anon,authenticated;
grant all on policy_search_documents,policy_search_passages,policy_search_jobs to service_role;
revoke all on function enqueue_policy_search_document(text,text),seed_policy_search_jobs(integer),policy_search_source_changed(),policy_search_bill_detail_changed(),claim_policy_search_job(),
  finish_policy_search_job(text,uuid,text),save_policy_search_document(jsonb,jsonb,uuid),
  search_policy_document_vectors(extensions.vector,text,integer),search_policy_document_terms(jsonb,integer),policy_search_status() from public,anon,authenticated;
grant execute on function enqueue_policy_search_document(text,text),seed_policy_search_jobs(integer),claim_policy_search_job(),finish_policy_search_job(text,uuid,text),
  save_policy_search_document(jsonb,jsonb,uuid),search_policy_document_vectors(extensions.vector,text,integer),
  search_policy_document_terms(jsonb,integer),policy_search_status() to service_role;
notify pgrst,'reload schema';
commit;
