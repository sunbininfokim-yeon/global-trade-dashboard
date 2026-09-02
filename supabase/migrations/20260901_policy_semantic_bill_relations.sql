-- Semantic bill relations. Safe for the existing policy DB.
-- It touches only relation_origin = 'semantic'; official and manual links stay intact.

begin;

create or replace function public.refresh_bill_semantic_relations(
  p_source_bill_id text,
  p_source_embedding extensions.vector(1536),
  p_embedding_model text,
  p_similarity_threshold double precision default 0.80,
  p_result_limit integer default 5
)
returns integer
language plpgsql
set search_path = public, extensions
as $$
declare
  inserted_count integer;
begin
  if p_source_bill_id is null or p_source_embedding is null or nullif(trim(p_embedding_model), '') is null then
    raise exception 'source bill, embedding, and embedding model are required';
  end if;
  if p_similarity_threshold < 0 or p_similarity_threshold > 1 then
    raise exception 'similarity threshold must be between 0 and 1';
  end if;

  -- A single RPC invocation is transactional. If the candidate query or
  -- insert fails, the delete below is rolled back as well.
  delete from public.bill_relations
  where source_bill_id = p_source_bill_id
    and relation_origin = 'semantic';

  with nearest as (
    select
      candidate.bill_id as target_bill_id,
      1 - (candidate.embedding <=> p_source_embedding) as similarity_score
    from public.bills candidate
    where candidate.bill_id <> p_source_bill_id
      and candidate.embedding is not null
      and candidate.embedding_model = p_embedding_model
    order by candidate.embedding <=> p_source_embedding
    limit least(greatest(p_result_limit, 1), 5)
  )
  insert into public.bill_relations (
    source_bill_id,
    target_bill_id,
    relation_type,
    relation_origin,
    identified_by,
    similarity_score
  )
  select
    p_source_bill_id,
    nearest.target_bill_id,
    'semantic_similarity',
    'semantic',
    p_embedding_model || ' cosine',
    nearest.similarity_score
  from nearest
  where nearest.similarity_score >= p_similarity_threshold;

  get diagnostics inserted_count = row_count;
  return inserted_count;
end;
$$;

commit;
