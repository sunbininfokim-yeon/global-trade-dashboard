-- Evidence is append-only and version-bound. No assertion changes legal_status.
begin;
set local lock_timeout='3s';
create table if not exists policy_idn.coverage_items (
 document_id text primary key check(document_id ~ '^idn-[a-z0-9-]+$'),
 title text not null check(length(title) between 1 and 2000),
 topics text[] not null check(cardinality(topics) between 1 and 40),
 priority smallint not null check(priority between 1 and 3),
 reason text not null check(length(reason) between 10 and 1500),
 discovery_url text not null check(discovery_url ~ '^https://[^/]+\.go\.id/'),
 updated_at timestamptz not null default now()
);
create table if not exists policy_idn.review_evidence (
 review_id text primary key check(review_id ~ '^idn-review-[a-f0-9]{64}$'),
 document_id text not null,
 source_hash text not null,
 record_type text not null check(record_type in ('relation','applicability','passage')),
 article text not null check(length(article) between 1 and 160),
 quote text not null check(length(quote) between 60 and 12000),
 source_url text not null check(source_url ~ '^https://[^/]+\.go\.id/'),
 target_id text references policy_idn.coverage_items(document_id) on delete restrict,
 relation_type text check(relation_type in ('amends','repeals','implements')),
 operator_roles text[] not null default '{}', product_forms text[] not null default '{}',
 permit_types text[] not null default '{}', business_issues text[] not null default '{}',
 geographic_scope text not null default 'unverified' check(geographic_scope in ('national_framework','specified_regions','unverified')),
 applicable_regions text[] not null default '{}',
 interpretation_ko text not null check(length(interpretation_ko) between 10 and 2000),
 review_basis text not null default 'source_excerpt_verified' check(review_basis='source_excerpt_verified'),
 applicability_status text not null default 'review_relevance' check(applicability_status='review_relevance'),
 reviewed_at timestamptz not null default now(),
 foreign key(document_id,source_hash) references policy_idn.versions(document_id,content_hash) on delete restrict,
 check(cardinality(operator_roles)<=12 and cardinality(product_forms)<=12 and cardinality(permit_types)<=12 and cardinality(business_issues)<=12 and cardinality(applicable_regions)<=12),
 check((record_type='relation' and target_id is not null and relation_type is not null and target_id<>document_id)
    or (record_type<>'relation' and target_id is null and relation_type is null)),
 check(geographic_scope<>'specified_regions' or cardinality(applicable_regions)>0)
);
create index if not exists idn_review_source_idx on policy_idn.review_evidence(document_id,source_hash);
create index if not exists idn_review_target_idx on policy_idn.review_evidence(target_id) where target_id is not null;
create table if not exists policy_idn.passage_embeddings (
 review_id text primary key references policy_idn.review_evidence on delete restrict,
 input_hash text not null check(input_hash ~ '^[a-f0-9]{64}$'),
 model text not null check(model='gemini-embedding-001'),
 profile_version text not null check(profile_version='passage-v1'),
 embedding extensions.vector(1536) not null,
 input_chars integer not null check(input_chars between 1 and 6000),
 embedded_at timestamptz not null default now()
);
alter table policy_idn.coverage_items enable row level security;
alter table policy_idn.review_evidence enable row level security;
alter table policy_idn.passage_embeddings enable row level security;
revoke all on policy_idn.coverage_items,policy_idn.review_evidence,policy_idn.passage_embeddings from public,anon,authenticated;
grant select,insert,update on policy_idn.coverage_items,policy_idn.passage_embeddings to service_role;
grant select,insert on policy_idn.review_evidence to service_role;
create or replace function policy_idn.guard_review_evidence()
 returns trigger language plpgsql security invoker set search_path='' as $$
declare v policy_idn.versions;
begin
 select * into v from policy_idn.versions where document_id=new.document_id and content_hash=new.source_hash;
 if not found or v.content_kind<>'official_text'
 or new.source_url<>coalesce(v.provenance->>'text_source_url',v.source_url)
 or position(regexp_replace(new.quote,'\s+',' ','g') in regexp_replace(v.text_content,'\s+',' ','g'))=0
 then raise exception 'Review requires a literal quote from the identified official text'; end if;
 if exists(select 1 from policy_idn.embedding_corpus c where c.document_id=new.document_id and c.content_hash<>new.source_hash)
 then raise exception 'Review source is no longer current'; end if;
 return new;
