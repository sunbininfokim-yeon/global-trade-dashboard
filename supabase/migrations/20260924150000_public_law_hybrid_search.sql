-- Cross-corpus semantic search for the policy UI.
-- Read-only: this function never inserts, updates, or deletes policy data.
-- A result is eligible only when it was embedded with the exact requested model.

begin;
set local lock_timeout = '5s';
alter table public.public_laws add column if not exists embedding extensions.vector(1536);
alter table public.public_laws add column if not exists embedding_model text;
alter table public.public_laws add column if not exists embedded_at timestamptz;
alter table public.public_laws add column if not exists embedding_input_hash text;
comment on column public.public_laws.embedding is 'Metadata embedding (official title and citation), not full law text.';


create or replace function public.search_policy_corpus(
  p_query_embedding extensions.vector(1536),
  p_embedding_model text,
  p_result_limit integer default 20
)
returns table (
  source_type text,
  source_id text,
  title text,
  similarity_score double precision
)
language plpgsql
stable
set search_path = public, extensions
as $$
declare
  effective_limit integer;
begin
  if p_query_embedding is null or nullif(trim(p_embedding_model), '') is null then
    raise exception 'query embedding and embedding model are required';
  end if;

  -- Bound each request so one public API call cannot force an unbounded
  -- nearest-neighbour scan. Twenty is the UI default; one hundred is an
  -- intentional administrative ceiling.
  effective_limit := least(greatest(coalesce(p_result_limit, 20), 1), 100);

  -- Take the nearest N candidates per corpus before the final UNION. A row
  -- outside its own corpus's top N can never appear in the global top N, so
  -- this retains exact top-N semantics while allowing each HNSW index to work.
  return query
  with bill_candidates as (
    select
      'bill'::text as source_type,
      candidate.bill_id::text as source_id,
      candidate.title,
      (1.0 - (candidate.embedding <=> p_query_embedding))::double precision as similarity_score
    from public.bills candidate
    where candidate.embedding is not null
      and candidate.embedding_model = p_embedding_model
    order by candidate.embedding <=> p_query_embedding
    limit effective_limit
  ),
  executive_order_candidates as (
    select
      'executive_order'::text as source_type,
      candidate.eo_number::text as source_id,
      candidate.title,
      (1.0 - (candidate.embedding <=> p_query_embedding))::double precision as similarity_score
    from public.executive_orders candidate
    where candidate.embedding is not null
      and candidate.embedding_model = p_embedding_model
    order by candidate.embedding <=> p_query_embedding
    limit effective_limit
  ),
  public_law_candidates as (
    select 'public_law'::text as source_type, l.public_law_id::text as source_id,
      l.law_title as title, (1.0 - (l.embedding <=> p_query_embedding))::double precision as similarity_score
    from public.public_laws l
    where l.embedding is not null and l.embedding_model = p_embedding_model
      and not exists (select 1 from public.bills b where b.bill_id = l.bill_id and b.embedding is not null and b.embedding_model = p_embedding_model)
    order by l.embedding <=> p_query_embedding limit effective_limit
  ),
  regulation_candidates as (
    select
      'regulation'::text as source_type,
      candidate.regulation_id::text as source_id,
      candidate.title,
      (1.0 - (candidate.embedding <=> p_query_embedding))::double precision as similarity_score
    from public.regulations candidate
    where candidate.embedding is not null
      and candidate.embedding_model = p_embedding_model
    order by candidate.embedding <=> p_query_embedding
    limit effective_limit
  )
  select
    candidates.source_type,
    candidates.source_id,
    candidates.title,
    candidates.similarity_score
  from (
    select * from bill_candidates
    union all
    select * from executive_order_candidates
    union all
    select * from regulation_candidates
    union all
    select * from public_law_candidates
  ) candidates
  order by candidates.similarity_score desc, candidates.source_type, candidates.source_id
  limit effective_limit;
end;
$$;

-- Keep old semantic RPC compatible; hybrid adds text without changing its callers.
create or replace function public.search_policy_hybrid(
  p_query text, p_query_embedding extensions.vector(1536), p_embedding_model text,
  p_result_limit integer default 20
) returns table(source_type text, source_id text, title text, similarity_score double precision)
language sql stable set search_path = public, extensions as $$
with params as (
 select least(greatest(coalesce(p_result_limit,20),1),100) n,
 websearch_to_tsquery('english',left(p_query,500)) q
), corpus as (
 select 'bill'::text kind, bill_id::text id, title, coalesce(summary,'') body from public.bills
 union all select 'public_law',l.public_law_id,l.law_title,'Public Law '||l.congress_number||'-'||l.law_number
 from public.public_laws l where not exists(select 1 from public.bills b where b.bill_id=l.bill_id)
 union all select 'executive_order',eo_number::text,title,coalesce(summary,'') from public.executive_orders
 union all select 'regulation',regulation_id::text,title,coalesce(abstract,'') from public.regulations
), lexical as (
 select c.*, ts_rank_cd(to_tsvector('english',coalesce(c.title,'')||' '||c.body),p.q) score
 from corpus c cross join params p where to_tsvector('english',coalesce(c.title,'')||' '||c.body) @@ p.q
 order by score desc,kind,id limit (select least(n*3,100) from params)
), sem as (
 select s.* from params p cross join lateral public.search_policy_corpus(p_query_embedding,p_embedding_model,least(p.n*3,100)) s
), ranked as (
 select kind,id,title,1.0/(60+row_number() over(order by score desc,kind,id)) score from lexical
 union all
 select source_type,source_id,title,1.0/(60+row_number() over(order by similarity_score desc,source_type,source_id)) from sem
)
select kind,id,max(title),sum(score)::double precision from ranked group by kind,id
order by sum(score) desc,kind,id limit (select n from params);
$$;
revoke all on function public.search_policy_hybrid(text,extensions.vector,text,integer) from public,anon,authenticated;
grant execute on function public.search_policy_hybrid(text,extensions.vector,text,integer) to service_role;
notify pgrst, 'reload schema';
commit;
