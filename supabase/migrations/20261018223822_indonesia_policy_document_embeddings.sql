-- IDN-only document-overview embeddings. Exact scan is intentional for this small corpus.
begin;
set local lock_timeout='3s';
create extension if not exists vector with schema extensions;
grant usage on schema extensions to service_role;
create table if not exists policy_idn.document_embeddings (
 document_id text primary key references policy_idn.documents on delete restrict,
 source_hash text not null check(length(source_hash)=64),
 metadata_hash text not null check(length(metadata_hash)=32),
 input_hash text not null check(length(input_hash)=64),
 model text not null check(model='gemini-embedding-001'),
 profile_version text not null check(profile_version='overview-v1'),
 embedding extensions.vector(1536) not null,
 input_chars integer not null check(input_chars between 1 and 6000),
 embedded_at timestamptz not null default now()
);
alter table policy_idn.document_embeddings enable row level security;
revoke all on policy_idn.document_embeddings from public,anon,authenticated;
grant select,insert,update on policy_idn.document_embeddings to service_role;
create or replace view policy_idn.embedding_corpus with (security_invoker=true) as
 select d.*,v.content_hash,v.content_kind,v.text_content,v.text_truncated,v.observed_at content_observed_at,
 v.provenance->>'text_source_url' text_source_url,
 md5(jsonb_build_array(d.title,d.title_ko,d.scope_note,d.topics)::text) metadata_hash
 from policy_idn.documents d join lateral (
  select * from policy_idn.versions v where v.document_id=d.document_id order by observed_at desc,content_hash limit 1
 ) v on true;
revoke all on policy_idn.embedding_corpus from public,anon,authenticated;
grant select on policy_idn.embedding_corpus to service_role;
create or replace function public.idn_embedding_queue(p_limit integer default 100)
 returns jsonb language plpgsql stable security invoker set search_path='' as $$
begin
 if p_limit not between 1 and 100 then raise exception 'Invalid limit'; end if;
 return (select coalesce(jsonb_agg(to_jsonb(q)),'[]'::jsonb) from (
 select c.document_id,c.title,c.title_ko,c.scope_note,c.topics,c.content_kind,c.content_hash,c.metadata_hash,
 left(c.text_content,3000) source_excerpt
 from policy_idn.embedding_corpus c left join policy_idn.document_embeddings e using(document_id)
 where e.document_id is null or e.source_hash<>c.content_hash or e.metadata_hash<>c.metadata_hash
 order by c.document_id limit p_limit) q);
end $$;
create or replace function public.idn_store_embedding(p_document jsonb)
 returns boolean language plpgsql security invoker set search_path='' as $$
declare n integer;
begin
 if octet_length(p_document::text)>150000 or p_document->>'model' is distinct from 'gemini-embedding-001'
 or p_document->>'profile_version' is distinct from 'overview-v1' or jsonb_array_length(p_document->'embedding')<>1536
 then raise exception 'Invalid IDN embedding'; end if;
 insert into policy_idn.document_embeddings(document_id,source_hash,metadata_hash,input_hash,model,profile_version,embedding,input_chars)
 select c.document_id,c.content_hash,c.metadata_hash,p_document->>'input_hash','gemini-embedding-001','overview-v1',
 (p_document->'embedding')::text::extensions.vector(1536),(p_document->>'input_chars')::integer
 from policy_idn.embedding_corpus c where c.document_id=p_document->>'document_id'
 and c.content_hash=p_document->>'source_hash' and c.metadata_hash=p_document->>'metadata_hash'
 on conflict(document_id) do update set source_hash=excluded.source_hash,metadata_hash=excluded.metadata_hash,
 input_hash=excluded.input_hash,embedding=excluded.embedding,input_chars=excluded.input_chars,embedded_at=now();
 get diagnostics n=row_count;
 if n<>1 then raise exception 'Stale embedding input'; end if;
 return true;
end $$;
revoke all on function public.idn_embedding_queue(integer),public.idn_store_embedding(jsonb) from public,anon,authenticated;
grant execute on function public.idn_embedding_queue(integer),public.idn_store_embedding(jsonb) to service_role;
CREATE OR REPLACE FUNCTION policy_idn.search_documents_v2(p_terms jsonb DEFAULT '[]'::jsonb, p_topic text DEFAULT NULL::text, p_level text DEFAULT NULL::text, p_jurisdiction text DEFAULT NULL::text, p_sort text DEFAULT 'relevance'::text, p_require_all boolean DEFAULT false, p_limit integer DEFAULT 20, p_offset integer DEFAULT 0, p_stream text DEFAULT NULL, p_group text DEFAULT NULL, p_type text DEFAULT NULL, p_query_embedding double precision[] DEFAULT NULL)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE
 SECURITY INVOKER
 SET search_path TO ''
