-- Additive, service-role-only lobbying ingestion. No triggers on policy/mail tables.
begin;
set local lock_timeout = '3s';
create table if not exists public.lobby_records (
  record_id text primary key,
  source text not null check (source in ('fara','lda')),
  kind text not null check (kind in ('document','registrant','principal','person')),
  source_url text not null,
  source_date date,
  registrant_id text,
  registrant_name text,
  client_name text,
  title text,
  country_raw text,
  country_codes text[] not null default '{}',
  related_countries text[] not null default '{}',
  topics text[] not null default '{}',
  raw_payload jsonb not null,
  payload_hash text not null,
  text_state text not null default 'pending' check (text_state in ('pending','extracted','ocr_required','source_unavailable','not_applicable')),
  body_text text,
  body_sha256 text,
  pages jsonb not null default '[]',
  text_error text,
  last_text_attempt timestamptz,
  updated_at timestamptz not null default now(),
  search_vector tsvector generated always as (to_tsvector('simple'::regconfig,
    coalesce(title,'') || ' ' || coalesce(registrant_name,'') || ' ' || coalesce(client_name,'') || ' ' || coalesce(body_text,''))) stored
);
create index if not exists lobby_records_search_idx on public.lobby_records using gin(search_vector);
create index if not exists lobby_records_date_idx on public.lobby_records(source,kind,source_date desc,record_id);
create index if not exists lobby_records_pending_idx on public.lobby_records(last_text_attempt,source_date desc)
  where source='fara' and kind='document' and text_state in ('pending','source_unavailable');
create index if not exists lobby_records_countries_idx on public.lobby_records using gin(country_codes);
create index if not exists lobby_records_related_countries_idx on public.lobby_records using gin(related_countries);
create index if not exists lobby_records_topics_idx on public.lobby_records using gin(topics);

create table if not exists public.lobby_record_versions (
  record_id text not null references public.lobby_records on delete cascade,
  payload_hash text not null,
  payload jsonb not null,
  observed_at timestamptz not null default now(),
  primary key(record_id,payload_hash)
);
create table if not exists public.lobby_activities (
  activity_id text primary key,
  record_id text not null references public.lobby_records on delete cascade,
  grain text not null check (grain='filing_issue_block'),
  description text not null,
  issue_code text,
  government_entities jsonb not null default '[]',
  lobbyists jsonb not null default '[]',
  topics text[] not null default '{}',
  evidence jsonb not null
);
create index if not exists lobby_activities_record_idx on public.lobby_activities(record_id);
create table if not exists public.lobby_policy_links (
  record_id text not null references public.lobby_records on delete cascade,
  reference_key text not null,
  target_type text not null check (target_type in ('bill','public_law','executive_order','regulation')),
  target_id text,
  raw_reference text not null,
  resolution_status text not null check (resolution_status in ('confirmed','ambiguous','target_not_collected')),
  evidence jsonb not null,
  primary key(record_id,reference_key)
);
create index if not exists lobby_policy_links_target_idx on public.lobby_policy_links(target_type,target_id,resolution_status);
create table if not exists public.lobby_sync_state (
  stream text primary key,
  cursor jsonb not null default '{}',
  status text not null default 'pending',
  expected_count bigint,
  last_attempt_at timestamptz,
  last_success_at timestamptz,
  last_completed_pass_at timestamptz,
  last_error text,
  lease_owner uuid,
  lease_until timestamptz
);

create or replace function public.lobby_claim_stream(p_stream text,p_owner uuid)
returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare result jsonb;
begin
  if p_stream !~ '^(fara:(document|registrant|principal|person|text|inventory)|lda:(backfill|refresh))$' then
    raise exception 'Invalid lobby stream';
  end if;
  insert into lobby_sync_state(stream) values(p_stream) on conflict do nothing;
  update lobby_sync_state set lease_owner=p_owner,lease_until=now()+interval '15 minutes',
    status='running',last_attempt_at=now()
    where stream=p_stream and (lease_until is null or lease_until<now())
    returning jsonb_build_object('cursor',cursor,'expected_count',expected_count) into result;
  return result;
end $$;

create or replace function public.lobby_commit_batch(p_stream text,p_owner uuid,p_records jsonb,
  p_cursor jsonb,p_expected bigint default null,p_complete boolean default false)
