-- Move only the IDN pilot. Preserve rows, hashes, keys and US dependencies.
begin;
set local lock_timeout='3s';
create schema if not exists policy_idn;
revoke all on schema policy_idn from public,anon,authenticated;
grant usage on schema policy_idn to service_role;
alter default privileges in schema policy_idn revoke execute on functions from public;
do $$
declare old_name text; new_name text;
begin
 for old_name,new_name in select * from (values
 ('idn_policy_documents','documents'),('idn_policy_versions','versions'),('idn_policy_source_checks','source_checks')) as t(old_name,new_name)
 loop
  if to_regclass('public.'||old_name) is not null then
   if to_regclass('policy_idn.'||new_name) is not null then raise exception 'IDN schema collision: %',new_name; end if;
   execute format('alter table public.%I set schema policy_idn',old_name);
   execute format('alter table policy_idn.%I rename to %I',old_name,new_name);
  elsif to_regclass('policy_idn.'||new_name) is null then raise exception 'Missing IDN pilot table: %',old_name;
  end if;
 end loop;
end $$;
create or replace function policy_idn.store_document(p_document jsonb)
returns boolean language plpgsql security invoker set search_path='' as $$
declare d policy_idn.documents; inserted integer;
begin
  if p_document->>'legal_status' is distinct from 'unverified' or
     p_document->>'country_code' is distinct from 'IDN' then
    raise exception 'Invalid pilot status/country';
  end if;
  if octet_length(p_document::text)>2500000 then raise exception 'Document exceeds pilot budget'; end if;
  select * into d from jsonb_populate_record(null::policy_idn.documents,p_document);
  insert into policy_idn.documents(document_id,country_code,title,title_ko,issuer_name,issuer_level,
    jurisdiction,document_type,document_number,document_year,topics,primary_stage,scope_note,source_url,
    legal_status,status_note,last_observed_at)
  values(d.document_id,d.country_code,d.title,d.title_ko,d.issuer_name,d.issuer_level,d.jurisdiction,
    d.document_type,d.document_number,d.document_year,d.topics,d.primary_stage,d.scope_note,d.source_url,
    d.legal_status,d.status_note,(p_document->>'observed_at')::timestamptz)
  on conflict(document_id) do update set title=excluded.title,title_ko=excluded.title_ko,
    scope_note=excluded.scope_note,source_url=excluded.source_url,
    last_observed_at=excluded.last_observed_at,topics=excluded.topics
    where policy_idn.documents.last_observed_at<=excluded.last_observed_at;
  insert into policy_idn.versions(document_id,content_hash,content_kind,text_content,text_truncated,
    source_url,observed_at,provenance)
  values(d.document_id,p_document->>'content_hash',p_document->>'content_kind',p_document->>'text_content',
    (p_document->>'text_truncated')::boolean,p_document->>'source_url',(p_document->>'observed_at')::timestamptz,
    p_document-'text_content')
  on conflict(document_id,content_hash) do nothing;
  get diagnostics inserted=row_count;
  return inserted=1;
end $$;

revoke all on function policy_idn.store_document(jsonb) from public,anon,authenticated;
grant execute on function policy_idn.store_document(jsonb) to service_role;
-- One-country gateway only; no US corpus reads, UNIONs or search fallback.
create or replace function public.idn_store_document(p_document jsonb)
returns boolean language sql security invoker set search_path=''
as $$ select policy_idn.store_document(p_document) $$;
create or replace function public.idn_store_source_check(p_check jsonb)
returns boolean language plpgsql security invoker set search_path='' as $$
declare r policy_idn.source_checks; n integer;
begin
 select * into r from jsonb_populate_record(null::policy_idn.source_checks,p_check);
 insert into policy_idn.source_checks select r.* on conflict(document_id,checked_at) do nothing;
 get diagnostics n=row_count;
 return n=1;
end $$;
create or replace function public.idn_status()
returns jsonb language sql stable security invoker set search_path='' as $$
 select jsonb_build_object('schema','policy_idn',
 'documents',(select count(*) from policy_idn.documents),
 'versions',(select count(*) from policy_idn.versions),
 'checks',(select count(*) from policy_idn.source_checks))
$$;
revoke all on function public.idn_store_document(jsonb),public.idn_store_source_check(jsonb),public.idn_status() from public,anon,authenticated;
grant execute on function public.idn_store_document(jsonb),public.idn_store_source_check(jsonb),public.idn_status() to service_role;
-- Drop the obsolete single-country pilot entrypoint, not any US function.
drop function if exists public.store_idn_policy_document(jsonb);
comment on schema policy_idn is '인도네시아 정책 전용: 미국 저장·검색·메일과 분리. 같은 프로젝트 내 논리 분리.';
notify pgrst,'reload schema';
commit;
