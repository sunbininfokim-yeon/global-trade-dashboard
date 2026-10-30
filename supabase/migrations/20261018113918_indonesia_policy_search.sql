-- Read-only IDN search; service gateway only, never a US fallback.
begin;
set local lock_timeout='3s';
create or replace function policy_idn.search_documents(
 p_terms jsonb default '[]',p_topic text default null,p_level text default null,
 p_jurisdiction text default null,p_sort text default 'relevance',
 p_require_all boolean default false,p_limit integer default 20,p_offset integer default 0)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare result jsonb;
begin
 if jsonb_typeof(p_terms) is distinct from 'array' or jsonb_array_length(p_terms)>6
 or p_limit not between 1 and 50 or p_offset not between 0 and 10000
 or p_sort not in ('relevance','year') then raise exception 'Invalid search parameters'; end if;
 if p_topic is not null and p_topic not in ('coal','nickel_mining','palm_oil','biofuel') then raise exception 'Invalid topic'; end if;
 if p_level is not null and p_level not in ('national','provincial','regency','city') then raise exception 'Invalid issuer level'; end if;
 if exists(select 1 from jsonb_array_elements(p_terms) x where jsonb_typeof(x->'aliases') is distinct from 'array'
 or coalesce(length(x->>'term'),0) not between 1 and 120) then raise exception 'Invalid search terms'; end if;
 if exists(select 1 from jsonb_array_elements(p_terms) x where jsonb_array_length(x->'aliases') not between 1 and 12)
 then raise exception 'Invalid aliases'; end if;
 if exists(select 1 from jsonb_array_elements(p_terms) x cross join lateral jsonb_array_elements(x->'aliases') a
 where jsonb_typeof(a)<>'string' or length(a#>>'{}') not between 1 and 120) then raise exception 'Invalid alias'; end if;
 with terms as (
  select x->>'term' term,x->'aliases' aliases from jsonb_array_elements(p_terms) x
 ), corpus as (
  select d.*,v.content_kind,v.text_content,v.text_truncated,v.observed_at content_observed_at,
   lower(d.title||' '||d.title_ko||' '||d.document_type||' '||d.document_number||'/'||d.document_year) title_text,
   lower(d.issuer_name||' '||d.jurisdiction||' '||array_to_string(d.topics,' ')) catalogue_text
  from policy_idn.documents d join lateral (
   select content_kind,text_content,text_truncated,observed_at from policy_idn.versions v
   where v.document_id=d.document_id order by observed_at desc,content_hash limit 1
  ) v on true
  where (p_topic is null or p_topic=any(d.topics)) and (p_level is null or d.issuer_level=p_level)
   and (p_jurisdiction is null or d.jurisdiction=p_jurisdiction)
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
   (case when p_require_all then matched_count=jsonb_array_length(p_terms) else matched_count>0 end)
 ), page as (
  select * from hits order by
    case when p_sort='relevance' then matched_count end desc,
    case when p_sort='relevance' then weight end desc,document_year desc,document_id
  limit p_limit offset p_offset
 )
 select jsonb_build_object('country','IDN','search_mode','keyword_alias','semantic_available',false,
  'total',(select count(*) from hits),'limit',p_limit,'offset',p_offset,
  'items',coalesce((select jsonb_agg(jsonb_build_object(
   'document_id',document_id,'title',title,'title_ko',title_ko,'issuer_name',issuer_name,
   'issuer_level',issuer_level,'jurisdiction',jurisdiction,'document_type',document_type,
   'document_number',document_number,'document_year',document_year,'topics',topics,'primary_stage',primary_stage,
   'scope_note',scope_note,'source_url',source_url,'legal_status',legal_status,'content_kind',content_kind,
   'text_truncated',text_truncated,'content_observed_at',content_observed_at,
   'matched_terms',matches,'matched_condition_count',matched_count,'total_condition_count',jsonb_array_length(p_terms),
   'excerpt',substring(text_content from greatest(1,position(lower(coalesce(first_alias,'')) in lower(text_content))-70) for 280)
   )) from page),'[]'::jsonb),
  'coverage',jsonb_build_object('documents',(select count(*) from policy_idn.documents),
    'held_sources',(select count(distinct document_id) from policy_idn.source_checks where outcome='failed'),
    'legal_status','unverified'),
  'jurisdictions',(select jsonb_agg(j order by j) from (select distinct jurisdiction j from policy_idn.documents) s)
 ) into result;
 return result;
end $$;

create or replace function policy_idn.get_document(p_document_id text)
returns jsonb language sql stable security invoker set search_path='' as $$
 select to_jsonb(d)||jsonb_build_object('country','IDN','version',
  (select jsonb_build_object('content_kind',v.content_kind,'text_content',v.text_content,
   'text_truncated',v.text_truncated,'content_hash',v.content_hash,'observed_at',v.observed_at,
   'text_source_url',v.provenance->>'text_source_url')
   from policy_idn.versions v where v.document_id=d.document_id order by v.observed_at desc,v.content_hash limit 1),
  'source_check',(select jsonb_build_object('outcome',c.outcome,'checked_at',c.checked_at)
   from policy_idn.source_checks c where c.document_id=d.document_id order by c.checked_at desc limit 1))
 from policy_idn.documents d where d.document_id=p_document_id
$$;
create or replace function public.idn_search_documents(
 p_terms jsonb default '[]',p_topic text default null,p_level text default null,
 p_jurisdiction text default null,p_sort text default 'relevance',
 p_require_all boolean default false,p_limit integer default 20,p_offset integer default 0)
returns jsonb language sql stable security invoker set search_path='' as $$
 select policy_idn.search_documents(p_terms,p_topic,p_level,p_jurisdiction,p_sort,p_require_all,p_limit,p_offset)
$$;
create or replace function public.idn_get_document(p_document_id text)
returns jsonb language sql stable security invoker set search_path='' as $$
 select policy_idn.get_document(p_document_id)
$$;
revoke all on function policy_idn.search_documents(jsonb,text,text,text,text,boolean,integer,integer),
 policy_idn.get_document(text),public.idn_search_documents(jsonb,text,text,text,text,boolean,integer,integer),
 public.idn_get_document(text) from public,anon,authenticated;
grant execute on function policy_idn.search_documents(jsonb,text,text,text,text,boolean,integer,integer),
 policy_idn.get_document(text),public.idn_search_documents(jsonb,text,text,text,text,boolean,integer,integer),
 public.idn_get_document(text) to service_role;
notify pgrst,'reload schema';
commit;
