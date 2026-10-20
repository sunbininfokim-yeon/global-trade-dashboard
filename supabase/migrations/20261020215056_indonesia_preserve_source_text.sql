-- Source failures must not replace complete text or manufacture freshness/mail.
begin;
set local lock_timeout='3s';
create or replace function policy_idn.store_document(p_document jsonb)
returns boolean language plpgsql security invoker set search_path='' as $$
declare d policy_idn.documents; inserted integer;
begin
 if p_document->>'legal_status' is distinct from 'unverified' or p_document->>'country_code' is distinct from 'IDN' then raise exception 'Invalid pilot status/country'; end if;
 if octet_length(p_document::text)>2500000 then raise exception 'Document exceeds pilot budget'; end if;
 select * into d from jsonb_populate_record(null::policy_idn.documents,p_document);
 -- Serialize concurrent refreshes of an existing IDN document.
 perform 1 from policy_idn.documents where document_id=d.document_id for update;
 if (p_document->>'content_kind' in ('official_metadata','abstract') or (p_document->>'text_truncated')::boolean is true)
 and exists(select 1 from policy_idn.versions where document_id=d.document_id and content_kind='official_text' and not text_truncated) then
  insert into policy_idn.source_checks(document_id,checked_at,source_url,outcome,detail)
  values(d.document_id,(p_document->>'observed_at')::timestamptz,d.source_url,'failed','incomplete_refresh_held: prior complete official text and last_observed_at preserved')
  on conflict(document_id,checked_at) do nothing;
  return false;
 end if;
 insert into policy_idn.documents(document_id,country_code,title,title_ko,issuer_name,issuer_level,jurisdiction,document_type,document_number,document_year,topics,primary_stage,scope_note,source_url,legal_status,status_note,last_observed_at)
 values(d.document_id,d.country_code,d.title,d.title_ko,d.issuer_name,d.issuer_level,d.jurisdiction,d.document_type,d.document_number,d.document_year,d.topics,d.primary_stage,d.scope_note,d.source_url,d.legal_status,d.status_note,(p_document->>'observed_at')::timestamptz)
 on conflict(document_id) do update set title=excluded.title,title_ko=excluded.title_ko,scope_note=excluded.scope_note,source_url=excluded.source_url,last_observed_at=excluded.last_observed_at,topics=excluded.topics
 where policy_idn.documents.last_observed_at<=excluded.last_observed_at;
 insert into policy_idn.versions(document_id,content_hash,content_kind,text_content,text_truncated,source_url,observed_at,provenance)
 values(d.document_id,p_document->>'content_hash',p_document->>'content_kind',p_document->>'text_content',(p_document->>'text_truncated')::boolean,p_document->>'source_url',(p_document->>'observed_at')::timestamptz,p_document-'text_content')
 on conflict(document_id,content_hash) do nothing;
 get diagnostics inserted=row_count;
 return inserted=1;
end $$;
revoke all on function policy_idn.store_document(jsonb) from public,anon,authenticated;
grant execute on function policy_idn.store_document(jsonb) to service_role;
commit;
