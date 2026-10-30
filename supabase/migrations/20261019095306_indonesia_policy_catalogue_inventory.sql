-- Official listing inventory, separate from reviewed laws and embeddings.
begin;
set local lock_timeout='3s';
create table if not exists policy_idn.catalogue_runs (
 checkpoint_id uuid primary key,
 source_id text not null check(source_id ~ '^[a-z0-9-]{1,100}$'),
 run_id uuid not null,
 finished_at timestamptz not null,
 status text not null check(status in ('enumerated_scope','partial','failed','held')),
 record_count integer not null check(record_count between 0 and 5000),
 summary jsonb not null check(jsonb_typeof(summary)='object')
);
create index if not exists idn_catalogue_runs_source_idx on policy_idn.catalogue_runs(source_id,finished_at desc);
create table if not exists policy_idn.catalogue_entries (
 source_id text not null,
 source_record_id text not null check(length(source_record_id) between 1 and 200),
 metadata jsonb not null check(jsonb_typeof(metadata)='object'),
 metadata_hash text not null check(metadata_hash ~ '^[a-f0-9]{32}$'),
 first_seen_at timestamptz not null,
 last_seen_at timestamptz not null,
 last_checkpoint_id uuid not null references policy_idn.catalogue_runs(checkpoint_id) on delete restrict,
 primary key(source_id,source_record_id)
);
create index if not exists idn_catalogue_entries_checkpoint_idx on policy_idn.catalogue_entries(last_checkpoint_id);
create table if not exists policy_idn.catalogue_versions (
 source_id text not null,
 source_record_id text not null,
 metadata_hash text not null,
 metadata jsonb not null,
 observed_at timestamptz not null,
 primary key(source_id,source_record_id,metadata_hash),
 foreign key(source_id,source_record_id) references policy_idn.catalogue_entries on delete restrict
);
alter table policy_idn.catalogue_runs enable row level security;
alter table policy_idn.catalogue_entries enable row level security;
alter table policy_idn.catalogue_versions enable row level security;
revoke all on policy_idn.catalogue_runs,policy_idn.catalogue_entries,policy_idn.catalogue_versions from public,anon,authenticated;
grant select,insert on policy_idn.catalogue_runs,policy_idn.catalogue_versions to service_role;
grant select,insert,update on policy_idn.catalogue_entries to service_role;

create or replace function public.idn_store_catalogue(p_snapshot jsonb)
 returns jsonb language plpgsql security invoker set search_path='' as $$
