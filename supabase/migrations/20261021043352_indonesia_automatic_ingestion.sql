-- Official-list discovery is separate from verified legal effect/mail review.
begin;
set local lock_timeout='3s';
create table if not exists policy_idn.automatic_ingestions (
 source_id text not null,
 source_record_id text not null,
 metadata_hash text not null,
 state text not null check(state in ('stored','held','failed')),
 reason text not null,
 document_id text references policy_idn.documents(document_id),
 checked_at timestamptz not null default now(),
 next_attempt_at timestamptz,
 primary key(source_id,source_record_id),
 foreign key(source_id,source_record_id) references policy_idn.catalogue_entries(source_id,source_record_id)
);
alter table policy_idn.automatic_ingestions enable row level security;
revoke all on policy_idn.automatic_ingestions from public,anon,authenticated;
grant select,insert,update on policy_idn.automatic_ingestions to service_role;
create index if not exists idn_automatic_ingestions_due on policy_idn.automatic_ingestions(next_attempt_at);

create or replace function public.idn_sync_store_catalogue(p_snapshot jsonb,p_lease_token uuid)
returns jsonb language plpgsql security invoker set search_path='' as $$
begin
 perform 1 from policy_idn.sync_lease where singleton and lease_token=p_lease_token and expires_at>clock_timestamp() for update;
 if not found then raise exception 'IDN sync lease lost'; end if;
 return public.idn_store_catalogue(p_snapshot);
end $$;

create or replace function public.idn_ingestion_queue(p_source_ids text[],p_limit integer default 5)
returns jsonb language plpgsql security invoker set search_path='' as $$
begin
 if p_limit is null or p_limit not between 1 and 20 or coalesce(array_ndims(p_source_ids),0)<>1
  or coalesce(cardinality(p_source_ids),0) not between 1 and 20 then raise exception 'invalid IDN discovery budget'; end if;
 return jsonb_build_object('country','IDN','items',coalesce((select jsonb_agg(to_jsonb(r)) from (
  select e.source_id,e.source_record_id,e.metadata,e.metadata_hash,e.match_status,e.matches,
   (select to_jsonb(d) from policy_idn.documents d where jsonb_array_length(e.matches)=1 and d.document_id=e.matches->0->>'document_id') matched_document
  from policy_idn.catalogue_reconciliation e left join policy_idn.automatic_ingestions a using(source_id,source_record_id)
  where e.source_id=any(p_source_ids)
   and (a.source_id is null or a.metadata_hash<>e.metadata_hash or a.next_attempt_at<=clock_timestamp())
   and not(a.source_id is null and jsonb_array_length(e.matches)=1 and e.matches->0->>'content_kind'='official_text' and (e.matches->0->>'text_truncated')::boolean=false)
   and e.metadata->>'title' ~* '(batubara|batu bara|nikel|minerba|mineral|pertambangan|smelter|sawit|palm oil|biofuel|biodiesel|bioetanol|bahan bakar nabati|bauksit|alumin|tembaga|timah|kobalt|mangan|besi|baja|silika|kuarsa|emas|perak|tanah jarang|lingkungan|perizinan berusaha|penanaman modal|perseroan terbatas|ketenagakerjaan|penerimaan negara|perpajakan|tata ruang|kebijakan dan pengaturan (ekspor|impor))'
  order by (a.source_id is null or a.metadata_hash<>e.metadata_hash) desc,
   coalesce(e.metadata->>'document_year','') desc,a.checked_at nulls first,e.first_seen_at,e.source_id,e.source_record_id
  limit p_limit
 ) r),'[]'::jsonb));
end $$;

create or replace function public.idn_complete_ingestion(p_source_id text,p_source_record_id text,p_metadata_hash text,
 p_document jsonb,p_outcome text,p_reason text,p_retry_seconds integer,p_lease_token uuid)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare current_hash text; changed boolean:=false; target_id text;
begin
 perform 1 from policy_idn.sync_lease where singleton and lease_token=p_lease_token and expires_at>clock_timestamp() for update;
 if not found then raise exception 'IDN sync lease lost'; end if;
 select metadata_hash into current_hash from policy_idn.catalogue_entries where source_id=p_source_id and source_record_id=p_source_record_id for update;
 if not found or current_hash is distinct from p_metadata_hash then return jsonb_build_object('stale',true,'new_version',false); end if;
 if p_outcome is null or p_outcome not in ('stored','held','failed') or length(coalesce(p_reason,'')) not between 1 and 400
  or p_retry_seconds is not null and p_retry_seconds not between 120 and 604800 then raise exception 'invalid IDN ingestion outcome'; end if;
 if p_document is not null then
  if p_outcome<>'stored' or p_document->>'content_kind' is distinct from 'official_text' or (p_document->>'text_truncated')::boolean is distinct from false
   or p_document->'automatic_admission'->>'metadata_hash' is distinct from p_metadata_hash then raise exception 'complete identified official text required'; end if;
  changed:=public.idn_store_document(p_document);target_id:=p_document->>'document_id';
  perform public.idn_store_source_check(jsonb_build_object('document_id',target_id,'checked_at',p_document->>'observed_at',
   'source_url',p_document->>'source_url','outcome','collected','detail','automatic_identity_verified; legal effect and applicability unverified'));
 elsif p_outcome='stored' then raise exception 'stored outcome needs a document';
 end if;
 insert into policy_idn.automatic_ingestions(source_id,source_record_id,metadata_hash,state,reason,document_id,checked_at,next_attempt_at)
 values(p_source_id,p_source_record_id,p_metadata_hash,p_outcome,p_reason,target_id,clock_timestamp(),
  case when p_retry_seconds is not null then clock_timestamp()+make_interval(secs=>p_retry_seconds) end)
 on conflict(source_id,source_record_id) do update set metadata_hash=excluded.metadata_hash,state=excluded.state,
  reason=excluded.reason,document_id=coalesce(excluded.document_id,automatic_ingestions.document_id),
  checked_at=excluded.checked_at,next_attempt_at=excluded.next_attempt_at;
 return jsonb_build_object('stale',false,'new_version',changed,'state',p_outcome,'document_id',target_id);
end $$;

create or replace function public.idn_ingestion_status()
returns jsonb language sql stable security invoker set search_path='' as $$
 select jsonb_build_object('country','IDN','states',coalesce((select jsonb_object_agg(state,n) from
  (select state,count(*) n from policy_idn.automatic_ingestions group by state) s),'{}'::jsonb),
 'last_attempt',(select max(checked_at) from policy_idn.automatic_ingestions))
$$;
revoke all on function public.idn_sync_store_catalogue(jsonb,uuid),public.idn_ingestion_queue(text[],integer),
 public.idn_complete_ingestion(text,text,text,jsonb,text,text,integer,uuid),public.idn_ingestion_status() from public,anon,authenticated;
grant execute on function public.idn_sync_store_catalogue(jsonb,uuid),public.idn_ingestion_queue(text[],integer),
 public.idn_complete_ingestion(text,text,text,jsonb,text,text,integer,uuid),public.idn_ingestion_status() to service_role;
notify pgrst,'reload schema';
commit;
