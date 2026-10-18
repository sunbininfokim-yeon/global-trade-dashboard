-- Avoid Latin substring false positives, e.g. tin inside kepentingan.
begin;
set local lock_timeout='3s';
create or replace function policy_idn.matches_alias(p_text text,p_alias text)
 returns boolean language sql immutable strict security invoker set search_path='' as $$
 select case when p_alias ~ '^[A-Za-z]+$' then p_text ~* ('\m'||p_alias||'\M')
 else position(lower(p_alias) in lower(p_text))>0 end;
$$;
revoke all on function policy_idn.matches_alias(text,text) from public,anon,authenticated;
grant execute on function policy_idn.matches_alias(text,text) to service_role;
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
      case when policy_idn.matches_alias(c.title_text,a) then 'title'
           when policy_idn.matches_alias(lower(c.text_content),a) then 'source_text' else 'catalogue' end field,
      case when policy_idn.matches_alias(c.title_text,a) then 3
           when policy_idn.matches_alias(lower(c.text_content),a) then 2 else 1 end weight
    from jsonb_array_elements_text(t.aliases) a
    where policy_idn.matches_alias(c.title_text,a) or policy_idn.matches_alias(lower(c.text_content),a)
       or policy_idn.matches_alias(c.catalogue_text,a)
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


notify pgrst,'reload schema';
commit;