declare key uuid; sid text; stamp timestamptz; rec jsonb; n integer; item_count integer; changed integer;
begin
 if jsonb_typeof(p_snapshot) is distinct from 'object' or octet_length(p_snapshot::text)>10000000
 or jsonb_typeof(p_snapshot->'records') is distinct from 'array'
 or jsonb_typeof(p_snapshot->'pages') is distinct from 'array'
 or jsonb_typeof(p_snapshot->'failures') is distinct from 'array'
 or jsonb_typeof(p_snapshot->'pending_urls') is distinct from 'array'
 or p_snapshot->>'status' is null or p_snapshot->>'status' not in ('enumerated_scope','partial','failed','held')
 or coalesce(length(p_snapshot->'source_config'->>'scope'),0)<20
 or coalesce(p_snapshot->'source_config'->>'url','') !~ '^https://[^/]+\.go\.id/'
 or p_snapshot->>'source_id' is distinct from p_snapshot->'source_config'->>'source_id'
 then raise exception 'Invalid IDN catalogue snapshot'; end if;
 item_count=jsonb_array_length(p_snapshot->'records');
 if item_count>5000 or (select count(distinct r->>'source_record_id') from jsonb_array_elements(p_snapshot->'records') r)<>item_count
 then raise exception 'Invalid or duplicate catalogue records'; end if;
 if p_snapshot->>'status'='enumerated_scope' and (item_count=0 or jsonb_array_length(p_snapshot->'pages')=0
 or jsonb_array_length(p_snapshot->'pending_urls')<>0 or jsonb_array_length(p_snapshot->'failures')<>0)
 then raise exception 'Incomplete catalogue cannot claim enumeration'; end if;
 key=md5(p_snapshot::text)::uuid;sid=p_snapshot->>'source_id';stamp=(p_snapshot->>'finished_at')::timestamptz;
 if stamp is null then raise exception 'Missing observation time'; end if;
 insert into policy_idn.catalogue_runs(checkpoint_id,source_id,run_id,finished_at,status,record_count,summary)
 values(key,sid,(p_snapshot->>'run_id')::uuid,stamp,p_snapshot->>'status',item_count,
 (p_snapshot-'records')||jsonb_build_object('record_ids',(select coalesce(jsonb_agg(r->>'source_record_id'),'[]'::jsonb) from jsonb_array_elements(p_snapshot->'records') r)))
 on conflict(checkpoint_id) do nothing;
 get diagnostics changed=row_count;
 if changed=0 then return jsonb_build_object('changed',false,'records',item_count,'new_versions',0); end if;
 n=0;
 for rec in select value from jsonb_array_elements(p_snapshot->'records') loop
  if jsonb_typeof(rec) is distinct from 'object' or coalesce(length(rec->>'title'),0) not between 1 and 2000
  or rec->>'page_url' is null or rec->>'page_url' !~ '^https://[^/]+\.go\.id/'
  or (rec->>'detail_url' is not null and rec->>'detail_url' !~ '^https://[^/]+\.go\.id/')
  or (rec->>'download_url' is not null and rec->>'download_url' !~ '^https://[^/]+\.go\.id/')
  then raise exception 'Invalid catalogue metadata'; end if;
  insert into policy_idn.catalogue_entries(source_id,source_record_id,metadata,metadata_hash,first_seen_at,last_seen_at,last_checkpoint_id)
  values(sid,rec->>'source_record_id',rec,md5(rec::text),stamp,stamp,key)
  on conflict(source_id,source_record_id) do update set metadata=excluded.metadata,metadata_hash=excluded.metadata_hash,
   last_seen_at=excluded.last_seen_at,last_checkpoint_id=excluded.last_checkpoint_id
   where catalogue_entries.last_seen_at<=excluded.last_seen_at;
  insert into policy_idn.catalogue_versions(source_id,source_record_id,metadata_hash,metadata,observed_at)
  values(sid,rec->>'source_record_id',md5(rec::text),rec,stamp) on conflict do nothing;
  get diagnostics changed=row_count;n=n+changed;
 end loop;
 return jsonb_build_object('changed',true,'records',item_count,'new_versions',n);
end $$;

create or replace view policy_idn.catalogue_reconciliation with (security_invoker=true) as
 select e.*,coalesce(m.matches,'[]'::jsonb) matches,
 case when m.n>1 then 'ambiguous' when m.url_n=1 then 'url_match' when m.n=1 then 'identity_candidate' else 'unmatched' end match_status
 from policy_idn.catalogue_entries e
 left join lateral (
  select jsonb_agg(jsonb_build_object('document_id',d.document_id,'basis',case when u.url_match then 'url' else 'identity' end,
   'content_kind',d.content_kind,'text_truncated',d.text_truncated)) matches,count(*) n,count(*) filter(where u.url_match) url_n
  from policy_idn.embedding_corpus d
  cross join lateral (select (d.source_url in (e.metadata->>'detail_url',e.metadata->>'download_url')
   or exists(select 1 from policy_idn.versions v where v.document_id=d.document_id and
    (v.source_url in (e.metadata->>'detail_url',e.metadata->>'download_url')
     or v.provenance->>'text_source_url' in (e.metadata->>'detail_url',e.metadata->>'download_url')))) is true url_match) u
  where u.url_match or (d.document_type=e.metadata->>'document_type' and d.document_number=e.metadata->>'document_number'
   and d.document_year::text=e.metadata->>'document_year' and (
    (d.issuer_level='national' and (e.metadata->>'issuer_key'='national' and d.document_type in ('UU','PP','Perpres','Inpres')
      or e.metadata->>'issuer_key'='kemendag' and d.document_type='Permendag'
      or e.metadata->>'issuer_key'='pertanian' and d.document_type='Permentan'
      or e.metadata->>'issuer_key'='kemenperin' and d.document_type='Permenperin'
      or e.metadata->>'issuer_key'='kemenkeu' and d.document_type='PMK'
      or e.metadata->>'issuer_key'='esdm' and d.document_type='Permen' and (d.issuer_name ilike '%energi%' or d.issuer_name ilike '%esdm%')))
    or (d.issuer_level<>'national' and e.metadata->>'jurisdiction'=d.jurisdiction and d.document_type in ('Perda','Pergub','Perbup'))))
 ) m on true;
