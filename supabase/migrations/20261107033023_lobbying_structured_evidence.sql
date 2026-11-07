begin;

create table public.lobby_principals (
  record_id text primary key references public.lobby_records(record_id),
  source_version text not null,
  name text not null,
  country_raw text,
  country_codes text[] not null default '{}',
  entity_kind text not null default 'unknown',
  classification_status text not null default 'unclassified',
  government_control text not null default 'unknown',
  evidence jsonb not null,
  updated_at timestamptz not null default now()
);

create table public.lobby_structure_jobs (
  record_id text not null references public.lobby_records(record_id),
  source_version text not null,
  profile text not null,
  next_ordinal integer not null default 0,
  status text not null default 'pending' check(status in ('pending','running','partial','complete','error','stale')),
  lease_owner uuid,
  lease_until timestamptz,
  last_attempt_at timestamptz,
  last_error text,
  primary key(record_id,source_version,profile)
);

create table public.lobby_passages (
  passage_id text primary key,
  record_id text not null references public.lobby_records(record_id),
  source_version text not null,
  profile text not null,
  ordinal integer not null check(ordinal>=0),
  content text not null check(length(content) between 1 and 4000),
  locator jsonb not null,
  extraction_model text not null,
  extraction jsonb not null,
  embedding extensions.vector(1536) not null,
  embedding_model text not null check(embedding_model='gemini-embedding-001'),
  created_at timestamptz not null default now(),
  unique(record_id,source_version,profile,ordinal)
);
create index lobby_passages_record on public.lobby_passages(record_id,source_version);
create index lobby_passages_vector on public.lobby_passages using hnsw(embedding extensions.vector_cosine_ops);

create table public.lobby_activity_units (
  unit_id text primary key,
  passage_id text not null references public.lobby_passages(passage_id),
  record_id text not null references public.lobby_records(record_id),
  group_key text not null,
  grain text not null check(grain in ('contact','narrative','filing_issue_block')),
  occurred_on date,
  principal_country text,
  principal_kind text not null,
  recipient_branches text[] not null default '{}',
  review_status text not null check(review_status in ('machine_extracted','source_structured')),
  detail jsonb not null,
  search_vector tsvector generated always as (to_tsvector('simple',detail::text)) stored
);
create index lobby_units_record on public.lobby_activity_units(record_id);
create index lobby_units_passage on public.lobby_activity_units(passage_id);
create index lobby_units_country on public.lobby_activity_units(principal_country,principal_kind);
create index lobby_units_recipients on public.lobby_activity_units using gin(recipient_branches);
create index lobby_units_search on public.lobby_activity_units using gin(search_vector);

create function public.lobby_refresh_principals(p_limit integer default 1000)
returns integer language plpgsql security invoker set search_path=public,pg_temp as $$
declare changed integer;
begin
  insert into lobby_principals(record_id,source_version,name,country_raw,country_codes,entity_kind,classification_status,evidence)
  select r.record_id,r.payload_hash||':'||coalesce(r.body_sha256,''),r.client_name,r.country_raw,r.country_codes,
    case when r.client_name ~* '(^Embassy of |^Ministry of |^Government of )' then 'government' else 'unknown' end,
    case when r.client_name ~* '(^Embassy of |^Ministry of |^Government of )' then 'name_hint' else 'unclassified' end,
    jsonb_build_object('source_url',r.source_url,'json_path',case when r.source='lda' then '$.client' else '$.Foreign Principal' end,
      'name',r.client_name,'country_raw',r.country_raw)
  from lobby_records r left join lobby_principals p using(record_id)
  where (r.kind='principal' or r.source='lda') and nullif(r.client_name,'') is not null
    and p.source_version is distinct from r.payload_hash||':'||coalesce(r.body_sha256,'')
  order by r.record_id limit least(greatest(p_limit,1),2000)
  on conflict(record_id) do update set source_version=excluded.source_version,name=excluded.name,
    country_raw=excluded.country_raw,country_codes=excluded.country_codes,entity_kind=excluded.entity_kind,
    classification_status=excluded.classification_status,evidence=excluded.evidence,updated_at=now();
  get diagnostics changed=row_count;
  return changed;
end $$;