end $$;
drop trigger if exists idn_review_evidence_guard on policy_idn.review_evidence;
create trigger idn_review_evidence_guard before insert on policy_idn.review_evidence for each row execute function policy_idn.guard_review_evidence();
create or replace function public.idn_store_coverage(p_item jsonb)
 returns boolean language plpgsql security invoker set search_path='' as $$
declare r policy_idn.coverage_items; n integer;
begin
 if octet_length(p_item::text)>15000 then raise exception 'Coverage payload too large'; end if;
 select * into r from jsonb_populate_record(null::policy_idn.coverage_items,p_item);
 insert into policy_idn.coverage_items(document_id,title,topics,priority,reason,discovery_url)
 values(r.document_id,r.title,r.topics,r.priority,r.reason,r.discovery_url)
 on conflict(document_id) do update set title=excluded.title,topics=excluded.topics,priority=excluded.priority,
 reason=excluded.reason,discovery_url=excluded.discovery_url,updated_at=now()
 where (coverage_items.title,coverage_items.topics,coverage_items.priority,coverage_items.reason,coverage_items.discovery_url)
 is distinct from (excluded.title,excluded.topics,excluded.priority,excluded.reason,excluded.discovery_url);
 get diagnostics n=row_count; return n=1;
end $$;
create or replace function public.idn_store_review(p_record jsonb)
 returns boolean language plpgsql security invoker set search_path='' as $$
declare r policy_idn.review_evidence; old_record policy_idn.review_evidence;
begin
 if octet_length(p_record::text)>65000 then raise exception 'Review payload too large'; end if;
 select * into r from jsonb_populate_record(null::policy_idn.review_evidence,
 jsonb_build_object('operator_roles','[]'::jsonb,'product_forms','[]'::jsonb,'permit_types','[]'::jsonb,'business_issues','[]'::jsonb,
 'applicable_regions','[]'::jsonb,'geographic_scope','unverified','review_basis','source_excerpt_verified','applicability_status','review_relevance') || p_record);
 select * into old_record from policy_idn.review_evidence where review_id=r.review_id;
 if found then
  if (to_jsonb(old_record)-'reviewed_at') is distinct from (to_jsonb(r)-'reviewed_at') then raise exception 'Review IDs are immutable'; end if;
  return false;
 end if;
 r.reviewed_at=now(); insert into policy_idn.review_evidence select r.*; return true;
end $$;
create or replace function public.idn_coverage(p_topic text default null,p_priority integer default null)
 returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare result jsonb;
begin
 if p_priority is not null and p_priority not between 1 and 3 then raise exception 'Invalid priority'; end if;
 if p_topic is not null and (length(p_topic)>80 or p_topic !~ '^[a-z_]+$') then raise exception 'Invalid topic'; end if;
 with items as (
 select i.*,c.content_kind,c.text_truncated,c.content_observed_at,
 case when c.document_id is null then 'missing' when c.content_kind<>'official_text' then 'metadata_only'
 when c.text_truncated then 'partial_text' else 'official_text' end coverage_status,
 ch.outcome latest_check_outcome,ch.checked_at latest_checked_at,ch.detail latest_check_detail
 from policy_idn.coverage_items i left join policy_idn.embedding_corpus c using(document_id)
 left join lateral(select outcome,checked_at,detail from policy_idn.source_checks where document_id=i.document_id order by checked_at desc limit 1) ch on true
 where (p_topic is null or p_topic=any(i.topics)) and (p_priority is null or i.priority=p_priority)
 ) select jsonb_build_object('country','IDN','legal_status','unverified','inventory_is_exhaustive',false,
 'total',(select count(*) from items),'missing',(select count(*) from items where coverage_status='missing'),
 'items',coalesce((select jsonb_agg(to_jsonb(x) order by priority,document_id) from items x),'[]'::jsonb)) into result;
 return result;
end $$;
create or replace function public.idn_document_context(p_document_id text)
 returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare result jsonb;