revoke all on policy_idn.catalogue_reconciliation from public,anon,authenticated;
grant select on policy_idn.catalogue_reconciliation to service_role;

create or replace function public.idn_catalogue_status()
 returns jsonb language sql stable security invoker set search_path='' as $$
 with latest as (select distinct on(source_id) * from policy_idn.catalogue_runs order by source_id,finished_at desc,checkpoint_id desc)
 select jsonb_build_object('country','IDN','catalogue_entries',(select count(*) from policy_idn.catalogue_entries),
 'catalogue_versions',(select count(*) from policy_idn.catalogue_versions),'sources',coalesce((select jsonb_agg(jsonb_build_object(
  'source_id',s.source_id,'status',s.status,'record_count',s.record_count,'finished_at',s.finished_at,
  'scope',s.summary->'source_config'->>'scope','stop_reason',s.summary->>'stop_reason',
  'pages',jsonb_array_length(s.summary->'pages'),'pending_pages',jsonb_array_length(s.summary->'pending_urls'),
  'failure_count',jsonb_array_length(s.summary->'failures'))) from latest s),'[]'::jsonb));
$$;
create or replace function public.idn_catalogue_gaps(p_source_id text default null,p_limit integer default 100,p_offset integer default 0)
 returns jsonb language plpgsql stable security invoker set search_path='' as $$
begin
 if p_limit not between 1 and 200 or p_offset not between 0 and 10000 then raise exception 'Invalid catalogue page'; end if;
 return jsonb_build_object('country','IDN','total',(select count(*) from policy_idn.catalogue_reconciliation where p_source_id is null or source_id=p_source_id),
 'counts',(select coalesce(jsonb_object_agg(match_status,n),'{}'::jsonb) from
  (select match_status,count(*) n from policy_idn.catalogue_reconciliation where p_source_id is null or source_id=p_source_id group by 1) s),
 'items',(select coalesce(jsonb_agg(to_jsonb(q)),'[]'::jsonb) from
  (select source_id,source_record_id,metadata,match_status,matches,last_seen_at,
    (select case when r.checkpoint_id is null then null else
       first_seen_at<=r.finished_at and not ((r.summary->'record_ids') ? source_record_id) end
     from (select * from policy_idn.catalogue_runs where source_id=e.source_id and status='enumerated_scope' order by finished_at desc,checkpoint_id desc limit 1) r) not_seen_in_latest_enumeration
   from policy_idn.catalogue_reconciliation e where p_source_id is null or source_id=p_source_id
   order by source_id,source_record_id limit p_limit offset p_offset) q));
end $$;
revoke all on function public.idn_store_catalogue(jsonb),public.idn_catalogue_status(),public.idn_catalogue_gaps(text,integer,integer) from public,anon,authenticated;
grant execute on function public.idn_store_catalogue(jsonb),public.idn_catalogue_status(),public.idn_catalogue_gaps(text,integer,integer) to service_role;
comment on table policy_idn.catalogue_entries is '인도네시아 공식 목록 후보. 원문·현행 효력·검색 문서와 별도이며 자동 승격하지 않음.';
comment on table policy_idn.catalogue_runs is '기관별 범위·페이지·실패·대기 목록. 열거 종료는 해당 게시 목록 범위에만 해당.';
commit;