create function public.lobby_claim_structure(p_owner uuid,p_profile text)
returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare chosen record; result jsonb;
begin
  select r.record_id,r.payload_hash||':'||coalesce(r.body_sha256,'') as version into chosen
  from lobby_records r left join lobby_structure_jobs j on j.record_id=r.record_id
    and j.source_version=r.payload_hash||':'||coalesce(r.body_sha256,'') and j.profile=p_profile
  where r.kind='document' and r.text_state='extracted'
    and (j.record_id is null or (j.status in ('pending','partial','error','running')
      and coalesce(j.lease_until,'-infinity')<now()
      and (j.status<>'error' or j.last_attempt_at<now()-interval '1 hour')))
  order by j.last_attempt_at nulls first,r.source_date desc nulls last,r.record_id
  limit 1 for update of r skip locked;
  if not found then return null; end if;
  insert into lobby_structure_jobs(record_id,source_version,profile,status,lease_owner,lease_until,last_attempt_at)
    values(chosen.record_id,chosen.version,p_profile,'running',p_owner,now()+interval '10 minutes',now())
  on conflict(record_id,source_version,profile) do update
    set status='running',lease_owner=p_owner,lease_until=now()+interval '10 minutes',last_attempt_at=now(),last_error=null
  returning jsonb_build_object('record_id',record_id,'source_version',source_version,'next_ordinal',next_ordinal) into result;
  return result;
end $$;

create function public.lobby_commit_structure(p_owner uuid,p_record_id text,p_version text,p_profile text,p_passage jsonb,p_units jsonb)
returns void language plpgsql security invoker set search_path=public,extensions,pg_temp as $$
declare job lobby_structure_jobs; unit jsonb; passage_key text; i integer:=0; current_version text;
begin
  select payload_hash||':'||coalesce(body_sha256,'') into current_version from lobby_records where record_id=p_record_id for share;
  if current_version is distinct from p_version then raise exception 'Source changed during extraction'; end if;
  select * into job from lobby_structure_jobs where record_id=p_record_id and source_version=p_version and profile=p_profile for update;
  if job.lease_owner is distinct from p_owner or job.lease_until<now() then raise exception 'Structure lease lost'; end if;
  if job.next_ordinal is distinct from (p_passage->>'ordinal')::integer then raise exception 'Unexpected passage cursor'; end if;
  if jsonb_typeof(p_units)<>'array' or jsonb_array_length(p_units)>100 then raise exception 'Invalid units'; end if;
  passage_key=p_passage->>'passage_id';
  insert into lobby_passages values(passage_key,p_record_id,p_version,p_profile,job.next_ordinal,
    p_passage->>'content',p_passage->'locator',p_passage->>'extraction_model',p_passage->'extraction',
    (p_passage->>'embedding')::extensions.vector(1536),'gemini-embedding-001',now());
  for unit in select value from jsonb_array_elements(p_units) loop
    if nullif(unit->>'quote','') is null or position(regexp_replace(unit->>'quote','\s+',' ','g') in
      regexp_replace(p_passage->>'content','\s+',' ','g'))=0 then raise exception 'Quote not in passage'; end if;
    insert into lobby_activity_units(unit_id,passage_id,record_id,group_key,grain,occurred_on,principal_country,
      principal_kind,recipient_branches,review_status,detail)
    values(passage_key||':'||i,passage_key,p_record_id,
      case when unit->>'grain'='filing_issue_block' then p_record_id||':'||(p_passage->'locator'->>'json_path') else passage_key||':'||i end,
      unit->>'grain',nullif(unit->>'date','')::date,unit->'principal'->>'country',coalesce(unit->'principal'->>'kind','unknown'),
      array(select distinct value->>'branch' from jsonb_array_elements(unit->'recipients')),
      unit->>'review_status',unit);
    i=i+1;
  end loop;
  update lobby_structure_jobs set next_ordinal=next_ordinal+1,lease_until=now()+interval '10 minutes'
    where record_id=p_record_id and source_version=p_version and profile=p_profile;
end $$;

create function public.lobby_finish_structure(p_owner uuid,p_record_id text,p_version text,p_profile text,p_complete boolean,p_error text default null)
returns void language sql security invoker set search_path=public,pg_temp as $$
  update lobby_structure_jobs set status=case when p_error is not null then 'error' when p_complete then 'complete' else 'partial' end,
    last_error=left(p_error,250),lease_owner=null,lease_until=null
  where record_id=p_record_id and source_version=p_version and profile=p_profile and lease_owner=p_owner;
$$;

-- Old source versions remain auditable and drop out of current search immediately.
create view public.lobby_current_units with(security_invoker=true) as
  select u.*,r.source,r.source_url,r.registrant_name,r.source_date,p.locator,p.content,p.embedding,p.embedding_model,p.profile
  from lobby_activity_units u join lobby_passages p using(passage_id) join lobby_records r on r.record_id=u.record_id
  where p.source_version=r.payload_hash||':'||coalesce(r.body_sha256,'');