begin
 if p_document_id !~ '^idn-[a-z0-9-]{1,160}$' then raise exception 'Invalid IDN document'; end if;
 if not exists(select 1 from policy_idn.documents where document_id=p_document_id)
 and not exists(select 1 from policy_idn.coverage_items where document_id=p_document_id) then return null; end if;
 with evidence as (
 select r.*,c.content_hash=r.source_hash source_current,c.title_ko source_title_ko,
 exists(select 1 from policy_idn.documents d where d.document_id=r.target_id) target_stored
 from policy_idn.review_evidence r join policy_idn.embedding_corpus c using(document_id)
 where r.document_id=p_document_id or r.target_id=p_document_id
 ) select jsonb_build_object('country','IDN','document_id',p_document_id,'legal_status','unverified',
 'applicability_status','review_relevance',
 'stale_evidence_count',(select count(*) from evidence where not source_current),
 'relations',coalesce((select jsonb_agg(to_jsonb(x) order by reviewed_at,review_id) from evidence x where record_type='relation' and source_current),'[]'::jsonb),
 'applicability',coalesce((select jsonb_agg(to_jsonb(x) order by reviewed_at,review_id) from evidence x where record_type='applicability' and source_current),'[]'::jsonb),
 'passages',coalesce((select jsonb_agg(to_jsonb(x) order by article,review_id) from evidence x where record_type='passage' and source_current),'[]'::jsonb)) into result;
 return result;
end $$;
create or replace function public.idn_passage_embedding_queue(p_limit integer default 100)
 returns jsonb language plpgsql stable security invoker set search_path='' as $$
begin
 if p_limit not between 1 and 100 then raise exception 'Invalid limit'; end if;
 return (select coalesce(jsonb_agg(to_jsonb(x)),'[]'::jsonb) from (
 select r.review_id,r.document_id,r.article,r.quote,r.interpretation_ko,c.title,c.title_ko
 from policy_idn.review_evidence r join policy_idn.embedding_corpus c using(document_id)
 left join policy_idn.passage_embeddings e using(review_id)
 where r.record_type='passage' and c.content_hash=r.source_hash and e.review_id is null order by r.review_id limit p_limit) x);
end $$;
create or replace function public.idn_store_passage_embedding(p_document jsonb)
 returns boolean language plpgsql security invoker set search_path='' as $$
begin
 if octet_length(p_document::text)>150000 or p_document->>'model' is distinct from 'gemini-embedding-001'
 or p_document->>'profile_version' is distinct from 'passage-v1' or jsonb_array_length(p_document->'embedding')<>1536
 then raise exception 'Invalid passage embedding'; end if;
 if not exists(select 1 from policy_idn.review_evidence r join policy_idn.embedding_corpus c using(document_id)
 where r.review_id=p_document->>'review_id' and r.record_type='passage' and c.content_hash=r.source_hash)
 then raise exception 'Missing or stale passage'; end if;
 insert into policy_idn.passage_embeddings(review_id,input_hash,model,profile_version,embedding,input_chars)
 values(p_document->>'review_id',p_document->>'input_hash','gemini-embedding-001','passage-v1',
 (p_document->>'embedding')::extensions.vector(1536),(p_document->>'input_chars')::int)
 on conflict(review_id) do nothing; return found;
end $$;
create or replace function public.idn_business_search(p_role text,p_region text default null,p_issue text default null)
 returns jsonb language plpgsql stable security invoker set search_path='' as $$
begin
 if coalesce(length(p_role),0) not between 1 and 80 or p_role !~ '^[a-z_]+$'
 or (p_region is not null and length(p_region) not between 1 and 120)
 or (p_issue is not null and (length(p_issue) not between 1 and 80 or p_issue !~ '^[a-z_]+$')) then raise exception 'Invalid business scope'; end if;
 return (select jsonb_build_object('country','IDN','applicability_status','review_relevance',
 'region',p_region,'regional_coverage_complete',false,'items',coalesce(jsonb_agg(to_jsonb(x) order by x.document_id),'[]'::jsonb)) from (
 select c.document_id,c.title_ko,c.issuer_level,c.jurisdiction,c.legal_status,
 jsonb_agg(jsonb_build_object('review_id',r.review_id,'operator_roles',r.operator_roles,'product_forms',r.product_forms,
 'permit_types',r.permit_types,'business_issues',r.business_issues,'geographic_scope',r.geographic_scope,
 'applicable_regions',r.applicable_regions,'article',r.article,'quote',r.quote,'source_url',r.source_url,
 'interpretation_ko',r.interpretation_ko) order by r.review_id) evidence
 from policy_idn.review_evidence r join policy_idn.embedding_corpus c using(document_id)
 where r.record_type='applicability' and r.source_hash=c.content_hash and p_role=any(r.operator_roles)
 and (p_issue is null or p_issue=any(r.business_issues))
 and (p_region is null or r.geographic_scope='national_framework' or (r.geographic_scope='specified_regions' and p_region=any(r.applicable_regions)))
 group by c.document_id,c.title_ko,c.issuer_level,c.jurisdiction,c.legal_status order by c.document_id limit 50) x);
