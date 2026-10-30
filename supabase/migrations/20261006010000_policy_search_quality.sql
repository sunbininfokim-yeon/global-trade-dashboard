-- Additive search RPCs; collection and notification triggers stay unchanged.
-- Load vector GUCs before validating function SET options on a fresh connection.
select extensions.vector_dims('[1,0]'::extensions.vector);
begin;
set local lock_timeout='2s';
create or replace function public.search_policy_legacy_vectors_for_type(p_query_embedding extensions.vector(1536),
  p_embedding_model text,p_source_type text,p_result_limit int default 25)
returns table(source_type text,source_id text,title text,similarity_score double precision)
language plpgsql stable set search_path=public,extensions set hnsw.ef_search='80' as $$
declare tbl text; ident text; heading text;
begin
  case p_source_type
    when 'bill' then tbl:='bills';ident:='bill_id';heading:='title';
    when 'public_law' then tbl:='public_laws';ident:='public_law_id';heading:='law_title';
    when 'executive_order' then tbl:='executive_orders';ident:='eo_number';heading:='title';
    when 'regulation' then tbl:='regulations';ident:='regulation_id';heading:='title';
    else return;
  end case;
  -- Some fresh/older installations have no legacy vector on a source table.
  if (select count(*) from information_schema.columns where table_schema='public' and table_name=tbl
      and column_name in ('embedding','embedding_model'))<>2 then return; end if;
  return query execute format('select $3::text,%I::text,%I::text,(1-(embedding<=>$1))::double precision
    from public.%I where embedding is not null and embedding_model=$2
    order by embedding<=>$1 limit $4',ident,heading,tbl)
    using p_query_embedding,p_embedding_model,p_source_type,least(greatest(p_result_limit,1),50);
end; $$;
create or replace function public.search_policy_vectors_for_type(p_query_embedding extensions.vector(1536),
  p_embedding_model text,p_source_type text,p_per_type_limit int default 25)
returns table(source_type text,source_id text,title text,similarity_score double precision,coverage jsonb,refresh_pending boolean)
language plpgsql stable set search_path=public,extensions set hnsw.ef_search='200' as $$
declare kind text:=p_source_type; budget int:=least(greatest(p_per_type_limit,1),50);
begin
  if p_query_embedding is null or kind not in ('bill','public_law','executive_order','regulation') then return; end if;
    return query execute format($query$
    with nearest as materialized (
      select p.document_id,p.embedding<=>$1 distance from public.policy_search_passages p
      where p.embedding is not null and p.embedding_model=$2 and p.document_id like %L
      order by p.embedding<=>$1 limit $3*24
    ), fresh as (
      select d.source_type,d.source_id,d.title,(1-min(n.distance))::double precision similarity_score
      from nearest n join public.policy_search_documents d using(document_id)
      where d.source_type=$4 group by d.source_type,d.source_id,d.title
      order by 4 desc,d.source_id limit $3
    ), combined as (
      select * from fresh union all
      select l.* from public.search_policy_legacy_vectors_for_type($1,$2,$4,$3*2) l
      where not exists(select 1 from public.policy_search_documents d join public.policy_search_passages p using(document_id)
        where d.source_type=$4 and d.source_id=l.source_id and p.embedding is not null and p.embedding_model=$2)
    ) select c.source_type,c.source_id,c.title,c.similarity_score,d.coverage,coalesce(j.status<>'done',false)
      from combined c left join public.policy_search_documents d on d.source_type=c.source_type and d.source_id=c.source_id
      left join public.policy_search_jobs j on j.document_id=d.document_id
      order by c.similarity_score desc,c.source_id limit $3
    $query$,kind||':%') using p_query_embedding,p_embedding_model,budget,kind;
end; $$;
-- Compatibility aggregate. The Worker calls typed RPCs concurrently so the
-- HTTP statement timeout applies to each lane rather than their cumulative work.
create or replace function public.search_policy_balanced_vectors(p_query_embedding extensions.vector(1536),
  p_embedding_model text,p_per_type_limit int default 25)
returns table(source_type text,source_id text,title text,similarity_score double precision,coverage jsonb,refresh_pending boolean)
language sql stable set search_path=public,extensions as $$
  select hit.* from unnest(array['bill','public_law','executive_order','regulation']) kind
    cross join lateral search_policy_vectors_for_type(p_query_embedding,p_embedding_model,kind,p_per_type_limit) hit;
$$;
create or replace function public.search_policy_document_terms_for_type(p_terms jsonb,p_source_type text,p_limit int default 25)
returns table(source_type text,source_id text,title text,source_url text,document_date date,
  evidence_parts jsonb,coverage jsonb,refresh_pending boolean)
language sql stable set search_path=public,extensions as $$
  with terms as materialized (
    select term->>'key' key,term->'aliases' aliases,
      (select string_agg('('||plainto_tsquery('simple',a)::text||')',' | ')::tsquery
        from jsonb_array_elements_text(term->'aliases') a) query
    from jsonb_array_elements(p_terms) term
  ), query as materialized (select string_agg('('||query::text||')',' | ')::tsquery value from terms),
  pool as materialized (
    select d.* from policy_search_documents d cross join query q
    where d.source_type=p_source_type and d.search_vector@@q.value
    order by (select count(*) from terms t where d.search_vector@@t.query) desc,
      (to_tsvector('simple',d.title)@@q.value) desc,ts_rank_cd(d.search_vector,q.value,32) desc,
      d.document_date desc nulls last,d.document_id
    -- Bounded proof extraction; candidate-limited is disclosed by the Worker.
    limit greatest(50,least(p_limit*2,200))
  ), matches as (
    select d.document_id,term->>'key' term_key,
      (part-'text')||jsonb_build_object('text',substring(part->>'text'
        from greatest(1,pos.value-100) for 360)) evidence,
      row_number() over(partition by d.document_id,term->>'key' order by
        case part->>'field' when 'title' then 0 when 'summary' then 1 when 'subjects' then 2 when 'body' then 3 else 4 end,
        length(alias) desc,part->>'source_url',pos.value) ordinal
    from pool d,jsonb_array_elements(d.evidence_parts) part,
      jsonb_array_elements(p_terms) term,jsonb_array_elements_text(term->'aliases') alias,
      lateral (select regexp_instr(lower(part->>'text'),
        case when alias~'^[a-z0-9]' then '(^|[^a-z0-9])' else '' end
        ||replace(alias,' ','[[:space:]-]+')||case when alias~'[a-z0-9]$' then '([^a-z0-9]|$)' else '' end) value) pos
    where pos.value>0
  ), proof as (
    select document_id,count(distinct term_key) hits,jsonb_agg(evidence order by term_key,ordinal) parts
    from matches where ordinal<=3 group by document_id
  ) select d.source_type,d.source_id,d.title,d.source_url,d.document_date,
    (select jsonb_agg(value) from (select value from jsonb_array_elements(proof.parts) limit 30) t),
    d.coverage,coalesce(j.status<>'done',false)
  from proof join policy_search_documents d using(document_id) left join policy_search_jobs j using(document_id)
  order by proof.hits desc,(to_tsvector('simple',d.title)@@(select value from query)) desc,
    ts_rank_cd(d.search_vector,(select value from query),32) desc,d.document_date desc nulls last,d.document_id
  limit least(greatest(p_limit,1),100);
$$;
create or replace function public.search_policy_balanced_terms(p_terms jsonb,p_per_type_limit int default 25)
returns table(source_type text,source_id text,title text,source_url text,document_date date,
  evidence_parts jsonb,coverage jsonb,refresh_pending boolean)
language sql stable set search_path=public,extensions as $$
  select hit.* from unnest(array['bill','public_law','executive_order','regulation']) kind
    cross join lateral search_policy_document_terms_for_type(p_terms,kind,least(greatest(p_per_type_limit,1),50)) hit;
$$;
revoke all on function search_policy_legacy_vectors_for_type(extensions.vector,text,text,integer),
  search_policy_vectors_for_type(extensions.vector,text,text,integer),
  search_policy_balanced_vectors(extensions.vector,text,integer),search_policy_document_terms_for_type(jsonb,text,integer),
  search_policy_balanced_terms(jsonb,integer) from public,anon,authenticated;
grant execute on function search_policy_legacy_vectors_for_type(extensions.vector,text,text,integer),
  search_policy_vectors_for_type(extensions.vector,text,text,integer),
  search_policy_balanced_vectors(extensions.vector,text,integer),search_policy_document_terms_for_type(jsonb,text,integer),
  search_policy_balanced_terms(jsonb,integer) to service_role;
notify pgrst,'reload schema';
commit;

-- The dominant bill lane reuses the global HNSW index; isolate minority lanes.
-- Independent commits preserve completed indexes if the editor times out.
begin;
set local lock_timeout='2s';
set local max_parallel_maintenance_workers=0;
set local maintenance_work_mem='64MB';
create index if not exists policy_search_passages_regulation_ann on public.policy_search_passages using hnsw (embedding extensions.vector_cosine_ops) where embedding is not null and document_id like 'regulation:%';
commit;
begin;
set local lock_timeout='2s';
set local max_parallel_maintenance_workers=0;
set local maintenance_work_mem='64MB';
create index if not exists policy_search_passages_public_law_ann on public.policy_search_passages using hnsw (embedding extensions.vector_cosine_ops) where embedding is not null and document_id like 'public_law:%';
commit;
begin;
set local lock_timeout='2s';
set local max_parallel_maintenance_workers=0;
set local maintenance_work_mem='64MB';
create index if not exists policy_search_passages_executive_order_ann on public.policy_search_passages using hnsw (embedding extensions.vector_cosine_ops) where embedding is not null and document_id like 'executive_order:%';
commit;