create function public.lobby_explore(p_filters jsonb default '{}',p_embedding extensions.vector(1536) default null)
returns jsonb language plpgsql stable security invoker set search_path=public,extensions,pg_temp as $$
declare result jsonb;
begin
  with filtered as materialized (
    select u.* from lobby_current_units u where u.profile='lobby-evidence-v1'
      and (nullif(p_filters->>'source','') is null or u.source=p_filters->>'source')
      and (nullif(p_filters->>'country','') is null or u.principal_country=p_filters->>'country')
      and (nullif(p_filters->>'principal_kind','') is null or u.principal_kind=p_filters->>'principal_kind')
      and (nullif(p_filters->>'branch','') is null or p_filters->>'branch'=any(u.recipient_branches))
      and (nullif(p_filters->>'recipient','') is null or exists(select 1 from jsonb_array_elements(u.detail->'recipients') actor where actor->>'name'=p_filters->>'recipient'))
      and (nullif(p_filters->>'record_id','') is null or u.record_id=p_filters->>'record_id')
      and (nullif(p_filters->>'q','') is null or p_embedding is not null or u.search_vector @@ plainto_tsquery('simple',p_filters->>'q'))
  ), ranked as (
    select f.*,case when p_embedding is null then null else 1-(embedding<=>p_embedding) end as similarity
    from filtered f where p_embedding is null or embedding_model='gemini-embedding-001'
    order by case when p_embedding is null then 0 else embedding<=>p_embedding end,source_date desc nulls last,unit_id
    limit least(greatest(coalesce((p_filters->>'limit')::integer,25),1),50)
    offset least(greatest(coalesce((p_filters->>'offset')::integer,0),0),1000000)
  )
  select jsonb_build_object(
    'items',(select coalesce(jsonb_agg(to_jsonb(r)-'embedding'-'search_vector'),'[]') from ranked r),
    'total_groups',(select count(distinct group_key) from filtered),
    'total_results',(select count(*) from filtered),
    'recipients',(select coalesce(jsonb_agg(t),'[]') from (select actor->>'name' as value,count(distinct group_key) as count from filtered cross join lateral jsonb_array_elements(detail->'recipients') actor group by actor->>'name' order by count desc limit 50)t),
    'countries',(select coalesce(jsonb_agg(t),'[]') from (select coalesce(principal_country,'unknown') as value,count(distinct group_key) as count from filtered group by principal_country order by count desc limit 50)t),
    'principal_kinds',(select coalesce(jsonb_agg(t),'[]') from (select principal_kind as value,count(distinct group_key) as count from filtered group by principal_kind order by count desc)t),
    'branches',(select coalesce(jsonb_agg(t),'[]') from (select b as value,count(distinct group_key) as count from filtered cross join lateral unnest(recipient_branches) b group by b order by count desc)t),
    'coverage',(select jsonb_build_object('eligible_documents',count(*),'fully_processed_documents',count(*) filter(where j.status='complete')) from lobby_records r left join lobby_structure_jobs j
      on j.record_id=r.record_id and j.source_version=r.payload_hash||':'||coalesce(r.body_sha256,'') and j.profile='lobby-evidence-v1'
      where r.kind='document' and r.text_state='extracted'),
    'count_unit','source_activity_group','semantic',p_embedding is not null
  ) into result;
  return result;
end $$;

alter table lobby_principals enable row level security;
alter table lobby_structure_jobs enable row level security;
alter table lobby_passages enable row level security;
alter table lobby_activity_units enable row level security;
revoke all on lobby_principals,lobby_structure_jobs,lobby_passages,lobby_activity_units,lobby_current_units from anon,authenticated;
grant all on lobby_principals,lobby_structure_jobs,lobby_passages,lobby_activity_units to service_role;
grant select on lobby_current_units to service_role;
revoke all on function lobby_refresh_principals(integer),lobby_claim_structure(uuid,text),
  lobby_commit_structure(uuid,text,text,text,jsonb,jsonb),lobby_finish_structure(uuid,text,text,text,boolean,text),
  lobby_explore(jsonb,extensions.vector) from public,anon,authenticated;
grant execute on function lobby_refresh_principals(integer),lobby_claim_structure(uuid,text),
  lobby_commit_structure(uuid,text,text,text,jsonb,jsonb),lobby_finish_structure(uuid,text,text,text,boolean,text),
  lobby_explore(jsonb,extensions.vector) to service_role;

commit;