AS $function$
declare result jsonb;
begin
 if jsonb_typeof(p_terms) is distinct from 'array' or jsonb_array_length(p_terms)>6
 or p_limit not between 1 and 50 or p_offset not between 0 and 10000
 or p_sort not in ('relevance','year') then raise exception 'Invalid search parameters'; end if;
 if p_topic is not null and p_topic not in ('coal','nickel_mining','palm_oil','biofuel','bauxite','copper','tin','cobalt','manganese','iron_steel','silica','gold_silver','rare_earths') then raise exception 'Invalid topic'; end if;
 if p_stream is not null and p_stream not in ('upstream','midstream','downstream','trading') then raise exception 'Invalid stream'; end if;
 if p_group is not null and p_group not in ('business','sector') then raise exception 'Invalid group'; end if;
 if p_type is not null and p_type not in ('UU','PP','Perpres','Inpres','Permen','Permendag','PMK','Perda','Pergub','Perbup','Keputusan','Kepmen','Permentan','Permenperin') then raise exception 'Invalid document type'; end if;
 if p_query_embedding is not null and (cardinality(p_query_embedding)<>1536 or array_position(p_query_embedding,null) is not null) then raise exception 'Invalid query vector'; end if;
 if p_level is not null and p_level not in ('national','local','provincial','regency','city') then raise exception 'Invalid issuer level'; end if;
 if exists(select 1 from jsonb_array_elements(p_terms) x where jsonb_typeof(x->'aliases') is distinct from 'array'
 or coalesce(length(x->>'term'),0) not between 1 and 120) then raise exception 'Invalid search terms'; end if;
 if exists(select 1 from jsonb_array_elements(p_terms) x where jsonb_array_length(x->'aliases') not between 1 and 12)
 then raise exception 'Invalid aliases'; end if;
 if exists(select 1 from jsonb_array_elements(p_terms) x cross join lateral jsonb_array_elements(x->'aliases') a
 where jsonb_typeof(a)<>'string' or length(a#>>'{}') not between 1 and 120) then raise exception 'Invalid alias'; end if;
 with terms as (
  select x->>'term' term,x->'aliases' aliases from jsonb_array_elements(p_terms) x
 ), corpus as (
  select d.*,
   lower(d.title||' '||d.title_ko||' '||d.document_type||' '||d.document_number||'/'||d.document_year) title_text,
   lower(d.issuer_name||' '||d.jurisdiction||' '||array_to_string(d.topics,' ')) catalogue_text,
   case when p_query_embedding is not null and e.document_id is not null
     then 1-(e.embedding operator(extensions.<=>) p_query_embedding::extensions.vector(1536)) end semantic_similarity
  from policy_idn.embedding_corpus d
  left join policy_idn.document_embeddings e on e.document_id=d.document_id
   and e.source_hash=d.content_hash and e.metadata_hash=d.metadata_hash
  where (p_topic is null or p_topic=any(d.topics)) and (p_level is null or d.issuer_level=p_level or (p_level='local' and d.issuer_level in ('provincial','regency','city')))
   and (p_jurisdiction is null or d.jurisdiction=p_jurisdiction)
   and (p_stream is null or ('stream_'||p_stream)=any(d.topics))
   and (p_group is null or (p_group='business' and 'cross_sector_business'=any(d.topics)) or (p_group='sector' and not 'cross_sector_business'=any(d.topics)))
   and (p_type is null or d.document_type=p_type)
 ), evidence as (
  select c.*,coalesce(m.matches,'[]'::jsonb) matches,coalesce(m.n,0) matched_count,coalesce(m.weight,0) weight,
   m.first_alias
  from corpus c left join lateral (
   select jsonb_agg(jsonb_build_object('term',t.term,'alias',hit.alias,'field',hit.field) order by t.term) matches,
    count(*)::int n,sum(hit.weight) weight,min(hit.alias) first_alias
   from terms t cross join lateral (
    select a alias,
      case when position(lower(a) in c.title_text)>0 then 'title'
           when position(lower(a) in lower(c.text_content))>0 then 'source_text' else 'catalogue' end field,
      case when position(lower(a) in c.title_text)>0 then 3
           when position(lower(a) in lower(c.text_content))>0 then 2 else 1 end weight
    from jsonb_array_elements_text(t.aliases) a
    where position(lower(a) in c.title_text)>0 or position(lower(a) in lower(c.text_content))>0
       or position(lower(a) in c.catalogue_text)>0
    order by weight desc,length(a) desc,a limit 1
   ) hit
  ) m on true
 ), hits as (
  select * from evidence where jsonb_array_length(p_terms)=0 or
   (case when p_require_all then matched_count=jsonb_array_length(p_terms) else matched_count>0 or semantic_similarity>=0.60 end)
 ), page as (
  select * from hits order by
    case when p_sort='relevance' then matched_count end desc,
    case when p_sort='relevance' then weight end desc,case when p_sort='relevance' then semantic_similarity end desc nulls last,document_year desc,document_id
  limit p_limit offset p_offset
 )
 select jsonb_build_object('country','IDN','search_mode',case when p_query_embedding is null then 'keyword_alias' else 'hybrid_overview' end,'semantic_available',exists(select 1 from policy_idn.document_embeddings e join policy_idn.embedding_corpus c using(document_id) where e.source_hash=c.content_hash and e.metadata_hash=c.metadata_hash),
  'total',(select count(*) from hits),'limit',p_limit,'offset',p_offset,
  'items',coalesce((select jsonb_agg(jsonb_build_object(
   'document_id',document_id,'title',title,'title_ko',title_ko,'issuer_name',issuer_name,
   'issuer_level',issuer_level,'jurisdiction',jurisdiction,'document_type',document_type,
   'document_number',document_number,'document_year',document_year,'topics',topics,'primary_stage',primary_stage,
   'scope_note',scope_note,'source_url',source_url,'text_source_url',text_source_url,'legal_status',legal_status,'content_kind',content_kind,
   'text_truncated',text_truncated,'content_observed_at',content_observed_at,
   'semantic_similarity',semantic_similarity,'matched_terms',matches,'matched_condition_count',matched_count,'total_condition_count',jsonb_array_length(p_terms),
   'excerpt',substring(text_content from greatest(1,position(lower(coalesce(first_alias,'')) in lower(text_content))-70) for 280)
   )) from page),'[]'::jsonb),
  'coverage',jsonb_build_object('documents',(select count(*) from policy_idn.documents),
    'held_sources',(select count(distinct document_id) from policy_idn.source_checks where outcome='failed'),
    'legal_status','unverified','embedded_documents',(select count(*) from policy_idn.document_embeddings e join policy_idn.embedding_corpus c using(document_id) where e.source_hash=c.content_hash and e.metadata_hash=c.metadata_hash)),
  'jurisdictions',coalesce((select jsonb_agg(j order by j) from (select distinct jurisdiction j from policy_idn.documents d where d.issuer_level<>'national' and (p_level is null or d.issuer_level=p_level or (p_level='local' and d.issuer_level in ('provincial','regency','city'))) and (p_topic is null or p_topic=any(d.topics))) s),'[]'::jsonb)
 ) into result;
 return result;
end $function$;


create or replace function public.idn_search_documents_v2(p_terms jsonb default '[]',p_topic text default null,p_level text default null,p_jurisdiction text default null,p_sort text default 'relevance',p_require_all boolean default false,p_limit integer default 20,p_offset integer default 0,p_stream text default null,p_group text default null,p_type text default null,p_query_embedding double precision[] default null)
 returns jsonb language sql stable security invoker set search_path='' as $$
 select policy_idn.search_documents_v2(p_terms,p_topic,p_level,p_jurisdiction,p_sort,p_require_all,p_limit,p_offset,p_stream,p_group,p_type,p_query_embedding);
$$;
revoke all on function policy_idn.search_documents_v2(jsonb,text,text,text,text,boolean,integer,integer,text,text,text,double precision[]),public.idn_search_documents_v2(jsonb,text,text,text,text,boolean,integer,integer,text,text,text,double precision[]) from public,anon,authenticated;
grant execute on function policy_idn.search_documents_v2(jsonb,text,text,text,text,boolean,integer,integer,text,text,text,double precision[]),public.idn_search_documents_v2(jsonb,text,text,text,text,boolean,integer,integer,text,text,text,double precision[]) to service_role;
notify pgrst,'reload schema';
commit;