returns integer language plpgsql security invoker set search_path=public,pg_temp as $$
declare r jsonb; a jsonb; ref jsonb; rid text; n integer:=0; resolved boolean;
begin
  perform 1 from lobby_sync_state where stream=p_stream and lease_owner=p_owner
    and lease_until>now() for update;
  if not found then raise exception 'Lobby lease unavailable'; end if;
  if jsonb_typeof(p_records)<>'array' or jsonb_array_length(p_records)>500 then
    raise exception 'Invalid lobby batch';
  end if;
  for r in select value from jsonb_array_elements(p_records) loop
    rid:=r->>'record_id';
    if r ? 'source' then
      if split_part(p_stream,':',1)<>r->>'source' then raise exception 'Source mismatch'; end if;
      insert into lobby_records(record_id,source,kind,source_url,source_date,registrant_id,registrant_name,
        client_name,title,country_raw,country_codes,related_countries,topics,raw_payload,payload_hash,text_state,body_text)
      values(rid,r->>'source',r->>'kind',r->>'source_url',(r->>'source_date')::date,r->>'registrant_id',r->>'registrant_name',
        r->>'client_name',r->>'title',r->>'country_raw',array(select jsonb_array_elements_text(r->'country_codes')),
        array(select jsonb_array_elements_text(r->'related_countries')),array(select jsonb_array_elements_text(r->'topics')),
        r->'raw_payload',r->>'payload_hash',r->>'text_state',r->>'body_text')
      on conflict(record_id) do update set
        source_date=excluded.source_date,registrant_name=excluded.registrant_name,client_name=excluded.client_name,
        title=excluded.title,country_raw=excluded.country_raw,country_codes=excluded.country_codes,
        related_countries=excluded.related_countries,raw_payload=excluded.raw_payload,payload_hash=excluded.payload_hash,
        body_text=case when r ? 'body_text' then excluded.body_text else lobby_records.body_text end,
        text_state=case when r ? 'body_text' then excluded.text_state else lobby_records.text_state end,
        topics=case when r ? 'body_text' then excluded.topics else lobby_records.topics end,updated_at=now();
      insert into lobby_record_versions(record_id,payload_hash,payload)
        values(rid,r->>'payload_hash',r->'raw_payload') on conflict do nothing;
    else
      if p_stream<>'fara:text' then raise exception 'Invalid text stream'; end if;
      update lobby_records set text_state=r->>'text_state',text_error=r->>'text_error',last_text_attempt=now(),
        body_text=coalesce(r->>'body_text',body_text),body_sha256=coalesce(r->>'body_sha256',body_sha256),
        pages=case when r ? 'body_text' then r->'pages' else pages end,
        topics=case when r ? 'body_text' then array(select jsonb_array_elements_text(r->'topics')) else topics end,
        updated_at=now() where record_id=rid and source='fara';
      if not found then raise exception 'Missing FARA text parent'; end if;
      if r ? 'body_sha256' then
        insert into lobby_record_versions(record_id,payload_hash,payload)
          values(rid,r->>'body_sha256',r) on conflict do nothing;
      end if;
    end if;
    if r ? 'activities' then
      delete from lobby_activities where record_id=rid;
      for a in select value from jsonb_array_elements(r->'activities') loop
        insert into lobby_activities values(a->>'activity_id',rid,a->>'grain',coalesce(a->>'description',''),
          a->>'issue_code',a->'government_entities',a->'lobbyists',
          array(select jsonb_array_elements_text(a->'topics')),a->'evidence');
      end loop;
    end if;
    if r ? 'references' then
      delete from lobby_policy_links where record_id=rid;
      for ref in select value from jsonb_array_elements(r->'references') loop
        resolved:=false;
        if ref->>'target_id' is not null then
          case ref->>'target_type'
            when 'bill' then select exists(select 1 from bills where bill_id=ref->>'target_id') into resolved;
            when 'public_law' then select exists(select 1 from public_laws where public_law_id=ref->>'target_id') into resolved;
            when 'executive_order' then select exists(select 1 from executive_orders where eo_number::text=ref->>'target_id') into resolved;
            when 'regulation' then select exists(select 1 from regulations where regulation_id=ref->>'target_id') into resolved;
          end case;
        end if;
        insert into lobby_policy_links values(rid,ref->>'reference_key',ref->>'target_type',ref->>'target_id',ref->>'raw_reference',
          case when resolved then 'confirmed' when ref->>'target_id' is null then 'ambiguous' else 'target_not_collected' end,ref->'evidence');
      end loop;
    end if;
    n:=n+1;
  end loop;
  update lobby_sync_state set cursor=p_cursor,expected_count=coalesce(p_expected,expected_count),
    last_success_at=now(),last_error=null,lease_until=now()+interval '15 minutes',
    last_completed_pass_at=case when p_complete then now() else last_completed_pass_at end,
    status=case when p_complete then 'complete_pass' else 'partial' end where stream=p_stream;
  return n;
end $$;

create or replace function public.lobby_finish_stream(p_stream text,p_owner uuid,p_error text default null)
returns void language sql security invoker set search_path=public,pg_temp as $$
  update lobby_sync_state set lease_owner=null,lease_until=null,
    status=case when p_error is not null then 'source_unavailable' when status='running' then 'partial' else status end,
    last_error=p_error where stream=p_stream and lease_owner=p_owner;
$$;

create or replace function public.lobby_coverage()
returns jsonb language sql security invoker set search_path=public,pg_temp as $$
 select jsonb_build_object('scope','all_countries_all_industries_all_available_history',
   'counts',(select coalesce(jsonb_agg(t),'[]') from
     (select source,kind,text_state,count(*) as count from lobby_records group by source,kind,text_state) t),
   'streams',(select coalesce(jsonb_agg(to_jsonb(s)-'lease_owner'-'lease_until'),'[]') from lobby_sync_state s));
$$;

do $$ declare t text; begin
  foreach t in array array['lobby_records','lobby_record_versions','lobby_activities','lobby_policy_links','lobby_sync_state'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on public.%I from anon,authenticated',t);
    execute format('grant all on public.%I to service_role',t);
  end loop;
end $$;
revoke all on function public.lobby_claim_stream(text,uuid) from public,anon,authenticated;
revoke all on function public.lobby_commit_batch(text,uuid,jsonb,jsonb,bigint,boolean) from public,anon,authenticated;
revoke all on function public.lobby_finish_stream(text,uuid,text) from public,anon,authenticated;
revoke all on function public.lobby_coverage() from public,anon,authenticated;
grant execute on function public.lobby_claim_stream(text,uuid),public.lobby_commit_batch(text,uuid,jsonb,jsonb,bigint,boolean),
  public.lobby_finish_stream(text,uuid,text),public.lobby_coverage() to service_role;
commit;