end $$;
-- Only annotates already selected documents: existing filters, totals and order remain authoritative.
create or replace function public.idn_search_passages(p_document_ids text[],p_terms jsonb default '[]',p_query_embedding double precision[] default null)
 returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare result jsonb;
begin
 if p_document_ids is null or cardinality(p_document_ids) not between 1 and 50 or jsonb_typeof(p_terms) is distinct from 'array' or jsonb_array_length(p_terms)>6
 or exists(select 1 from unnest(p_document_ids) id where id !~ '^idn-[a-z0-9-]{1,160}$') then raise exception 'Invalid passage request'; end if;
 if p_query_embedding is not null and array_length(p_query_embedding,1)<>1536 then raise exception 'Invalid query vector'; end if;
 if exists(select 1 from jsonb_array_elements(p_terms) t where jsonb_typeof(t->'aliases') is distinct from 'array') then raise exception 'Invalid terms'; end if;
 if exists(select 1 from jsonb_array_elements(p_terms) t where jsonb_array_length(t->'aliases') not between 1 and 12) then raise exception 'Invalid aliases'; end if;
 if exists(select 1 from jsonb_array_elements(p_terms) t cross join lateral jsonb_array_elements(t->'aliases') a where jsonb_typeof(a)<>'string' or length(a#>>'{}') not between 1 and 120) then raise exception 'Invalid alias'; end if;
 with hits as (
 select r.review_id,r.document_id,r.article,r.quote,r.source_url,r.interpretation_ko,r.source_hash,jsonb_array_length(p_terms) total_condition_count,
 (select count(*) from jsonb_array_elements(p_terms) t where exists(select 1 from jsonb_array_elements_text(t->'aliases') a where policy_idn.matches_alias(r.quote,a))) matched_condition_count,
 case when p_query_embedding is not null and e.embedding is not null then 1-(e.embedding operator(extensions.<=>) p_query_embedding::extensions.vector(1536)) else null end semantic_similarity
 from policy_idn.review_evidence r join policy_idn.embedding_corpus c using(document_id)
 left join policy_idn.passage_embeddings e using(review_id)
 where r.document_id=any(p_document_ids) and r.record_type='passage' and r.source_hash=c.content_hash
 ), ranked as (select *,row_number() over(partition by document_id order by matched_condition_count desc,semantic_similarity desc nulls last,review_id) rn from hits
 where matched_condition_count>0 or semantic_similarity>=0.60)
 select jsonb_build_object('country','IDN','items',coalesce((select jsonb_agg(to_jsonb(x)-'rn' order by document_id,rn) from ranked x where rn<=3),'[]'::jsonb)) into result;
 return result;
end $$;
revoke all on function policy_idn.guard_review_evidence(),public.idn_store_coverage(jsonb),public.idn_store_review(jsonb),public.idn_coverage(text,integer),public.idn_document_context(text),public.idn_business_search(text,text,text),public.idn_passage_embedding_queue(integer),public.idn_store_passage_embedding(jsonb),public.idn_search_passages(text[],jsonb,double precision[]) from public,anon,authenticated;
grant execute on function policy_idn.guard_review_evidence(),public.idn_store_coverage(jsonb),public.idn_store_review(jsonb),public.idn_coverage(text,integer),public.idn_document_context(text),public.idn_business_search(text,text,text),public.idn_passage_embedding_queue(integer),public.idn_store_passage_embedding(jsonb),public.idn_search_passages(text[],jsonb,double precision[]) to service_role;
comment on table policy_idn.review_evidence is 'IDN 원문 인용 기반 관계·사업 검토범위·선택 조문. 현행 효력·적용성 확정과 구분.';
notify pgrst,'reload schema';
commit;
