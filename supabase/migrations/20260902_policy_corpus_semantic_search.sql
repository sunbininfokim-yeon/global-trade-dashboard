-- Cross-corpus semantic search for the policy UI.
-- Read-only: this function never inserts, updates, or deletes policy data.
-- A result is eligible only when it was embedded with the exact requested model.

begin;

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
  ) candidates
  order by candidates.similarity_score desc, candidates.source_type, candidates.source_id
  limit effective_limit;
end;
$$;

commit;
